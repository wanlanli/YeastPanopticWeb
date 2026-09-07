# Yeast panoptic segmentation service

A standalone HTTP service: POST a whole frame, get back every detected
instance (cell/shmoo/zygote/tetrad/lysis/spore/mating_type/paired_unknown)
as a polygon, using the fine-tuned Panoptic-DeepLab model at
`/home/wlli/project/PytrochDeepyeast`. Kept separate from `backend/` so
torch/detectron2/that model repo don't have to live in the main API
process — the backend calls this over HTTP
(`backend/app/services/segmentation/http_auto_model.py`) once
`PANOPTIC_SERVICE_URL` is set.

This service **reads** `/home/wlli/project/PytrochDeepyeast` (adds it to
`sys.path`, same as that repo's own `demo.py`) but never writes into it —
all new code lives here in `panoptic_service/`.

## Run

```
cd panoptic_service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install 'git+https://github.com/cocodataset/panopticapi.git'
uvicorn app:app --port 8200
```

Then point the backend at it: `PANOPTIC_SERVICE_URL=http://localhost:8200 uvicorn app.main:app --reload --port 8000` (from `backend/`).

Defaults (all overridable, see Config below):
- Model repo (detectron2 + `prediction.Predictor`, read-only): `/home/wlli/project/PytrochDeepyeast`
- Model dir (checkpoint + its own matching config.yaml, from the same
  training run -- see `PANOPTIC_REPO_PATH`'s `demo.py` for the reference
  inference pattern this mirrors): `/home/wlli/Data/oneformer_output`
- Config: `<model dir>/config.yaml`
- Checkpoint: `<model dir>/model_final.pth`
- Device: auto-detected (`cuda` if `torch.cuda.is_available()`, else `cpu`;
  override with `PANOPTIC_DEVICE`). ~4s/frame on CPU.

Verified end to end: loads the checkpoint (~3s), runs real inference on a
real multi-channel test series (6/6 cells detected, matching the prior
checkpoint's output), and serves through the full backend API.

## How model loading works

`model_handler.py` mirrors `demo.py`'s `build_predictor()` in the model
repo: it inserts `<repo>/detectron2`, `<repo>`, and
`<repo>/projects/Panoptic-DeepLab` onto `sys.path`, builds the config the
same way (`add_panoptic_deeplab_config` + `merge_from_file` + CPU BatchNorm
overrides), and loads `prediction.Predictor` with the checkpoint. The model
loads once at service startup (`ModelHandler()` in `app.py`'s
`on_event("startup")`) and is reused for every `/predict-frame` call.

Per-instance filtering (score/instance-confidence/area thresholds, dropping
masks that touch the frame edge, keeping only the largest connected
component per mask) mirrors `segment_post_process()` in that repo's
`run_notebooks/post_process_utils.py`, using `instances.panoptic_label`
(already `class_id * 1000 + instance_id`) to read off each instance's class.

No compiled detectron2 extension (`detectron2._C`) is needed for this
model: its ROI/NMS ops resolve to `torchvision`, and deformable conv is
disabled in the yeast config -- confirmed by running it. If you point this
at a different checkpoint/config that does need it, you'll need to build
that extension yourself.

## Endpoints

- `GET /health` — `{"status": "ok"}` once the model has loaded, or
  `{"status": "error", "detail": "..."}` explaining what's missing.
- `POST /predict-frame` — multipart form: `image` (file). Returns
  `{"predictions": [{"class_id": int, "class_name": str, "points": [[x, y], ...], "confidence": float}, ...]}`.

## Config (env vars)

- `PANOPTIC_REPO_PATH` — default `/home/wlli/project/PytrochDeepyeast` (detectron2 + `prediction.Predictor` code)
- `PANOPTIC_MODEL_DIR` — default `/home/wlli/Data/oneformer_output` (checkpoint + its matching config.yaml)
- `PANOPTIC_CONFIG_PATH` — default `<model dir>/config.yaml`
- `PANOPTIC_CHECKPOINT_PATH` — default `<model dir>/model_final.pth`. To try
  a different checkpoint, point this (and usually `PANOPTIC_CONFIG_PATH` too,
  since checkpoints are saved paired with the exact config used to train
  them) at it directly -- no code change needed as long as it's the same
  architecture.
- `PANOPTIC_DEVICE` — auto-detected (`cuda` if available, else `cpu`) unless
  set explicitly.
- `PANOPTIC_SCORE_THRESHOLD` (default `0.1`), `PANOPTIC_INSTANCE_THRESHOLD`
  (default `0.6`), `PANOPTIC_AREA_THRESHOLD` (default `300`) — match
  `segment_post_process()`'s defaults in the model repo.

## Until this is running

The backend's "Auto-Segment Frame" button doesn't need this service to
work: without `PANOPTIC_SERVICE_URL` set, it falls back to a classical-CV
placeholder (Otsu threshold + connected components, labeled "cell") -- see
`backend/app/services/segmentation/placeholder_auto.py`.
