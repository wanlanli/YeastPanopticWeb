"""Instance-mask -> polygon conversion for the panoptic service's HTTP API
(the frontend's annotation canvas edits polygons, not raster masks).

`deepyeast_panoptic`'s own post-processing (largest-component selection,
hole-filling, border/score/area filtering) already runs inside
`YeastPredictor.predict()`/`PredictionResult.refine()` -- this module only
turns its cleaned, already-labeled instance mask into the
`{class_id, class_name, points, confidence}` shape the rest of
YeastPanopticWeb expects.
"""

from __future__ import annotations

import numpy as np
from skimage.measure import approximate_polygon, find_contours

DEFAULT_SIMPLIFY_TOLERANCE = 1.4  # lower tolerance keeps more points
# Matches CVAT's own default polygon-approximation accuracy (cvat-ui's
# thresholdFromAccuracy(9), MAX_ACCURACY=13 -> ~1.43px) -- a smaller value
# stays too close to the raw marching-squares contour, which follows the
# mask's pixel-level noise and produces a visibly jagged (many near-
# collinear vertices) outline rather than a clean cell boundary.
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


def segment_to_polygon(
    instance_mask: np.ndarray, segment: dict, tolerance: float = DEFAULT_SIMPLIFY_TOLERANCE
) -> list[list[float]] | None:
    """Extract one `refine_candidates()`/`PredictionResult.refine()` segment
    (an entry of its `segments_info`, with a `bbox` and `id`) as a polygon in
    full-image coordinates.

    Cropping to the segment's own (already-computed) bounding box first,
    rather than running `find_contours` on the full-image mask, keeps this
    cheap regardless of image size -- consistent with
    `deepyeast_panoptic.postprocess`'s own bbox-first approach."""
    y0, y1, x0, x1 = segment["bbox"]
    crop = instance_mask[y0:y1, x0:x1] == segment["id"]
    polygon = mask_to_polygon(crop, tolerance=tolerance)
    if polygon is None:
        return None
    return [[x + x0, y + y0] for x, y in polygon]
