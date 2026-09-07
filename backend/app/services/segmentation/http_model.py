"""Point-prompt segmentation via a standalone HTTP inference service (see
`sam_service/` at the repo root) -- keeps heavy ML deps (torch, SAM) out of
the main API process."""

from __future__ import annotations

import json

import numpy as np
import requests

from app.services import image_io
from app.services.segmentation.base import SegmentationModel


class SegmentationServiceError(RuntimeError):
    """Raised when the point-prompt service can't be reached or fails."""


class HttpSegmentationModel(SegmentationModel):
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def predict_point(
        self, image: np.ndarray, points: list[tuple[float, float, int]]
    ) -> list[list[list[float]]]:
        png_bytes = image_io.render_frame_png(image)
        points_json = json.dumps([{"x": x, "y": y, "label": label} for x, y, label in points])
        try:
            resp = requests.post(
                f"{self.base_url}/predict-point",
                files={"image": ("frame.png", png_bytes, "image/png")},
                data={"points": points_json},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise SegmentationServiceError(
                f"Point-prompt service at {self.base_url} is unreachable or failed: {exc}"
            ) from exc
        return resp.json()["polygons"]
