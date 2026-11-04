"""Pluggable point-prompt segmentation model interface.

Swap in a real model (fine-tuned SAM, a custom DL model, or an HTTP call to
an existing inference server) by implementing `predict_point` and pointing
`app.services.segmentation.get_model()` at the new implementation. Nothing
in the API layer or frontend needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class SegmentationModel(ABC):
    @abstractmethod
    def predict_point(
        self, image: np.ndarray, points: list[tuple[float, float, int]]
    ) -> list[list[list[float]]]:
        """Given a grayscale/RGB image and one or more clicked points, each
        (x, y, label) in image pixel coordinates with label 1=include
        (foreground) or 0=exclude (background), return one or more
        polygons, each a list of [x, y] points, describing the predicted
        mask(s)."""
        raise NotImplementedError


class AutoSegmentationModel(ABC):
    @abstractmethod
    def predict_frame(
        self,
        image: np.ndarray,
        score_threshold: float | None = None,
        instance_threshold: float | None = None,
        area_threshold: int | None = None,
        hole_area_threshold: int | None = None,
        keep_border: bool = False,
    ) -> dict:
        """Given a grayscale/RGB image, detect every instance in it (no
        point prompt). Returns
        {"result_id": str | None, "predictions": [{"class_id": int, "class_name": str, "points": [[x, y], ...], "confidence": float}, ...]}.

        score_threshold/instance_threshold/area_threshold/hole_area_threshold
        (smoothing: max internal-hole area to fill)/keep_border are
        user-adjustable filtering knobs (see the Advanced Settings panel);
        None means "use this model's own default".

        `result_id`, when not None, identifies a server-side cache of this
        prediction's pre-threshold candidates that `refine_frame` can
        recompute from -- see below. None means this model has no such
        cache (every call to `refine_frame` would have to fall back to a
        fresh `predict_frame`)."""
        raise NotImplementedError

    def refine_frame(
        self,
        result_id: str,
        score_threshold: float | None = None,
        instance_threshold: float | None = None,
        area_threshold: int | None = None,
        hole_area_threshold: int | None = None,
        keep_border: bool = False,
    ) -> dict:
        """Cheaply recompute `predict_frame`'s result under new thresholds,
        from the cached candidates behind `result_id` -- no model forward
        pass. Same return shape as `predict_frame`.

        Not every model can do this (it needs predict_frame to have cached
        something to refine from); the default raises `NotImplementedError`,
        and callers (see app.api.annotations) should fall back to a fresh
        `predict_frame` call in that case."""
        raise NotImplementedError(f"{type(self).__name__} does not support refine_frame")
