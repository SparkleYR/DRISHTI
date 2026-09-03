import fs from "node:fs/promises";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const sourcePptx = "C:/Users/madha/Downloads/DRISHTI_RECURSION_EDITION_II.pptx";
const outputPptx = "C:/Drishti AI/.tmp-ppt-update/final.pptx";
const outDir = "C:/Drishti AI/.tmp-ppt-update/export";

const presentation = await PresentationFile.importPptx(await FileBlob.load(sourcePptx));

function replace(id, from, to) {
  const shape = presentation.resolve(id);
  shape.text.replace(from, to);
}

replace(
  "sh/qtk3mx07",
  "DRISHTI - Local AI Safety Assistance for Safer Everyday Mobility",
  "DRISHTI - Local AI Safety Assistance for Indoor Hall Mobility",
);
replace(
  "sh/1cbmtor6",
  "A phone-camera safety assistant with local edge AI guidance and a campus hazard-response dashboard.",
  "A local indoor safety assistant with live guidance, on-demand OCR/VLM, and hall hazard intelligence.",
);
replace(
  "sh/a9sj29gv",
  "A phone-camera safety assistant: local edge AI on a laptop turns the camera feed into cautious walking guidance, on-demand text reading, and verified hazard reports.",
  "A phone-camera safety assistant: local edge AI turns a live hall view into cautious walking guidance, on-demand OCR/VLM answers, and recurring hazard intelligence.",
);
replace(
  "sh/qtgjyhsf",
  "Runs entirely on a local laptop over private Wi-Fi, so guidance keeps working without cloud connectivity - and every confirmed hazard flows straight into a dashboard facilities can act on.",
  "Runs entirely on a local laptop over private Wi-Fi, so Walk Mode stays independent; the dashboard is optional local hall intelligence, not an approval gate for guidance.",
);
replace(
  "sh/x4ripsny",
  "FASTAPI +\nSQLITE (LOCAL)",
  "FASTAPI +\nSQLITE + VLM\n(LOCAL)",
);
replace(
  "sh/qtsv69kj",
  "YOLO11n + SEGFORMER-B0\n(RTX 4060, LOCAL)",
  "YOLO11n + SEGFORMER-B0\n(RTX 4060, LOCAL)",
);
replace(
  "sh/zel0je1w",
  "GUIDANCE +\nACCESSOPS",
  "GUIDANCE +\nHALL DASHBOARD",
);
replace(
  "sh/al4n2h0z",
  "Two specialised local models (YOLO11n for objects, SegFormer-B0 for walkable surface) feed one deterministic risk engine instead of an LLM, so every guidance decision stays fast and explainable.",
  "YOLO11n detects indoor obstacles while SegFormer-B0 reads walkable surface and walls. A deterministic risk engine governs Walk Mode; the local VLM answers only explicit Explore requests.",
);
replace(
  "sh/9wnulkby",
  "109 backend automated tests, 34 Expo-harness tests, 3 dashboard tests, plus CUDA checks on the detector/segmenter and a working local OCR API - all passing on the team's RTX 4060.",
  "128 backend automated tests, 34 Expo-harness tests and 3 dashboard tests validate the local detector, segmentation, OCR, VLM and hall analytics pipeline on the team's RTX 4060.",
);
replace(
  "sh/2h072143",
  "In:  Indoor/campus testing, full detection + guidance pipeline, hazard reports.",
  "In: Indoor Hall Obstacle Course, full detection + guidance, OCR/VLM exploration, recurring hazards and route scoring.",
);
replace(
  "sh/8325kje9",
  "Out:  Outdoor roads, autonomous nav, auto emergency dispatch, facial recognition, cloud AI.",
  "Out: Outdoor roads, traffic hazards, autonomous navigation, emergency dispatch, facial recognition and cloud AI.",
);
replace(
  "sh/nipkf2tw",
  "AFTER THE HACKATHON",
  "IMPLEMENTED NOW",
);
replace(
  "sh/1kzydsna",
  "India-specific hazard classes, a tightly bounded local VLM for user-triggered questions only, recurring-hazard analytics, and a native Kotlin production app once the Expo harness is validated.",
  "Local VLM for on-demand questions, recurring-hazard consolidation and expiry, hall route scoring, and a local dashboard for course intelligence.",
);

const references = presentation.resolve("tb/o7mhsv6t");
references.cells.set(1, 2, "Segmentation architecture behind our indoor walkable / wall / obstruction corridor model");
references.cells.set(2, 2, "Real-time object detector (YOLO11n) for person / chair / bag / desk");
references.cells.set(4, 2, "Underlying training data for the indoor obstacle labels used by the pretrained checkpoint");
references.cells.set(5, 2, "On-demand English text / sign reading; local VLM supports user-triggered visual questions");

presentation.resolve("sh/zap4nyx4").text = [
  "A real screenshot from the indoor Hall Obstacle Course - not a mockup.",
  "Yellow boxes: YOLO11n detects person, chair, bag and desk obstacles",
  "Coloured overlay: SegFormer-B0 identifies walkable surface, walls and corridor clearance",
  "Bottom panel: live telemetry shows frame timing, corridor score and the cautious guidance state",
  "OCR and the local VLM run only when the user explicitly enters Explore Mode",
  "Shown as captured - including an uncertain frame - so the safety behaviour is honest, not cherry-picked.",
];

await fs.mkdir(outDir, { recursive: true });
const renders = await presentation.export({ format: "png", outputDir: outDir, scale: 1, montage: true });
await fs.writeFile("C:/Drishti AI/.tmp-ppt-update/export-manifest.json", JSON.stringify(renders, null, 2));
const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(outputPptx);
