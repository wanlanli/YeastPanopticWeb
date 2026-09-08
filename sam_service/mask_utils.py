"""Turn a binary mask into a simplified [x, y] polygon."""

from __future__ import annotations

import numpy as np
from skimage.measure import approximate_polygon, find_contours

DEFAULT_SIMPLIFY_TOLERANCE = 1.4  # lower tolerance keeps more points
# Matches CVAT's own default polygon-approximation accuracy (cvat-ui's
# thresholdFromAccuracy(9), MAX_ACCURACY=13 -> ~1.43px) -- see
# panoptic_service/mask_utils.py for the same change and why.
MIN_POLYGON_POINTS = 3


def mask_to_polygon(
    mask: np.ndarray, tolerance: float = DEFAULT_SIMPLIFY_TOLERANCE
) -> list[list[float]] | None:
    contours = find_contours(mask.astype(np.float32), level=0.5)
    if not contours:
        return None

    largest = max(contours, key=len)
    simplified = approximate_polygon(largest, tolerance=tolerance)
    if len(simplified) < MIN_POLYGON_POINTS:
        return None

    # contours are (row, col); convert to (x, y) for the frontend
    return [[float(c), float(r)] for r, c in simplified]
