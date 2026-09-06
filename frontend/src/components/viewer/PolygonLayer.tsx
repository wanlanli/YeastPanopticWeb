import Konva from 'konva';
import { Circle, Line } from 'react-konva';
import type { PolygonAnnotation } from '../../api/types';
import { classFromLabel, strokeAndFillForClass } from './colorByClass';

interface Props {
  polygon: PolygonAnnotation;
  isSelected: boolean;
  scale: number;
  onSelect: () => void;
  /** called continuously while dragging, for smooth local feedback */
  onChangePoints: (points: [number, number][]) => void;
  /** called once an edit is finished (drag end, insert, delete) — persist to backend here */
  onCommitPoints: (points: [number, number][]) => void;
}

const COLORS = {
  manual: { stroke: '#3dd6a8', fill: 'rgba(61,214,168,0.15)' },
  model: { stroke: '#f2b84b', fill: 'rgba(242,184,75,0.15)' },
  selected: { stroke: '#ff5c7c', fill: 'rgba(255,92,124,0.2)' },
};

function distanceToSegment(
  p: [number, number],
  a: [number, number],
  b: [number, number],
): { dist: number; point: [number, number] } {
  const [px, py] = p;
  const [ax, ay] = a;
  const [bx, by] = b;
  const dx = bx - ax;
  const dy = by - ay;
  const lenSq = dx * dx + dy * dy || 1;
  let t = ((px - ax) * dx + (py - ay) * dy) / lenSq;
  t = Math.max(0, Math.min(1, t));
  const point: [number, number] = [ax + t * dx, ay + t * dy];
  const dist = Math.hypot(px - point[0], py - point[1]);
  return { dist, point };
}

export function PolygonLayer({
  polygon,
  isSelected,
  scale,
  onSelect,
  onChangePoints,
  onCommitPoints,
}: Props) {
  const classId = classFromLabel(polygon.label);
  const baseColors =
    classId !== null ? strokeAndFillForClass(classId) : (COLORS[polygon.source] ?? COLORS.manual);
  const colors = isSelected ? COLORS.selected : baseColors;
  const flatPoints = polygon.points.flat();
  const handleRadius = 4 / scale;

  function moveVertex(index: number, x: number, y: number) {
    const next = polygon.points.map((p, i) => (i === index ? ([x, y] as [number, number]) : p));
    onChangePoints(next);
  }

  function deleteVertex(index: number) {
    if (polygon.points.length <= 3) return;
    const next = polygon.points.filter((_, i) => i !== index);
    onChangePoints(next);
    onCommitPoints(next);
  }

  function insertVertexOnClick(e: Konva.KonvaEventObject<MouseEvent>) {
    onSelect();
    if (!isSelected) return; // first click selects; second click (while selected) inserts
    const stage = e.target.getStage();
    const group = e.target.getParent();
    if (!stage || !group) return;
    const pos = group.getRelativePointerPosition();
    if (!pos) return;
    const clicked: [number, number] = [pos.x, pos.y];

    let bestIdx = 0;
    let bestDist = Infinity;
    for (let i = 0; i < polygon.points.length; i++) {
      const a = polygon.points[i];
      const b = polygon.points[(i + 1) % polygon.points.length];
      const { dist } = distanceToSegment(clicked, a, b);
      if (dist < bestDist) {
        bestDist = dist;
        bestIdx = i;
      }
    }
    const next = [...polygon.points];
    next.splice(bestIdx + 1, 0, clicked);
    onChangePoints(next);
    onCommitPoints(next);
  }

  return (
    <>
      <Line
        points={flatPoints}
        closed
        stroke={colors.stroke}
        fill={colors.fill}
        strokeWidth={2 / scale}
        onClick={insertVertexOnClick}
        onTap={onSelect}
      />
      {isSelected &&
        polygon.points.map(([x, y], i) => (
          <Circle
            key={i}
            x={x}
            y={y}
            radius={handleRadius}
            fill="#fff"
            stroke={colors.stroke}
            strokeWidth={1.5 / scale}
            draggable
            onDragMove={(e) => moveVertex(i, e.target.x(), e.target.y())}
            onDragEnd={() => onCommitPoints(polygon.points)}
            onDblClick={() => deleteVertex(i)}
            onDblTap={() => deleteVertex(i)}
          />
        ))}
    </>
  );
}
