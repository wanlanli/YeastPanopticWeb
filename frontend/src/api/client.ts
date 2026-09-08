import type {
  FeatureTablePage,
  FrameMeasureResult,
  PolygonAnnotation,
  Project,
  QuantificationDataset,
  SegmentSettings,
  Series,
  SeriesTrackingMap,
  TrackingTree,
  TsneResult,
} from './types';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  const contentType = res.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    return res.json() as Promise<T>;
  }
  return undefined as T;
}

export const api = {
  // Projects
  listProjects: () => request<Project[]>('/api/projects'),
  createProject: (name: string) =>
    request<Project>('/api/projects', { method: 'POST', body: JSON.stringify({ name }) }),
  getProject: (id: number) => request<Project>(`/api/projects/${id}`),

  // Series
  listSeries: (projectId: number) =>
    request<Series[]>(`/api/series?project_id=${projectId}`),
  getSeries: (id: number) => request<Series>(`/api/series/${id}`),
  deleteSeries: (id: number) => request<{ ok: boolean }>(`/api/series/${id}`, { method: 'DELETE' }),
  registerSeriesPath: (projectId: number, name: string, path: string) =>
    request<Series>('/api/series/register-path', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, name, path }),
    }),
  uploadSeries: (projectId: number, name: string, files: FileList | File[]) => {
    const form = new FormData();
    form.append('project_id', String(projectId));
    form.append('name', name);
    Array.from(files).forEach((f) => form.append('files', f));
    return request<Series>('/api/series/upload', { method: 'POST', body: form });
  },
  frameUrl: (seriesId: number, frameIndex: number, vmin?: number, vmax?: number, channel?: number) => {
    const params = new URLSearchParams();
    if (vmin !== undefined) params.set('vmin', String(vmin));
    if (vmax !== undefined) params.set('vmax', String(vmax));
    if (channel !== undefined) params.set('channel', String(channel));
    const qs = params.toString();
    return `/api/series/${seriesId}/frame/${frameIndex}${qs ? `?${qs}` : ''}`;
  },
  setSeriesChannel: (seriesId: number, dicChannelIndex: number) =>
    request<Series>(`/api/series/${seriesId}/channel`, {
      method: 'PATCH',
      body: JSON.stringify({ dic_channel_index: dicChannelIndex }),
    }),
  getSeriesTracking: (seriesId: number) =>
    request<SeriesTrackingMap>(`/api/series/${seriesId}/tracking`),
  getFrameNames: (seriesId: number) =>
    request<{ names: string[] | null }>(`/api/series/${seriesId}/frame-names`),
  measureFrame: (seriesId: number, frameIndex: number, pixelSize = 1) =>
    request<FrameMeasureResult>(
      `/api/series/${seriesId}/frame/${frameIndex}/measure?pixel_size=${pixelSize}`,
    ),
  frameMaskUrl: (seriesId: number, frameIndex: number) =>
    `/api/series/${seriesId}/frame/${frameIndex}/mask`,
  seriesMaskUrl: (seriesId: number) => `/api/series/${seriesId}/mask`,

  // Annotations
  listPolygons: (seriesId: number, frameIndex: number) =>
    request<PolygonAnnotation[]>(`/api/series/${seriesId}/frame/${frameIndex}/polygons`),
  /** `classId` (preferred for any brand-new object) lets the backend pick
   * the next unused `1000*classId + instance` label itself, scanned across
   * the whole series -- never colliding with an existing object on another
   * frame, unlike computing it client-side from just the current frame's
   * polygons. Pass an explicit `label` instead only when the caller already
   * knows the exact label it wants (e.g. nothing left that needs this --
   * kept for backward compatibility). */
  createPolygon: (
    seriesId: number,
    frameIndex: number,
    points: [number, number][],
    source: 'manual' | 'model' = 'manual',
    labelOrClassId: { label: string } | { classId: number } = { label: '' },
  ) =>
    request<PolygonAnnotation>(`/api/series/${seriesId}/frame/${frameIndex}/polygons`, {
      method: 'POST',
      body: JSON.stringify({
        points,
        source,
        label: 'label' in labelOrClassId ? labelOrClassId.label : '',
        class_id: 'classId' in labelOrClassId ? labelOrClassId.classId : undefined,
      }),
    }),
  updatePolygon: (
    polygonId: number,
    updates: { points?: [number, number][]; label?: string },
  ) =>
    request<PolygonAnnotation>(`/api/series/polygons/${polygonId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    }),
  deletePolygon: (polygonId: number) =>
    request<{ ok: boolean }>(`/api/series/polygons/${polygonId}`, { method: 'DELETE' }),
  deleteFramePolygons: (seriesId: number, frameIndex: number) =>
    request<{ deleted: number }>(`/api/series/${seriesId}/frame/${frameIndex}/polygons`, {
      method: 'DELETE',
    }),
  deleteSeriesPolygons: (seriesId: number) =>
    request<{ deleted: number }>(`/api/series/${seriesId}/polygons`, { method: 'DELETE' }),
  predictPoint: (
    seriesId: number,
    frameIndex: number,
    points: { x: number; y: number; label: 0 | 1 }[],
  ) =>
    request<{ polygons: [number, number][][] }>(
      `/api/series/${seriesId}/frame/${frameIndex}/predict-point`,
      { method: 'POST', body: JSON.stringify({ points }) },
    ),
  predictFrame: (seriesId: number, frameIndex: number, settings?: SegmentSettings, signal?: AbortSignal) => {
    const params = new URLSearchParams();
    if (settings) {
      params.set('score_threshold', String(settings.scoreThreshold));
      params.set('instance_threshold', String(settings.instanceThreshold));
      params.set('area_threshold', String(settings.areaThreshold));
      params.set('keep_border', String(settings.keepBorderCells));
    }
    const qs = params.toString();
    return request<{
      predictions: { class_id: number; class_name: string; points: [number, number][]; confidence: number }[];
    }>(`/api/series/${seriesId}/frame/${frameIndex}/predict-frame${qs ? `?${qs}` : ''}`, {
      method: 'POST',
      signal,
    });
  },

  // Quantification
  listDatasets: (projectId: number) =>
    request<QuantificationDataset[]>(`/api/quantification?project_id=${projectId}`),
  uploadDataset: (
    projectId: number,
    name: string,
    kind: 'features' | 'tracking',
    file: File,
  ) => {
    const form = new FormData();
    form.append('project_id', String(projectId));
    form.append('name', name);
    form.append('kind', kind);
    form.append('file', file);
    return request<QuantificationDataset>('/api/quantification/upload', {
      method: 'POST',
      body: form,
    });
  },
  getFeatures: (datasetId: number, offset = 0, limit = 200, sortBy?: string, ascending = true) => {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit), ascending: String(ascending) });
    if (sortBy) params.set('sort_by', sortBy);
    return request<FeatureTablePage>(`/api/quantification/${datasetId}/features?${params}`);
  },
  getTracking: (datasetId: number) =>
    request<TrackingTree>(`/api/quantification/${datasetId}/tracking`),
  getTsne: (datasetId: number, perplexity = 30, colorBy?: string) => {
    const params = new URLSearchParams({ perplexity: String(perplexity) });
    if (colorBy) params.set('color_by', colorBy);
    return request<TsneResult>(`/api/quantification/${datasetId}/tsne?${params}`);
  },
  datasetDownloadUrl: (datasetId: number) => `/api/quantification/${datasetId}/download`,
  computeQuantification: (seriesId: number, fillGaps = false, pixelSize = 1) =>
    request<QuantificationDataset[]>('/api/quantification/compute', {
      method: 'POST',
      body: JSON.stringify({ series_id: seriesId, fill_gaps: fillGaps, pixel_size: pixelSize }),
    }),
};
