export interface Project {
  id: number;
  name: string;
  created_at: string;
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

export interface QuantificationDataset {
  id: number;
  project_id: number;
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
