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
  const selectedPolygonId = useViewerStore((s) => s.selectedPolygonId);
  const removePolygon = useViewerStore((s) => s.removePolygon);

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
    </div>
  );
}
