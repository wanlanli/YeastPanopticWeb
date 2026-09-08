"""Instance-mask post-processing shared by the panoptic model handler.

`largest_component` mirrors get_largest_object() in
/home/wlli/project/PytrochDeepyeast/run_notebooks/post_process_utils.py."""

from __future__ import annotations

import numpy as np
from skimage import morphology
from skimage.measure import approximate_polygon, find_contours, label, regionprops

DEFAULT_SIMPLIFY_TOLERANCE = 1.4  # lower tolerance keeps more points
# Matches CVAT's own default polygon-approximation accuracy (cvat-ui's
# thresholdFromAccuracy(9), MAX_ACCURACY=13 -> ~1.43px) -- our previous 0.5
# stayed too close to the raw marching-squares contour, which follows the
# mask's pixel-level noise and produces a visibly jagged (many near-
# collinear vertices) outline rather than a clean cell boundary.
MIN_POLYGON_POINTS = 3
DEFAULT_HOLE_AREA_THRESHOLD = 1000


def largest_component(
    mask: np.ndarray, hole_area_threshold: int = DEFAULT_HOLE_AREA_THRESHOLD
) -> np.ndarray:
    """Detectron2's per-instance masks can contain small disconnected
    fragments; keep only the largest connected region, and fill any small
    holes left inside it."""
    labeled = label(mask)
    props = regionprops(labeled)
    if not props:
        return np.zeros_like(mask, dtype=bool)
    largest = max(props, key=lambda r: r.area)
    largest_mask = labeled == largest.label
    return morphology.remove_small_holes(largest_mask, area_threshold=hole_area_threshold)


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
