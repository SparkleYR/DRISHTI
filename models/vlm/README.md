# Local VLM files

Place the development-downloaded Moondream2 snapshot in
`models/vlm/moondream2` and its Starmie tokenizer at
`models/vlm/starmie-v1/tokenizer.json`. Runtime loading is strictly local and
offline; model weights, tokenizer assets, and generated Transformers module
caches are intentionally ignored by source control.
