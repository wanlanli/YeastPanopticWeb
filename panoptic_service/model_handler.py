"""Loads the fine-tuned yeast panoptic model via the `deepyeast_panoptic`
package (https://github.com/wanlanli/deepyeast-panoptic, a sibling checkout
at DEEPYEAST_PANOPTIC_PATH -- read-only, this module only adds it to
sys.path and imports from it, it never writes into it) and runs whole-frame
instance segmentation.

All post-processing (score/instance/area/border filtering, hole-filling,
tiling for large images) is `deepyeast_panoptic`'s own -- see its README's
"Live threshold and smoothing changes" section. The key property this
module relies on: `YeastPredictor.predict()` caches cheap, bbox-cropped
candidates in the `PredictionResult` it returns, and
`PredictionResult.refine()` can recompute the final instance mask from
those candidates under *new* thresholds without rerunning the model --
that's what backs this service's `/refine-frame/{result_id}` endpoint, and
in turn the web app's "change a filtering slider without re-segmenting"
Advanced Settings panel.

Checkpoint: /home/wlli/Data/oneformer_output/model_final.pth, paired with
the config.yaml saved alongside it from the same training run (see
PANOPTIC_MODEL_DIR below) -- this is the same checkpoint/config pairing the
service used before switching to `deepyeast_panoptic`.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import numpy as np
import torch

from mask_utils import segment_to_polygon
from yeast_categories import class_name

logger = logging.getLogger(__name__)

# Read-only reference to the deepyeast_panoptic package checkout -- see
# module docstring. Needs the vendored detectron2/projects/ layout documented
# in its README (siblings at the repo root); inserting the repo root onto
# sys.path (rather than requiring `pip install -e .`) works the same way,
# since its `detectron2.projects` plugin finder resolves paths relative to
# `__file__`, not install metadata.
DEEPYEAST_PANOPTIC_PATH = Path(
    os.environ.get("DEEPYEAST_PANOPTIC_PATH", "/home/wlli/project/deepyeast-panoptic")
)

# Checkpoint + its own matching config.yaml, saved together from the same
# training run -- NOT deepyeast_panoptic's bundled
# deepyeast_panoptic/configs/default.yaml, which is a generically
# reconstructed inference config and may not match this exact checkpoint's
# training-time architecture choices bit-for-bit. Override PANOPTIC_CONFIG_PATH
# to "" (empty) to use the bundled default instead.
PANOPTIC_MODEL_DIR = Path(os.environ.get("PANOPTIC_MODEL_DIR", "/home/wlli/Data/oneformer_output"))
PANOPTIC_CONFIG_PATH = os.environ.get(
    "PANOPTIC_CONFIG_PATH", str(PANOPTIC_MODEL_DIR / "config.yaml")
)
PANOPTIC_CHECKPOINT_PATH = Path(
    os.environ.get("PANOPTIC_CHECKPOINT_PATH", str(PANOPTIC_MODEL_DIR / "model_final.pth"))
)
# Auto-detect GPU unless explicitly overridden.
PANOPTIC_DEVICE = os.environ.get("PANOPTIC_DEVICE", "auto")

# Large-image strategy -- see deepyeast_panoptic's README "Large images"
# section. "tile" (default) is right for a bigger field of view (more
# cells, not bigger ones), the normal case for whole-frame microscopy.
PANOPTIC_STRATEGY = os.environ.get("PANOPTIC_STRATEGY", "tile")
PANOPTIC_MAX_SIDE = int(os.environ.get("PANOPTIC_MAX_SIDE", "1024"))
PANOPTIC_TILE_SIZE = int(os.environ.get("PANOPTIC_TILE_SIZE", "1024"))
PANOPTIC_TILE_OVERLAP = int(os.environ.get("PANOPTIC_TILE_OVERLAP", "160"))
PANOPTIC_NMS_IOU_THRESHOLD = float(os.environ.get("PANOPTIC_NMS_IOU_THRESHOLD", "0.3"))
PANOPTIC_OOM_FALLBACK_MAX_SIDE = int(os.environ.get("PANOPTIC_OOM_FALLBACK_MAX_SIDE", "768"))

# Post-process filtering defaults -- user-adjustable per-request via the
# app's Advanced Settings panel (see app.py's /predict-frame and
# /refine-frame). Score/instance/area match this model's own prior
# defaults; hole_area_threshold is new (deepyeast_panoptic's smoothing
# knob -- max internal-hole area, in pixels, to fill).
SCORE_THRESHOLD = float(os.environ.get("PANOPTIC_SCORE_THRESHOLD", "0.1"))
INSTANCE_THRESHOLD = float(os.environ.get("PANOPTIC_INSTANCE_THRESHOLD", "0.6"))
AREA_THRESHOLD = int(os.environ.get("PANOPTIC_AREA_THRESHOLD", "300"))
HOLE_AREA_THRESHOLD = int(os.environ.get("PANOPTIC_HOLE_AREA_THRESHOLD", "1000"))
# Ceiling on how far hole_area_threshold can be raised in a /refine-frame
# call without a fresh /predict-frame -- see PredictionResult.refine() in
# deepyeast_panoptic. Raise this (and re-predict) if the UI's smoothing
# slider needs more headroom.
MAX_HOLE_AREA_THRESHOLD = int(os.environ.get("PANOPTIC_MAX_HOLE_AREA_THRESHOLD", "5000"))

# How many predictions to keep cached for cheap /refine-frame calls --
# see app.py's result cache. Each entry holds small, bbox-cropped candidate
# masks (not full-image arrays), but it's still a bound: oldest results are
# evicted first.
RESULT_CACHE_SIZE = int(os.environ.get("PANOPTIC_RESULT_CACHE_SIZE", "50"))


def release_gpu_memory() -> None:
    """Call after dropping the last reference to a ModelHandler, so its CUDA
    memory is handed back to the driver (visible in nvidia-smi) instead of
    sitting in PyTorch's allocator cache."""
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


for _sub in ("detectron2", "", "projects/Panoptic-DeepLab", "projects/DeepLab"):
    _path = DEEPYEAST_PANOPTIC_PATH / _sub if _sub else DEEPYEAST_PANOPTIC_PATH
    sys.path.insert(0, str(_path.resolve()))


class ModelHandler:
    def __init__(self):
        if not DEEPYEAST_PANOPTIC_PATH.exists():
            raise RuntimeError(
                f"deepyeast_panoptic checkout not found at {DEEPYEAST_PANOPTIC_PATH}. "
                "Set DEEPYEAST_PANOPTIC_PATH."
            )
        if not PANOPTIC_CHECKPOINT_PATH.exists():
            raise RuntimeError(
                f"Checkpoint not found at {PANOPTIC_CHECKPOINT_PATH}. Set PANOPTIC_CHECKPOINT_PATH."
            )

        from deepyeast_panoptic import YeastPredictor

        config_path = PANOPTIC_CONFIG_PATH or None
        if config_path and not Path(config_path).exists():
            raise RuntimeError(f"Config not found at {config_path}. Set PANOPTIC_CONFIG_PATH.")

        logger.info(
            "Loading yeast panoptic model: repo=%s config=%s checkpoint=%s device=%s",
            DEEPYEAST_PANOPTIC_PATH,
            config_path or "<bundled default>",
            PANOPTIC_CHECKPOINT_PATH,
            PANOPTIC_DEVICE,
        )
        self.predictor = YeastPredictor(
            weights_path=PANOPTIC_CHECKPOINT_PATH,
            device=PANOPTIC_DEVICE,
            config_path=config_path,
        )

    @property
    def device(self) -> str:
        return self.predictor.device

    def predict(self, image: np.ndarray):
        """Runs the model once. Returns a `deepyeast_panoptic.PredictionResult`
        -- cache it (see app.py) and pass it to `refine()` as many times as
        thresholds change, instead of calling this again."""
        return self.predictor.predict(
            image,
            strategy=PANOPTIC_STRATEGY,
            max_side=PANOPTIC_MAX_SIDE,
            tile_size=PANOPTIC_TILE_SIZE,
            tile_overlap=PANOPTIC_TILE_OVERLAP,
            nms_iou_threshold=PANOPTIC_NMS_IOU_THRESHOLD,
            max_hole_area_threshold=MAX_HOLE_AREA_THRESHOLD,
            oom_fallback_max_side=PANOPTIC_OOM_FALLBACK_MAX_SIDE,
        )

    def refine(
        self,
        result,
        score_threshold: float = SCORE_THRESHOLD,
        instance_threshold: float = INSTANCE_THRESHOLD,
        area_threshold: int = AREA_THRESHOLD,
        hole_area_threshold: int = HOLE_AREA_THRESHOLD,
        keep_border: bool = False,
    ) -> list[dict]:
        """No model forward pass -- recomputes from `result`'s cached
        candidates (see deepyeast_panoptic.PredictionResult.refine), then
        vectorizes the surviving instances into polygons. Cost scales with
        how many candidates pass the thresholds, not image size.

        `keep_border` always overrides whatever border-handling the
        prediction's strategy defaulted to -- it's an explicit user toggle
        (see the app's Advanced Settings panel), not a structural property
        of how the image was tiled."""
        mask, segments_info = result.refine(
            seg_threshold=score_threshold,
            ins_threshold=instance_threshold,
            area_threshold=area_threshold,
            hole_area_threshold=hole_area_threshold,
            remove_border=not keep_border,
        )
        predictions = []
        for segment in segments_info:
            polygon = segment_to_polygon(mask, segment)
            if polygon is None:
                continue
            predictions.append(
                {
                    "class_id": segment["category_id"],
                    "class_name": class_name(segment["category_id"]),
                    "points": polygon,
                    "confidence": segment["score"],
                }
            )
        return predictions
