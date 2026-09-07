import { create } from 'zustand';
import type { PolygonAnnotation, Series, SeriesTrackingMap } from '../api/types';

export type RightPanelTab = 'labels' | 'tracking';

export type Tool = 'select' | 'draw' | 'point-prompt';

export type PolygonAction =
  | { type: 'create'; polygon: PolygonAnnotation }
  | { type: 'createMany'; polygons: PolygonAnnotation[] }
  | {
      type: 'update';
      id: number;
      before: { points: [number, number][]; label: string };
      after: { points: [number, number][]; label: string };
    }
  | { type: 'delete'; polygon: PolygonAnnotation }
  | { type: 'deleteMany'; polygons: PolygonAnnotation[] };

interface ViewerState {
  series: Series | null;
  frameIndex: number;
  /** which imaging channel is currently displayed (view-only; segmentation
   * always uses series.dic_channel_index regardless of this) */
  viewChannel: number;
  vmin: number | null;
  vmax: number | null;
  tool: Tool;
  polygons: PolygonAnnotation[];
  selectedPolygonId: number | null;
  isPlaying: boolean;

  /** points clicked so far for a new polygon (draw tool) -- lifted out of
   * ImageCanvas so the Toolbar's Save button can finish it too */
  draftPoints: [number, number][];
  /** accumulated SAM point-prompt clicks, and the live mask preview they produced */
  promptPoints: { x: number; y: number; label: 0 | 1 }[];
  promptPreview: [number, number][] | null;
  /** class new point-prompt polygons are labeled with (ignored when refining
   * an existing selected polygon -- that keeps its own label) */
  promptClassId: number;

  history: PolygonAction[];
  future: PolygonAction[];
  /** timestamp of the last successful persist (create/update/delete, via
   * the button, Ctrl+S, or auto-save) -- drives the "Saved" confirmation,
   * since most edits (drag a vertex, a cut, a type change) already persist
   * immediately with nothing left to explicitly "Save" */
  lastSavedAt: number | null;
  /** bumped to ask the canvas to re-fit the image to the window, centered,
   * at its initial zoom -- see ContrastControls' "Fit to Window" button */
  resetViewToken: number;

  /** which right-panel tab is showing: the polygon/label list, or the
   * tracking lineage tree (movies only -- see RightPanel) */
  rightPanelTab: RightPanelTab;
  /** the current series' latest computed tracking (frame -> original label
   * -> stable track id), fetched non-destructively -- polygon labels
   * themselves are never rewritten. Null until fetched / if none exists. */
  seriesTracking: SeriesTrackingMap | null;

  setSeries: (series: Series | null) => void;
  setFrameIndex: (index: number) => void;
  setViewChannel: (channel: number) => void;
  setContrast: (vmin: number | null, vmax: number | null) => void;
  setTool: (tool: Tool) => void;
  setPolygons: (polygons: PolygonAnnotation[]) => void;
  upsertPolygon: (polygon: PolygonAnnotation) => void;
  removePolygon: (id: number) => void;
  setSelectedPolygonId: (id: number | null) => void;
  /** select a polygon and switch to the select/edit tool in one atomic update */
  selectPolygon: (id: number) => void;
  setIsPlaying: (playing: boolean) => void;

  setDraftPoints: (points: [number, number][]) => void;
  setPromptPoints: (points: { x: number; y: number; label: 0 | 1 }[]) => void;
  setPromptPreview: (preview: [number, number][] | null) => void;
  setPromptClassId: (classId: number) => void;
  clearDrafts: () => void;

  pushAction: (action: PolygonAction) => void;
  popUndo: () => PolygonAction | undefined;
  popRedo: () => PolygonAction | undefined;
  replaceTopFuture: (action: PolygonAction) => void;
  replaceTopHistory: (action: PolygonAction) => void;
  clearHistory: () => void;
  markSaved: () => void;
  requestResetView: () => void;
  setRightPanelTab: (tab: RightPanelTab) => void;
  setSeriesTracking: (tracking: SeriesTrackingMap | null) => void;
}

export const useViewerStore = create<ViewerState>((set, get) => ({
  series: null,
  frameIndex: 0,
  viewChannel: 0,
  vmin: null,
  vmax: null,
  tool: 'select',
  polygons: [],
  selectedPolygonId: null,
  isPlaying: false,

  draftPoints: [],
  promptPoints: [],
  promptPreview: null,
  promptClassId: 1, // default: class 1 (cell)

  history: [],
  future: [],
  lastSavedAt: null,
  resetViewToken: 0,
  rightPanelTab: 'labels',
  seriesTracking: null,

  setSeries: (series) =>
    set({
      series,
      frameIndex: 0,
      viewChannel: series?.dic_channel_index ?? 0,
      polygons: [],
      selectedPolygonId: null,
      history: [],
      future: [],
      seriesTracking: null,
      rightPanelTab: 'labels',
    }),
  setFrameIndex: (frameIndex) =>
    set((state) => ({
      frameIndex: state.series
        ? Math.max(0, Math.min(frameIndex, state.series.frame_count - 1))
        : frameIndex,
      selectedPolygonId: null,
      history: [],
      future: [],
    })),
  setViewChannel: (viewChannel) => set({ viewChannel }),
  setContrast: (vmin, vmax) => set({ vmin, vmax }),
  setTool: (tool) =>
    set((state) => ({
      tool,
      // Entering point-prompt keeps whatever was selected -- that polygon
      // becomes the refine target (its shape gets replaced on finish
      // instead of creating a new polygon). Any other tool clears it.
      selectedPolygonId: tool === 'point-prompt' ? state.selectedPolygonId : null,
    })),
  setPolygons: (polygons) => set({ polygons }),
  upsertPolygon: (polygon) =>
    set((state) => {
      const idx = state.polygons.findIndex((p) => p.id === polygon.id);
      if (idx === -1) return { polygons: [...state.polygons, polygon] };
      const next = [...state.polygons];
      next[idx] = polygon;
      return { polygons: next };
    }),
  removePolygon: (id) =>
    set((state) => ({
      polygons: state.polygons.filter((p) => p.id !== id),
      selectedPolygonId: state.selectedPolygonId === id ? null : state.selectedPolygonId,
    })),
  setSelectedPolygonId: (selectedPolygonId) => set({ selectedPolygonId }),
  selectPolygon: (id) => set({ tool: 'select', selectedPolygonId: id }),
  setIsPlaying: (isPlaying) => set({ isPlaying }),

  setDraftPoints: (draftPoints) => set({ draftPoints }),
  setPromptPoints: (promptPoints) => set({ promptPoints }),
  setPromptPreview: (promptPreview) => set({ promptPreview }),
  setPromptClassId: (promptClassId) => set({ promptClassId }),
  clearDrafts: () => set({ draftPoints: [], promptPoints: [], promptPreview: null }),

  pushAction: (action) =>
    set((state) => ({ history: [...state.history, action], future: [], lastSavedAt: Date.now() })),
  popUndo: () => {
    const { history } = get();
    if (history.length === 0) return undefined;
    const action = history[history.length - 1];
    set((state) => ({ history: state.history.slice(0, -1), future: [...state.future, action] }));
    return action;
  },
  popRedo: () => {
    const { future } = get();
    if (future.length === 0) return undefined;
    const action = future[future.length - 1];
    set((state) => ({ future: state.future.slice(0, -1), history: [...state.history, action] }));
    return action;
  },
  replaceTopFuture: (action) => set((state) => ({ future: [...state.future.slice(0, -1), action] })),
  replaceTopHistory: (action) => set((state) => ({ history: [...state.history.slice(0, -1), action] })),
  clearHistory: () => set({ history: [], future: [] }),
  markSaved: () => set({ lastSavedAt: Date.now() }),
  requestResetView: () => set((state) => ({ resetViewToken: state.resetViewToken + 1 })),
  setRightPanelTab: (rightPanelTab) => set({ rightPanelTab }),
  setSeriesTracking: (seriesTracking) => set({ seriesTracking }),
}));
