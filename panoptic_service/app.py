"""Standalone whole-frame yeast panoptic segmentation service: POST a
frame, get back every detected instance (cell/shmoo/zygote/tetrad/lysis/
spore/unknown) as a polygon, with cheap re-thresholding via /refine-frame.
Kept separate from the main backend so its heavy deps (torch, detectron2,
the deepyeast_panoptic package) don't have to live in the API process.

Run directly:
    uvicorn app:app --port 8200

Requires DEEPYEAST_PANOPTIC_PATH (a checkout of
https://github.com/wanlanli/deepyeast-panoptic) and PANOPTIC_CHECKPOINT_PATH
(the fine-tuned weights) -- see README.md. Until those are in place, the
service still starts; /health reports why the model isn't loaded, and
/predict-frame returns 503.

The main backend talks to this over HTTP -- see
`backend/app/services/segmentation/http_auto_model.py` -- once
`PANOPTIC_SERVICE_URL` is set to this service's address.
"""

from __future__ import annotations

import io
import logging
import os
import threading
import time
import uuid
from collections import OrderedDict

import skimage.io
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from model_handler import (
    AREA_THRESHOLD,
    HOLE_AREA_THRESHOLD,
    INSTANCE_THRESHOLD,
    RESULT_CACHE_SIZE,
    SCORE_THRESHOLD,
    ModelHandler,
    release_gpu_memory,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Yeast panoptic segmentation service")
_model: ModelHandler | None = None
_load_error: str | None = None
_model_lock = threading.Lock()
_last_used = time.monotonic()
_idle_unloaded = False

# After this many idle seconds with no request, drop the model and free its
# GPU memory; the next request pays a one-time reload cost. 0/unset disables
# this and keeps the model resident forever (the old behavior).
IDLE_TIMEOUT_SECONDS = float(os.environ.get("PANOPTIC_IDLE_TIMEOUT_SECONDS", "600"))

# Short-lived, in-memory cache of recent PredictionResults, keyed by
# result_id, so /refine-frame can be called repeatedly (e.g. a UI slider for
# score threshold or smoothing) without re-uploading the image or re-running
# the model. Single-process only -- for multiple worker processes, this
# would need to move to a shared store (e.g. Redis) keyed the same way.
_results: "OrderedDict[str, object]" = OrderedDict()
_results_lock = threading.Lock()


def _cache_put(result) -> str:
    result_id = uuid.uuid4().hex
    with _results_lock:
        _results[result_id] = result
        while len(_results) > RESULT_CACHE_SIZE:
            _results.popitem(last=False)
    return result_id


def _cache_get(result_id: str):
    with _results_lock:
        result = _results.get(result_id)
    if result is None:
        raise HTTPException(
            404, f"Unknown or expired result_id: {result_id!r} -- predict the frame again"
        )
    return result


class FramePrediction(BaseModel):
    class_id: int
    class_name: str
    points: list[list[float]]
    confidence: float


class FramePredictResult(BaseModel):
    result_id: str | None
    predictions: list[FramePrediction]


def _get_model() -> ModelHandler:
    """Returns the loaded model, reloading it first if a previous idle
    period caused it to be dropped. Raises if the model can't be loaded
    (e.g. missing checkpoint) -- same failure this used to report at
    startup, now surfaced on first use instead."""
    global _model, _load_error, _last_used, _idle_unloaded
    with _model_lock:
        if _model is None:
            try:
                _model = ModelHandler()
                _load_error = None
            except Exception as exc:
                _load_error = str(exc)
                logger.exception("Failed to load the panoptic model")
                raise
            finally:
                _idle_unloaded = False
        _last_used = time.monotonic()
        return _model


def _idle_unload_loop() -> None:
    if IDLE_TIMEOUT_SECONDS <= 0:
        return
    global _model, _idle_unloaded
    while True:
        time.sleep(min(60, IDLE_TIMEOUT_SECONDS))
        with _model_lock:
            if _model is not None and time.monotonic() - _last_used > IDLE_TIMEOUT_SECONDS:
                logger.info(
                    "Panoptic model idle for >%.0fs -- unloading to free GPU memory", IDLE_TIMEOUT_SECONDS
                )
                _model = None
                _idle_unloaded = True
                release_gpu_memory()


@app.on_event("startup")
def load_model() -> None:
    try:
        _get_model()
    except Exception:
        pass  # reported via /health and retried lazily on first request
    threading.Thread(target=_idle_unload_loop, daemon=True).start()


@app.get("/health")
def health():
    if _model is not None:
        return {"status": "ok", "device": _model.device}
    if _idle_unloaded:
        return {"status": "idle (will reload on next request)"}
    return {"status": "error", "detail": _load_error}


@app.post("/predict-frame", response_model=FramePredictResult)
async def predict_frame(
    image: UploadFile = File(...),
    score_threshold: float = Form(SCORE_THRESHOLD),
    instance_threshold: float = Form(INSTANCE_THRESHOLD),
    area_threshold: int = Form(AREA_THRESHOLD),
    hole_area_threshold: int = Form(HOLE_AREA_THRESHOLD),
    keep_border: bool = Form(False),
):
    """`score_threshold`/`instance_threshold`/`area_threshold`/
    `hole_area_threshold`/`keep_border` are per-request overrides of this
    service's own filtering defaults -- see the "Advanced Settings" panel
    next to Auto-Segment Frame in the app.

    Runs the model once, caches the result under a fresh `result_id`, then
    applies the requested thresholds. Later threshold changes for the same
    frame should call `/refine-frame/{result_id}` instead of this endpoint
    -- it recomputes from the cached candidates, without rerunning the
    model."""
    try:
        model = _get_model()
    except Exception as exc:
        raise HTTPException(503, f"Model not loaded: {exc}") from exc

    try:
        arr = skimage.io.imread(io.BytesIO(await image.read()))
    except Exception as exc:
        raise HTTPException(400, f"Could not decode image: {exc}") from exc

    result = model.predict(arr)
    result_id = _cache_put(result)
    try:
        predictions = model.refine(
            result,
            score_threshold=score_threshold,
            instance_threshold=instance_threshold,
            area_threshold=area_threshold,
            hole_area_threshold=hole_area_threshold,
            keep_border=keep_border,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return FramePredictResult(result_id=result_id, predictions=predictions)


@app.get("/refine-frame/{result_id}", response_model=FramePredictResult)
def refine_frame(
    result_id: str,
    score_threshold: float = SCORE_THRESHOLD,
    instance_threshold: float = INSTANCE_THRESHOLD,
    area_threshold: int = AREA_THRESHOLD,
    hole_area_threshold: int = HOLE_AREA_THRESHOLD,
    keep_border: bool = False,
):
    """Cheaply recompute which masks to keep, and how smooth they are, for
    an already-predicted frame -- no model forward pass, no re-upload. Cost
    scales with the number of cached candidates that pass the thresholds,
    not image size, so this is fast enough to call on every UI slider
    change."""
    try:
        model = _get_model()
    except Exception as exc:
        raise HTTPException(503, f"Model not loaded: {exc}") from exc
    result = _cache_get(result_id)
    try:
        predictions = model.refine(
            result,
            score_threshold=score_threshold,
            instance_threshold=instance_threshold,
            area_threshold=area_threshold,
            hole_area_threshold=hole_area_threshold,
            keep_border=keep_border,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return FramePredictResult(result_id=result_id, predictions=predictions)
