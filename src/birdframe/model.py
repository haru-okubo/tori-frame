"""Perch v2 TFLite inference wrapper."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from birdframe.audio import WINDOW_SAMPLES

# Output tensor index for species logits in ernensbjorn perch_v2_* tflite
# (verified against model card: index 3 = 14,795 logits).
LOGIT_OUTPUT_INDEX = 3


class PerchV2TFLite:
    """Run official-faithful Perch v2 TFLite (Apache-2.0 conversion)."""

    def __init__(self, model_path: str | Path, num_threads: int = 4):
        from ai_edge_litert.interpreter import Interpreter

        self.model_path = Path(model_path)
        if not self.model_path.is_file():
            raise FileNotFoundError(
                f"Model not found: {self.model_path}. Run scripts/download_model.py"
            )
        self.interpreter = Interpreter(
            model_path=str(self.model_path), num_threads=num_threads
        )
        self.interpreter.allocate_tensors()
        self._in = self.interpreter.get_input_details()
        self._out = self.interpreter.get_output_details()
        # Prefer output named 'label' when present
        self._logit_index = LOGIT_OUTPUT_INDEX
        for i, d in enumerate(self._out):
            name = (d.get("name") or "").lower()
            if "label" in name and "spatial" not in name:
                self._logit_index = i
                break

    @property
    def num_classes(self) -> int:
        shape = self._out[self._logit_index]["shape"]
        return int(shape[-1])

    def embed_logits(self, window: np.ndarray) -> np.ndarray:
        """Return raw logits for one 5 s mono window (float32, shape [C])."""
        if window.shape != (WINDOW_SAMPLES,):
            raise ValueError(f"expected shape ({WINDOW_SAMPLES},), got {window.shape}")
        x = window.reshape(1, WINDOW_SAMPLES).astype(np.float32)
        self.interpreter.set_tensor(self._in[0]["index"], x)
        self.interpreter.invoke()
        logits = self.interpreter.get_tensor(self._out[self._logit_index]["index"])
        return np.asarray(logits[0], dtype=np.float32)
