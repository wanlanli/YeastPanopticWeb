from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ComputeQuantificationRequest(BaseModel):
    series_id: int
    pixel_size: float = 1.0
    sampling_interval: int = 5
    fill_gaps: bool = False


class RegionIntensityRequest(BaseModel):
    series_id: int
    channel_index: int
    # cytoplasm = whole cell area, membrane = CellMate's sampled contour
    # points (outline), skeleton = CellMate's sampled centerline points
    region: str
    pixel_size: float = 1.0
    sampling_interval: int = 5
    # opt-in geometry columns to merge onto the result (see
    # quantification_compute.SELECTABLE_GEOMETRY_FEATURES) -- none by
    # default, geometry isn't mixed in unless asked for
    geometry_features: list[str] = []
    # membrane/skeleton only: read each sampled point as the mean over a
    # disk instead of the single nearest pixel -- 0 (the default) keeps the
    # single-pixel read. A physical distance, same unit as pixel_size (e.g.
    # um), not a pixel count -- converted internally so the actual ROI size
    # stays the same regardless of a series' resolution
    radius: float = 0
    # link "cell" across frames via CellMate's tracker + CellNetwork instead
    # of using each frame's own instance number -- off by default, matching
    # this endpoint's original untracked behavior
    track: bool = False
    # membrane/skeleton only, and only when track=True: reorient/resample
    # each frame's points so point_index N is the same physical location on
    # the cell across time (see CellNetwork.aligned_coords_overtime /
    # aligned_skeleton_overtime); ignored otherwise
    align: bool = True
    iou_threshold: float = 0.25
    max_miss: int = 5
    neighbor_threshold: float = 50


class QuantificationDatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    series_id: int | None = None
    name: str
    kind: str
    uploaded_at: datetime


class FeatureTablePage(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    total: int


class TrackingTree(BaseModel):
    # list of node dicts: {id, parent_id, frame_start, frame_end, label, ...}
    nodes: list[dict[str, Any]]


class FrameMeasureResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]


class SeriesTrackingMap(BaseModel):
    dataset_id: int | None
    # {frame_index (str) -> {original_polygon_label (str) -> track_id}}
    frame_track_map: dict[str, dict[str, int]]


class TsneResult(BaseModel):
    ids: list[Any]
    x: list[float]
    y: list[float]
    color_by: str | None = None
    color_values: list[Any] | None = None
