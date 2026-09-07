# SAM point-prompt service

A small standalone HTTP service: POST an image and one or more clicked
points (include/exclude), get back a polygon. Kept separate from `backend/`
so torch/segment-anything don't have to live in the main API process — the
backend calls this over HTTP
(`backend/app/services/segmentation/http_model.py`) once `SAM_SERVICE_URL`
is set.

## Run

```
cd sam_service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 scripts/download_checkpoint.py vit_b   # or vit_l / vit_h
uvicorn app:app --port 8100
```

Then point the backend at it: `SAM_SERVICE_URL=http://localhost:8100 uvicorn app.main:app --reload --port 8000` (from `backend/`).

## Swapping in a fine-tuned checkpoint

Overwrite `sam_service/storage/models/sam_point_prompt.pth` with your own
weights (or set `SAM_CHECKPOINT_PATH` to point elsewhere) — no code change
needed as long as `SAM_MODEL_TYPE` (default `vit_b`) still matches its
architecture.

## Endpoints

- `GET /health` — `{"status": "ok"}` once the model has loaded.
- `POST /predict-point` — multipart form: `image` (file), `points` (JSON
  string: `[{"x": float, "y": float, "label": 0|1}, ...]`, image pixel
  coordinates, label 1 = include/foreground, 0 = exclude/background).
  Returns `{"polygons": [[[x, y], ...], ...]}`.

## Config (env vars)

- `SAM_CHECKPOINT_PATH` — default `sam_service/storage/models/sam_point_prompt.pth`
- `SAM_MODEL_TYPE` — `vit_b` (default) / `vit_l` / `vit_h`
- `SAM_DEVICE` — `cpu` (default) / `cuda`
