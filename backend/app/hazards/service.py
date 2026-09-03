from __future__ import annotations

import base64
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from uuid import uuid4

from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import (
    AccessibilityRoute,
    AccessibilitySegment,
    Hazard,
    HazardObservation,
    HazardStatusHistory,
)
from app.errors import AppError, ErrorCode
from app.hazards.analytics import (
    ScoringPolicy,
    canonical_category,
    score_route,
    temporary_ttl_seconds,
)
from app.schemas.common import utc_now
from app.schemas.hazards import (
    ACTIVE_HAZARD_STATUSES,
    CreateHazardRequest,
    DashboardAccessibilityResponse,
    DashboardCounts,
    DashboardSummaryResponse,
    GeoCoordinate,
    HazardListResponse,
    HazardRecord,
    HazardResponse,
    HazardStatus,
    HazardStatusHistoryRecord,
    MergeHazardRequest,
    MergeHazardResponse,
    UpdateHazardStatusRequest,
    UpdateHazardStatusResponse,
    VersionedMapCoordinate,
)


ALLOWED_TRANSITIONS: dict[HazardStatus, frozenset[HazardStatus]] = {
    HazardStatus.NEW: frozenset({HazardStatus.VERIFIED, HazardStatus.REJECTED}),
    HazardStatus.VERIFIED: frozenset(
        {HazardStatus.ASSIGNED, HazardStatus.RESOLVED, HazardStatus.REJECTED}
    ),
    HazardStatus.ASSIGNED: frozenset(
        {HazardStatus.IN_PROGRESS, HazardStatus.RESOLVED}
    ),
    HazardStatus.IN_PROGRESS: frozenset({HazardStatus.RESOLVED}),
    HazardStatus.RESOLVED: frozenset(),
    HazardStatus.REJECTED: frozenset(),
}


class HazardService:
    def __init__(self, engine: Engine, evidence_dir: Path, settings: Settings) -> None:
        self._engine = engine
        self._evidence_dir = evidence_dir
        self._settings = settings
        self._scoring_policy = ScoringPolicy(
            temporary_ttl_seconds=settings.hazard_temporary_ttl_seconds,
            person_ttl_seconds=settings.hazard_person_ttl_seconds,
        )

    def create(
        self,
        payload: CreateHazardRequest,
        evidence_bytes: bytes | None = None,
    ) -> HazardResponse:
        source_hazard_id = str(uuid4())
        evidence_path: Path | None = None
        wrote_evidence = False
        merged = False
        try:
            with Session(self._engine) as database:
                with database.begin():
                    existing = self._find_duplicate(database, payload)
                    if existing is None:
                        hazard = Hazard(
                            id=source_hazard_id,
                            category=payload.category,
                            severity=payload.severity.value,
                            status=HazardStatus.NEW.value,
                            map_id=payload.map_coordinate.map_id if payload.map_coordinate else None,
                            map_version=payload.map_coordinate.map_version if payload.map_coordinate else None,
                            map_x=payload.map_coordinate.x if payload.map_coordinate else None,
                            map_y=payload.map_coordinate.y if payload.map_coordinate else None,
                            latitude=payload.geo_coordinate.latitude if payload.geo_coordinate else None,
                            longitude=payload.geo_coordinate.longitude if payload.geo_coordinate else None,
                            accuracy_m=payload.geo_coordinate.accuracy_m if payload.geo_coordinate else None,
                            first_seen_at=payload.observed_at,
                            last_seen_at=payload.observed_at,
                            confidence=payload.confidence,
                            confirmation_count=1,
                            temporary=payload.temporary,
                            assigned_to=None,
                            version=1,
                            evidence_path=None,
                        )
                        database.add(hazard)
                    else:
                        hazard = existing
                        merged = True
                        hazard.last_seen_at = max(
                            _as_utc(hazard.last_seen_at), payload.observed_at
                        )
                        hazard.confidence = max(hazard.confidence, payload.confidence)
                        hazard.confirmation_count += 1
                        hazard.temporary = hazard.temporary and payload.temporary
                        hazard.severity = _higher_severity(
                            hazard.severity, payload.severity.value
                        )
                        hazard.version += 1

                    if evidence_bytes is not None and hazard.evidence_path is None:
                        evidence_path = self._evidence_dir / f"{hazard.id}.jpg"
                        hazard.evidence_path = str(evidence_path)
                    observation = HazardObservation(
                        id=str(uuid4()),
                        hazard_id=hazard.id,
                        source_hazard_id=source_hazard_id,
                        session_id=payload.session_id,
                        observed_at=payload.observed_at,
                        confidence=payload.confidence,
                        risk_score=payload.risk_score,
                        direction=payload.direction.value,
                    )
                    database.add(observation)
                    database.flush()
                    if evidence_path is not None and evidence_bytes is not None:
                        self._evidence_dir.mkdir(parents=True, exist_ok=True)
                        evidence_path.write_bytes(evidence_bytes)
                        wrote_evidence = True
                database.refresh(hazard)
                record = _to_record(hazard)
        except SQLAlchemyError as exc:
            if wrote_evidence and evidence_path is not None:
                evidence_path.unlink(missing_ok=True)
            raise _database_error() from exc
        except OSError as exc:
            if wrote_evidence and evidence_path is not None:
                evidence_path.unlink(missing_ok=True)
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                "The consented evidence could not be stored locally.",
                status_code=500,
                retryable=True,
            ) from exc

        return HazardResponse(
            server_time=utc_now(), hazard=record, merged_with_existing=merged
        )

    def _find_duplicate(
        self, database: Session, payload: CreateHazardRequest
    ) -> Hazard | None:
        coordinate = payload.map_coordinate
        if coordinate is None:
            return None
        candidates = list(
            database.scalars(
                select(Hazard).where(
                    Hazard.merged_into_id.is_(None),
                    Hazard.status.in_([item.value for item in ACTIVE_HAZARD_STATUSES]),
                    Hazard.map_id == coordinate.map_id,
                    Hazard.map_version == coordinate.map_version,
                    Hazard.map_x.is_not(None),
                    Hazard.map_y.is_not(None),
                )
            )
        )
        expected_category = canonical_category(payload.category)
        eligible: list[tuple[float, datetime, str, Hazard]] = []
        for candidate in candidates:
            if canonical_category(candidate.category) != expected_category:
                continue
            age = abs(
                (payload.observed_at - _as_utc(candidate.last_seen_at)).total_seconds()
            )
            if age > self._settings.hazard_duplicate_window_seconds:
                continue
            distance = math.hypot(
                float(candidate.map_x) - coordinate.x,
                float(candidate.map_y) - coordinate.y,
            )
            if distance <= self._settings.hazard_duplicate_radius:
                eligible.append(
                    (
                        distance,
                        _as_utc(candidate.first_seen_at),
                        candidate.id,
                        candidate,
                    )
                )
        if not eligible:
            return None
        eligible.sort(key=lambda item: (item[0], item[1], item[2]))
        return eligible[0][3]

    def list(
        self,
        *,
        statuses: list[HazardStatus] | None,
        active: bool,
        category: str | None,
        limit: int,
        cursor: str | None,
    ) -> HazardListResponse:
        self.expire_temporary()
        offset = _decode_cursor(cursor)
        try:
            with Session(self._engine) as database:
                statement = select(Hazard).where(Hazard.merged_into_id.is_(None))
                if active:
                    statement = statement.where(
                        Hazard.status.in_([item.value for item in ACTIVE_HAZARD_STATUSES])
                    )
                elif statuses:
                    statement = statement.where(
                        Hazard.status.in_([item.value for item in statuses])
                    )
                if category:
                    statement = statement.where(Hazard.category == category)
                rows = list(
                    database.scalars(
                        statement.order_by(Hazard.last_seen_at.desc(), Hazard.id)
                        .offset(offset)
                        .limit(limit + 1)
                    )
                )
        except SQLAlchemyError as exc:
            raise _database_error() from exc

        has_more = len(rows) > limit
        return HazardListResponse(
            server_time=utc_now(),
            items=[_to_record(item) for item in rows[:limit]],
            next_cursor=_encode_cursor(offset + limit) if has_more else None,
        )

    def nearby_map(
        self,
        *,
        map_id: str,
        map_version: str,
        x: float,
        y: float,
        radius: float,
    ) -> HazardListResponse:
        self.expire_temporary()
        try:
            with Session(self._engine) as database:
                rows = list(
                    database.scalars(
                        select(Hazard)
                        .where(
                            Hazard.merged_into_id.is_(None),
                            Hazard.status.in_(
                                [item.value for item in ACTIVE_HAZARD_STATUSES]
                            ),
                            Hazard.map_id == map_id,
                            Hazard.map_version == map_version,
                            Hazard.map_x.is_not(None),
                            Hazard.map_y.is_not(None),
                            (
                                (Hazard.map_x - x) * (Hazard.map_x - x)
                                + (Hazard.map_y - y) * (Hazard.map_y - y)
                            )
                            <= radius * radius,
                        )
                        .order_by(Hazard.last_seen_at.desc(), Hazard.id)
                    )
                )
        except SQLAlchemyError as exc:
            raise _database_error() from exc
        return HazardListResponse(
            server_time=utc_now(), items=[_to_record(item) for item in rows]
        )

    def nearby_geo(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_m: float,
    ) -> HazardListResponse:
        self.expire_temporary()
        try:
            with Session(self._engine) as database:
                candidates = list(
                    database.scalars(
                        select(Hazard)
                        .where(
                            Hazard.merged_into_id.is_(None),
                            Hazard.status.in_(
                                [item.value for item in ACTIVE_HAZARD_STATUSES]
                            ),
                            Hazard.latitude.is_not(None),
                            Hazard.longitude.is_not(None),
                        )
                        .order_by(Hazard.last_seen_at.desc(), Hazard.id)
                    )
                )
        except SQLAlchemyError as exc:
            raise _database_error() from exc

        rows = [
            item
            for item in candidates
            if _haversine_metres(
                latitude,
                longitude,
                float(item.latitude),
                float(item.longitude),
            )
            <= radius_m
        ]
        return HazardListResponse(
            server_time=utc_now(), items=[_to_record(item) for item in rows]
        )

    def update_status(
        self, hazard_id: str, payload: UpdateHazardStatusRequest
    ) -> UpdateHazardStatusResponse:
        if payload.new_status not in ALLOWED_TRANSITIONS[payload.expected_status]:
            raise AppError(
                ErrorCode.INVALID_STATUS_TRANSITION,
                "The requested hazard status transition is not allowed.",
                status_code=409,
                details={
                    "from_status": payload.expected_status.value,
                    "to_status": payload.new_status.value,
                },
            )

        now = utc_now()
        transition = HazardStatusHistory(
            id=str(uuid4()),
            hazard_id=hazard_id,
            from_status=payload.expected_status.value,
            to_status=payload.new_status.value,
            changed_at=now,
            operator_alias=payload.operator_alias,
            note=payload.note,
        )
        values: dict[str, object] = {
            "status": payload.new_status.value,
            "version": payload.expected_version + 1,
        }
        if payload.new_status == HazardStatus.ASSIGNED:
            values["assigned_to"] = payload.assigned_to

        try:
            with Session(self._engine) as database:
                with database.begin():
                    existing = database.get(Hazard, hazard_id)
                    if existing is None or existing.merged_into_id is not None:
                        raise _not_found(hazard_id)
                    changed = database.execute(
                        update(Hazard)
                        .where(
                            Hazard.id == hazard_id,
                            Hazard.version == payload.expected_version,
                            Hazard.status == payload.expected_status.value,
                            Hazard.merged_into_id.is_(None),
                        )
                        .values(**values)
                    )
                    if changed.rowcount != 1:
                        raise _conflict(existing)
                    database.add(transition)
                updated = database.get(Hazard, hazard_id)
                assert updated is not None
                record = _to_record(updated)
                transition_record = _to_history(transition)
        except AppError:
            raise
        except SQLAlchemyError as exc:
            raise _database_error() from exc

        return UpdateHazardStatusResponse(
            server_time=now,
            hazard=record,
            transition=transition_record,
        )

    def merge(
        self, primary_id: str, payload: MergeHazardRequest
    ) -> MergeHazardResponse:
        if primary_id == payload.duplicate_hazard_id:
            raise AppError(
                ErrorCode.CONFLICT,
                "A hazard cannot be merged into itself.",
                status_code=409,
            )
        now = utc_now()
        try:
            with Session(self._engine) as database:
                with database.begin():
                    primary = database.get(Hazard, primary_id)
                    duplicate = database.get(Hazard, payload.duplicate_hazard_id)
                    if primary is None or primary.merged_into_id is not None:
                        raise _not_found(primary_id)
                    if duplicate is None or duplicate.merged_into_id is not None:
                        raise _not_found(payload.duplicate_hazard_id)
                    if (
                        primary.version != payload.expected_primary_version
                        or duplicate.version != payload.expected_duplicate_version
                    ):
                        raise AppError(
                            ErrorCode.CONFLICT,
                            "A hazard changed before the merge could be applied.",
                            status_code=409,
                            retryable=True,
                        )

                    primary_changed = database.execute(
                        update(Hazard)
                        .where(
                            Hazard.id == primary.id,
                            Hazard.version == payload.expected_primary_version,
                            Hazard.merged_into_id.is_(None),
                        )
                        .values(
                            first_seen_at=min(
                                primary.first_seen_at, duplicate.first_seen_at
                            ),
                            last_seen_at=max(
                                primary.last_seen_at, duplicate.last_seen_at
                            ),
                            confidence=max(primary.confidence, duplicate.confidence),
                            confirmation_count=(
                                primary.confirmation_count
                                + duplicate.confirmation_count
                            ),
                            version=payload.expected_primary_version + 1,
                        )
                    )
                    database.execute(
                        update(HazardObservation)
                        .where(HazardObservation.hazard_id == duplicate.id)
                        .values(hazard_id=primary.id)
                    )
                    prior_duplicate_status = duplicate.status
                    duplicate_changed = database.execute(
                        update(Hazard)
                        .where(
                            Hazard.id == duplicate.id,
                            Hazard.version == payload.expected_duplicate_version,
                            Hazard.merged_into_id.is_(None),
                        )
                        .values(
                            status=HazardStatus.REJECTED.value,
                            merged_into_id=primary.id,
                            version=payload.expected_duplicate_version + 1,
                        )
                    )
                    if primary_changed.rowcount != 1 or duplicate_changed.rowcount != 1:
                        raise AppError(
                            ErrorCode.CONFLICT,
                            "A hazard changed before the merge could be applied.",
                            status_code=409,
                            retryable=True,
                        )
                    database.add(
                        HazardStatusHistory(
                            id=str(uuid4()),
                            hazard_id=duplicate.id,
                            from_status=prior_duplicate_status,
                            to_status=HazardStatus.REJECTED.value,
                            changed_at=now,
                            operator_alias=payload.operator_alias,
                            note=payload.note or f"Merged into {primary.id}.",
                        )
                    )
                database.refresh(primary)
                record = _to_record(primary)
        except AppError:
            raise
        except SQLAlchemyError as exc:
            raise _database_error() from exc

        return MergeHazardResponse(
            server_time=now,
            primary_hazard=record,
            merged_hazard_id=payload.duplicate_hazard_id,
        )

    def summary(self) -> DashboardSummaryResponse:
        self.expire_temporary()
        try:
            with Session(self._engine) as database:
                counts = {
                    status: int(
                        database.scalar(
                            select(func.count(Hazard.id)).where(
                                Hazard.status == status.value,
                                Hazard.merged_into_id.is_(None),
                            )
                        )
                        or 0
                    )
                    for status in HazardStatus
                }
                resolved_rows = list(
                    database.execute(
                        select(Hazard, HazardStatusHistory.changed_at)
                        .join(
                            HazardStatusHistory,
                            HazardStatusHistory.hazard_id == Hazard.id,
                        )
                        .where(
                            HazardStatusHistory.to_status == HazardStatus.RESOLVED.value,
                            Hazard.merged_into_id.is_(None),
                        )
                        .order_by(HazardStatusHistory.changed_at.desc())
                    ).all()
                )
        except SQLAlchemyError as exc:
            raise _database_error() from exc

        resolution_minutes = [
            max(
                0.0,
                (
                    _as_utc(changed_at) - _as_utc(hazard.first_seen_at)
                ).total_seconds()
                / 60,
            )
            for hazard, changed_at in resolved_rows
        ]
        return DashboardSummaryResponse(
            server_time=utc_now(),
            counts=DashboardCounts(
                new=counts[HazardStatus.NEW],
                verified=counts[HazardStatus.VERIFIED],
                assigned=counts[HazardStatus.ASSIGNED],
                in_progress=counts[HazardStatus.IN_PROGRESS],
                resolved=counts[HazardStatus.RESOLVED],
                rejected=counts[HazardStatus.REJECTED],
            ),
            active_verified_hazards=(
                counts[HazardStatus.VERIFIED]
                + counts[HazardStatus.ASSIGNED]
                + counts[HazardStatus.IN_PROGRESS]
            ),
            awaiting_review=counts[HazardStatus.NEW],
            recently_resolved=[
                _to_record(hazard) for hazard, _changed_at in resolved_rows[:10]
            ],
            median_resolution_minutes=(
                float(median(resolution_minutes)) if resolution_minutes else None
            ),
        )

    def expire_temporary(self, *, now: datetime | None = None) -> int:
        checked_at = _as_utc(now or utc_now())
        expired_count = 0
        try:
            with Session(self._engine) as database:
                with database.begin():
                    hazards = list(
                        database.scalars(
                            select(Hazard).where(
                                Hazard.merged_into_id.is_(None),
                                Hazard.temporary.is_(True),
                                Hazard.status.in_(
                                    [item.value for item in ACTIVE_HAZARD_STATUSES]
                                ),
                            )
                        )
                    )
                    for hazard in hazards:
                        ttl = temporary_ttl_seconds(hazard, self._scoring_policy)
                        if checked_at - _as_utc(hazard.last_seen_at) < timedelta(
                            seconds=ttl
                        ):
                            continue
                        previous = hazard.status
                        changed = database.execute(
                            update(Hazard)
                            .where(
                                Hazard.id == hazard.id,
                                Hazard.version == hazard.version,
                                Hazard.status.in_(
                                    [item.value for item in ACTIVE_HAZARD_STATUSES]
                                ),
                                Hazard.merged_into_id.is_(None),
                            )
                            .values(
                                status=HazardStatus.RESOLVED.value,
                                version=hazard.version + 1,
                            )
                        )
                        if changed.rowcount != 1:
                            continue
                        database.add(
                            HazardStatusHistory(
                                id=str(uuid4()),
                                hazard_id=hazard.id,
                                from_status=previous,
                                to_status=HazardStatus.RESOLVED.value,
                                changed_at=checked_at,
                                operator_alias="system-expiry",
                                note=(
                                    f"Temporary {canonical_category(hazard.category)} "
                                    "expired without reconfirmation."
                                ),
                            )
                        )
                        expired_count += 1
        except SQLAlchemyError as exc:
            raise _database_error() from exc
        return expired_count

    def accessibility(self) -> DashboardAccessibilityResponse:
        now = utc_now()
        self.expire_temporary(now=now)
        try:
            with Session(self._engine) as database:
                expired_count = int(
                    database.scalar(
                        select(func.count(HazardStatusHistory.id)).where(
                            HazardStatusHistory.operator_alias == "system-expiry",
                            HazardStatusHistory.to_status == HazardStatus.RESOLVED.value,
                        )
                    )
                    or 0
                )
                routes = list(
                    database.scalars(
                        select(AccessibilityRoute)
                        .where(AccessibilityRoute.active.is_(True))
                        .order_by(AccessibilityRoute.name, AccessibilityRoute.id)
                    )
                )
                scored_routes = []
                for route in routes:
                    segments = list(
                        database.scalars(
                            select(AccessibilitySegment)
                            .where(AccessibilitySegment.route_id == route.id)
                            .order_by(
                                AccessibilitySegment.sequence,
                                AccessibilitySegment.id,
                            )
                        )
                    )
                    hazards = list(
                        database.scalars(
                            select(Hazard).where(
                                Hazard.merged_into_id.is_(None),
                                Hazard.status.in_(
                                    [item.value for item in ACTIVE_HAZARD_STATUSES]
                                ),
                                Hazard.map_id == route.map_id,
                                Hazard.map_version == route.map_version,
                            )
                        )
                    )
                    scored_routes.append(
                        score_route(
                            route,
                            segments,
                            hazards,
                            now=now,
                            policy=self._scoring_policy,
                        )
                    )
        except SQLAlchemyError as exc:
            raise _database_error() from exc
        return DashboardAccessibilityResponse(
            server_time=now,
            advisory_only=True,
            disclaimer=(
                "Operational hall score only. It is not live navigation, a safety "
                "certification, or a replacement for current Walk Mode guidance "
                "and established mobility aids."
            ),
            expired_temporary_count=expired_count,
            routes=scored_routes,
        )


def _to_record(hazard: Hazard) -> HazardRecord:
    map_coordinate = None
    if (
        hazard.map_id is not None
        and hazard.map_version is not None
        and hazard.map_x is not None
        and hazard.map_y is not None
    ):
        map_coordinate = VersionedMapCoordinate(
            map_id=hazard.map_id,
            map_version=hazard.map_version,
            x=hazard.map_x,
            y=hazard.map_y,
        )
    geo_coordinate = None
    if hazard.latitude is not None and hazard.longitude is not None:
        geo_coordinate = GeoCoordinate(
            latitude=hazard.latitude,
            longitude=hazard.longitude,
            accuracy_m=hazard.accuracy_m,
        )
    return HazardRecord(
        id=hazard.id,
        category=hazard.category,
        severity=hazard.severity,
        status=hazard.status,
        map_coordinate=map_coordinate,
        geo_coordinate=geo_coordinate,
        first_seen_at=_as_utc(hazard.first_seen_at),
        last_seen_at=_as_utc(hazard.last_seen_at),
        confidence=hazard.confidence,
        confirmation_count=hazard.confirmation_count,
        temporary=hazard.temporary,
        assigned_to=hazard.assigned_to,
        version=hazard.version,
        has_consented_evidence=hazard.evidence_path is not None,
    )


def _higher_severity(current: str, incoming: str) -> str:
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    return incoming if order[incoming] > order[current] else current


def _to_history(history: HazardStatusHistory) -> HazardStatusHistoryRecord:
    return HazardStatusHistoryRecord(
        id=history.id,
        hazard_id=history.hazard_id,
        from_status=history.from_status,
        to_status=history.to_status,
        changed_at=_as_utc(history.changed_at),
        operator_alias=history.operator_alias,
        note=history.note,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _encode_cursor(offset: int) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps({"offset": offset}, separators=(",", ":")).encode("utf-8")
    )
    return encoded.decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        offset = payload["offset"]
        if not isinstance(offset, int) or offset < 0:
            raise ValueError
        return offset
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AppError(
            ErrorCode.INVALID_REQUEST,
            "The hazard cursor is invalid.",
            status_code=422,
        ) from exc


def _not_found(hazard_id: str) -> AppError:
    return AppError(
        ErrorCode.NOT_FOUND,
        "The requested hazard was not found.",
        status_code=404,
        details={"hazard_id": hazard_id},
    )


def _conflict(existing: Hazard) -> AppError:
    return AppError(
        ErrorCode.CONFLICT,
        "The hazard changed before the update could be applied.",
        status_code=409,
        retryable=True,
        details={"current_status": existing.status, "current_version": existing.version},
    )


def _database_error() -> AppError:
    return AppError(
        ErrorCode.DATABASE_UNAVAILABLE,
        "The local hazard database is unavailable.",
        status_code=503,
        retryable=True,
    )


def _haversine_metres(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    radius_m = 6_371_000.0
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius_m * math.asin(math.sqrt(haversine))
