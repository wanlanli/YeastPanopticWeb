import Konva from 'konva';
import { Circle, Line } from 'react-konva';
import type { PolygonAnnotation } from '../../api/types';
import { classFromLabel, hexToRgba, strokeAndFillForClass } from './colorByClass';

interface Props {
  polygon: PolygonAnnotation;
  isSelected: boolean;
  scale: number;
  /** false when a different tool (draw, point-prompt) is active: this
   * polygon must not intercept clicks then, so they pass through to the
   * stage/new-shape-in-progress underneath instead of being swallowed here */
  interactive: boolean;
  /** true once a reshape-between-anchors is in progress on this polygon */
  reshaping: boolean;
  /** false while a cut/reshape or candidate pick is in progress (on any
   * polygon), so hovering elsewhere can't switch selection mid-edit */
  hoverSelectEnabled: boolean;
  onSelect: () => void;
  /** called continuously while dragging, for smooth local feedback */
  onChangePoints: (points: [number, number][]) => void;
  /** called once an edit is finished (drag end, insert, delete) — persist to backend here */
  onCommitPoints: (points: [number, number][]) => void;
  /** shift+click on a vertex starts a reshape; while reshaping, a plain click
   * on any vertex ends it there (see the `reshaping` gate in this component) */
  onVertexClick: (index: number) => void;
  /** while reshaping, a click on this polygon's own fill/edge adds a cut
   * point there (Konva routes the click here rather than bubbling it to the
   * stage, so this polygon has to forward it) */
  onReshapeClick: (point: [number, number]) => void;
}

// Fallback stroke color for polygons with no numeric (class) label -- the
// hue never changes on selection, only the fill's opacity does (see `colors`
// below), so a polygon's color always identifies its class/source.
const SOURCE_STROKE: Record<PolygonAnnotation['source'], string> = {
  manual: '#3dd6a8',
  model: '#f2b84b',
};
const SELECTED_FILL_ALPHA = 0.4;
const UNSELECTED_FILL_ALPHA = 0.18;

export function PolygonLayer({
  polygon,
  isSelected,
  scale,
  interactive,
  reshaping,
  hoverSelectEnabled,
  onSelect,
  onChangePoints,
  onCommitPoints,
  onVertexClick,
  onReshapeClick,
}: Props) {
  const classId = classFromLabel(polygon.label);
  const fillAlpha = isSelected ? SELECTED_FILL_ALPHA : UNSELECTED_FILL_ALPHA;
  const colors =
    classId !== null
      ? strokeAndFillForClass(classId, fillAlpha)
      : { stroke: SOURCE_STROKE[polygon.source], fill: hexToRgba(SOURCE_STROKE[polygon.source], fillAlpha) };
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

  function handlePolygonClick(e: Konva.KonvaEventObject<MouseEvent>) {
    onSelect();
    if (!reshaping) return; // plain clicks on the fill/edge don't insert points -- too easy to miss-click
    const stage = e.target.getStage();
    const group = e.target.getParent();
    if (!stage || !group) return;
    const pos = group.getRelativePointerPosition();
    if (!pos) return;
    // a cut is in progress on this polygon: this click adds a cut point --
    // clicks inside the fill must reach this handler too, since Konva routes
    // them here instead of bubbling to the stage
    onReshapeClick([pos.x, pos.y]);
  }

  return (
    <>
      <Line
        points={flatPoints}
        closed
        stroke={colors.stroke}
        fill={colors.fill}
        strokeWidth={2 / scale}
        listening={interactive}
        onClick={handlePolygonClick}
        onTap={onSelect}
        onMouseEnter={() => {
          if (hoverSelectEnabled && !isSelected) onSelect();
        }}
      />
      {interactive &&
        isSelected &&
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
            onClick={(e) => {
              if (e.evt.altKey) {
                deleteVertex(i);
                return;
              }
              // shift+click starts a reshape (cut); once one's in progress, a
              // plain click on any vertex (including the start one, to cancel) ends it
              if (reshaping || e.evt.shiftKey) onVertexClick(i);
            }}
            onDblClick={() => deleteVertex(i)}
            onDblTap={() => deleteVertex(i)}
          />
        ))}
    </>
  );
}
