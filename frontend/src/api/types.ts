export interface Project {
  id: number;
  name: string;
  created_at: string;
  /** the permanent, world-readable demo project -- not owned by anyone */
  is_sample: boolean;
  /** an anonymous visitor's ephemeral project, deleted after a few hours */
  is_sandbox: boolean;
}

export interface User {
  id: number;
  email: string;
  created_at: string;
}

/** Auto-segment (panoptic model) filtering knobs -- see the "Advanced
 * Settings" panel next to Auto-Segment Frame / Segment All Frames. */
export interface SegmentSettings {
  scoreThreshold: number;
  instanceThreshold: number;
  areaThreshold: number;
  /** smoothing: max internal-hole area (px) the model fills in per mask */
  holeAreaThreshold: number;
  keepBorderCells: boolean;
}

/** One instance detected by auto-segment, before it's accepted into the
 * database as a Polygon -- see predictFrame/refineFrame/acceptPredictions. */
export interface FramePrediction {
  class_id: number;
  class_name: string;
  points: [number, number][];
  confidence: number;
}

/** predictFrame/refineFrame's response: a *preview*, not yet persisted --
 * see acceptPredictions. `result_id` is null when the active model has no
 * server-side cache to refine from (predictFrame must be called again on
 * every settings change in that case; the frontend doesn't need to know
 * why -- refineFrame transparently falls back to it on the backend). */
export interface FramePredictResult {
  result_id: string | null;
  predictions: FramePrediction[];
}

export interface Series {
  id: number;
  project_id: number;
  name: string;
  source_type: 'folder' | 'multipage_tiff' | 'upload';
  frame_count: number;
  width: number;
  height: number;
  dtype: string;
  channels: number;
  /** number of imaging channels (e.g. DIC/GFP/...), distinct from `channels`
   * above which is per-pixel (RGB etc) */
  channel_count: number;
  channel_names: string[] | null;
  /** which channel segmentation models read; null if not yet chosen */
  dic_channel_index: number | null;
  /** real source filename, for a series backed by one file; null for a
   * folder/upload of many files (see api.getFrameNames for those) */
  original_filename: string | null;
}

export interface PolygonAnnotation {
  id: number;
  series_id: number;
  frame_index: number;
  points: [number, number][];
  label: string;
  source: 'manual' | 'model';
  updated_at: string;
}

export interface FrameMeasureResult {
  columns: string[];
  rows: Record<string, unknown>[];
}

/** Which part of the cell to measure a channel's intensity from -- see
 * RegionDemo for the visual explanation of each. */
export type MeasurementRegion = 'cytoplasm' | 'membrane' | 'skeleton';

export interface SeriesTrackingMap {
  dataset_id: number | null;
  /** {frame_index (string) -> {original_polygon_label (string) -> track_id}} */
  frame_track_map: Record<string, Record<string, number>>;
}

export interface QuantificationDataset {
  id: number;
  project_id: number;
  series_id: number | null;
  name: string;
  kind: 'features' | 'tracking';
  uploaded_at: string;
}

export interface FeatureTablePage {
  columns: string[];
  rows: Record<string, unknown>[];
  total: number;
}

export interface TrackingNode {
  id: number | string;
  parent_id: number | string | null;
  [key: string]: unknown;
}

export interface TrackingTree {
  nodes: TrackingNode[];
}

export interface TsneResult {
  ids: (number | string)[];
  x: number[];
  y: number[];
  color_by: string | null;
  color_values: unknown[] | null;
}
