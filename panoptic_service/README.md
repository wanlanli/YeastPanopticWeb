# Yeast panoptic segmentation service

A standalone HTTP service: POST a whole frame, get back every detected
instance (cell/shmoo/zygote/tetrad/lysis/spore/mating_type/paired_unknown)
as a polygon, using the fine-tuned Panoptic-DeepLab model via the
[`deepyeast_panoptic`](https://github.com/wanlanli/deepyeast-panoptic)
package. Kept separate from `backend/` so torch/detectron2/that package
don't have to live in the main API process — the backend calls this over
HTTP (`backend/app/services/segmentation/http_auto_model.py`) once
`PANOPTIC_SERVICE_URL` is set.

This service **reads** a `deepyeast-panoptic` checkout (adds it to
`sys.path`) but never writes into it — all new code lives here in
`panoptic_service/`.

## Run

```
cd panoptic_service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --port 8200
```

Then point the backend at it: `PANOPTIC_SERVICE_URL=http://localhost:8200 uvicorn app.main:app --reload --port 8000` (from `backend/`).

Defaults (all overridable, see Config below):
- `deepyeast_panoptic` checkout (read-only): `/home/wlli/project/deepyeast-panoptic`
- Model dir (checkpoint + its own matching config.yaml, from the same
  training run): `/home/wlli/Data/oneformer_output`
- Config: `<model dir>/config.yaml`
- Checkpoint: `<model dir>/model_final.pth`
- Device: auto-detected (`cuda` if available, else `cpu`; override with
  `PANOPTIC_DEVICE`). ~1s/frame on CPU for a 512x512 frame.

Verified end to end on this machine: loads the real checkpoint, runs
inference on a real test frame (6 cells detected), and refines (re-applies
thresholds without rerunning the model) in ~20ms vs. ~1.2s for the initial
prediction.

## How model loading works

`model_handler.py` adds `<deepyeast-panoptic>/detectron2`,
`<deepyeast-panoptic>`, and the `projects/` subfolders onto `sys.path`,
then builds a `deepyeast_panoptic.YeastPredictor` from the checkpoint and
(optionally) a matching config.yaml. The model loads once at service
startup (`ModelHandler()` in `app.py`'s `on_event("startup")`) and is
reused for every request.

All post-processing (score/instance-confidence/area/border filtering,
hole-filling/smoothing, large-image tiling) is `deepyeast_panoptic`'s own —
see that package's README. This service's own code
(`mask_utils.segment_to_polygon`) only turns its cleaned, labeled instance
mask into the `{class_id, class_name, points, confidence}` polygon shape
the rest of YeastPanopticWeb expects.

## Endpoints

- `GET /health` — `{"status": "ok", "device": "cpu"|"cuda"}` once the
  model has loaded, or `{"status": "error", "detail": "..."}` explaining
  what's missing.
- `POST /predict-frame` — multipart form: `image` (file), plus optional
  `score_threshold`/`instance_threshold`/`area_threshold`/
  `hole_area_threshold`/`keep_border` overrides. Runs the model once,
  caches the result, and returns
  `{"result_id": "...", "predictions": [{"class_id": int, "class_name": str, "points": [[x, y], ...], "confidence": float}, ...]}`.
- `GET /refine-frame/{result_id}` — same threshold query params. Cheaply
  recomputes `predictions` for an already-predicted frame **without**
  rerunning the model — this is what a UI slider should call on every
  change, instead of `/predict-frame` again. 404 if `result_id` has expired
  from the cache (see `PANOPTIC_RESULT_CACHE_SIZE`) — callers should fall
  back to a fresh `/predict-frame` in that case.

## Config (env vars)

- `DEEPYEAST_PANOPTIC_PATH` — default `/home/wlli/project/deepyeast-panoptic`
- `PANOPTIC_MODEL_DIR` — default `/home/wlli/Data/oneformer_output` (checkpoint + its matching config.yaml)
- `PANOPTIC_CONFIG_PATH` — default `<model dir>/config.yaml`; set to an
  empty string to use `deepyeast_panoptic`'s own bundled
  `deepyeast_panoptic/configs/default.yaml` instead
- `PANOPTIC_CHECKPOINT_PATH` — default `<model dir>/model_final.pth`
- `PANOPTIC_DEVICE` — `auto` (default, picks `cuda` if available, else `cpu`), or `cpu`/`cuda` explicitly
- `PANOPTIC_STRATEGY` — `tile` (default), `resize`, or `none` — see
  `deepyeast_panoptic`'s README "Large images" section
- `PANOPTIC_MAX_SIDE` (default `1024`), `PANOPTIC_TILE_SIZE` (default
  `1024`), `PANOPTIC_TILE_OVERLAP` (default `160`),
  `PANOPTIC_NMS_IOU_THRESHOLD` (default `0.3`),
  `PANOPTIC_OOM_FALLBACK_MAX_SIDE` (default `768`) — tiling/resize knobs,
  passed straight through to `YeastPredictor.predict()`
- `PANOPTIC_SCORE_THRESHOLD` (default `0.1`), `PANOPTIC_INSTANCE_THRESHOLD`
  (default `0.6`), `PANOPTIC_AREA_THRESHOLD` (default `300`),
  `PANOPTIC_HOLE_AREA_THRESHOLD` (default `1000`) — this service's own
  filtering defaults, overridable per-request (see Endpoints above)
- `PANOPTIC_MAX_HOLE_AREA_THRESHOLD` (default `5000`) — ceiling on how far
  a `/refine-frame` call can raise `hole_area_threshold` above what
  `/predict-frame` was called with; raise this if the UI's smoothing slider
  needs more headroom
- `PANOPTIC_RESULT_CACHE_SIZE` (default `50`) — how many predictions to
  keep cached for `/refine-frame`; oldest evicted first

## Until this is running

The backend's "Auto-Segment Frame" button doesn't need this service to
work: without `PANOPTIC_SERVICE_URL` set, it falls back to a classical-CV
placeholder (Otsu threshold + connected components, labeled "cell") -- see
`backend/app/services/segmentation/placeholder_auto.py`.
