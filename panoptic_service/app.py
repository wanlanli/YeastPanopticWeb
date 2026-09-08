"""Standalone whole-frame yeast panoptic segmentation service: POST a
frame, get back every detected instance (cell/shmoo/zygote/tetrad/lysis/
spore/unknown) as a polygon. Kept separate from the main backend so its
heavy deps (torch, detectron2, the private model repo) don't have to live
in the API process.

Run directly:
    uvicorn app:app --port 8200

Requires PANOPTIC_REPO_PATH (a checkout of the private yeast Panoptic-DeepLab
repo) and PANOPTIC_CHECKPOINT_PATH (the fine-tuned weights) -- see README.md.
Until those are in place, the service still starts; /health reports why the
model isn't loaded, and /predict-frame returns 503.

The main backend talks to this over HTTP -- see
`backend/app/services/segmentation/http_auto_model.py` -- once
`PANOPTIC_SERVICE_URL` is set to this service's address.
"""

from __future__ import annotations

import io
import logging

import numpy as np
import skimage.io
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from model_handler import (
    AREA_THRESHOLD,
    INSTANCE_SCORE_THRESHOLD,
    SCORE_THRESHOLD,
    ModelHandler,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Yeast panoptic segmentation service")
_model: ModelHandler | None = None
_load_error: str | None = None


class FramePrediction(BaseModel):
    class_id: int
    class_name: str
    points: list[list[float]]
    confidence: float


class FramePredictResult(BaseModel):
    predictions: list[FramePrediction]


@app.on_event("startup")
def load_model() -> None:
    global _model, _load_error
    try:
        _model = ModelHandler()
    except Exception as exc:
        # Most likely: the private model repo/checkpoint isn't in place yet.
        # Don't crash the process for that -- report it at /health instead.
        _load_error = str(exc)
        logger.exception("Failed to load the panoptic model")


@app.get("/health")
def health():
    if _model is not None:
        return {"status": "ok"}
    return {"status": "error", "detail": _load_error}


def _to_uint8_rgb(image: np.ndarray) -> np.ndarray:
    """Global min/max stretch to the full 0-255 range, then replicate to 3
    channels if the source is single-channel (as microscopy frames from the
    backend always are). Deliberately just this -- no percentile clipping
    or other windowing -- so the data reaching the model is the actual
    frame, not a display-oriented contrast adjustment."""
    if image.ndim == 3 and image.shape[-1] >= 3:
        image = image[..., :3]  # drop alpha if present; already has color channels
    image = image.astype(np.float32)
    image = image - image.min()
    max_val = image.max()
    if max_val > 0:
        image = image / max_val
    image = (image * 255).astype(np.uint8)
    if image.ndim == 2:
        image = np.stack((image,) * 3, axis=-1)
    return image


@app.post("/predict-frame", response_model=FramePredictResult)
async def predict_frame(
    image: UploadFile = File(...),
    score_threshold: float = Form(SCORE_THRESHOLD),
    instance_threshold: float = Form(INSTANCE_SCORE_THRESHOLD),
    area_threshold: int = Form(AREA_THRESHOLD),
    keep_border: bool = Form(False),
):
    """`score_threshold`/`instance_threshold`/`area_threshold`/`keep_border`
    are per-request overrides of this service's own filtering defaults --
    see the "Advanced Settings" panel next to Auto-Segment Frame in the app."""
    if _model is None:
        raise HTTPException(503, f"Model not loaded: {_load_error}")

    try:
        arr = skimage.io.imread(io.BytesIO(await image.read()))
    except Exception as exc:
        raise HTTPException(400, f"Could not decode image: {exc}") from exc

    rgb = _to_uint8_rgb(arr)
    predictions = _model.predict_frame(
        rgb,
        score_threshold=score_threshold,
        instance_threshold=instance_threshold,
        area_threshold=area_threshold,
        keep_border=keep_border,
    )
    return FramePredictResult(predictions=predictions)
