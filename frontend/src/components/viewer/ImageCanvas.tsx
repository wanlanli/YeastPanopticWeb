import Konva from 'konva';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Circle, Group, Image as KonvaImage, Layer, Line, Stage } from 'react-konva';
import { api } from '../../api/client';
import { useViewerStore } from '../../store/useViewerStore';
import { BufferBar } from './BufferBar';
import { CLASS_IDS, classDisplayName, classFromLabel, colorForClass } from './colorByClass';
import './ContextMenu.css';
import { PolygonLayer } from './PolygonLayer';
import { useDraftActions } from './useDraftActions';
import { useHtmlImage } from './useHtmlImage';
import { useUndoRedo } from './useUndoRedo';
import './ImageCanvas.css';

const CLOSE_POLYGON_TOLERANCE_PX = 8; // screen pixels, converted via /scale below
const AUTOSAVE_INTERVAL_MS = 5 * 60 * 1000;

/** Clamp a point to the image bounds -- clicking past the edge while
 * drawing (easy to do once zoomed/panned) lands the vertex on the edge
 * instead of outside the frame. */
function clampToImage(pt: [number, number], width: number, height: number): [number, number] {
  return [Math.min(Math.max(pt[0], 0), width), Math.min(Math.max(pt[1], 0), height)];
}

export function ImageCanvas() {
  const series = useViewerStore((s) => s.series);
  const frameIndex = useViewerStore((s) => s.frameIndex);
  const resetViewToken = useViewerStore((s) => s.resetViewToken);
  const vmin = useViewerStore((s) => s.vmin);
  const vmax = useViewerStore((s) => s.vmax);
  const viewChannel = useViewerStore((s) => s.viewChannel);
  const tool = useViewerStore((s) => s.tool);
  const polygons = useViewerStore((s) => s.polygons);
  const setPolygons = useViewerStore((s) => s.setPolygons);
  const upsertPolygon = useViewerStore((s) => s.upsertPolygon);
  const selectedPolygonId = useViewerStore((s) => s.selectedPolygonId);
  const setSelectedPolygonId = useViewerStore((s) => s.setSelectedPolygonId);
  const removePolygon = useViewerStore((s) => s.removePolygon);
  const draftPoints = useViewerStore((s) => s.draftPoints);
  const setDraftPoints = useViewerStore((s) => s.setDraftPoints);
  const promptPoints = useViewerStore((s) => s.promptPoints);
  const setPromptPoints = useViewerStore((s) => s.setPromptPoints);
  const promptPreview = useViewerStore((s) => s.promptPreview);
  const setPromptPreview = useViewerStore((s) => s.setPromptPreview);
  const clearDrafts = useViewerStore((s) => s.clearDrafts);
  const pushAction = useViewerStore((s) => s.pushAction);
  const markSaved = useViewerStore((s) => s.markSaved);
  const { undo, redo } = useUndoRedo();
  const { finishDraft, finishPrompt, cancelPrompt, refineTarget, hasPendingDraft, saveCurrent } = useDraftActions();

  const containerRef = useRef<HTMLDivElement>(null);
  const groupRef = useRef<Konva.Group>(null);
  const [size, setSize] = useState({ width: 800, height: 600 });
  const [transform, setTransform] = useState({ scale: 1, x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [isPredicting, setIsPredicting] = useState(false);
  const [promptWarning, setPromptWarning] = useState<string | null>(null);
  const promptWarningTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (promptWarningTimeoutRef.current) clearTimeout(promptWarningTimeoutRef.current);
  }, []);
  /** index of the existing vertex a reshape-between-anchors started at (select tool) */
  const [reshapeAnchor, setReshapeAnchor] = useState<number | null>(null);
  const [reshapeDraft, setReshapeDraft] = useState<[number, number][]>([]);
  /** once both anchors are picked, the two ways to close the loop -- user picks one */
  const [reshapeCandidates, setReshapeCandidates] = useState<{
    a: [number, number][];
    b: [number, number][];
  } | null>(null);
  /** right-click-on-polygon menu: select it / change its cell type */
  const [typeMenu, setTypeMenu] = useState<{ polygonId: number; x: number; y: number } | null>(null);

  useEffect(() => {
    if (!typeMenu) return;
    const close = () => setTypeMenu(null);
    const onKeyDown = (e: KeyboardEvent) => e.key === 'Escape' && close();
    window.addEventListener('click', close);
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('click', close);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [typeMenu]);

  async function handleChangeType(polygonId: number, newClassId: number) {
    setTypeMenu(null);
    const p = polygons.find((poly) => poly.id === polygonId);
    if (!p) return;
    setSelectedPolygonId(polygonId);
    const currentClassId = classFromLabel(p.label);
    const instance = currentClassId !== null ? Number(p.label) - currentClassId * 1000 : 1;
    const newLabel = String(newClassId * 1000 + (Number.isFinite(instance) ? instance : 1));
    if (newLabel === p.label) return;
    const updated = await api.updatePolygon(p.id, { label: newLabel });
    upsertPolygon(updated);
    pushAction({
      type: 'update',
      id: p.id,
      before: { points: p.points, label: p.label },
      after: { points: updated.points, label: updated.label },
    });
  }

  const imageUrl = series
    ? api.frameUrl(
        series.id,
        frameIndex,
        vmin ?? undefined,
        vmax ?? undefined,
        series.channel_count > 1 ? viewChannel : undefined,
      )
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
    const scale = Math.min(size.width / series.width, size.height / series.height) || 1;
    setTransform({
      scale,
      x: (size.width - series.width * scale) / 2,
      y: (size.height - series.height * scale) / 2,
    });
    // Refit when the series, the viewport, or an explicit "Fit to Window"
    // click (resetViewToken) changes -- not on every frame flip, and not on
    // every pan/zoom, which live in the same `transform` state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series?.id, size.width, size.height, resetViewToken]);

  useEffect(() => {
    if (!series) return;
    let cancelled = false;
    api.listPolygons(series.id, frameIndex).then((data) => {
      if (!cancelled) setPolygons(data);
    });
    clearDrafts();
    setReshapeAnchor(null);
    setReshapeDraft([]);
    setReshapeCandidates(null);
    return () => {
      cancelled = true;
    };
  }, [series?.id, frameIndex, setPolygons, clearDrafts]);

  useEffect(() => {
    // Switching tools does NOT clear an in-progress draw/point-prompt draft
    // -- it stays pending (and the Toolbar's Save button can still finish
    // it) until you explicitly finish it or press Esc. Only the reshape/cut
    // state is tool-scoped, since it only makes sense in the select tool.
    if (tool !== 'select') {
      setReshapeAnchor(null);
      setReshapeDraft([]);
      setReshapeCandidates(null);
    }
  }, [tool]);

  // switching (or clearing) the selected polygon cancels any in-progress reshape
  useEffect(() => {
    setReshapeAnchor(null);
    setReshapeDraft([]);
    setReshapeCandidates(null);
  }, [selectedPolygonId]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target;
      const isTyping =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        (target instanceof HTMLElement && target.isContentEditable);
      if (isTyping) return;

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'y') {
        e.preventDefault();
        redo();
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault(); // stop the browser's native "Save Page" dialog
        (async () => {
          if (hasPendingDraft) await saveCurrent();
          markSaved();
        })();
        return;
      }

      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedPolygonId !== null) {
        e.preventDefault();
        const existing = polygons.find((p) => p.id === selectedPolygonId);
        api.deletePolygon(selectedPolygonId).then(() => {
          removePolygon(selectedPolygonId);
          if (existing) pushAction({ type: 'delete', polygon: existing });
        });
        return;
      }

      if (tool === 'draw' && e.key === 'Enter') finishDraft();
      if (tool === 'point-prompt' && e.key === 'Enter') finishPrompt();

      if (e.key === 'Escape') {
        // Esc always cancels whatever's in progress, regardless of which
        // tool you're currently on (a draft survives switching tools away
        // from it, so this needs to reach it there too).
        if (draftPoints.length > 0) setDraftPoints([]);
        if (promptPoints.length > 0 || promptPreview) cancelPrompt();
        if (reshapeCandidates) setReshapeCandidates(null);
        if (reshapeAnchor !== null) {
          setReshapeAnchor(null);
          setReshapeDraft([]);
        }
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    tool,
    draftPoints,
    promptPreview,
    reshapeAnchor,
    reshapeCandidates,
    polygons,
    series,
    frameIndex,
    selectedPolygonId,
    removePolygon,
    undo,
    redo,
    hasPendingDraft,
    saveCurrent,
    markSaved,
  ]);

  // Auto-save any pending draft every 5 minutes, so work isn't lost if a
  // draw/point-prompt draft is left unfinished for a while.
  useEffect(() => {
    const interval = setInterval(() => {
      if (hasPendingDraft) {
        saveCurrent().then(markSaved);
      }
    }, AUTOSAVE_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [hasPendingDraft, saveCurrent, markSaved]);

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

  /** Cut the closed polygon along a new line drawn from vertex `anchorA` to
   * vertex `anchorB` (via `draft`, in that click order). There are two ways
   * to close the resulting loop -- returns both, matching CVAT's polygon
   * edit tool (cvat-canvas/src/typescript/editHandler.ts's stopEdit). */
  function cutCandidates(
    points: [number, number][],
    anchorA: number,
    anchorB: number,
    draft: [number, number][],
  ): { a: [number, number][]; b: [number, number][] } {
    const idxLow = Math.min(anchorA, anchorB);
    const idxHigh = Math.max(anchorA, anchorB);
    let line = [points[anchorA], ...draft, points[anchorB]];
    if (anchorA !== idxLow) line = [...line].reverse(); // always low -> high now

    const a = [...points.slice(0, idxLow), ...line, ...points.slice(idxHigh + 1)];
    const b = [...points.slice(idxLow, idxHigh), ...line.slice(1).reverse()];
    return { a, b };
  }

  function handleVertexClick(index: number) {
    if (tool !== 'select' || reshapeCandidates) return;
    if (reshapeAnchor === null) {
      setReshapeAnchor(index);
      setReshapeDraft([]);
      return;
    }
    if (index === reshapeAnchor) {
      // clicking the same anchor again cancels
      setReshapeAnchor(null);
      setReshapeDraft([]);
      return;
    }
    const poly = polygons.find((p) => p.id === selectedPolygonId);
    if (poly) {
      const { a, b } = cutCandidates(poly.points, reshapeAnchor, index, reshapeDraft);
      if (a.length >= 3 && b.length >= 3) {
        setReshapeCandidates({ a, b });
      } // otherwise a degenerate cut -- silently cancel, same as CVAT
    }
    setReshapeAnchor(null);
    setReshapeDraft([]);
  }

  function chooseReshapeCandidate(points: [number, number][]) {
    if (selectedPolygonId !== null) commitPolygon(selectedPolygonId, points);
    setReshapeCandidates(null);
  }

  /** Add a cut point while reshaping -- shared by clicks on empty canvas
   * (handleStageClick) and clicks on the polygon's own fill/edge, which
   * Konva routes to PolygonLayer instead of bubbling here. */
  function addReshapePoint(point: [number, number]) {
    setReshapeDraft((prev) => [...prev, point]);
  }

  async function handleStageClick(e: Konva.KonvaEventObject<MouseEvent>) {
    // Konva's onClick fires for every mouse button, not just left -- without
    // this guard, a right-click double-fires: handleContextMenu adds the
    // intended exclude point, and this handler (unfiltered) added an unwanted
    // include point in the same click, corrupting the point sequence.
    if (e.evt.button !== 0) return;

    const stage = e.target.getStage();
    const clickedOnEmpty = e.target === stage || e.target.className === 'Image';
    if (!clickedOnEmpty) return; // a polygon/vertex handled its own click

    if (tool === 'select') {
      if (reshapeAnchor !== null) {
        const pt = getImagePoint();
        if (pt) addReshapePoint(pt);
        return;
      }
      setSelectedPolygonId(null);
      return;
    }
    if (!series) return;
    const pt = getImagePoint();
    if (!pt) return;

    if (tool === 'draw') {
      const clamped = clampToImage(pt, series.width, series.height);
      if (draftPoints.length >= 3) {
        // click back on the starting point to close the loop -- deliberate
        // and unambiguous, unlike relying on double-click timing
        const [fx, fy] = draftPoints[0];
        const tolerance = CLOSE_POLYGON_TOLERANCE_PX / transform.scale;
        if (Math.hypot(clamped[0] - fx, clamped[1] - fy) <= tolerance) {
          finishDraft();
          return;
        }
      }
      setDraftPoints([...draftPoints, clamped]);
      return;
    }

    if (tool === 'point-prompt') {
      await addPromptPoint(pt, 1); // left click = include (foreground)
    }
  }

  function showPromptWarning(message: string) {
    if (promptWarningTimeoutRef.current) clearTimeout(promptWarningTimeoutRef.current);
    setPromptWarning(message);
    promptWarningTimeoutRef.current = setTimeout(() => setPromptWarning(null), 2000);
  }

  /** Shared by left-click (include) and right-click (exclude) point-prompt clicks.
   * Every accumulated point (both include and exclude, in click order) is sent
   * together on each call, so the model always resolves one combined mask from
   * the full set -- not just the latest click. */
  async function addPromptPoint(pt: [number, number], label: 0 | 1) {
    if (!series) return;
    const nextPoints = [...promptPoints, { x: pt[0], y: pt[1], label }];
    setPromptPoints(nextPoints);
    setIsPredicting(true);
    try {
      const result = await api.predictPoint(series.id, frameIndex, nextPoints);
      setPromptPreview(result.polygons[0] ?? null);
    } catch (e) {
      setPromptPoints(promptPoints); // roll back -- this point never resolved to a mask
      showPromptWarning(e instanceof Error ? e.message : 'Point-prompt prediction failed');
    } finally {
      setIsPredicting(false);
    }
  }

  function handleContextMenu(e: Konva.KonvaEventObject<MouseEvent>) {
    e.evt.preventDefault();
    // right-click undoes the last added point, matching CVAT's draw/edit tools
    if (tool === 'select' && reshapeAnchor !== null && reshapeDraft.length > 0) {
      setReshapeDraft((prev) => prev.slice(0, -1));
    }
    if (tool === 'draw' && draftPoints.length > 0) {
      setDraftPoints(draftPoints.slice(0, -1));
    }
    // right-click = exclude (background) point, refining the mask live
    if (tool === 'point-prompt') {
      const stage = e.target.getStage();
      const clickedOnEmpty = e.target === stage || e.target.className === 'Image';
      if (!clickedOnEmpty) return;
      const pt = getImagePoint();
      if (pt) addPromptPoint(pt, 0);
    }
  }

  async function commitPolygon(id: number, points: [number, number][]) {
    const existing = polygons.find((p) => p.id === id);
    const updated = await api.updatePolygon(id, { points });
    upsertPolygon(updated);
    if (existing) {
      pushAction({
        type: 'update',
        id,
        before: { points: existing.points, label: existing.label },
        after: { points: updated.points, label: updated.label },
      });
    }
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
      <div className="canvas-badges">
        {isPredicting && (
          <div className="predicting-badge">
            <BufferBar label="Predicting mask…" />
          </div>
        )}
        {draftPoints.length > 0 && (
          <div className="predicting-badge">
            {draftPoints.length} point{draftPoints.length === 1 ? '' : 's'} — right-click to undo a point, click the
            first point (or Enter) to close, Esc to cancel
          </div>
        )}
        {tool === 'point-prompt' && refineTarget && promptPoints.length === 0 && !isPredicting && (
          <div className="predicting-badge">
            Refining polygon #{refineTarget.id} — left-click to include, right-click to exclude, Enter to replace its
            shape
          </div>
        )}
        {!isPredicting && promptPoints.length > 0 && (
          <div className="predicting-badge">
            {promptPoints.length} point{promptPoints.length === 1 ? '' : 's'} — left-click to include, right-click to
            exclude, Enter to {refineTarget ? 'replace its shape' : 'confirm'}, Esc to cancel
          </div>
        )}
        {reshapeAnchor !== null && (
          <div className="predicting-badge">
            Cutting — click to add points, right-click to undo a point, click a vertex to finish there, Esc to cancel
          </div>
        )}
        {reshapeCandidates && (
          <div className="predicting-badge">Pick which side to keep — click a highlighted shape, Esc to cancel</div>
        )}
        {promptWarning && <div className="predicting-badge warning-badge">{promptWarning}</div>}
      </div>
      <Stage
        width={size.width}
        height={size.height}
        onWheel={handleWheel}
        onClick={handleStageClick}
        onContextMenu={handleContextMenu}
        style={{ cursor: isPanning ? 'grabbing' : tool === 'select' ? 'default' : 'crosshair' }}
      >
        <Layer>
          <Group
            ref={groupRef}
            x={transform.x}
            y={transform.y}
            scaleX={transform.scale}
            scaleY={transform.scale}
            draggable
            onDragStart={(e) => {
              // Konva bubbles drag events up from whatever was actually
              // dragged (e.g. a vertex Circle in PolygonLayer) -- only react
              // when this Group itself is the thing being dragged, not a
              // draggable descendant.
              if (e.target !== e.currentTarget) return;
              setIsPanning(true);
            }}
            onDragEnd={(e) => {
              if (e.target !== e.currentTarget) return;
              setIsPanning(false);
              setTransform((t) => ({ ...t, x: e.target.x(), y: e.target.y() }));
            }}
          >
            {image && <KonvaImage image={image} width={series.width} height={series.height} />}

            {polygons.map((poly) => (
              <PolygonLayer
                key={poly.id}
                polygon={poly}
                isSelected={selectedPolygonId === poly.id}
                scale={transform.scale}
                interactive={tool === 'select'}
                reshaping={selectedPolygonId === poly.id && reshapeAnchor !== null}
                hoverSelectEnabled={tool === 'select' && reshapeAnchor === null && !reshapeCandidates}
                onSelect={() => tool === 'select' && setSelectedPolygonId(poly.id)}
                onChangePoints={(pts) => localChange(poly.id, pts)}
                onCommitPoints={(pts) => commitPolygon(poly.id, pts)}
                onVertexClick={handleVertexClick}
                onReshapeClick={addReshapePoint}
                onRequestTypeMenu={(polygonId, x, y) => {
                  setSelectedPolygonId(polygonId);
                  setTypeMenu({ polygonId, x, y });
                }}
              />
            ))}

            {draftPoints.length > 0 && (
              <>
                <Line
                  points={draftPoints.flat()}
                  stroke="#3d63dd"
                  strokeWidth={2 / transform.scale}
                  dash={[6 / transform.scale, 4 / transform.scale]}
                  listening={false}
                />
                {draftPoints.map(([x, y], i) => (
                  <Circle
                    key={i}
                    x={x}
                    y={y}
                    radius={(i === 0 ? 6 : 4) / transform.scale}
                    fill={i === 0 ? undefined : '#3d63dd'}
                    stroke={i === 0 ? '#3d63dd' : undefined}
                    strokeWidth={i === 0 ? 2 / transform.scale : undefined}
                    listening={false}
                  />
                ))}
              </>
            )}

            {promptPoints.length > 0 && (
              <>
                {promptPreview && (
                  <Line
                    points={promptPreview.flat()}
                    closed
                    stroke="#0ea5a5"
                    strokeWidth={2 / transform.scale}
                    dash={[6 / transform.scale, 4 / transform.scale]}
                    fill="rgba(14,165,165,0.15)"
                    listening={false}
                  />
                )}
                {promptPoints.map((p, i) => (
                  <Circle
                    key={i}
                    x={p.x}
                    y={p.y}
                    radius={4 / transform.scale}
                    fill={p.label === 1 ? '#22c55e' : '#ef4444'}
                    listening={false}
                  />
                ))}
              </>
            )}

            {reshapeAnchor !== null &&
              (() => {
                const poly = polygons.find((p) => p.id === selectedPolygonId);
                if (!poly) return null;
                const anchorPoint = poly.points[reshapeAnchor];
                const previewPoints = [anchorPoint, ...reshapeDraft];
                return (
                  <>
                    <Line
                      points={previewPoints.flat()}
                      stroke="#ffb020"
                      strokeWidth={2 / transform.scale}
                      dash={[6 / transform.scale, 4 / transform.scale]}
                      listening={false}
                    />
                    <Circle
                      x={anchorPoint[0]}
                      y={anchorPoint[1]}
                      radius={6 / transform.scale}
                      stroke="#ffb020"
                      strokeWidth={2 / transform.scale}
                      listening={false}
                    />
                    {reshapeDraft.map(([x, y], i) => (
                      <Circle key={i} x={x} y={y} radius={4 / transform.scale} fill="#ffb020" listening={false} />
                    ))}
                  </>
                );
              })()}

            {reshapeCandidates && (
              <>
                <Line
                  points={reshapeCandidates.a.flat()}
                  closed
                  stroke="#3d9bff"
                  fill="rgba(61,155,255,0.35)"
                  strokeWidth={2 / transform.scale}
                  onClick={() => chooseReshapeCandidate(reshapeCandidates.a)}
                  onMouseEnter={(e) => (e.target.getStage()!.container().style.cursor = 'pointer')}
                  onMouseLeave={(e) => (e.target.getStage()!.container().style.cursor = 'default')}
                />
                <Line
                  points={reshapeCandidates.b.flat()}
                  closed
                  stroke="#ff7a3d"
                  fill="rgba(255,122,61,0.35)"
                  strokeWidth={2 / transform.scale}
                  onClick={() => chooseReshapeCandidate(reshapeCandidates.b)}
                  onMouseEnter={(e) => (e.target.getStage()!.container().style.cursor = 'pointer')}
                  onMouseLeave={(e) => (e.target.getStage()!.container().style.cursor = 'default')}
                />
              </>
            )}
          </Group>
        </Layer>
      </Stage>

      {typeMenu && (
        <div
          className="context-menu"
          style={{ left: typeMenu.x, top: typeMenu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          {CLASS_IDS.map((id) => (
            <button key={id} onClick={() => handleChangeType(typeMenu.polygonId, id)}>
              <span className="context-menu-swatch" style={{ background: colorForClass(id) }} />
              {classDisplayName(id)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
