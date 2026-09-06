from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
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
