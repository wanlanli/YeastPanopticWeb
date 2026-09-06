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
        self, image: np.ndarray, x: float, y: float
    ) -> list[list[list[float]]]:
        """Given a grayscale/RGB image and a clicked point (image pixel
        coordinates), return one or more polygons, each a list of [x, y]
        points, describing the predicted mask(s)."""
        raise NotImplementedError
