"""Standalone point-prompt segmentation service: POST an image and one or
more points, get back a polygon. Kept separate from the main backend so its
heavy ML deps (torch, segment-anything) don't have to live in the API
process.

Run directly:
    uvicorn app:app --port 8100

The main backend talks to this over HTTP -- see
`backend/app/services/segmentation/http_model.py` -- once `SAM_SERVICE_URL`
is set to this service's address.
"""

from __future__ import annotations

import io
import json
import logging

import numpy as np
import skimage.io
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from model_handler import ModelHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SAM point-prompt service")
_model: ModelHandler | None = None


class PredictResult(BaseModel):
    polygons: list[list[list[float]]]


@app.on_event("startup")
def load_model() -> None:
    global _model
    _model = ModelHandler()


@app.get("/health")
def health():
    return {"status": "ok" if _model is not None else "loading"}


def _to_uint8_rgb(image: np.ndarray) -> np.ndarray:
    """Global min/max stretch to the full 0-255 range, then replicate to 3
    channels if the source is single-channel (as microscopy frames from the
    backend always are). Deliberately just this -- no percentile clipping
    or other windowing -- so the data reaching SAM is the actual frame, not
    a display-oriented contrast adjustment."""
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


@app.post("/predict-point", response_model=PredictResult)
async def predict_point(
    image: UploadFile = File(...),
    points: str = Form(...),
):
    """`points` is a JSON string: [{"x": float, "y": float, "label": 0|1}, ...]
    (label 1 = include/foreground, 0 = exclude/background)."""
    if _model is None:
        raise HTTPException(503, "Model still loading")

    try:
        arr = skimage.io.imread(io.BytesIO(await image.read()))
    except Exception as exc:
        raise HTTPException(400, f"Could not decode image: {exc}") from exc

    try:
        raw_points = json.loads(points)
        point_list = [(float(p["x"]), float(p["y"]), int(p.get("label", 1))) for p in raw_points]
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, f"Invalid points payload: {exc}") from exc

    rgb = _to_uint8_rgb(arr)
    polygon = _model.predict_point(rgb, point_list)
    return PredictResult(polygons=[polygon] if polygon is not None else [])
