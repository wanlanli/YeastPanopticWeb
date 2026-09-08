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

    def predict_frame(
        self,
        image: np.ndarray,
        score_threshold: float | None = None,
        instance_threshold: float | None = None,
        area_threshold: int | None = None,
        keep_border: bool = False,
    ) -> list[dict]:
        # Raw/lossless -- the model's own preprocessing does the contrast
        # normalization on the actual data, not a percentile-clipped
        # display rendering (see raw_frame_tiff_bytes).
        tiff_bytes = image_io.raw_frame_tiff_bytes(image)
        data = {"keep_border": str(keep_border)}
        if score_threshold is not None:
            data["score_threshold"] = str(score_threshold)
        if instance_threshold is not None:
            data["instance_threshold"] = str(instance_threshold)
        if area_threshold is not None:
            data["area_threshold"] = str(area_threshold)
        try:
            resp = requests.post(
                f"{self.base_url}/predict-frame",
                files={"image": ("frame.tiff", tiff_bytes, "image/tiff")},
                data=data,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise SegmentationServiceError(
                f"Panoptic service at {self.base_url} is unreachable or failed: {exc}"
            ) from exc
        return resp.json()["predictions"]
