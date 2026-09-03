# Phase 6 controlled local workflow

1. Run the Phase 6 Alembic migration, backend, dashboard, and Expo harness.
2. Capture a controlled indoor obstacle frame while sighted.
3. Select **Prepare hazard report**. Confirm that the draft contains no name or
   user identity, then select **Confirm anonymous report**.
4. Confirm the report appears in AccessOps within two seconds on the neutral
   normalized map plane and in the verification queue.
5. Enter a local operator alias and exercise `Verify -> Assign -> Start ->
   Resolve`. Confirm each step increments the displayed version.
6. Confirm the resolved report leaves the active queue and the Expo nearby-active
   count returns to zero after polling.
7. Optionally create a second report and test the explicit merge control by
   copying its full ID into **Duplicate report ID** and selecting **Merge into
   this** on the primary report.
8. Stop the dashboard and confirm continuous Walk Mode remains operational.

`phase6-test-map` version `1` at `(0.5, 0.5)` is test-harness data only. It is
not a real campus map. Do not use a roadway, blindfold, or unsafe mobility test.
