# Local ADE20K SegFormer snapshot

- Upstream: `nvidia/segformer-b0-finetuned-ade-512-512`
- Architecture: SegFormer-B0 semantic segmentation
- Dataset vocabulary: ADE20K, 150 labels
- Active DRISHTI use: local indoor surface evidence in the continuous Walk Loop
- Verified `model.safetensors` SHA-256:
  `6AE39ADDD01DE6B1B8BDE2CF677D43A5CD733424B8D186DE3F95D1C51FEE23F9`

The downloaded `config.json` is the source of truth for `id2label`. DRISHTI
token-normalizes labels so both single labels and comma-separated synonyms are
handled. Relevant verified IDs include wall `0`, floor `3`, road `6`, cabinet
`10`, sidewalk `11`, door `14`, rug `28`, wardrobe `35`, stairs `53`, stairway
`59`, escalator `96`, and step `121`.

The model is downloaded only during development. Runtime forces Hugging Face
offline mode, disables telemetry, uses `local_files_only=True`, and never sends
frames outside the laptop. Submitted walking frames remain in memory and are not
persisted.

SegFormer and ADE20K licensing/terms must be reviewed again before distribution
or commercial use. This internal prototype makes only relative image-space
claims; it does not infer exact distance or guarantee safe passage.
