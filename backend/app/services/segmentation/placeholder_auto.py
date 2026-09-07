"""Classical-CV placeholder for the whole-frame auto-segmentation model.

Wires the "segment everything in the frame" workflow end to end without the
fine-tuned panoptic model: Otsu-thresholds the frame and vectorizes each
connected component above a minimum area. Every detection is labeled
"cell" -- not biologically accurate, just enough to exercise the pipeline.
Swap in `AutoSegmentationModel` backed by panoptic_service/ when it's ready.
"""

from __future__ import annotations

import numpy as np
from skimage.color import rgb2gray
from skimage.filters import threshold_otsu
from skimage.measure import label, regionprops

from app.services.segmentation.base import AutoSegmentationModel
from app.services.segmentation.mask_utils import mask_to_polygon
from app.services.segmentation.yeast_categories import class_name

MIN_AREA = 30
CELL_CLASS_ID = 1


class ThresholdBlobModel(AutoSegmentationModel):
    def predict_frame(
        self,
        image: np.ndarray,
        score_threshold: float | None = None,
        instance_threshold: float | None = None,
        area_threshold: int | None = None,
        keep_border: bool = False,
    ) -> list[dict]:
        # score_threshold/instance_threshold don't apply here -- every blob
        # gets confidence=1.0, there's no per-instance model score to filter on.
        min_area = area_threshold if area_threshold is not None else MIN_AREA

        gray = self._to_gray(image)
        threshold = threshold_otsu(gray)
        binary = gray > threshold
        # brighter-than-background is the usual case for these frames; fall
        # back to the darker half if it covers most of the image instead
        if binary.mean() > 0.5:
            binary = ~binary

        labeled = label(binary)
        results = []
        for region in regionprops(labeled):
            if region.area < min_area:
                continue
            mask = labeled == region.label
            if not keep_border and (
                mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any()
            ):
                continue  # touches the frame edge -- likely truncated
            polygon = mask_to_polygon(mask)
            if polygon is None:
                continue
            results.append(
                {
                    "class_id": CELL_CLASS_ID,
                    "class_name": class_name(CELL_CLASS_ID),
                    "points": polygon,
                    "confidence": 1.0,
                }
            )
        return results

    @staticmethod
    def _to_gray(image: np.ndarray) -> np.ndarray:
        if image.ndim == 3:
            return rgb2gray(image[:, :, :3]).astype(np.float32)
        return image.astype(np.float32)
