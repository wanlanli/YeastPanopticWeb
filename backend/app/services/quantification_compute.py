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
from skimage.draw import disk as sk_disk
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

# Where in the cell to measure intensity from -- see compute_region_intensity.
REGION_CYTOPLASM = "cytoplasm"  # the whole cell area
REGION_MEMBRANE = "membrane"  # CellMate's sampled contour/outline points
REGION_SKELETON = "skeleton"  # CellMate's sampled centerline points
REGIONS = (REGION_CYTOPLASM, REGION_MEMBRANE, REGION_SKELETON)


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


def _sample_intensity_at_points(
    intensity_image: np.ndarray, points: np.ndarray, radius: float = 0, pixel_size: float = 1.0
) -> np.ndarray:
    """Intensity at each (row, col) point -- CellMate's coordinate()/
    skeleton() points are sub-pixel (sampled along a fitted contour/
    centerline). radius=0 (the default) takes the nearest actual pixel;
    radius>0 instead averages over a disk centered on the point (clipped at
    the image border) -- a steadier read than a single pixel, at some cost
    to spatial resolution along the profile. Matches test.ipynb's
    intensities_around_points helper.

    `radius` is physical (the same unit as `pixel_size`, e.g. um -- matching
    every other physical measurement in this module), not pixels, so the
    actual ROI size a user asks for doesn't silently change with a series'
    resolution; it's converted here via radius / pixel_size."""
    if len(points) == 0:
        return np.array([], dtype=np.float32)
    points = np.asarray(points)
    if radius > 0:
        radius_px = radius / pixel_size
        values = np.empty(len(points), dtype=np.float32)
        for i, (row, col) in enumerate(points):
            rr, cc = sk_disk((row, col), radius=radius_px, shape=intensity_image.shape)
            values[i] = intensity_image[rr, cc].mean()
        return values
    rows = np.clip(np.round(points[:, 0]).astype(int), 0, intensity_image.shape[0] - 1)
    cols = np.clip(np.round(points[:, 1]).astype(int), 0, intensity_image.shape[1] - 1)
    return intensity_image[rows, cols]


# Geometry columns a caller can opt into merging onto the measurement
# table (see compute_series_measurements's geometry_features) -- "label"
# and "type" are always the identity columns, not optional.
SELECTABLE_GEOMETRY_FEATURES = [
    "area",
    "skeleton_major_length",
    "skeleton_minor_length",
    "eccentricity",
    "orientation",
    "centroid_0",
    "centroid_1",
]


def compute_region_intensity(
    mask: np.ndarray,
    intensity_image: np.ndarray,
    region: str,
    pixel_size: float = 1.0,
    sampling_interval: int = 5,
    radius: float = 0,
) -> pd.DataFrame:
    """Per-cell intensity from one channel's raw frame, over a specific
    sub-region of each cell rather than always the whole area:

    - "cytoplasm": every pixel in the cell -- mean/max/min over the whole
      area (one row per cell; a filled area has no natural point order, so
      a single summary is what makes sense here).
    - "membrane": CellMate's sampled contour points (ImageMeasure.coordinate)
      -- the cell's outline/edge, not its interior. One row PER POINT
      (point_index, its (row, col), and the intensity there) rather than
      one averaged number, so you can see how intensity varies around the
      membrane -- e.g. a polarized/localized signal wouldn't show up at all
      in a mean.
    - "skeleton": same, but CellMate's sampled centerline points
      (ImageMeasure.skeleton) -- an intensity profile along the cell's
      centerline.

    `radius` controls how each membrane/skeleton point is read -- see
    _sample_intensity_at_points (0 = nearest pixel, >0 = disk-mean; a
    physical distance like pixel_size, not a pixel count).

    Returns [label, intensity_mean, intensity_max, intensity_min] for
    cytoplasm, or [label, point_index, coord_row, coord_col, intensity] for
    membrane/skeleton."""
    if region == REGION_CYTOPLASM:
        columns = ["label", "intensity_mean", "intensity_max", "intensity_min"]
        if not np.any(mask):
            return pd.DataFrame(columns=columns)
        df = compute_intensity(mask, intensity_image[..., np.newaxis], ["v"])
        return df.rename(
            columns={
                "intensity_mean_v": "intensity_mean",
                "intensity_max_v": "intensity_max",
                "intensity_min_v": "intensity_min",
            }
        )[columns]

    if region not in (REGION_MEMBRANE, REGION_SKELETON):
        raise ValueError(f"Unknown region {region!r} -- expected one of {REGIONS}")

    columns = ["label", "point_index", "coord_row", "coord_col", "intensity"]
    if not np.any(mask):
        return pd.DataFrame(columns=columns)

    _ensure_cellmate_on_path()
    from cellmate.image_measure import ImageMeasure

    measure = ImageMeasure(
        mask.astype(np.int32),
        pixel_size=pixel_size,
        sampling_interval=sampling_interval * pixel_size,
        equidistant=True,
    )
    rows = []
    for i, label in enumerate(measure.labels):
        points = np.asarray(measure.coordinate(index=i) if region == REGION_MEMBRANE else measure.skeleton(index=i))
        values = _sample_intensity_at_points(intensity_image, points, radius=radius, pixel_size=pixel_size)
        for point_index, ((row, col), value) in enumerate(zip(points, values)):
            rows.append(
                {
                    "label": int(label),
                    "point_index": point_index,
                    "coord_row": float(row),
                    "coord_col": float(col),
                    "intensity": float(value),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _pivot_point_profile(long_df: pd.DataFrame, geometry_features: list[str]) -> pd.DataFrame:
    """Reshapes a long membrane/skeleton table (one row per sampled POINT:
    frame, cell, type, point_index, coord_row, coord_col, intensity) into
    one row per (frame, cell) -- an intensity profile, with one column per
    point_index. coord_row/coord_col are dropped: they're just the sampling
    position, not worth storing once the table's shape already lines up
    point_index N across every row (this matters most with align=True,
    where N is meant to be the same physical spot on the cell every time,
    but the column layout is the same either way)."""
    if long_df.empty:
        return long_df
    id_cols = ["frame", "cell", "type", *geometry_features]
    wide = long_df.pivot(index=id_cols, columns="point_index", values="intensity")
    wide = wide.reindex(sorted(wide.columns), axis=1)
    wide.columns = [str(c) for c in wide.columns]
    return wide.reset_index().sort_values(["cell", "frame"])


def compute_series_measurements(
    db: Session,
    series: ImageSeries,
    channel_index: int,
    region: str,
    pixel_size: float = 1.0,
    sampling_interval: int = 5,
    geometry_features: list[str] | None = None,
    radius: float = 0,
    track: bool = False,
    align: bool = True,
    iou_threshold: float = 0.25,
    max_miss: int = 5,
    neighbor_threshold: float = 50,
) -> pd.DataFrame:
    """The main quantification table for one series: one channel's
    intensity over the selected sub-region of each cell (cytoplasm/
    membrane/skeleton -- see compute_region_intensity), for every cell on
    every frame, with an explicit, opt-in selection of geometry columns
    (from SELECTABLE_GEOMETRY_FEATURES) merged on -- geometry isn't mixed
    in by default, since the table's actual subject is the intensity
    measurement, not geometry (see compute_series_quantification for a
    geometry-only/all-columns table instead).

    One row per (frame, cell). For cytoplasm that's [frame, cell, type,
    *geometry_features, intensity_mean, intensity_max, intensity_min]; for
    membrane/skeleton it's the same identity columns followed by one column
    per sampled point ("0", "1", ... -- see _pivot_point_profile), each
    holding that point's intensity, i.e. the whole profile as one line
    rather than one row per point. Sampled (row, col) positions aren't kept
    -- they're the sampling geometry, not a measurement.

    By default (track=False), "cell" is each frame's own instance number
    (the 1000*semantic+instance label's instance part), not a stable
    identity linked across frames.

    track=True links "cell" across frames instead, via CellMate's IoU
    tracker + CellNetwork (see _compute_tracked_measurements) -- the same
    primitives compute_tracking/compute_series_quantification use, but
    consumed through CellNetwork so a cell's coordinates/skeleton over its
    tracked lifetime are available directly (CellNetwork.coords_overtime /
    skeleton_overtime) instead of being re-derived frame by frame. When
    align=True (the default, membrane/skeleton only), those per-point
    profiles are additionally reoriented/resampled so point_index N is
    roughly the same physical location on the cell in every frame (see
    CellNetwork.aligned_coords_overtime / aligned_skeleton_overtime) --
    align=False gives raw, unregistered per-frame points instead.

    `radius` (membrane/skeleton only) reads each point as the mean over a
    disk rather than the single nearest pixel -- a steadier signal, matching
    test.ipynb's intensities_around_points. It's a physical distance (the
    same unit as pixel_size, e.g. um), converted to pixels internally, so
    the actual ROI size doesn't silently change with a series' resolution.
    0 (the default) keeps the single-pixel read."""
    geometry_features = geometry_features or []
    unknown = set(geometry_features) - set(SELECTABLE_GEOMETRY_FEATURES)
    if unknown:
        raise ValueError(f"Unknown geometry feature(s): {sorted(unknown)}")

    if track:
        return _compute_tracked_measurements(
            db,
            series,
            channel_index,
            region,
            pixel_size=pixel_size,
            sampling_interval=sampling_interval,
            geometry_features=geometry_features,
            radius=radius,
            align=align,
            iou_threshold=iou_threshold,
            max_miss=max_miss,
            neighbor_threshold=neighbor_threshold,
        )

    rows = []
    for frame_index in range(series.frame_count):
        mask = frame_mask(db, series, frame_index)
        if not np.any(mask):
            continue
        channel_frame = image_io.read_frame(
            series.source_type, series.path, frame_index, channel_index
        ).astype(np.float32)
        inten = compute_region_intensity(
            mask, channel_frame, region, pixel_size=pixel_size, sampling_interval=sampling_interval, radius=radius
        )
        if inten.empty:
            continue

        # "type" is always attached as an identity column (cheap, useful
        # for filtering) regardless of whether any geometry_features were
        # selected; the selected ones (if any) come along with it.
        geom = compute_geometry(mask, pixel_size=pixel_size, sampling_interval=sampling_interval)
        merged = inten.merge(geom[["label", "type", *geometry_features]], on="label", how="left")
        merged.insert(0, "cell", merged["label"] % 1000)
        merged.insert(0, "frame", frame_index)
        merged = merged.drop(columns=["label"])
        rows.append(merged)

    if not rows:
        return pd.DataFrame()
    result = pd.concat(rows, ignore_index=True)

    if region == REGION_CYTOPLASM:
        ordered = ["frame", "cell", "type", *geometry_features, "intensity_mean", "intensity_max", "intensity_min"]
        return result[[c for c in ordered if c in result.columns]].sort_values(["cell", "frame"])

    return _pivot_point_profile(result, geometry_features)


def _compute_tracked_measurements(
    db: Session,
    series: ImageSeries,
    channel_index: int,
    region: str,
    pixel_size: float,
    sampling_interval: int,
    geometry_features: list[str],
    radius: float,
    align: bool,
    iou_threshold: float,
    max_miss: int,
    neighbor_threshold: float,
) -> pd.DataFrame:
    """The track=True path of compute_series_measurements -- see there for
    the parameter/column contract. Runs CellMate's tracker once for the
    whole series, wraps the result in a CellNetwork, and samples intensity
    per tracked cell over its own lifetime rather than per independent
    frame."""
    masks = [frame_mask(db, series, f) for f in range(series.frame_count)]
    mask_stack = (
        np.stack(masks, axis=0)
        if masks
        else np.zeros((0, series.height, series.width), dtype=np.uint16)
    )
    if mask_stack.shape[0] == 0 or not mask_stack.any():
        return pd.DataFrame()

    _ensure_cellmate_on_path()
    from cellmate.mating import CellNetwork
    from cellmate.tracking._iou_tracker import Tracker

    tracker = Tracker(
        mask_stack.astype(np.int32), threshold=iou_threshold, min_hist=1, max_miss=max_miss
    )
    tracker()
    tracked_image = tracker.to_image().astype(np.int32)
    cellnet = CellNetwork(
        image=tracked_image,
        time_network=tracker.network,
        tracker=tracker.save_trackers(),
        threshold=neighbor_threshold,
    )

    channel_cache: dict[int, np.ndarray] = {}

    def channel_frame(time: int) -> np.ndarray:
        if time not in channel_cache:
            channel_cache[time] = image_io.read_frame(
                series.source_type, series.path, time, channel_index
            ).astype(np.float32)
        return channel_cache[time]

    rows = []
    for cell_id, cell in cellnet.cells.items():
        frames = [int(t) for t in cell.frames]
        if not frames:
            continue

        if region == REGION_CYTOPLASM:
            for time in frames:
                cell_label_t = cellnet.label_map[time][cell_id]
                cell_mask = tracked_image[time] == cell_label_t
                if not cell_mask.any():
                    continue
                values = channel_frame(time)[cell_mask]
                rows.append(
                    {
                        "frame": time,
                        "cell": cell_id,
                        "intensity_mean": float(values.mean()),
                        "intensity_max": float(values.max()),
                        "intensity_min": float(values.min()),
                    }
                )
            continue

        if align:
            points_overtime = (
                cellnet.aligned_coords_overtime(cell_id)
                if region == REGION_MEMBRANE
                else cellnet.aligned_skeleton_overtime(cell_id)
            )
        else:
            points_overtime = (
                cellnet.coords_overtime(cell_id)
                if region == REGION_MEMBRANE
                else cellnet.skeleton_overtime(cell_id)
            )
        for i, time in enumerate(frames):
            points = np.asarray(points_overtime[i])
            values = _sample_intensity_at_points(channel_frame(time), points, radius=radius, pixel_size=pixel_size)
            for point_index, ((row, col), value) in enumerate(zip(points, values)):
                rows.append(
                    {
                        "frame": time,
                        "cell": cell_id,
                        "point_index": point_index,
                        "coord_row": float(row),
                        "coord_col": float(col),
                        "intensity": float(value),
                    }
                )

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)

    # "type" is always attached as an identity column, the same as the
    # untracked path -- computed per unique frame (cheap relative to the
    # tracking itself) rather than re-deriving it from CellNetwork's
    # mating-oriented per-cell state.
    geom_frames = []
    for time in sorted(result["frame"].unique()):
        geom = compute_geometry(
            tracked_image[time], pixel_size=pixel_size, sampling_interval=sampling_interval
        )
        geom = geom.copy()
        geom["frame"] = time
        geom["cell"] = geom["label"] % 1000
        geom_frames.append(geom)
    geom_all = pd.concat(geom_frames, ignore_index=True)
    result = result.merge(geom_all[["frame", "cell", "type", *geometry_features]], on=["frame", "cell"], how="left")

    if region == REGION_CYTOPLASM:
        ordered = ["frame", "cell", "type", *geometry_features, "intensity_mean", "intensity_max", "intensity_min"]
        return result[[c for c in ordered if c in result.columns]].sort_values(["cell", "frame"])

    return _pivot_point_profile(result, geometry_features)


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
