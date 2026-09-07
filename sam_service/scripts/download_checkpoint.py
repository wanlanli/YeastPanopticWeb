"""Download an official Segment Anything checkpoint to this service's
default weights path (`sam_service/storage/models/sam_point_prompt.pth`).

    cd sam_service && python3 scripts/download_checkpoint.py [vit_b|vit_l|vit_h]

To use a fine-tuned checkpoint later, just overwrite that same file (or set
SAM_CHECKPOINT_PATH) -- no code change needed as long as SAM_MODEL_TYPE
still matches its architecture.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_DIR))

from model_handler import SAM_CHECKPOINT_PATH, SAM_MODEL_TYPE  # noqa: E402

CHECKPOINT_URLS = {
    "vit_b": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth",
    "vit_l": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_l_0b3195.pth",
    "vit_h": "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth",
}


def main() -> None:
    model_type = sys.argv[1] if len(sys.argv) > 1 else SAM_MODEL_TYPE
    if model_type not in CHECKPOINT_URLS:
        raise SystemExit(f"Unknown model type {model_type!r}; choose one of {list(CHECKPOINT_URLS)}")

    url = CHECKPOINT_URLS[model_type]
    dest = SAM_CHECKPOINT_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url} -> {dest}")
    urllib.request.urlretrieve(url, dest)
    print(f"Done ({dest.stat().st_size / 1e6:.0f} MB). Set SAM_MODEL_TYPE={model_type} if that isn't already the default.")


if __name__ == "__main__":
    main()
