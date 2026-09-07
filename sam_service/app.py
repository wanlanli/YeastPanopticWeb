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
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image
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


def _to_uint8_rgb(image: Image.Image) -> np.ndarray:
    # 16-bit microscopy frames need a min/max stretch before SAM can use
    # them; 8-bit frames are already displayable as-is.
    if image.mode in ("I;16", "I;16B", "I;16L", "I"):
        arr = np.array(image).astype(np.float32)
        lo, hi = float(arr.min()), float(arr.max())
        arr = (arr - lo) / (hi - lo) * 255 if hi > lo else arr * 0
        image = Image.fromarray(arr.astype(np.uint8))
    return np.array(image.convert("RGB"))


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
        pil_image = Image.open(io.BytesIO(await image.read()))
    except Exception as exc:
        raise HTTPException(400, f"Could not decode image: {exc}") from exc

    try:
        raw_points = json.loads(points)
        point_list = [(float(p["x"]), float(p["y"]), int(p.get("label", 1))) for p in raw_points]
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, f"Invalid points payload: {exc}") from exc

    rgb = _to_uint8_rgb(pil_image)
    polygon = _model.predict_point(rgb, point_list)
    return PredictResult(polygons=[polygon] if polygon is not None else [])
