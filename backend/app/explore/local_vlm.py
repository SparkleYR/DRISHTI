from __future__ import annotations

import gc
import inspect
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Protocol

import cv2
import numpy as np
from PIL import Image

from app.config import Settings


MODEL_NAME = "moondream2"


@dataclass(frozen=True)
class VLMResult:
    text: str
    load_ms: float
    inference_ms: float
    unload_ms: float


class VLMError(RuntimeError):
    pass


class VLMResourceError(VLMError):
    pass


class VLMEngine(Protocol):
    @property
    def ready(self) -> bool: ...

    @property
    def detail(self) -> str: ...

    def query(self, image: np.ndarray, prompt: str) -> VLMResult: ...

    def unload(self) -> None: ...


class UnavailableVLMEngine:
    def __init__(self, detail: str) -> None:
        self._detail = detail

    @property
    def ready(self) -> bool:
        return False

    @property
    def detail(self) -> str:
        return self._detail

    def query(self, _image: np.ndarray, _prompt: str) -> VLMResult:
        raise VLMError(self._detail)

    def unload(self) -> None:
        return None


class LazyMoondreamVLM:
    """Loads Moondream2 for one CUDA query and releases it immediately."""

    def __init__(self, settings: Settings) -> None:
        self._model_path = settings.vlm_model_path
        self._tokenizer_path = settings.vlm_tokenizer_path
        self._modules_cache = settings.vlm_modules_cache
        self._min_free_vram_mb = settings.vlm_min_free_vram_mb
        self._max_tokens = settings.vlm_max_new_tokens
        self._lock = Lock()
        self._loaded_model = None

    @property
    def ready(self) -> bool:
        if not self._required_files_available:
            return False
        try:
            import torch
        except ImportError:
            return False
        return bool(torch.cuda.is_available())

    @property
    def detail(self) -> str:
        if not self._required_files_available:
            return f"Local Moondream2 files are missing at {self._model_path}."
        try:
            import torch
        except ImportError:
            return "PyTorch is unavailable for the local VLM."
        if not torch.cuda.is_available():
            return "CUDA is unavailable; the local VLM requires the RTX 4060."
        return "Local Moondream2 is available for lazy, on-demand CUDA loading."

    @property
    def _required_files_available(self) -> bool:
        return self._tokenizer_path.is_file() and all(
            (self._model_path / filename).is_file()
            for filename in ("config.json", "model.safetensors")
        )

    def query(self, image: np.ndarray, prompt: str) -> VLMResult:
        with self._lock:
            if not self.ready:
                raise VLMError(self.detail)

            self._configure_local_runtime()

            import torch
            from tokenizers import Tokenizer
            from transformers import AutoModelForCausalLM

            free_bytes, _total_bytes = torch.cuda.mem_get_info()
            free_mb = free_bytes / (1024 * 1024)
            if free_mb < self._min_free_vram_mb:
                raise VLMResourceError(
                    "Insufficient free CUDA memory for the isolated VLM request "
                    f"({free_mb:.0f} MiB available; "
                    f"{self._min_free_vram_mb} MiB required)."
                )

            model = None
            load_started = perf_counter()
            tokenizer_from_pretrained = Tokenizer.from_pretrained

            def local_tokenizer(identifier: str, *args, **kwargs):
                if identifier == "moondream/starmie-v1":
                    return Tokenizer.from_file(
                        str(self._tokenizer_path.resolve())
                    )
                return tokenizer_from_pretrained(identifier, *args, **kwargs)

            Tokenizer.from_pretrained = staticmethod(local_tokenizer)
            try:
                model = AutoModelForCausalLM.from_pretrained(
                    str(self._model_path),
                    trust_remote_code=True,
                    local_files_only=True,
                    dtype=torch.float16,
                )
                model = model.to("cuda")
                model.eval()
                self._loaded_model = model
                load_ms = (perf_counter() - load_started) * 1000

                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(rgb)
                inference_started = perf_counter()
                with torch.inference_mode():
                    parameters = inspect.signature(model.query).parameters
                    if "settings" in parameters:
                        output = model.query(
                            pil_image,
                            prompt,
                            settings={
                                "max_tokens": self._max_tokens,
                                "variant": None,
                            },
                        )
                    else:
                        output = model.query(pil_image, prompt)
                inference_ms = (perf_counter() - inference_started) * 1000
                text = _answer_text(output)
                if not text:
                    raise VLMError("The local VLM returned an empty answer.")
            except torch.OutOfMemoryError as exc:
                raise VLMResourceError(
                    "CUDA ran out of memory while processing the VLM snapshot."
                ) from exc
            finally:
                Tokenizer.from_pretrained = tokenizer_from_pretrained
                unload_started = perf_counter()
                self._loaded_model = None
                if model is not None:
                    del model
                gc.collect()
                torch.cuda.empty_cache()
                try:
                    torch.cuda.ipc_collect()
                except RuntimeError:
                    pass
                unload_ms = (perf_counter() - unload_started) * 1000

            return VLMResult(
                text=text,
                load_ms=load_ms,
                inference_ms=inference_ms,
                unload_ms=unload_ms,
            )

    def _configure_local_runtime(self) -> None:
        self._modules_cache.mkdir(parents=True, exist_ok=True)
        os.environ["HF_MODULES_CACHE"] = str(self._modules_cache)
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

        # Transformers may already be imported by the core SegFormer loader.
        # Keep trusted local model code inside the repository in that case too.
        try:
            from transformers import dynamic_module_utils
        except ImportError:
            return
        dynamic_module_utils.HF_MODULES_CACHE = str(self._modules_cache)

        # Local-path dynamic loading does not always discover transitive relative
        # imports in trusted model code. Seed the isolated cache with the complete
        # downloaded Python snapshot so loading never reaches the network.
        package_dir = (
            self._modules_cache
            / "transformers_modules"
            / self._model_path.name.replace("-", "_")
        )
        package_dir.mkdir(parents=True, exist_ok=True)
        for parent in (self._modules_cache, package_dir.parent, package_dir):
            (parent / "__init__.py").touch(exist_ok=True)
        for source in self._model_path.glob("*.py"):
            shutil.copy2(source, package_dir / source.name)


    def unload(self) -> None:
        with self._lock:
            self._loaded_model = None
            try:
                import torch
            except ImportError:
                return
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                try:
                    torch.cuda.ipc_collect()
                except RuntimeError:
                    pass


def load_vlm_engine(settings: Settings) -> VLMEngine:
    if settings.compute_device != "CUDA":
        return UnavailableVLMEngine(
            "The approved local VLM path requires CUDA on the RTX 4060."
        )
    return LazyMoondreamVLM(settings)


def _answer_text(output: object) -> str:
    if isinstance(output, str):
        return " ".join(output.strip().split())
    if isinstance(output, dict):
        answer = output.get("answer")
        if isinstance(answer, str):
            return " ".join(answer.strip().split())
    raise VLMError("The local VLM returned an unsupported response shape.")
