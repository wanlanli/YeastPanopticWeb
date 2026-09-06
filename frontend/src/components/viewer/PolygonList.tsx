import { useState } from 'react';
import { api } from '../../api/client';
import type { PolygonAnnotation } from '../../api/types';
import { useViewerStore } from '../../store/useViewerStore';
import { classFromLabel, colorForClass } from './colorByClass';
import './PolygonList.css';

const SOURCE_COLOR: Record<PolygonAnnotation['source'], string> = {
  manual: '#3dd6a8',
  model: '#f2b84b',
};

function swatchColor(p: PolygonAnnotation): string {
  const classId = classFromLabel(p.label);
  return classId !== null ? colorForClass(classId) : SOURCE_COLOR[p.source];
}

function sortKey(p: PolygonAnnotation): number {
  const n = Number(p.label);
  return Number.isNaN(n) ? p.id + 1e9 : n;
}

export function PolygonList() {
  const polygons = useViewerStore((s) => s.polygons);
  const selectedPolygonId = useViewerStore((s) => s.selectedPolygonId);
  const selectPolygon = useViewerStore((s) => s.selectPolygon);
  const upsertPolygon = useViewerStore((s) => s.upsertPolygon);
  const removePolygon = useViewerStore((s) => s.removePolygon);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState('');

  const sorted = [...polygons].sort((a, b) => sortKey(a) - sortKey(b));
  const classes = Array.from(
    new Set(polygons.map((p) => classFromLabel(p.label)).filter((c): c is number => c !== null)),
  ).sort((a, b) => a - b);

  function handleSelect(p: PolygonAnnotation) {
    selectPolygon(p.id);
  }

  function startEditing(p: PolygonAnnotation) {
    setEditingId(p.id);
    setEditValue(p.label);
  }

  async function commitEdit(p: PolygonAnnotation) {
    setEditingId(null);
    if (editValue === p.label) return;
    const updated = await api.updatePolygon(p.id, { label: editValue });
    upsertPolygon(updated);
  }

  async function handleDelete(p: PolygonAnnotation, e: React.MouseEvent) {
    e.stopPropagation();
    await api.deletePolygon(p.id);
    removePolygon(p.id);
  }

  return (
    <div className="polygon-list">
      <div className="polygon-list-header">
        Polygons <span className="polygon-list-count">{polygons.length}</span>
      </div>
      {classes.length > 0 && (
        <div className="polygon-class-legend">
          {classes.map((c) => (
            <span key={c} className="polygon-class-legend-item">
              <span className="polygon-swatch" style={{ background: colorForClass(c) }} />
              class {c}
            </span>
          ))}
        </div>
      )}
      <ul className="polygon-list-items">
        {sorted.map((p) => (
          <li
            key={p.id}
            className={p.id === selectedPolygonId ? 'selected' : ''}
            onClick={() => handleSelect(p)}
          >
            <span className="polygon-swatch" style={{ background: swatchColor(p) }} />
            {editingId === p.id ? (
              <input
                autoFocus
                className="polygon-label-input"
                value={editValue}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => setEditValue(e.target.value)}
                onBlur={() => commitEdit(p)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                  if (e.key === 'Escape') setEditingId(null);
                }}
              />
            ) : (
              <span
                className="polygon-label"
                onDoubleClick={(e) => {
                  e.stopPropagation();
                  startEditing(p);
                }}
                title="Double-click to rename"
              >
                {p.label || `#${p.id}`}
              </span>
            )}
            <button
              className="polygon-delete-btn"
              onClick={(e) => handleDelete(p, e)}
              title="Delete polygon"
            >
              ×
            </button>
          </li>
        ))}
        {polygons.length === 0 && <li className="polygon-list-empty">No polygons on this frame</li>}
      </ul>
    </div>
  );
}
