import Konva from 'konva';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Circle, Group, Image as KonvaImage, Layer, Line, Stage } from 'react-konva';
import { api } from '../../api/client';
import { useViewerStore } from '../../store/useViewerStore';
import { PolygonLayer } from './PolygonLayer';
import { useHtmlImage } from './useHtmlImage';
import './ImageCanvas.css';

export function ImageCanvas() {
  const series = useViewerStore((s) => s.series);
  const frameIndex = useViewerStore((s) => s.frameIndex);
  const vmin = useViewerStore((s) => s.vmin);
  const vmax = useViewerStore((s) => s.vmax);
  const tool = useViewerStore((s) => s.tool);
  const polygons = useViewerStore((s) => s.polygons);
  const setPolygons = useViewerStore((s) => s.setPolygons);
  const upsertPolygon = useViewerStore((s) => s.upsertPolygon);
  const selectedPolygonId = useViewerStore((s) => s.selectedPolygonId);
  const setSelectedPolygonId = useViewerStore((s) => s.setSelectedPolygonId);

  const containerRef = useRef<HTMLDivElement>(null);
  const groupRef = useRef<Konva.Group>(null);
  const [size, setSize] = useState({ width: 800, height: 600 });
  const [transform, setTransform] = useState({ scale: 1, x: 0, y: 0 });
  const [draftPoints, setDraftPoints] = useState<[number, number][]>([]);
  const [isPredicting, setIsPredicting] = useState(false);

  const imageUrl = series
    ? api.frameUrl(series.id, frameIndex, vmin ?? undefined, vmax ?? undefined)
    : null;
  const image = useHtmlImage(imageUrl);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!series || size.width === 0) return;
    const scale = Math.min(size.width / series.width, size.height / series.height, 1) || 1;
    setTransform({
      scale,
      x: (size.width - series.width * scale) / 2,
      y: (size.height - series.height * scale) / 2,
    });
    // Refit only when the series (or the viewport) changes, not on every frame flip.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series?.id, size.width, size.height]);

  useEffect(() => {
    if (!series) return;
    let cancelled = false;
    api.listPolygons(series.id, frameIndex).then((data) => {
      if (!cancelled) setPolygons(data);
    });
    setDraftPoints([]);
    return () => {
      cancelled = true;
    };
  }, [series?.id, frameIndex, setPolygons]);

  useEffect(() => {
    if (tool !== 'draw') setDraftPoints([]);
  }, [tool]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (tool !== 'draw') return;
      if (e.key === 'Enter') finishDraft();
      if (e.key === 'Escape') setDraftPoints([]);
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tool, draftPoints, series, frameIndex]);

  function handleWheel(e: Konva.KonvaEventObject<WheelEvent>) {
    e.evt.preventDefault();
    const stage = e.target.getStage();
    const pointer = stage?.getPointerPosition();
    if (!stage || !pointer) return;

    const scaleBy = 1.05;
    const oldScale = transform.scale;
    const direction = e.evt.deltaY > 0 ? -1 : 1;
    const newScale = direction > 0 ? oldScale / scaleBy : oldScale * scaleBy;
    const clamped = Math.max(0.05, Math.min(newScale, 20));

    const mousePointTo = {
      x: (pointer.x - transform.x) / oldScale,
      y: (pointer.y - transform.y) / oldScale,
    };
    setTransform({
      scale: clamped,
      x: pointer.x - mousePointTo.x * clamped,
      y: pointer.y - mousePointTo.y * clamped,
    });
  }

  const getImagePoint = useCallback((): [number, number] | null => {
    const pos = groupRef.current?.getRelativePointerPosition();
    return pos ? [pos.x, pos.y] : null;
  }, []);

  async function finishDraft() {
    if (!series || draftPoints.length < 3) {
      setDraftPoints([]);
      return;
    }
    const created = await api.createPolygon(series.id, frameIndex, draftPoints, 'manual');
    upsertPolygon(created);
    setDraftPoints([]);
  }

  async function handleStageClick(e: Konva.KonvaEventObject<MouseEvent>) {
    const stage = e.target.getStage();
    const clickedOnEmpty = e.target === stage || e.target.className === 'Image';
    if (!clickedOnEmpty) return; // a polygon/vertex handled its own click

    if (tool === 'select') {
      setSelectedPolygonId(null);
      return;
    }
    if (!series) return;
    const pt = getImagePoint();
    if (!pt) return;

    if (tool === 'draw') {
      setDraftPoints((prev) => [...prev, pt]);
      return;
    }

    if (tool === 'point-prompt') {
      setIsPredicting(true);
      try {
        const result = await api.predictPoint(series.id, frameIndex, pt[0], pt[1]);
        for (const poly of result.polygons) {
          const created = await api.createPolygon(series.id, frameIndex, poly, 'model');
          upsertPolygon(created);
        }
      } finally {
        setIsPredicting(false);
      }
    }
  }

  async function commitPolygon(id: number, points: [number, number][]) {
    const updated = await api.updatePolygon(id, points);
    upsertPolygon(updated);
  }

  function localChange(id: number, points: [number, number][]) {
    const existing = polygons.find((p) => p.id === id);
    if (existing) upsertPolygon({ ...existing, points });
  }

  if (!series) {
    return (
      <div className="image-canvas-empty" ref={containerRef}>
        Select or add an image series to begin.
      </div>
    );
  }

  return (
    <div className="image-canvas-container" ref={containerRef}>
      {isPredicting && <div className="predicting-badge">Predicting mask…</div>}
      <Stage
        width={size.width}
        height={size.height}
        onWheel={handleWheel}
        onClick={handleStageClick}
        onDblClick={tool === 'draw' ? finishDraft : undefined}
        style={{ cursor: tool === 'select' ? 'default' : 'crosshair' }}
      >
        <Layer>
          <Group
            ref={groupRef}
            x={transform.x}
            y={transform.y}
            scaleX={transform.scale}
            scaleY={transform.scale}
          >
            {image && <KonvaImage image={image} width={series.width} height={series.height} />}

            {polygons.map((poly) => (
              <PolygonLayer
                key={poly.id}
                polygon={poly}
                isSelected={selectedPolygonId === poly.id}
                scale={transform.scale}
                onSelect={() => tool === 'select' && setSelectedPolygonId(poly.id)}
                onChangePoints={(pts) => localChange(poly.id, pts)}
                onCommitPoints={(pts) => commitPolygon(poly.id, pts)}
              />
            ))}

            {draftPoints.length > 0 && (
              <>
                <Line
                  points={draftPoints.flat()}
                  stroke="#3d63dd"
                  strokeWidth={2 / transform.scale}
                  dash={[6 / transform.scale, 4 / transform.scale]}
                />
                {draftPoints.map(([x, y], i) => (
                  <Circle key={i} x={x} y={y} radius={4 / transform.scale} fill="#3d63dd" />
                ))}
              </>
            )}
          </Group>
        </Layer>
      </Stage>
    </div>
  );
}
