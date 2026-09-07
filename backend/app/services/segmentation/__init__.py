from functools import lru_cache

from app.config import PANOPTIC_SERVICE_URL, SAM_SERVICE_URL
from app.services.segmentation.base import AutoSegmentationModel, SegmentationModel
from app.services.segmentation.placeholder import PlaceholderPointModel
from app.services.segmentation.placeholder_auto import ThresholdBlobModel


@lru_cache
def get_model() -> SegmentationModel:
    """Single place to swap the active point-prompt model. Uses the SAM
    HTTP service (see sam_service/ at the repo root) once SAM_SERVICE_URL
    is set, otherwise falls back to the classical-CV placeholder so the app
    still runs with no extra setup."""
    if SAM_SERVICE_URL:
        from app.services.segmentation.http_model import HttpSegmentationModel

        return HttpSegmentationModel(SAM_SERVICE_URL)
    return PlaceholderPointModel()


@lru_cache
def get_auto_model() -> AutoSegmentationModel:
    """Single place to swap the active whole-frame auto-segmentation model.
    Uses the fine-tuned panoptic HTTP service (see panoptic_service/ at the
    repo root) once PANOPTIC_SERVICE_URL is set, otherwise falls back to a
    classical-CV placeholder so the app still runs with no extra setup."""
    if PANOPTIC_SERVICE_URL:
        from app.services.segmentation.http_auto_model import HttpAutoSegmentationModel

        return HttpAutoSegmentationModel(PANOPTIC_SERVICE_URL)
    return ThresholdBlobModel()
