"""Wraps `segment_anything.SamPredictor` for the point-prompt endpoint.

Adapted from CVAT's SAM Nuclio function (serverless/pytorch/facebookresearch/sam/)
but self-contained: no Nuclio/CVAT runtime, and returns a ready-to-use
polygon instead of a raw embedding.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

import numpy as np
from segment_anything import SamPredictor, sam_model_registry

from mask_utils import mask_to_polygon

logger = logging.getLogger(__name__)

SERVICE_DIR = Path(__file__).resolve().parent
DEFAULT_CHECKPOINT_PATH = SERVICE_DIR / "storage" / "models" / "sam_point_prompt.pth"

# To try a fine-tuned model, overwrite the checkpoint file at this path (or
# point SAM_CHECKPOINT_PATH at it) -- no code change needed as long as
# SAM_MODEL_TYPE still matches its architecture.
SAM_CHECKPOINT_PATH = Path(os.environ.get("SAM_CHECKPOINT_PATH", str(DEFAULT_CHECKPOINT_PATH)))
SAM_MODEL_TYPE = os.environ.get("SAM_MODEL_TYPE", "vit_b")
SAM_DEVICE = os.environ.get("SAM_DEVICE", "cpu")


class ModelHandler:
    def __init__(self):
        logger.info("Loading SAM checkpoint %s (%s) on %s", SAM_CHECKPOINT_PATH, SAM_MODEL_TYPE, SAM_DEVICE)
        sam = sam_model_registry[SAM_MODEL_TYPE](checkpoint=str(SAM_CHECKPOINT_PATH))
        sam.to(device=SAM_DEVICE)
        self.predictor = SamPredictor(sam)
        self._cached_digest: bytes | None = None

    def predict_point(
        self, rgb: np.ndarray, points: list[tuple[float, float, int]]
    ) -> list[list[float]] | None:
        h, w = rgb.shape[:2]
        valid = [(x, y, label) for x, y, label in points if 0 <= x < w and 0 <= y < h]
        if not valid:
            return None

        self._ensure_image_embedded(rgb)

        coords = np.array([[x, y] for x, y, _ in valid], dtype=np.float32)
        labels = np.array([label for _, _, label in valid], dtype=np.int32)
        masks, scores, _ = self.predictor.predict(
            point_coords=coords,
            point_labels=labels,
            multimask_output=True,
        )
        best_mask = masks[int(np.argmax(scores))]
        return mask_to_polygon(best_mask)

    def _ensure_image_embedded(self, rgb: np.ndarray) -> None:
        # SAM's image encoder is the expensive part of a prediction; cache
        # the embedding so repeated clicks on the same frame are cheap.
        digest = hashlib.md5(rgb.tobytes()).digest()
        if digest == self._cached_digest:
            return
        self.predictor.set_image(rgb)
        self._cached_digest = digest
