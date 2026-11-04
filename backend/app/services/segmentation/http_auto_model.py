"""Whole-frame auto-segmentation via a standalone HTTP inference service
(see `panoptic_service/` at the repo root, which wraps the `deepyeast_panoptic`
package) -- keeps heavy ML deps (torch, detectron2, the model package) out
of the main API process."""

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
        hole_area_threshold: int | None = None,
        keep_border: bool = False,
    ) -> dict:
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
        if hole_area_threshold is not None:
            data["hole_area_threshold"] = str(hole_area_threshold)
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
        body = resp.json()
        return {"result_id": body.get("result_id"), "predictions": body["predictions"]}

    def refine_frame(
        self,
        result_id: str,
        score_threshold: float | None = None,
        instance_threshold: float | None = None,
        area_threshold: int | None = None,
        hole_area_threshold: int | None = None,
        keep_border: bool = False,
    ) -> dict:
        # No image to upload -- the service re-thresholds its own cached
        # candidates for this result_id, not a fresh model forward pass.
        params = {"keep_border": str(keep_border)}
        if score_threshold is not None:
            params["score_threshold"] = str(score_threshold)
        if instance_threshold is not None:
            params["instance_threshold"] = str(instance_threshold)
        if area_threshold is not None:
            params["area_threshold"] = str(area_threshold)
        if hole_area_threshold is not None:
            params["hole_area_threshold"] = str(hole_area_threshold)
        try:
            resp = requests.get(
                f"{self.base_url}/refine-frame/{result_id}",
                params=params,
                # Cheap -- no model forward pass -- so a short timeout is
                # fine and catches a hung service quickly.
                timeout=min(self.timeout, 15.0),
            )
            if resp.status_code == 404:
                raise SegmentationServiceError(
                    f"Panoptic service's cached result {result_id!r} is unknown or expired "
                    "-- predict the frame again."
                )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise SegmentationServiceError(
                f"Panoptic service at {self.base_url} is unreachable or failed: {exc}"
            ) from exc
        body = resp.json()
        return {"result_id": body.get("result_id"), "predictions": body["predictions"]}
