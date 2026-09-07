"""Loads the fine-tuned yeast Panoptic-DeepLab model from
/home/wlli/project/PytrochDeepyeast (read-only -- this module only adds
that repo to sys.path and imports from it, it never writes into it) and
runs whole-frame instance segmentation.

Mirrors demo.py's `build_predictor()` (same sys.path setup, same cfg
overrides for CPU) and run_notebooks/post_process_utils.py's
`segment_post_process()` (same score/instance/area/edge filtering, using
`instances.panoptic_label` which is already `class_id * 1000 + instance_id`)
from that repo, verified by running it directly against a real checkpoint
and test image.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import numpy as np

from mask_utils import largest_component, mask_to_polygon
from yeast_categories import class_name

logger = logging.getLogger(__name__)

# Read-only reference to the model repo -- see module docstring. Override
# with PANOPTIC_REPO_PATH if it lives somewhere else.
PANOPTIC_REPO_PATH = Path(os.environ.get("PANOPTIC_REPO_PATH", "/home/wlli/project/PytrochDeepyeast"))
PANOPTIC_CONFIG_PATH = os.environ.get(
    "PANOPTIC_CONFIG_PATH",
    str(PANOPTIC_REPO_PATH / "projects/Panoptic-DeepLab/configs/yeast_panoptics/config.yaml"),
)
PANOPTIC_CHECKPOINT_PATH = Path(
    os.environ.get("PANOPTIC_CHECKPOINT_PATH", str(PANOPTIC_REPO_PATH / "model_0159999_v2.pth"))
)
PANOPTIC_DEVICE = os.environ.get("PANOPTIC_DEVICE", "cpu")
# DETECTRON2_DATASETS just needs to be set for dataset registration at
# import time (see cityscapes_panoptic.py); it's never read from disk for
# single-image inference.
PANOPTIC_DATASET_ROOT = os.environ.get("PANOPTIC_DATASET_ROOT", "/tmp/yeastpanopticweb-unused-datasets")

# Matches segment_post_process()'s defaults in post_process_utils.py.
SCORE_THRESHOLD = float(os.environ.get("PANOPTIC_SCORE_THRESHOLD", "0.1"))
INSTANCE_SCORE_THRESHOLD = float(os.environ.get("PANOPTIC_INSTANCE_THRESHOLD", "0.6"))
AREA_THRESHOLD = int(os.environ.get("PANOPTIC_AREA_THRESHOLD", "300"))

for _sub in ("detectron2", "", "projects/Panoptic-DeepLab"):
    _path = PANOPTIC_REPO_PATH / _sub if _sub else PANOPTIC_REPO_PATH
    sys.path.insert(0, str(_path.resolve()))
os.environ.setdefault("DETECTRON2_DATASETS", PANOPTIC_DATASET_ROOT)


class ModelHandler:
    def __init__(self):
        if not PANOPTIC_REPO_PATH.exists():
            raise RuntimeError(f"Model repo not found at {PANOPTIC_REPO_PATH}. Set PANOPTIC_REPO_PATH.")
        if not PANOPTIC_CHECKPOINT_PATH.exists():
            raise RuntimeError(
                f"Checkpoint not found at {PANOPTIC_CHECKPOINT_PATH}. Set PANOPTIC_CHECKPOINT_PATH."
            )

        from detectron2.config import get_cfg
        from detectron2.projects.panoptic_deeplab import add_panoptic_deeplab_config
        from prediction import Predictor

        logger.info(
            "Loading yeast panoptic model: config=%s checkpoint=%s device=%s",
            PANOPTIC_CONFIG_PATH,
            PANOPTIC_CHECKPOINT_PATH,
            PANOPTIC_DEVICE,
        )
        cfg = get_cfg()
        add_panoptic_deeplab_config(cfg)
        cfg.merge_from_file(PANOPTIC_CONFIG_PATH)
        cfg.MODEL.DEVICE = PANOPTIC_DEVICE
        if PANOPTIC_DEVICE == "cpu":
            # SyncBN needs a distributed process group; plain BN runs anywhere.
            cfg.MODEL.SEM_SEG_HEAD.NORM = "BN"
            cfg.MODEL.INS_EMBED_HEAD.NORM = "BN"
            cfg.MODEL.RESNETS.NORM = "BN"
        cfg.MODEL.WEIGHTS = str(PANOPTIC_CHECKPOINT_PATH)

        self.predictor = Predictor(cfg)

    def predict_frame(self, rgb: np.ndarray) -> list[dict]:
        prediction_output = self.predictor(rgb)
        instances = prediction_output["instances"]

        pred_masks = instances.pred_masks.to("cpu").numpy()
        scores = instances.scores
        instance_scores = instances.center_scores
        panoptic_labels = instances.panoptic_label.to("cpu").numpy()

        results = []
        for pred_mask, score, instance_score, panoptic_label in zip(
            pred_masks, scores, instance_scores, panoptic_labels
        ):
            if score < SCORE_THRESHOLD or instance_score < INSTANCE_SCORE_THRESHOLD:
                continue
            if pred_mask[0, :].any() or pred_mask[-1, :].any() or pred_mask[:, 0].any() or pred_mask[:, -1].any():
                continue  # touches the frame edge -- likely truncated

            mask = largest_component(pred_mask)
            if mask.sum() < AREA_THRESHOLD:
                continue

            polygon = mask_to_polygon(mask)
            if polygon is None:
                continue

            class_id = int(panoptic_label) // 1000
            results.append(
                {
                    "class_id": class_id,
                    "class_name": class_name(class_id),
                    "points": polygon,
                    "confidence": float(score),
                }
            )
        return results
