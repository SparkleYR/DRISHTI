---
license: apache-2.0
pipeline_tag: image-text-to-text
---

Moondream is a small vision language model designed to run efficiently everywhere. 

[Website](https://moondream.ai/) / [Demo](https://moondream.ai/playground) / [GitHub](https://github.com/vikhyat/moondream)

This repository contains the latest (**2025-06-21**) release of Moondream, as well as [historical releases](https://huggingface.co/vikhyatk/moondream2/blob/main/versions.txt). The model is updated frequently, so we recommend specifying a revision as shown below if you're using it in a production application.


### Usage

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from PIL import Image

model = AutoModelForCausalLM.from_pretrained(
    "vikhyatk/moondream2",
    revision="2025-06-21",
    trust_remote_code=True,
    # Uncomment to run on GPU.
    # device_map={"": "cuda"}
)

# Captioning
print("Short caption:")
print(model.caption(image, length="short")["caption"])

print("\nNormal caption:")
for t in model.caption(image, length="normal", stream=True)["caption"]:
    # Streaming generation example, supported for caption() and detect()
    print(t, end="", flush=True)
print(model.caption(image, length="normal"))

# Visual Querying
print("\nVisual query: 'How many people are in the image?'")
print(model.query(image, "How many people are in the image?")["answer"])

# Object Detection
print("\nObject detection: 'face'")
objects = model.detect(image, "face")["objects"]
print(f"Found {len(objects)} face(s)")

# Pointing
print("\nPointing: 'person'")
points = model.point(image, "person")["points"]
print(f"Found {len(points)} person(s)")
```

### Changelog

**2025-06-21**

(release notes coming soon)

**2025-04-15** ([full release notes](https://moondream.ai/blog/moondream-2025-04-14-release))

1. Improved chart understanding (ChartQA up from 74.8 to 77.5, 82.2 with PoT)
2. Added temperature and nucleus sampling to reduce repetitive outputs
3. Better OCR for documents and tables (prompt with “Transcribe the text” or “Transcribe the text in natural reading order”)
4. Object detection supports document layout detection (figure, formula, text, etc)
5. UI understanding (ScreenSpot F1\@0.5 up from 53.3 to 60.3)
6. Improved text understanding (DocVQA up from 76.5 to 79.3, TextVQA up from 74.6 to 76.3)

**2025-03-27** ([full release notes](https://moondream.ai/blog/moondream-2025-03-27-release))

1. Added support for long-form captioning
2. Open vocabulary image tagging
3. Improved counting accuracy (e.g. CountBenchQA increased from 80 to 86.4)
4. Improved text understanding (e.g. OCRBench increased from 58.3 to 61.2)
5. Improved object detection, especially for small objects (e.g. COCO up from 30.5 to 51.2)
6. Fixed token streaming bug affecting multi-byte unicode characters
7. gpt-fast style `compile()` now supported in HF Transformers implementation
