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
        keep_border: bool = False,
    ) -> list[dict]:
        """Given a grayscale/RGB image, detect every instance in it (no
        point prompt). Returns a list of
        {"class_id": int, "class_name": str, "points": [[x, y], ...], "confidence": float}.

        score_threshold/instance_threshold/area_threshold/keep_border are
        user-adjustable filtering knobs (see the Advanced Settings panel);
        None means "use this model's own default"."""
        raise NotImplementedError
