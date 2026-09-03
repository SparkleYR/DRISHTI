# DRISHTI Idea Submission PPT Content

## Purpose

This is the content storyboard for the DRISHTI idea-submission presentation.
It is aligned with the **Smart Safety, Mobility & Emergency Response Systems**
brief in the IoT & Smart Living theme from Microsoft Innovation Club, VIT
Chennai.

Use this as a 12-slide deck. Keep each slide visual, use short phrases instead
of paragraphs, and put technical detail in speaker notes if the submission
format permits it.

## Truthfulness rules for the deck

- Call DRISHTI an **assistive prototype**, not a replacement for a white cane,
  guide dog, mobility training, or human judgment.
- Never claim that a road is safe to cross or that the system measures exact
  real-world distance from a single camera.
- Do not claim cloud AI, real-time emergency dispatch, facial recognition, or
  automatic emergency calling. They are not part of the current prototype.
- Say **relative proximity** rather than metres.
- Use only measurements the team has actually recorded. Replace every
  `[MEASURE]` placeholder before final submission.
- The production mobile application is planned as native Kotlin. Expo is only a
  basic physical test harness for the current backend prototype.

---

## Slide 1 - Title and one-line vision

### Title

**DRISHTI - Local AI Safety Assistance for Safer Everyday Mobility**

### Subtitle

**Phone-as-sensor, edge AI on a local laptop, and a local response dashboard**

### One-line pitch

DRISHTI helps a user notice obstacles, understand safer available corridors,
read essential visible text on demand, and report verified local hazards -
without depending on cloud connectivity at runtime.

### Include

- Team name: `[TEAM NAME]`
- Team members and roles: `[NAME - ROLE]`
- Institution: `VIT Chennai`
- Theme: `IoT & Smart Living - Smart Safety, Mobility & Emergency Response`
- A clean logo or eye/route visual, not a cluttered collage

### Visual

One simple diagram: **Phone camera -> Local AI hub -> Guidance + AccessOps
dashboard**.

---

## Slide 2 - The problem

### Heading

**Safety support is often reactive, disconnected, and unavailable when it is
needed most.**

### Content

- People with mobility or sensory challenges can encounter obstacles, blocked
  paths, poor visibility, and uncertain walking surfaces.
- Existing safety information is often delayed, manual, or disconnected from
  the person currently navigating the environment.
- Institutions may receive hazard reports late and lack a clear local workflow
  to verify, assign, and resolve them.
- Cloud-dependent tools can be unreliable or inappropriate on restricted,
  low-connectivity, or privacy-sensitive premises.

### Connection to the official brief

DRISHTI addresses the brief's concerns about delayed hazard detection, limited
real-time monitoring, accessibility support, weak sensor-to-response
communication, and manual safety intervention.

### Visual

Show a simple before-state journey:

```text
Obstacle noticed late -> user uncertainty -> manual report -> delayed response
```

---

## Slide 3 - Target users and use case

### Heading

**Designed for controlled campus and indoor mobility support first.**

### Primary users

- Students, visitors, and staff who benefit from additional situational
  awareness.
- People with low vision or mobility challenges, with appropriate human and
  mobility-aid support.
- Campus accessibility and facilities teams who need a clear local hazard
  workflow.

### Example scenario

1. A user points the phone camera toward the walking area.
2. DRISHTI identifies visible obstacles and approximate walkable/blocked space.
3. The backend returns a cautious action such as `CAUTION`, `MOVE_LEFT`,
   `MOVE_RIGHT`, `STOP`, or `PAUSE_UNCLEAR`.
4. The user can explicitly report a confirmed local obstacle.
5. AccessOps shows the report for verification, assignment, and resolution.

### Scope statement

Start in indoor/campus environments with sighted, controlled testing. Outdoor
roadway guidance, autonomous navigation, and emergency calling are outside the
current scope.

### Visual

Use a three-persona strip: **User -> Campus operator -> Facilities responder**.

---

## Slide 4 - The solution

### Heading

**DRISHTI closes the loop from local perception to local response.**

### Four solution pillars

1. **Walk assistance** - detects approved object classes and spatial evidence.
2. **Cautious guidance** - converts evidence into one stable, explainable
   action; uncertainty results in `PAUSE_UNCLEAR`, not a guess.
3. **Explore mode** - reads visible English text and likely route numbers on
   explicit user request.
4. **AccessOps loop** - turns user-confirmed hazards into verify, assign,
   resolve, and sync operations.

### Value proposition

An offline-capable, privacy-aware edge system that combines personal mobility
assistance with an operational campus hazard-response workflow.

### Visual

Use four labelled cards or icons: eye/camera, route arrow, text sign, dashboard.

---

## Slide 5 - End-to-end user journey

### Heading

**One connected local workflow**

### Flow

```text
Phone camera
    -> private-LAN frame transfer
    -> local AI perception and risk engine
    -> typed guidance and normalized AR coordinates
    -> user-confirmed anonymous hazard report
    -> AccessOps verification and resolution
    -> active-hazard sync back to the phone
```

### Explain in one sentence

The phone is the sensor, the laptop is the local AI and database host, and the
dashboard is the institutional response surface.

### Visual

Use the flow above as the central architecture graphic. Mark all components as
**local/private LAN**; do not draw a cloud.

---

## Slide 6 - How the technology works

### Heading

**Specialized edge AI, not a black-box chatbot.**

### Current technical pipeline

- **YOLO11n on the RTX 4060**: generic obstacle detection for person, chair,
  bag, bicycle, motorcycle, car, bus, and bench.
- **SegFormer-B0 on CUDA**: walkable, road, non-walkable, and unknown surface
  evidence.
- **Tracking and spatial analysis**: session-scoped tracks, path overlap,
  corridor occupancy, relative proximity, and approach evidence.
- **Deterministic risk engine**: transparent scoring, safety overrides,
  persistence, hysteresis, and cooldowns.
- **Tesseract 5 on CPU**: on-demand English OCR, isolated from Walk Mode.
- **FastAPI + SQLite**: typed local APIs, local persistence, and dashboard
  workflow.

### Important design choice

Continuous Walk Mode does not use an LLM, VLM, OCR engine, cloud service, or
agent framework.

### Visual

Stack diagram from camera image to perception, spatial evidence, risk decision,
guidance, and dashboard.

---

## Slide 7 - What makes DRISHTI different

### Heading

**Privacy-first safety assistance with an operational response loop.**

### Differentiators

| Common limitation | DRISHTI response |
|---|---|
| Cloud dependency | Local-only runtime on a private LAN |
| Raw object labels only | Spatial context, corridor analysis, and cautious actions |
| Repeated noisy alerts | Persistence, hysteresis, cooldown, and deduplication |
| Personal assistance isolated from operations | Anonymous report-to-resolution dashboard loop |
| Unexplained AI output | Typed evidence, risk level, reason code, and normalized geometry |
| Continuous image collection | No continuous walking-frame storage |

### One sentence takeaway

DRISHTI is not simply an object detector; it is an explainable local safety
workflow from perception to institutional follow-up.

---

## Slide 8 - Privacy, safety, and responsible design

### Heading

**Safety claims are deliberately bounded.**

### Commitments

- Runtime uses no cloud inference, cloud storage, analytics, or hosted
  database.
- Continuous walking images are not stored.
- Hazard evidence is optional and stored locally only after explicit consent.
- No facial recognition, identity tracking, or personal route history.
- Relative proximity is not reported as exact distance.
- Weak or contradictory evidence triggers `PAUSE_UNCLEAR` rather than invented
  guidance.
- The system never says that it is safe to cross a road.

### Visual

Use a shield graphic surrounded by: **Local**, **Consent**, **No identity
tracking**, **Cautious guidance**, **Human judgment remains essential**.

---

## Slide 9 - Prototype status and proof

### Heading

**Core local MVP is built and verified.**

### Completed core capabilities

- Phone-to-laptop frame transfer over a private LAN.
- Local CUDA object detection and semantic segmentation.
- Tracking, corridor analysis, deterministic risk and guidance.
- Latest-frame-wins scheduling and stale-result handling.
- SQLite hazard reporting and AccessOps dashboard workflow.
- Verify, assign, start, resolve, merge, and nearby-hazard synchronization.

### Current verification evidence

- **109 backend automated tests**
- **34 Expo-harness tests**
- **3 dashboard tests**
- CUDA detector and segmenter checks on the local RTX 4060
- Local Tesseract OCR API check

### Honest status note

Phases 0-6 are complete. Phase 7 Explore OCR is implemented and in review;
its final controlled physical sign check is pending approval.

### Visuals to insert

- One clean phone screenshot with overlays visible.
- One dashboard screenshot showing a report lifecycle.
- One terminal/health screenshot showing all local models ready.

Do not use a screenshot that shows a failed connection or an empty overlay.

---

## Slide 10 - Impact and success metrics

### Heading

**Measure usefulness, reliability, and response closure.**

### Metrics to report only after measurement

- Controlled-scene object detection precision/recall: `[MEASURE]`
- Median local frame processing time: `[MEASURE] ms`
- Fresh accepted-frame rate: `[MEASURE] %`
- Stable tracking rate over nearby frames: `[MEASURE] %`
- Hazard report to dashboard visibility time: `[MEASURE] s`
- Report resolution completion rate in a controlled workflow: `[MEASURE] %`
- OCR text/route read success on prepared signs: `[MEASURE] %`

### Expected impact

- Earlier awareness of visible obstacles and blocked corridors.
- Faster, auditable institutional handling of reported hazards.
- A local deployment model suitable for privacy-sensitive campuses or sites with
  unreliable internet.

### Visual

Use a small scorecard. Never fabricate a numerical result.

---

## Slide 11 - Roadmap and scalability

### Heading

**Build reliability first; expand only with measured evidence.**

### Current stage

- Core MVP complete: Phases 0-6.
- Explore OCR: Phase 7 implemented and under physical review.

### Next approved opportunities

1. India-specific hazard classes with licensed data and measured false-positive
   controls.
2. A carefully bounded local vision-language model for user-triggered scene
   questions only, if it does not impair Walk Mode.
3. Recurring-hazard analytics and transparent accessibility scoring.
4. Native Kotlin mobile application for production camera lifecycle,
   accessibility interaction, speech, haptics, and release packaging.
5. Campus-map asset integration after the institution supplies an approved map.

### Scalability statement

The backend contracts are client-independent: the test harness can be replaced
by the future native client without redesigning the local AI, API, or database
workflow.

---

## Slide 12 - Closing and ask

### Heading

**DRISHTI: see the risk, choose a cautious response, close the hazard loop.**

### Closing message

DRISHTI combines local visual perception, explainable mobility guidance,
on-demand text reading, and an operational reporting workflow to make safety
support more timely, private, and actionable.

### Ask

- Support for controlled campus validation with accessibility stakeholders.
- Feedback from facilities and safety operators on report workflow.
- Approved campus map assets and safe test locations.
- Mentorship on accessibility validation, inclusive design, and responsible
deployment.

### Footer

- Team name and member names
- Contact email or QR code
- Repository/demo QR code only if it opens a permitted local or approved demo
  destination

---

## Submission checklist

Before exporting the final PPT/PDF, verify all of the following:

- [ ] Team name, member names, roles, and contact details are filled in.
- [ ] Every `[MEASURE]` value is either replaced by actual evidence or removed.
- [ ] The title clearly names the problem, solution, and IoT & Smart Living
      theme.
- [ ] The deck explains both the individual user benefit and the campus
      operations benefit.
- [ ] At least one architecture visual, one phone visual, and one dashboard
      visual are included.
- [ ] Every diagram labels the runtime as local/private LAN and avoids cloud
      imagery.
- [ ] All safety limitations are retained: no exact distance, no safe-crossing
      claim, no replacement of mobility aids, and no unimplemented emergency
      dispatch claim.
- [ ] The current status is truthful: core MVP complete; Phase 7 OCR is in
      review until its physical sign test is approved.
- [ ] Screenshots are readable, cropped, and free of secrets, personal data, or
      failed test messages.
- [ ] Slides use large text, high contrast, and one main idea per slide.
- [ ] The final deck is checked on the actual submission screen size and exported
      in the required format.

## Suggested deck style

- Use dark navy or charcoal for the base, green for available/ready states,
  amber for caution, and red only for blocked/stop states.
- Keep an accessible contrast ratio; never use colour as the only signal.
- Prefer one diagram or screenshot plus three short points per slide.
- Avoid stock images of unsafe blindfolded walking, emergency vehicles, or
  unverifiable statistics.
- Use consistent labels: **local**, **private LAN**, **relative proximity**,
  **cautious guidance**, and **human-in-the-loop response**.

## Source brief

- `PS1_Smart_Safety_Mobility_Emergency_Response.pdf` - Microsoft Innovation
  Club, VIT Chennai, IoT & Smart Living problem statement.
