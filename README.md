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

## Deploying to another machine (e.g. a server)

One-time setup, then one script starts everything:

```
git clone <this repo> && cd YeastPanopticWeb

cd backend          && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && deactivate && cd ..
cd sam_service       && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && deactivate && cd ..
cd panoptic_service  && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && pip install 'git+https://github.com/cocodataset/panopticapi.git' && deactivate && cd ..
cd frontend          && npm install && cd ..

cp .env.example .env   # then edit the paths in it -- see below
./scripts/run_all.sh   # starts all 4 services, prints the URL to open
```

`torch` (in `sam_service`/`panoptic_service`) installs with GPU support
automatically from PyPI -- no special index/CUDA setup needed. If this
machine has an NVIDIA GPU + driver, it's used automatically
(`torch.cuda.is_available()`); otherwise everything runs on CPU.

**No sudo, and `python3 -m venv` fails with "ensurepip is not
available"?** That's the `python3-venv` system package missing, which
normally needs `apt install` (root) to fix. If conda is already on this
machine (`which conda`), set `PYTHON_ENV_MANAGER=conda` in `.env` and
create conda envs instead of venvs -- see the comment at the top of
`scripts/run_all.sh` for the exact commands (naming convention:
`yeastpanoptic-backend`, `yeastpanoptic-sam_service`,
`yeastpanoptic-panoptic_service`). No conda either? `python3 -m venv
--without-pip .venv && source .venv/bin/activate && curl -sS
https://bootstrap.pypa.io/get-pip.py | python3` bootstraps pip manually,
no new system packages needed (just outbound network access).

Stop everything with `./scripts/stop_all.sh`. Logs land in `logs/*.log`.

### Config you need to change (`.env`)

None of these live in this git repo -- they're large, machine-specific, or
private, so a fresh checkout has none of them. See `.env.example` for the
full list with explanations; the short version:

- **`PANOPTIC_REPO_PATH`** — a separate private repo (detectron2 code the
  panoptic model needs). Copy/clone it onto this machine first.
- **`PANOPTIC_MODEL_DIR`** — the fine-tuned checkpoint + its matching
  `config.yaml`, saved together. Copy this directory over (e.g. `rsync -avP`
  from wherever it currently lives).
- **`SAM_CHECKPOINT_PATH`** / **`SAM_MODEL_TYPE`** — either copy an existing
  SAM checkpoint here, or run `cd sam_service && python3
  scripts/download_checkpoint.py vit_h` (or `vit_b` for a smaller/faster
  model if this server has no GPU) to fetch the official one directly.
- **`CELLMATE_PATH`** — a checkout of the CellMate quantification library,
  **with its Cython extensions built for this machine's own Python
  version** (a `.so` built elsewhere won't load if the Python version
  differs -- rebuild with `python3 setup.py build_ext --inplace` in
  `cellmate/image_measure/measure/`, see `.env.example` for the exact
  commands). Without this set, quantification features return a clear error
  but everything else still works.
- `SAM_SERVICE_URL` / `PANOPTIC_SERVICE_URL` can usually stay as
  `http://localhost:8100` / `:8200` -- only change these if you're running
  those services on a different machine than the backend.

Any of the above left unset degrades gracefully rather than crashing:
without `PANOPTIC_REPO_PATH`/`PANOPTIC_MODEL_DIR`, `panoptic_service`
starts but `/health` reports why it can't load, and the backend falls back
to a classical-CV placeholder for auto-segmentation; same idea for SAM and
CellMate.

### Accessing it from another machine (by IP)

`scripts/run_all.sh` already binds every service to `0.0.0.0` and prints
the URL to use (`http://<this-server-ip>:5173`). Only port **5173** needs
to be reachable from wherever you're connecting from -- the frontend dev
server proxies `/api/*` to the backend internally, so the other three ports
(8000/8100/8200) don't need to be open through any firewall. Check the
server's own IP with `hostname -I` if it's not obvious (e.g. it changed, or
you're on a different network).

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
