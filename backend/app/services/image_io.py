"""Reading microscopy image series (folders of frames or multi-page TIFFs)
and rendering individual frames as contrast-adjusted 8-bit PNGs for the
browser."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

from app.config import SUPPORTED_IMAGE_EXTENSIONS


@dataclass
class SeriesMetadata:
    frame_count: int
    width: int
    height: int
    dtype: str
    channels: int


def _sorted_frame_files(folder: Path) -> list[Path]:
    files = [
        p
        for p in folder.iterdir()
        if p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]
    return sorted(files, key=lambda p: p.name)


def probe_series(source_type: str, path: str) -> SeriesMetadata:
    p = Path(path)
    if source_type == "multipage_tiff":
        with tifffile.TiffFile(p) as tf:
            n = len(tf.pages)
            page = tf.pages[0]
            arr = page.asarray()
            h, w = arr.shape[:2]
            channels = 1 if arr.ndim == 2 else arr.shape[2]
            dtype = str(arr.dtype)
        return SeriesMetadata(n, w, h, dtype, channels)

    if source_type in ("folder", "upload"):
        files = _sorted_frame_files(p)
        if not files:
            raise ValueError(f"No supported image files found in {p}")
        first = _read_single_frame_file(files[0])
        h, w = first.shape[:2]
        channels = 1 if first.ndim == 2 else first.shape[2]
        return SeriesMetadata(len(files), w, h, str(first.dtype), channels)

    raise ValueError(f"Unknown source_type: {source_type}")


def _read_single_frame_file(path: Path) -> np.ndarray:
    if path.suffix.lower() in (".tif", ".tiff"):
        return tifffile.imread(path)
    return np.array(Image.open(path))


def read_frame(source_type: str, path: str, frame_index: int) -> np.ndarray:
    p = Path(path)
    if source_type == "multipage_tiff":
        with tifffile.TiffFile(p) as tf:
            if frame_index < 0 or frame_index >= len(tf.pages):
                raise IndexError(f"frame_index {frame_index} out of range")
            return tf.pages[frame_index].asarray()

    if source_type in ("folder", "upload"):
        files = _sorted_frame_files(p)
        if frame_index < 0 or frame_index >= len(files):
            raise IndexError(f"frame_index {frame_index} out of range")
        return _read_single_frame_file(files[frame_index])

    raise ValueError(f"Unknown source_type: {source_type}")


def auto_contrast_range(arr: np.ndarray) -> tuple[float, float]:
    """1st/99th percentile window, a reasonable default for microscopy data."""
    lo, hi = np.percentile(arr, (1, 99))
    if hi <= lo:
        lo, hi = float(arr.min()), float(arr.max() or 1)
    return float(lo), float(hi)


def _contrast_stretch_uint8(
    arr: np.ndarray, vmin: float | None = None, vmax: float | None = None
) -> np.ndarray:
    """Contrast-stretch an 8/16-bit (or float) single-channel array into 8-bit."""
    work = arr.astype(np.float32)
    if vmin is None or vmax is None:
        auto_lo, auto_hi = auto_contrast_range(work)
        vmin = auto_lo if vmin is None else vmin
        vmax = auto_hi if vmax is None else vmax
    if vmax <= vmin:
        vmax = vmin + 1

    stretched = np.clip((work - vmin) / (vmax - vmin), 0, 1)
    return (stretched * 255).astype(np.uint8)


def render_frame_png(
    arr: np.ndarray, vmin: float | None = None, vmax: float | None = None
) -> bytes:
    """Contrast-stretch an 8/16-bit (or float) array into an 8-bit PNG."""
    if arr.ndim == 3 and arr.shape[2] > 3:
        arr = arr[:, :, 0]  # unsupported multi-channel: show first channel

    img8 = _contrast_stretch_uint8(arr, vmin, vmax)

    image = Image.fromarray(img8)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def to_uint8_rgb(arr: np.ndarray) -> np.ndarray:
    """Contrast-stretch any microscopy frame (8/16-bit, 1+ channels) into an
    8-bit RGB array -- the input format SAM's image encoder expects."""
    if arr.ndim == 3 and arr.shape[2] > 3:
        arr = arr[:, :, 0]

    img8 = _contrast_stretch_uint8(arr)
    if img8.ndim == 2:
        return np.stack([img8] * 3, axis=-1)
    if img8.shape[2] == 1:
        return np.repeat(img8, 3, axis=2)
    return img8
