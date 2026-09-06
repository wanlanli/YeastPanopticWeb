"""Rasterizing stored polygon annotations back into label-mask images/stacks
(the inverse of segmentation: polygons -> a mask a downstream tool can read)."""

from __future__ import annotations

import io

import numpy as np
import tifffile
from skimage.draw import polygon as sk_polygon


def _polygon_label(label: str, fallback_index: int) -> int:
    try:
        return int(label)
    except (TypeError, ValueError):
        return fallback_index


def rasterize_polygons(
    polygons: list[tuple[str, list[list[float]]]], height: int, width: int
) -> np.ndarray:
    """polygons: list of (label, points) where points are [x, y] pairs.
    Later polygons in the list win on overlap."""
    mask = np.zeros((height, width), dtype=np.uint16)
    for i, (label, points) in enumerate(polygons, start=1):
        if len(points) < 3:
            continue
        pts = np.array(points)
        rows = pts[:, 1]
        cols = pts[:, 0]
        rr, cc = sk_polygon(rows, cols, shape=(height, width))
        mask[rr, cc] = _polygon_label(label, i)
    return mask


def mask_to_tiff_bytes(mask: np.ndarray) -> bytes:
    buf = io.BytesIO()
    tifffile.imwrite(buf, mask)
    return buf.getvalue()


def mask_stack_to_tiff_bytes(frames: list[np.ndarray]) -> bytes:
    buf = io.BytesIO()
    tifffile.imwrite(buf, np.stack(frames))
    return buf.getvalue()
