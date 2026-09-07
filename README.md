# YeastPanopticWeb

Microscopy image annotation and quantification viewer: view image
series/movies (8/16-bit TIFF, PNG, JPEG), edit segmentation masks as
polygons, request a mask from a point-prompt model, navigate frames, and
browse precomputed quantification results (feature table, tracking/lineage
tree, t-SNE).

See `PLAN.md`-equivalent context in the original design plan for the full
architecture writeup. Segmentation lives behind swappable interfaces at
`backend/app/services/segmentation/`, with two models, each its own
standalone HTTP service so heavy ML deps stay out of the main API process:

- **Point-prompt (SAM)** — click a cell, get one mask back. Calls out to
  `sam_service/` once running; falls back to a classical-CV placeholder
  (region growing from the clicked point) otherwise.
- **Whole-frame auto-segmentation (yeast panoptic model)** — one click,
  every instance in the frame back (cell/shmoo/zygote/tetrad/lysis/spore),
  each labeled by class. Calls out to `panoptic_service/` once running;
  falls back to a classical-CV placeholder (Otsu threshold + connected
  components, labeled "cell") otherwise.

## Backend

```
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Storage (SQLite DB, registered/uploaded images, quantification files) lives
under `backend/storage/`, created automatically on first run.

### Sample project

If `sample_data/yeast_demo/` (gitignored -- local test fixtures, not
version controlled) contains an image folder, the backend seeds a "Sample
Project" pointing at it on first startup, so there's something to open
immediately. This is a one-time, idempotent seed keyed by project name --
delete the project from the UI and restart the backend to reseed it, or
just add more folders under `sample_data/` and register them yourself from
the Viewer.

### Segmentation services

See `sam_service/README.md` and `panoptic_service/README.md` to run each
model service (separate processes). Once they're up, point the backend at
them:

```
SAM_SERVICE_URL=http://localhost:8100 \
PANOPTIC_SERVICE_URL=http://localhost:8200 \
uvicorn app.main:app --reload --port 8000
```

Either (or both) can be left unset — the app falls back to the matching
classical-CV placeholder so it still runs with no extra setup. `sam_service`
works out of the box with the official SAM weights; `panoptic_service`
additionally needs the private fine-tuned model repo and checkpoint (see
its README) before it'll actually load.

## Frontend

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` to
`http://localhost:8000`.

## Trying it out

1. Create a project on the home page.
2. In the Viewer, register a server-side folder of frames or a `.tif`/`.tiff`
   stack (or upload files directly).
3. Draw polygons, switch to "Point Prompt" and click a cell to get a
   predicted mask, or click "Auto-Segment Frame" to detect every instance
   in the frame at once.
4. In Quantification, upload a features CSV/JSON and/or a tracking CSV/JSON
   (needs `id` and `parent_id` columns) to see the feature table, t-SNE, and
   lineage tree.
