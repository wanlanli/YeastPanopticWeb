import { create } from 'zustand';
import type { PolygonAnnotation, Series } from '../api/types';

export type Tool = 'select' | 'draw' | 'point-prompt';

interface ViewerState {
  series: Series | null;
  frameIndex: number;
  vmin: number | null;
  vmax: number | null;
  tool: Tool;
  polygons: PolygonAnnotation[];
  selectedPolygonId: number | null;
  isPlaying: boolean;

  setSeries: (series: Series | null) => void;
  setFrameIndex: (index: number) => void;
  setContrast: (vmin: number | null, vmax: number | null) => void;
  setTool: (tool: Tool) => void;
  setPolygons: (polygons: PolygonAnnotation[]) => void;
  upsertPolygon: (polygon: PolygonAnnotation) => void;
  removePolygon: (id: number) => void;
  setSelectedPolygonId: (id: number | null) => void;
  setIsPlaying: (playing: boolean) => void;
}

export const useViewerStore = create<ViewerState>((set) => ({
  series: null,
  frameIndex: 0,
  vmin: null,
  vmax: null,
  tool: 'select',
  polygons: [],
  selectedPolygonId: null,
  isPlaying: false,

  setSeries: (series) => set({ series, frameIndex: 0, polygons: [], selectedPolygonId: null }),
  setFrameIndex: (frameIndex) =>
    set((state) => ({
      frameIndex: state.series
        ? Math.max(0, Math.min(frameIndex, state.series.frame_count - 1))
        : frameIndex,
      selectedPolygonId: null,
    })),
  setContrast: (vmin, vmax) => set({ vmin, vmax }),
  setTool: (tool) => set({ tool, selectedPolygonId: null }),
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
  setIsPlaying: (isPlaying) => set({ isPlaying }),
}));
