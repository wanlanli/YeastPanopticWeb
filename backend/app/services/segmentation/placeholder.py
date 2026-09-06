"""Classical-CV placeholder for the point-prompt segmentation model.

Wires the "click a point, get a mask" workflow end to end without a heavy
ML dependency: flood-fills a region of similar intensity around the clicked
point, then vectorizes its boundary into a polygon. Not intended to be
biologically accurate — swap in `SegmentationModel` subclass backed by a
real model when it's ready to serve.
"""

from __future__ import annotations

import numpy as np
from skimage.color import rgb2gray
from skimage.measure import approximate_polygon, find_contours
from skimage.segmentation import flood

from app.services.segmentation.base import SegmentationModel

DEFAULT_TOLERANCE_FRACTION = 0.08
MAX_REGION_FRACTION = 0.25  # refuse regions covering more than this share of the image


class PlaceholderPointModel(SegmentationModel):
    def predict_point(
        self, image: np.ndarray, x: float, y: float
    ) -> list[list[list[float]]]:
        gray = self._to_gray(image)
        h, w = gray.shape
        row, col = int(round(y)), int(round(x))
        if not (0 <= row < h and 0 <= col < w):
            return []

        tolerance = DEFAULT_TOLERANCE_FRACTION * (
            float(gray.max()) - float(gray.min()) or 1.0
        )
        mask = flood(gray, (row, col), tolerance=tolerance)

        if mask.sum() == 0 or mask.sum() > MAX_REGION_FRACTION * mask.size:
            # fall back to a small fixed box around the point so the UI
            # always gets *something* editable back
            return [self._box_polygon(row, col, h, w)]

        contours = find_contours(mask.astype(np.float32), level=0.5)
        if not contours:
            return [self._box_polygon(row, col, h, w)]

        largest = max(contours, key=len)
        simplified = approximate_polygon(largest, tolerance=1.5)
        # contours are (row, col); convert to (x, y) for the frontend
        polygon = [[float(c), float(r)] for r, c in simplified]
        return [polygon]

    @staticmethod
    def _to_gray(image: np.ndarray) -> np.ndarray:
        if image.ndim == 3:
            return rgb2gray(image[:, :, :3]).astype(np.float32)
        return image.astype(np.float32)

    @staticmethod
    def _box_polygon(row: int, col: int, h: int, w: int, half: int = 10) -> list[list[float]]:
        r0, r1 = max(0, row - half), min(h - 1, row + half)
        c0, c1 = max(0, col - half), min(w - 1, col + half)
        return [
            [float(c0), float(r0)],
            [float(c1), float(r0)],
            [float(c1), float(r1)],
            [float(c0), float(r1)],
        ]
