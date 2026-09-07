"""Loads the fine-tuned yeast Panoptic-DeepLab model from
/home/wlli/project/PytrochDeepyeast (read-only -- this module only adds
that repo to sys.path and imports from it, it never writes into it) and
runs whole-frame instance segmentation.

Mirrors demo.py's `build_predictor()` (same sys.path setup, same cfg
overrides for CPU, same auto GPU/CPU device selection) and
run_notebooks/post_process_utils.py's `segment_post_process()` (same
score/instance/area/edge filtering, using `instances.panoptic_label`
which is already `class_id * 1000 + instance_id`) from that repo,
verified by running it directly against a real checkpoint and test image.

Checkpoint: /home/wlli/Data/oneformer_output/model_final.pth, paired with
the config.yaml saved alongside it from the same training run (see
PANOPTIC_MODEL_DIR below).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import torch

from mask_utils import largest_component, mask_to_polygon
from yeast_categories import class_name

logger = logging.getLogger(__name__)

# Read-only reference to the model repo -- see module docstring. Override
# with PANOPTIC_REPO_PATH if it lives somewhere else.
PANOPTIC_REPO_PATH = Path(os.environ.get("PANOPTIC_REPO_PATH", "/home/wlli/project/PytrochDeepyeast"))

# Checkpoint + its own matching config.yaml, saved together from the same
# training run (see demo.py in PANOPTIC_REPO_PATH for the reference
# inference pattern this mirrors) -- NOT the repo's own
# projects/Panoptic-DeepLab/configs/yeast_panoptics/config.yaml, which
# differs slightly (e.g. MAX_SIZE_TRAIN, contrastive-loss head fields) and
# corresponds to a different checkpoint.
PANOPTIC_MODEL_DIR = Path(os.environ.get("PANOPTIC_MODEL_DIR", "/home/wlli/Data/oneformer_output"))
PANOPTIC_CONFIG_PATH = os.environ.get(
    "PANOPTIC_CONFIG_PATH", str(PANOPTIC_MODEL_DIR / "config.yaml")
)
PANOPTIC_CHECKPOINT_PATH = Path(
    os.environ.get("PANOPTIC_CHECKPOINT_PATH", str(PANOPTIC_MODEL_DIR / "model_final.pth"))
)
# Auto-detect GPU unless explicitly overridden.
PANOPTIC_DEVICE = os.environ.get("PANOPTIC_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
# DETECTRON2_DATASETS just needs to be set for dataset registration at
# import time (see cityscapes_panoptic.py); it's never read from disk for
# single-image inference.
PANOPTIC_DATASET_ROOT = os.environ.get("PANOPTIC_DATASET_ROOT", "/tmp/yeastpanopticweb-unused-datasets")

# Matches segment_post_process()'s defaults in post_process_utils.py.
SCORE_THRESHOLD = float(os.environ.get("PANOPTIC_SCORE_THRESHOLD", "0.1"))
INSTANCE_SCORE_THRESHOLD = float(os.environ.get("PANOPTIC_INSTANCE_THRESHOLD", "0.6"))
AREA_THRESHOLD = int(os.environ.get("PANOPTIC_AREA_THRESHOLD", "300"))

# Matches demo.py's --infer-size: resize so the longer side is this many
# pixels before running the model, then scale results back up to the
# original resolution. Real microscopy frames (e.g. 2048x2048) are much
# bigger than this fine-tuned model was trained/is fast at; skipping this
# on a large frame is a lot slower for no accuracy benefit. 0/unset to
# disable and always predict at full resolution.
_infer_size_env = int(os.environ.get("PANOPTIC_INFER_SIZE", "1024"))
INFER_SIZE = _infer_size_env or None

for _sub in ("detectron2", "", "projects/Panoptic-DeepLab"):
    _path = PANOPTIC_REPO_PATH / _sub if _sub else PANOPTIC_REPO_PATH
    sys.path.insert(0, str(_path.resolve()))
os.environ.setdefault("DETECTRON2_DATASETS", PANOPTIC_DATASET_ROOT)


def _resize_long_side(image: np.ndarray, target: int) -> np.ndarray:
    """Mirrors demo.py's resize_long_side(): resize so the longer side
    equals `target`, keeping aspect ratio."""
    h, w = image.shape[:2]
    scale = target / max(h, w)
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    return cv2.resize(image, (new_w, new_h), interpolation=interp)


def _resize_masks(masks: np.ndarray, orig_size: tuple[int, int]) -> np.ndarray:
    """Mirrors the mask-resizing part of demo.py's resize_instances(): scale
    each predicted boolean mask back up to the original frame size (nearest-
    neighbor, since these are label masks, not continuous-valued)."""
    orig_h, orig_w = orig_size
    if len(masks) == 0:
        return np.zeros((0, orig_h, orig_w), dtype=bool)
    return np.stack(
        [
            cv2.resize(m.astype(np.uint8), (orig_w, orig_h), interpolation=cv2.INTER_NEAREST).astype(bool)
            for m in masks
        ]
    )


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

    def predict_frame(
        self,
        rgb: np.ndarray,
        score_threshold: float = SCORE_THRESHOLD,
        instance_threshold: float = INSTANCE_SCORE_THRESHOLD,
        area_threshold: int = AREA_THRESHOLD,
        keep_border: bool = False,
    ) -> list[dict]:
        orig_size = rgb.shape[:2]
        if INFER_SIZE and max(orig_size) > INFER_SIZE:
            infer_rgb = _resize_long_side(rgb, INFER_SIZE)
            logger.info("Resized %s -> %s for inference", orig_size, infer_rgb.shape[:2])
        else:
            infer_rgb = rgb

        prediction_output = self.predictor(infer_rgb)
        instances = prediction_output["instances"]

        pred_masks = instances.pred_masks.to("cpu").numpy()
        scores = instances.scores
        instance_scores = instances.center_scores
        panoptic_labels = instances.panoptic_label.to("cpu").numpy()

        if infer_rgb.shape[:2] != orig_size:
            pred_masks = _resize_masks(pred_masks, orig_size)

        results = []
        for pred_mask, score, instance_score, panoptic_label in zip(
            pred_masks, scores, instance_scores, panoptic_labels
        ):
            if score < score_threshold or instance_score < instance_threshold:
                continue
            if not keep_border and (
                pred_mask[0, :].any() or pred_mask[-1, :].any() or pred_mask[:, 0].any() or pred_mask[:, -1].any()
            ):
                continue  # touches the frame edge -- likely truncated

            mask = largest_component(pred_mask)
            if mask.sum() < area_threshold:
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
