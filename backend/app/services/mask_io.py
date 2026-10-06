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


def unique_raster_ids(labels: list[str]) -> list[int]:
    """One distinct mask value per polygon, for analysis that must see every
    polygon as its own object. A polygon keeps its own label as long as no
    earlier polygon on the frame already took it; a duplicate (e.g. two
    model polygons both saved as "1011") gets the lowest free instance in
    the same class, so the `1000*class + instance` encoding -- and with it
    the class -- is preserved. Without this, rasterizing duplicates merges
    them into one disconnected object, which CellMate can't measure."""
    taken: set[int] = set()
    ids = []
    for i, label in enumerate(labels, start=1):
        value = _polygon_label(label, i)
        if value in taken:
            base = (value // 1000) * 1000
            value = next(base + k for k in range(1, 1000) if base + k not in taken)
        taken.add(value)
        ids.append(value)
    return ids


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
