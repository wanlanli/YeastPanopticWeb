"""Whole-frame auto-segmentation via a standalone HTTP inference service
(see `panoptic_service/` at the repo root) -- keeps heavy ML deps (torch,
detectron2, the private model repo) out of the main API process."""

from __future__ import annotations

import numpy as np
import requests

from app.services import image_io
from app.services.segmentation.base import AutoSegmentationModel
from app.services.segmentation.http_model import SegmentationServiceError


class HttpAutoSegmentationModel(AutoSegmentationModel):
    def __init__(self, base_url: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def predict_frame(self, image: np.ndarray) -> list[dict]:
        png_bytes = image_io.render_frame_png(image)
        try:
            resp = requests.post(
                f"{self.base_url}/predict-frame",
                files={"image": ("frame.png", png_bytes, "image/png")},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise SegmentationServiceError(
                f"Panoptic service at {self.base_url} is unreachable or failed: {exc}"
            ) from exc
        return resp.json()["predictions"]
