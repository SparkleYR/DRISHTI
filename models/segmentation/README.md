# Walk segmentation assets

The active indoor semantic segmenter is NVIDIA SegFormer-B0 fine-tuned on
ADE20K, downloaded from `nvidia/segformer-b0-finetuned-ade-512-512` into
`models/segmentation/segformer-b0-ade20k`.

The model is used under its non-commercial research/evaluation terms for this
internal hackathon prototype. Any commercial or production use requires a new
licensing review.

Model weights are development-time downloads ignored by source control.
Runtime startup uses local files only and must not contact Hugging Face or any
other remote service.

Verified ADE20K `model.safetensors` SHA-256:
`6AE39ADDD01DE6B1B8BDE2CF677D43A5CD733424B8D186DE3F95D1C51FEE23F9`

The previous Cityscapes directory remains available only for explicit
`DRISHTI_SEGMENTATION_LABEL_SET=CITYSCAPES` comparisons. Its verified
`pytorch_model.bin` SHA-256 is
`FFE3494E1339ABF7AF09A13C914E72C3D2745E2F315EBA1FD2B1DEE15B7A73ED`.
