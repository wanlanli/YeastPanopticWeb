from functools import lru_cache

from app.services.segmentation.base import SegmentationModel
from app.services.segmentation.placeholder import PlaceholderPointModel


@lru_cache
def get_model() -> SegmentationModel:
    """Single place to swap the active point-prompt model. Point this at a
    real SAM/DL-backed implementation (in-process or via an HTTP client to
    an inference server) once one is ready to serve."""
    return PlaceholderPointModel()
