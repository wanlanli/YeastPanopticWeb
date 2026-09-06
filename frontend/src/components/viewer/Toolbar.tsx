import { api } from '../../api/client';
import { useViewerStore, type Tool } from '../../store/useViewerStore';
import './Toolbar.css';

const TOOLS: { id: Tool; label: string; hint: string }[] = [
  { id: 'select', label: 'Select / Edit', hint: 'Click a polygon to select it, drag vertices to edit' },
  { id: 'draw', label: 'Draw Polygon', hint: 'Click to add vertices, double-click to close' },
  { id: 'point-prompt', label: 'Point Prompt', hint: 'Click a point to request a mask from the model' },
];

export function Toolbar() {
  const tool = useViewerStore((s) => s.tool);
  const setTool = useViewerStore((s) => s.setTool);
  const series = useViewerStore((s) => s.series);
  const frameIndex = useViewerStore((s) => s.frameIndex);
  const selectedPolygonId = useViewerStore((s) => s.selectedPolygonId);
  const removePolygon = useViewerStore((s) => s.removePolygon);
  const polygons = useViewerStore((s) => s.polygons);
  const setPolygons = useViewerStore((s) => s.setPolygons);

  async function handleClearFrame() {
    if (!series || polygons.length === 0) return;
    if (!window.confirm(`Delete all ${polygons.length} polygon(s) on this frame?`)) return;
    await api.deleteFramePolygons(series.id, frameIndex);
    setPolygons([]);
  }

  async function handleClearMovie() {
    if (!series) return;
    if (
      !window.confirm(
        `Delete ALL polygons across all ${series.frame_count} frames of "${series.name}"? This cannot be undone.`,
      )
    )
      return;
    await api.deleteSeriesPolygons(series.id);
    setPolygons([]);
  }

  return (
    <div className="toolbar">
      {TOOLS.map((t) => (
        <button
          key={t.id}
          className={tool === t.id ? 'active' : ''}
          onClick={() => setTool(t.id)}
          title={t.hint}
        >
          {t.label}
        </button>
      ))}
      <div className="toolbar-spacer" />
      <button
        disabled={selectedPolygonId === null}
        onClick={async () => {
          if (selectedPolygonId === null) return;
          await api.deletePolygon(selectedPolygonId);
          removePolygon(selectedPolygonId);
        }}
        title="Delete selected polygon"
      >
        Delete Selected
      </button>
      {series && (
        <>
          <button
            className="toolbar-danger-btn"
            disabled={polygons.length === 0}
            onClick={handleClearFrame}
            title="Delete all polygons on this frame"
          >
            Clear Frame
          </button>
          <button
            className="toolbar-danger-btn"
            onClick={handleClearMovie}
            title="Delete all polygons across every frame of this series"
          >
            Clear Movie
          </button>
          <a
            className="toolbar-link-btn"
            href={api.frameMaskUrl(series.id, frameIndex)}
            title="Download this frame's polygons rasterized as a label-mask TIFF"
          >
            Export Frame Mask
          </a>
          <a
            className="toolbar-link-btn"
            href={api.seriesMaskUrl(series.id)}
            title="Download every frame's polygons rasterized as a multi-page label-mask TIFF"
          >
            Export Mask Stack
          </a>
        </>
      )}
    </div>
  );
}
