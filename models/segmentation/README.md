# Phase 3 segmentation asset

The active semantic segmenter is NVIDIA SegFormer-B0 fine-tuned on Cityscapes,
downloaded from `nvidia/segformer-b0-finetuned-cityscapes-640-1280`.

The model is used under its non-commercial research/evaluation terms for this
internal hackathon prototype. Any commercial or production use requires a new
licensing review.

Model files are development-time downloads stored below
`models/segmentation/segformer-b0-cityscapes/` and ignored by source control.
Runtime startup uses local files only and must not contact Hugging Face or any
other remote service.

Verified `pytorch_model.bin` SHA-256:
`FFE3494E1339ABF7AF09A13C914E72C3D2745E2F315EBA1FD2B1DEE15B7A73ED`
