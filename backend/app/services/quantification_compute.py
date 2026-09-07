"""Computes quantification (per-object geometry, per-channel intensity, and
cross-frame tracking) from a series' saved polygon annotations, using the
CellMate library (see app.config.CELLMATE_PATH) for the actual algorithms.

Polygon labels already follow CellMate's own `1000*semantic + instance`
convention (see app.services.mask_io.rasterize_polygons), so rasterized
masks feed directly into CellMate with no adapter."""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.config import CELLMATE_PATH
from app.models.polygon import Polygon
from app.models.series import ImageSeries
from app.services import image_io, mask_io
from app.services.segmentation.yeast_categories import class_name

_cellmate_ready = False

# The subset of ImageMeasure's property_table kept in the quantification
# output (it computes many more -- coords, skeleton point arrays, bbox,
# is_out_of_border, ... -- not useful as flat table columns). "semantic" is
# translated to a readable "type" name (see compute_geometry) rather than
# kept as a raw class id.
GEOMETRY_COLUMNS = [
    "label",
    "semantic",
    "area",
    "skeleton_major_length",
    "skeleton_minor_length",
    "eccentricity",
    "orientation",
    "centroid_0",
    "centroid_1",
]
INTENSITY_PROPERTIES = ("label", "intensity_mean", "intensity_max", "intensity_min")


def _ensure_cellmate_on_path() -> None:
    global _cellmate_ready
    if _cellmate_ready:
        return
    if not CELLMATE_PATH:
        raise RuntimeError(
            "CELLMATE_PATH is not configured -- set it to a local CellMate "
            "checkout (with its Cython extensions built for this Python "
            "version) to enable quantification. See README."
        )
    if CELLMATE_PATH not in sys.path:
        sys.path.insert(0, CELLMATE_PATH)
    _cellmate_ready = True


def compute_geometry(
    mask: np.ndarray, pixel_size: float = 1.0, sampling_interval: int = 5
) -> pd.DataFrame:
    """Per-object geometric features (area, skeleton lengths, eccentricity,
    ...) from a labeled mask, via CellMate's ImageMeasure. `pixel_size` is
    the physical size of one pixel (e.g. um/px); area/length columns come
    back already scaled by it (area by pixel_size**2, lengths by
    pixel_size) -- leave at 1.0 for raw pixel units.

    `sampling_interval` is in *pixels* from this function's perspective (we
    never expose it to the user, only `pixel_size`), but CellMate itself
    treats it as a physical distance and converts to pixels by dividing by
    pixel_size (`pixel_distance = sampling_interval / pixel_size`). At a
    small pixel_size (e.g. 0.065 um/px, a real microscopy resolution) that
    inflates to a huge pixel distance -- larger than a whole cell's
    skeleton -- leaving zero sample points and crashing deep inside
    CellMate (IndexError on an empty skeleton grid). Pre-multiplying here
    cancels that division out, keeping the sampling grid a constant few
    pixels regardless of resolution."""
    if pixel_size <= 0:
        raise RuntimeError("Resolution (pixel_size) must be greater than 0")

    out_columns = [*GEOMETRY_COLUMNS[:1], "type", *GEOMETRY_COLUMNS[2:]]
    if not np.any(mask):
        return pd.DataFrame(columns=out_columns)

    _ensure_cellmate_on_path()
    from cellmate.image_measure import ImageMeasure

    measure = ImageMeasure(
        mask.astype(np.int32),
        pixel_size=pixel_size,
        sampling_interval=sampling_interval * pixel_size,
        equidistant=True,
    )
    table = measure.property_table
    cols = [c for c in GEOMETRY_COLUMNS if c in table.columns]
    result = table[cols].copy()
    result["semantic"] = result["semantic"].apply(lambda c: class_name(int(c)))
    result = result.rename(columns={"semantic": "type"})
    return result[[c for c in out_columns if c in result.columns]]


def compute_intensity(
    mask: np.ndarray, intensity_stack: np.ndarray, channel_names: list[str]
) -> pd.DataFrame:
    """Per-object, per-channel intensity stats (mean/max/min) from a labeled
    mask and a (H, W, C) stack of raw (non-DIC) channel frames, via
    CellMate's regionprops_table."""
    if not np.any(mask):
        return pd.DataFrame(columns=["label"])

    _ensure_cellmate_on_path()
    from cellmate.image_measure import regionprops_table

    values, cols = regionprops_table(
        mask.astype(np.int32),
        intensity_image=intensity_stack,
        properties=INTENSITY_PROPERTIES,
    )
    df = pd.DataFrame(values.T, columns=cols)

    rename: dict[str, str] = {}
    base_props = ("intensity_mean", "intensity_max", "intensity_min")
    for c in df.columns:
        for i, name in enumerate(channel_names):
            suffix = f"_{i}"
            if c.endswith(suffix) and c[: -len(suffix)] in base_props:
                rename[c] = f"{c[: -len(suffix)]}_{name}"
                break
    df = df.rename(columns=rename)
    df["label"] = df["label"].astype(int)
    return df


def compute_tracking(
    mask_stack: np.ndarray,
    threshold: float = 0.25,
    min_hist: int = 1,
    max_miss: int = 5,
    fill_gaps: bool = False,
) -> tuple[np.ndarray, list[dict], set[tuple[int, int]]]:
    """Cross-frame tracking via CellMate's IoU tracker. Returns a relabeled
    mask stack (label = stable track id, same 1000*semantic+instance scheme),
    a lineage node list ({id, parent_id, frame_start, frame_end, ...})
    suitable for the app's existing tracking-tree viewer, and (only when
    fill_gaps=True) the set of (frame_index, track_id) pairs that were
    filled in rather than actually segmented -- see _interpolated_cells."""
    _ensure_cellmate_on_path()
    from cellmate.tracking._iou_tracker import Tracker

    tracker = Tracker(
        mask_stack.astype(np.int32), threshold=threshold, min_hist=min_hist, max_miss=max_miss
    )
    tracker()

    interpolated: set[tuple[int, int]] = set()
    if fill_gaps:
        # Fills short gaps (a track present before and after, missing in
        # between) with the pixel overlap of the surrounding frames' masks
        # -- only when those two masks are similar enough (IoU > 0.8) and
        # the gap frame doesn't already have a substantial real mask there.
        # Not a real measurement for those frames -- callers must tag rows
        # built from `interpolated` cells accordingly (see compute_series_quantification).
        original_image, tracked_image = tracker.to_image_auto_fill_miss()
        interpolated = _interpolated_cells(original_image, tracked_image)
    else:
        tracked_image = tracker.to_image()

    trackers_saved = tracker.save_trackers()

    parent_of: dict[int, int] = {}
    for u, v, data in tracker.network.edges(data=True):
        if data.get("weight") == 1:  # division (e.g. budding): u -> v
            parent_of[int(v)] = int(u)

    nodes = []
    for track_id, info in trackers_saved.items():
        frames = info.get("frame", [])
        nodes.append(
            {
                "id": int(track_id),
                "parent_id": parent_of.get(int(track_id)),
                "frame_start": int(min(frames)) if frames else None,
                "frame_end": int(max(frames)) if frames else None,
                "n_frames": len(frames),
                "label": f"cell {track_id}",
            }
        )
    return tracked_image, nodes, interpolated


def _interpolated_cells(original_image: np.ndarray, filled_image: np.ndarray) -> set[tuple[int, int]]:
    """Which (frame_index, track_id) pairs exist only in the gap-filled image,
    not in the original tracked image -- i.e. were synthesized, not segmented."""
    interpolated: set[tuple[int, int]] = set()
    for t in range(original_image.shape[0]):
        orig_ids = set(np.unique(original_image[t]).tolist()) - {0}
        filled_ids = set(np.unique(filled_image[t]).tolist()) - {0}
        for raster_label in filled_ids - orig_ids:
            interpolated.add((t, int(raster_label) % 1000))
    return interpolated


def _series_non_dic_channels(series: ImageSeries) -> list[tuple[int, str]]:
    if series.channel_count <= 1:
        return []
    dic = series.dic_channel_index if series.dic_channel_index is not None else 0
    if series.channel_names:
        names = json.loads(series.channel_names)
    else:
        names = [f"channel {i}" for i in range(series.channel_count)]
    return [(i, names[i]) for i in range(series.channel_count) if i != dic]


def frame_mask(db: Session, series: ImageSeries, frame_index: int) -> np.ndarray:
    rows = (
        db.query(Polygon)
        .filter(Polygon.series_id == series.id, Polygon.frame_index == frame_index)
        .order_by(Polygon.id)
        .all()
    )
    polys = [(p.label, p.points) for p in rows]
    return mask_io.rasterize_polygons(polys, series.height, series.width)


def compute_series_quantification(
    db: Session,
    series: ImageSeries,
    pixel_size: float = 1.0,
    sampling_interval: int = 5,
    iou_threshold: float = 0.25,
    max_miss: int = 5,
    fill_gaps: bool = False,
) -> dict:
    """The full pipeline for one series: rasterize every frame's saved
    polygons, (optionally) track objects across frames, then compute
    geometry + per-channel intensity for every object on every frame.
    Returns {"features": DataFrame, "tracking": list[dict]}.

    fill_gaps: when a track is missing for a few frames in the middle (e.g.
    the segmentation model missed it) but present with a similar mask right
    before and after, synthesize an approximate mask for those frames too
    (see compute_tracking). Rows built from a synthesized mask are tagged
    source="interpolated" (vs "segmented") in the features table -- they are
    not real measurements, just a best-effort fill so time series stay
    continuous."""
    non_dic_channels = _series_non_dic_channels(series)

    masks = [frame_mask(db, series, f) for f in range(series.frame_count)]
    mask_stack = (
        np.stack(masks, axis=0)
        if masks
        else np.zeros((0, series.height, series.width), dtype=np.uint16)
    )

    tracking_nodes: list[dict] = []
    frame_track_map: dict[int, dict[int, int]] = {}
    interpolated: set[tuple[int, int]] = set()
    working_masks = masks
    if series.frame_count > 1 and mask_stack.shape[0] > 0 and mask_stack.any():
        tracked_image, tracking_nodes, interpolated = compute_tracking(
            mask_stack, threshold=iou_threshold, max_miss=max_miss, fill_gaps=fill_gaps
        )
        working_masks = [tracked_image[t] for t in range(tracked_image.shape[0])]
        frame_track_map = _build_frame_track_map(masks, working_masks)

    feature_frames = []
    for frame_index, mask in enumerate(working_masks):
        geom = compute_geometry(mask, pixel_size=pixel_size, sampling_interval=sampling_interval)
        if geom.empty:
            continue

        if non_dic_channels:
            chans = [
                image_io.read_frame(series.source_type, series.path, frame_index, ci)
                for ci, _ in non_dic_channels
            ]
            stack = np.stack(chans, axis=-1)
            names = [name for _, name in non_dic_channels]
            inten = compute_intensity(mask, stack, names)
            merged = geom.merge(inten, on="label", how="left")
        else:
            merged = geom

        if interpolated:
            # instance = label % 1000 (the `1000*semantic + instance` scheme)
            merged["source"] = merged["label"].apply(
                lambda label: "interpolated" if (frame_index, int(label) % 1000) in interpolated else "segmented"
            )
        else:
            merged["source"] = "segmented"

        merged.insert(0, "frame", frame_index)
        feature_frames.append(merged)

    features_df = pd.concat(feature_frames, ignore_index=True) if feature_frames else pd.DataFrame()
    return {"features": features_df, "tracking": tracking_nodes, "frame_track_map": frame_track_map}


def _build_frame_track_map(
    original_masks: list[np.ndarray], tracked_masks: list[np.ndarray]
) -> dict[int, dict[int, int]]:
    """Non-destructive mapping from each frame's *original* polygon label
    (the class+instance encoding already saved on the Polygon rows) to the
    stable track id assigned to that object -- lets the Viewer show "this is
    the same cell across frames" without touching stored annotations. Voted
    by pixel-majority overlap between the pre- and post-tracking masks.

    tracked_masks pixels are raster-encoded as 1000*semantic + track_id (see
    Tracker.to_image()); this returns the *raw* track id (matching the "id"
    field in compute_tracking's node list), not the raster-encoded value."""
    frame_map: dict[int, dict[int, int]] = {}
    for t, (orig, tracked) in enumerate(zip(original_masks, tracked_masks)):
        labels = np.unique(orig)
        per_frame: dict[int, int] = {}
        for label in labels:
            if label == 0:
                continue
            region = tracked[orig == label]
            if region.size == 0:
                continue
            vals, counts = np.unique(region, return_counts=True)
            nonzero = vals != 0
            if nonzero.any():
                majority = vals[nonzero][np.argmax(counts[nonzero])]
            else:
                continue
            per_frame[int(label)] = int(majority) % 1000
        if per_frame:
            frame_map[t] = per_frame
    return frame_map
