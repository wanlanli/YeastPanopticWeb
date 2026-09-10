import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
SAMPLE_DATA_DIR = REPO_ROOT / "sample_data"
STORAGE_DIR = BACKEND_DIR / "storage"
SERIES_DIR = STORAGE_DIR / "series"
PREVIEW_DIR = STORAGE_DIR / "previews"
UPLOAD_DIR = STORAGE_DIR / "uploads"
QUANT_DIR = STORAGE_DIR / "quant"
DB_PATH = STORAGE_DIR / "app.db"

for d in (STORAGE_DIR, SERIES_DIR, PREVIEW_DIR, UPLOAD_DIR, QUANT_DIR):
    d.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

SUPPORTED_IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}

# Point-prompt segmentation (see app.services.segmentation). Set this to a
# running sam_service/ instance (e.g. http://localhost:8100) to use real
# SAM; left unset, the app falls back to a classical-CV placeholder.
SAM_SERVICE_URL = os.environ.get("SAM_SERVICE_URL", "")

# Whole-frame auto-segmentation. Set this to a running panoptic_service/
# instance (e.g. http://localhost:8200) to use the fine-tuned yeast
# panoptic model; left unset, the app falls back to a classical-CV
# placeholder (Otsu threshold + connected components).
PANOPTIC_SERVICE_URL = os.environ.get("PANOPTIC_SERVICE_URL", "")

# Local checkout of the CellMate library (geometry/tracking/intensity
# quantification), used by app.services.quantification_compute. Not
# vendored into this repo -- point it at wherever CellMate lives, e.g.
# /home/user/project/CellMate. Its Cython extensions must be built for
# this backend's Python version first (see README).
CELLMATE_PATH = os.environ.get("CELLMATE_PATH", "")

# Auth/session cookie. SESSION_COOKIE_SECURE should be set true once the app
# is served over HTTPS (a plain-HTTP browser silently drops `Secure`
# cookies, which would break login on an unencrypted deployment).
SESSION_COOKIE_NAME = "ypw_session"
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
SESSION_TTL_DAYS = int(os.environ.get("SESSION_TTL_DAYS", "30"))

# How long an anonymous visitor's sandbox project (and its uploads/
# quantification output) survives before being swept -- see
# app.services.sandbox_cleanup.
SANDBOX_TTL_HOURS = float(os.environ.get("SANDBOX_TTL_HOURS", "2"))
