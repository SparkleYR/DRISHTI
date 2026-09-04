# SOS Alert — phone to coordinator

- Spec version: `sos/1.0.0`
- Raised: 2026-09-04
- Status: **Proposed — needs D-080 sign-off before implementation**
- Split: **backend team implements §3–§6 on the main PC.** The Android client
  (§7) and the dashboard surface (§8) are done in the app repo and can land
  first, because both degrade silently when the endpoint is absent.

## 1. What exists today

`apps/android/.../sos/SosController.kt` is deliberately local-only — a loud
alternating siren, a repeating spoken plea, and a full-screen banner. Its own
comment says *"No network, no SMS, no call."* Volume-down triggers it, a
three-finger tap cancels it.

That is the right behaviour when nothing else is reachable, and it stays exactly
as it is. What is missing is that **nobody else finds out.** A coordinator
watching the dashboard has no idea a walker has pressed SOS, and the walker has
no way to know anyone noticed.

There is no SOS endpoint on the backend. `grep -rn 'sos' backend/app/` returns
nothing.

## 2. What this adds

The phone additionally tells the local backend "session X raised SOS". The
dashboard, which already polls every 2 s, shows a loud persistent banner and
gives the coordinator one button: **I'm responding**. The walker's phone is told
that acknowledgement happened and says so out loud.

Nothing about the local siren depends on any of this working.

## 3. D-080 (proposed)

Add a local, in-memory SOS alert channel: `POST /api/v1/sos`,
`GET /api/v1/sos/active`, `PATCH /api/v1/sos/{alert_id}/acknowledge`.

- **In-process only**, alongside `WalkSessionStore` — no SQLite table, no
  migration, no file. An alert does not survive a backend restart; the phone's
  own siren is the durable signal, not the server record.
- **No identity, no location, no frames.** An alert carries a session id, the
  time it was raised, and its acknowledgement state. Nothing else. D-022 holds.
- **Advisory only.** This notifies a coordinator on the same LAN. It is not an
  emergency service, does not dial anyone, and must never be described as doing
  so.

## 4. Contract

```ts
type SosState = "RAISED" | "ACKNOWLEDGED" | "CANCELLED";

interface SosAlert {
  alert_id: OpaqueId;
  session_id: OpaqueId;
  state: SosState;
  raised_at: Timestamp;
  acknowledged_at: Timestamp | null;
  acknowledged_by: string | null;   // operator alias, free text, no identity check
  cancelled_at: Timestamp | null;
}
```

### `POST /api/v1/sos`

Body: `{ session_id: string, kind: "RAISED" | "CANCELLED" }`

- `RAISED` on an active session with no live alert → creates one, `201`.
  Re-raising an already-live alert returns the **existing** alert `200` and does
  not reset its acknowledgement — a phone retrying after a dropped packet must
  not silently un-acknowledge a coordinator who already responded.
- `CANCELLED` → marks the live alert cancelled, `200`. Cancelling nothing is
  also `200` (idempotent; the phone must never be stuck retrying).
- Unknown or ended session → `404 SESSION_NOT_FOUND`.

Response: `{ schema_version, server_time, alert: SosAlert }`

### `GET /api/v1/sos/active`

Returns `{ schema_version, server_time, alerts: SosAlert[] }` — every alert in
`RAISED` or `ACKNOWLEDGED`. Cancelled alerts leave the list immediately, exactly
as ended walk sessions do in `/walk/sessions/active` (D-079).

An alert whose walk session has ended is dropped too: a phone that lost power
mid-alert must not leave a ghost banner on the dashboard forever.

### `PATCH /api/v1/sos/{alert_id}/acknowledge`

Body: `{ operator_alias: string }` (1–64 chars).
`RAISED → ACKNOWLEDGED`, stamping `acknowledged_at` / `acknowledged_by`.
Already acknowledged → `200` with the unchanged alert (idempotent).
Unknown or cancelled alert → `404`.

### Walk telemetry

`FrameAnalysisResponse` gains **nothing**. The phone learns about
acknowledgement from its own `POST /api/v1/sos` responses and a light poll while
its siren is active (§7) — adding a field to the 2 fps safety response for a
rare event would tax the latency-critical path for no benefit.

## 5. Backend implementation sketch

New `backend/app/sos.py`, modelled on `walk_sessions.py`:

```
SosAlertStore
  raise_alert(session_id, now)  -> SosAlert     # idempotent per session
  cancel(session_id, now)       -> SosAlert|None
  acknowledge(alert_id, alias, now) -> SosAlert
  active(now, live_session_ids) -> list[SosAlert]
  end_session(session_id)                        # called from end_walk_session
```

`RLock`-guarded dict, same as the other stores. Wire into `app.state.sos_alerts`
in `main.py`; call `end_session` from `end_walk_session` beside the existing
tracking / risk / landmark cleanups. New router `backend/app/api/sos.py`
mounted in `main.py`. `ErrorCode` needs no new members.

## 6. Not in scope

- Persistence, history, audit trail. If that is wanted later it is a separate
  decision with a migration.
- SMS, phone calls, email, push, or any egress off the LAN. D-008 forbids it.
- Location. The system has no localisation (D-057); an SOS says *someone* needs
  help, not where they are.
- Automatic SOS from fall detection or inactivity. Out of scope; a false
  automatic emergency is worse than none.

## 7. Android client (this repo)

`SosController` keeps siren + speech exactly as-is and gains a network side-car
that can fail without consequence:

- On `activate()`: fire-and-forget `POST /api/v1/sos {session_id, kind:"RAISED"}`
  on the IO dispatcher, **after** the siren has started. A failure is logged and
  otherwise ignored — never spoken, never blocking.
- While active and the alert is un-acknowledged, poll `GET /api/v1/sos/active`
  every ~5 s. On seeing this session's alert become `ACKNOWLEDGED`, speak once:
  *"Help is on the way."* This is the reassurance the current design cannot give.
- On `cancel()`: fire-and-forget `kind:"CANCELLED"`.
- No session id (SOS pressed outside Walk Mode) → skip the network entirely and
  behave exactly as today.

New strings in en/hi/ta: `sos_acknowledged`.

## 8. Dashboard (this repo)

- `GET /api/v1/sos/active` folded into the **existing** `Promise.all` in
  `App.refresh()` — one more request per 2 s cycle, no new timer, no new poll
  loop, no WebSocket.
- A `SosBanner` rendered **above everything**, before `WalkersNow`: red,
  `role="alert"`, device tag derived from the session id the same way
  `WalkersNow` does it, elapsed time since raised, and one large
  **I'm responding** button calling the acknowledge endpoint with the operator
  alias already captured in `HazardOperations`.
- Once acknowledged the banner stays but turns amber and reads
  "`<alias>` is responding", so it is obvious the alert is handled but still live.
- If `/sos/active` 404s (backend without this feature) the dashboard treats it
  as "no alerts" and shows nothing. This is what lets the client land first.

## 9. Acceptance criteria

- Press volume-down on the phone during a walk → siren starts immediately, and
  the banner appears on the dashboard within one poll cycle (≤2 s).
- Backend unreachable → siren and spoken plea are completely unaffected.
- Click **I'm responding** → the phone speaks "Help is on the way." within one
  phone poll (≤5 s); the banner turns amber and names the operator.
- Three-finger cancel on the phone → banner disappears within one poll cycle.
- Kill the phone mid-alert (end the walk session) → the alert leaves
  `/sos/active`; no ghost banner.
- Re-raise while already acknowledged → acknowledgement is preserved.
- Backend restart → alerts are gone (documented, intended); the phone siren is
  still going and re-raises on its next state change.
