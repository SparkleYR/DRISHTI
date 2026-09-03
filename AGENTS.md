# DRISHTI Agent Rules

This repository implements DRISHTI, a local-only accessibility prototype. These rules apply to every coding agent and every change in this repository.

## Source of truth

1. `docs/DECISIONS.md` records accepted architecture decisions.
2. `docs/API_CONTRACTS.md` defines the wire contracts.
3. `docs/IMPLEMENTATION_PLAN.md` defines phase order, scope, and acceptance gates.
4. The approved DRISHTI blueprint supplies product requirements where the documents above are silent.

Do not silently resolve conflicts or make material architecture decisions. Record a proposed decision and obtain user approval first.

## Mandatory runtime boundaries

- Runtime operation is local-only: Android phone, private LAN, laptop backend, local SQLite, and laptop dashboard.
- Make zero cloud calls during product runtime. Do not add hosted databases, remote inference, telemetry, analytics, tracking SDKs, or public endpoints.
- Development-time package and model downloads are allowed; normal operation must require no internet connection.
- Never run an LLM, VLM, OCR engine, agent framework, or generative model in the continuous Walk Loop.
- Keep the continuous Walk Loop separate from on-demand Explore processing.
- Never store continuous walking frames. A hazard evidence image may be stored only after explicit user confirmation.
- Do not add facial recognition, identity tracking, continuous video recording, or personal route-history collection.
- Describe monocular depth only as relative proximity. Never claim exact distance or guaranteed crossing safety.

## Phase discipline

- Work on exactly one active phase at a time.
- Read `docs/IMPLEMENTATION_PLAN.md` before changing code.
- Do not scaffold, install, or implement a later phase before the active phase passes its gate.
- Phases 0 through 6 are the core hackathon MVP. Phases 7 through 11 require separate approval after the core loop is stable.
- A phase may be marked `COMPLETE` only after all automated checks and required physical/manual acceptance checks pass and the user approves the gate.
- Failed or unperformed acceptance checks must be reported plainly; never infer success.

## Architecture boundaries

- The future production Kotlin mobile app owns camera preview, coordinate transformation, AR rendering, stale-result rejection, speech, and haptics. Expo implements only the minimum test behavior needed to validate the active backend phase.
- FastAPI owns API validation, scheduling, model execution, spatial reasoning, risk decisions, and persistence.
- Only FastAPI accesses SQLite; mobile and dashboard use the API.
- Keep `perception`, `spatial`, `risk`, `guidance`, `hazards`, and `explore` modules separate.
- Preserve latest-frame-wins behavior and never permit an unbounded inference queue.
- Load core models once. Optional model failure must not break the core detector or Walk Mode.
- Preserve the typed and versioned contracts in `docs/API_CONTRACTS.md`. Contract changes require review and corresponding tests.

## Review and test gates

- Add deterministic tests in the same phase as the behavior they cover.
- Test malformed input, stale frames, uncertainty, degradation, and failure paths as well as success paths.
- Verify that incoming walking images are not written to disk.
- Verify overlay transforms against known corner points, crop, rotation, and preview scaling.
- Verify that visible corridor, direction arrow, spoken action, and haptic action agree.
- Critical safety rules must override scores and cooldowns.
- Never conduct unsafe blindfolded walking tests. Physical tests must use controlled scenes and normal mobility safeguards.
- Before requesting a phase review, run its tests, document any manual checks, and confirm that no later-phase behavior or cloud dependency was introduced.

## Current gate

Phases 0 through 8 are `COMPLETE`. Phase 9 is `IN_REVIEW`: the local Moondream2 snapshot-query endpoint, local-only assets, lazy per-request CUDA loading, bounded non-queueing execution, immediate unload, and isolation from the continuous Walk Loop are implemented; automated tests and the real RTX 4060 model/core-model coexistence check pass, while user gate approval remains pending. Phase 10 remains `IN_REVIEW`: deterministic recurring-hazard consolidation, expiry, versioned indoor hall routes, explainable accessibility scoring, local seed data, dashboard analytics, and automated checks are implemented; the controlled hall demonstration and user approval remain pending. Accessibility scores and VLM answers are advisory and must never become Walk Loop guidance. Phase 11 remains prohibited. Expo remains a bare-bones physical backend test harness; Android application work is being developed separately against the typed local API.
