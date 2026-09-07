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
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel

from model_handler import ModelHandler

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


def _to_uint8_rgb(image: Image.Image) -> np.ndarray:
    if image.mode in ("I;16", "I;16B", "I;16L", "I"):
        arr = np.array(image).astype(np.float32)
        lo, hi = float(arr.min()), float(arr.max())
        arr = (arr - lo) / (hi - lo) * 255 if hi > lo else arr * 0
        image = Image.fromarray(arr.astype(np.uint8))
    return np.array(image.convert("RGB"))


@app.post("/predict-frame", response_model=FramePredictResult)
async def predict_frame(image: UploadFile = File(...)):
    if _model is None:
        raise HTTPException(503, f"Model not loaded: {_load_error}")

    try:
        pil_image = Image.open(io.BytesIO(await image.read()))
    except Exception as exc:
        raise HTTPException(400, f"Could not decode image: {exc}") from exc

    rgb = _to_uint8_rgb(pil_image)
    predictions = _model.predict_frame(rgb)
    return FramePredictResult(predictions=predictions)
