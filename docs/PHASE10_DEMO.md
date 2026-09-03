# Phase 10 Controlled Hall Demonstration

## Purpose

Phase 10 demonstrates how repeated anonymous observations can help a hall team
prioritize accessibility problems. The accessibility score is not live
navigation and must never replace current Walk Mode guidance, a white cane, a
guide dog, mobility training, or human judgment.

The `hackathon-demo-hall` version `1` coordinate plane is declared demo data.
The camera does not generate indoor map coordinates. Until a real positioning
method and surveyed floor plan exist, the Expo harness reports to one configured
centre point only.

## Start

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe backend\scripts\seed_phase10_demo.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

In a second terminal:

```powershell
npm run dev --workspace apps/dashboard
```

Open `http://127.0.0.1:5173`.

## Judge walkthrough

1. Show **Hall Obstacle Course**, map version `1`, specification `1.0.0`.
2. Point out that six seeded observations became three hazard records. The chair
   and backpack display recurrence counts while every source observation remains
   in SQLite.
3. Expand a route segment. Read the visible calculation inputs: severity,
   verification status, recurrence, confidence, freshness, spatial influence,
   and points deducted.
4. Explain that a new unverified report has a smaller status factor. Verify the
   chair and show that trusted evidence has a stronger score effect.
5. Resolve the chair with the note `Chair removed from demo aisle`. After the
   next poll, show that it disappears from active hazards and no longer reduces
   the score.
6. In the Expo harness, confirm the same controlled chair report more than once.
   Show that the nearest same-category report on the same map/version is reused
   and its observation count rises instead of creating a noisy duplicate.
7. Create a controlled person report, then remove the person from the course.
   After the configured 45-second window without reconfirmation, show the report
   automatically resolved by `system-expiry`. Chairs, bags, and desks use the
   longer 15-minute temporary window.
8. Stop or close the dashboard and show that Walk Mode frame analysis continues.

## Acceptance checklist

- [ ] Same-category reports inside the configured radius and time window merge.
- [ ] A different category, map version, or distant location remains separate.
- [ ] Every merged report increases the observation count and preserves source provenance.
- [ ] Each route and segment deduction is visible and explainable.
- [ ] Resolving a hazard removes its score penalty on the next refresh.
- [ ] A temporary person expires before temporary furniture unless reconfirmed.
- [ ] The page clearly states that the score is advisory and not live navigation.
- [ ] Walk Mode remains usable when the dashboard is closed.
- [ ] No unsafe blindfolded walking test is performed.

## Automated verification

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
npm run typecheck
npm test
npm run build --workspace apps/dashboard
npm run config:check --workspace apps/mobile
npm run export:android --workspace apps/mobile
```
