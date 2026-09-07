import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { PolygonAnnotation } from '../../api/types';
import { useViewerStore, type Tool } from '../../store/useViewerStore';
import { BufferBar } from './BufferBar';
import { CLASS_IDS, classDisplayName, classFromLabel, colorForClass, textColorForClass } from './colorByClass';
import { useDraftActions } from './useDraftActions';
import { useUndoRedo } from './useUndoRedo';
import './Toolbar.css';

function formatDuration(ms: number): string {
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}m ${seconds}s`;
}

const TOOLS: { id: Tool; label: string; hint: string }[] = [
  {
    id: 'select',
    label: 'Select / Edit',
    hint:
      'Hover a polygon to select it, drag vertices to move, Alt+click (or double-click) a vertex to delete. ' +
      'Shift+click a vertex to cut: click to add points, click another vertex to finish there, then pick which ' +
      'side to keep. Right-click undoes a point, Esc cancels',
  },
  {
    id: 'draw',
    label: 'Draw Polygon',
    hint: 'Click to add vertices, right-click to undo a point, double-click (or Enter) to close, Esc to cancel',
  },
  {
    id: 'point-prompt',
    label: 'Point Prompt',
    hint:
      'Left-click to include, right-click to exclude, refining the mask live. Enter to confirm, Esc to cancel. ' +
      'Select a polygon first to refine its shape instead of creating a new one',
  },
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
  const upsertPolygon = useViewerStore((s) => s.upsertPolygon);
  const pushAction = useViewerStore((s) => s.pushAction);
  const promptClassId = useViewerStore((s) => s.promptClassId);
  const setPromptClassId = useViewerStore((s) => s.setPromptClassId);
  const lastSavedAt = useViewerStore((s) => s.lastSavedAt);
  const markSaved = useViewerStore((s) => s.markSaved);
  const [justSaved, setJustSaved] = useState(false);
  const [autoSegmenting, setAutoSegmenting] = useState(false);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchProgress, setBatchProgress] = useState<{ done: number; total: number; startedAt: number } | null>(
    null,
  );
  const batchStopRef = useRef(false);
  const { undo, redo, canUndo, canRedo } = useUndoRedo();
  const { hasPendingDraft, saveCurrent, refineTarget } = useDraftActions();

  /** Run the panoptic model on one frame and create a polygon per detected
   * instance, keeping instance numbers (the `1000 * class + instance` label
   * scheme) from colliding with whatever's already on that frame. */
  async function segmentFrame(
    seriesId: number,
    frameIdx: number,
    existing: PolygonAnnotation[],
  ): Promise<PolygonAnnotation[]> {
    const { predictions } = await api.predictFrame(seriesId, frameIdx);
    const nextInstance = new Map<number, number>();
    for (const p of existing) {
      const classId = classFromLabel(p.label);
      if (classId === null) continue;
      const instance = Number(p.label) - classId * 1000;
      nextInstance.set(classId, Math.max(nextInstance.get(classId) ?? 0, instance));
    }
    const created: PolygonAnnotation[] = [];
    for (const pred of predictions) {
      const instance = (nextInstance.get(pred.class_id) ?? 0) + 1;
      nextInstance.set(pred.class_id, instance);
      const label = String(pred.class_id * 1000 + instance);
      created.push(await api.createPolygon(seriesId, frameIdx, pred.points, 'model', label));
    }
    return created;
  }

  async function handleAutoSegment() {
    if (!series) return;
    setAutoSegmenting(true);
    try {
      const created = await segmentFrame(series.id, frameIndex, polygons);
      for (const p of created) upsertPolygon(p);
      if (created.length > 0) pushAction({ type: 'createMany', polygons: created });
    } finally {
      setAutoSegmenting(false);
    }
  }

  async function handleBatchSegment() {
    if (!series || series.frame_count <= 1 || batchRunning) return;
    const proceed = window.confirm(
      `Segment all ${series.frame_count} frames with the panoptic model?\n\n` +
        'This runs one frame at a time and can take anywhere from a few seconds to a couple of minutes per ' +
        'frame, depending on the model and hardware -- for a large stack this could take a while. ' +
        'You can stop it partway through and keep whatever has already been segmented.\n\n' +
        'This does not affect undo/redo, which only tracks the current frame.\n\nContinue?',
    );
    if (!proceed) return;

    batchStopRef.current = false;
    setBatchRunning(true);
    setBatchProgress({ done: 0, total: series.frame_count, startedAt: Date.now() });

    for (let f = 0; f < series.frame_count; f++) {
      if (batchStopRef.current) break;
      try {
        const existingForFrame = await api.listPolygons(series.id, f);
        const created = await segmentFrame(series.id, f, existingForFrame);
        if (f === frameIndex) {
          for (const p of created) upsertPolygon(p);
        }
      } catch (err) {
        // keep going -- a single frame's failure shouldn't abort a
        // multi-minute batch job over the rest of the stack
        console.error(`Batch segment failed on frame ${f}`, err);
      }
      setBatchProgress((prev) => (prev ? { ...prev, done: f + 1 } : prev));
    }

    setBatchRunning(false);
  }

  function handleStopBatch() {
    batchStopRef.current = true;
  }

  // Flash "Saved" whenever anything actually persists -- create/update/
  // delete, undo/redo, or an explicit Save/Ctrl+S/auto-save -- since most
  // edits (drag a vertex, a cut, a type change) already save immediately
  // with no pending draft, so a button that's only ever enabled for
  // drafts reads as broken even when everything is in fact saved.
  useEffect(() => {
    if (lastSavedAt === null) return;
    setJustSaved(true);
    const t = setTimeout(() => setJustSaved(false), 1600);
    return () => clearTimeout(t);
  }, [lastSavedAt]);

  async function handleSaveClick() {
    if (hasPendingDraft) await saveCurrent();
    markSaved();
  }

  async function handleClearFrame() {
    if (!series || polygons.length === 0) return;
    if (!window.confirm(`Delete all ${polygons.length} polygon(s) on this frame?`)) return;
    const deleted = polygons;
    await api.deleteFramePolygons(series.id, frameIndex);
    setPolygons([]);
    pushAction({ type: 'deleteMany', polygons: deleted });
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
    <>
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
      {tool === 'point-prompt' && !refineTarget && (
        <select
          className="prompt-class-select"
          style={{ backgroundColor: colorForClass(promptClassId), color: textColorForClass(promptClassId) }}
          value={promptClassId}
          onChange={(e) => setPromptClassId(Number(e.target.value))}
          title="Class new point-prompt polygons are labeled with"
        >
          {CLASS_IDS.map((id) => (
            <option key={id} value={id}>
              {classDisplayName(id)}
            </option>
          ))}
        </select>
      )}
      {tool === 'point-prompt' && refineTarget && (
        <span className="toolbar-hint-text">Refining polygon #{refineTarget.id}</span>
      )}
      {series && (
        <button
          onClick={handleAutoSegment}
          disabled={autoSegmenting || batchRunning}
          title="Detect every cell/instance in this frame with the panoptic model"
        >
          Auto-Segment Frame
        </button>
      )}
      {series && series.frame_count > 1 && (
        <button
          onClick={handleBatchSegment}
          disabled={autoSegmenting || batchRunning}
          title={`Run the panoptic model on all ${series.frame_count} frames, one at a time`}
        >
          Segment All Frames
        </button>
      )}
      {autoSegmenting && (
        <div className="toolbar-buffer">
          <BufferBar label="Segmenting frame…" />
        </div>
      )}
      <div className="toolbar-spacer" />
      {justSaved && <span className="saved-indicator">✓ Saved</span>}
      <button
        onClick={handleSaveClick}
        title={
          hasPendingDraft
            ? "Save the polygon/mask currently being drawn (same as pressing Enter or Ctrl+S)"
            : 'Everything is already saved -- every edit persists immediately. Click to confirm, or Ctrl+S'
        }
      >
        Save
      </button>
      <button onClick={undo} disabled={!canUndo} title="Undo (Ctrl+Z)">
        Undo
      </button>
      <button onClick={redo} disabled={!canRedo} title="Redo (Ctrl+Shift+Z)">
        Redo
      </button>
      <button
        disabled={selectedPolygonId === null}
        onClick={async () => {
          if (selectedPolygonId === null) return;
          const existing = polygons.find((p) => p.id === selectedPolygonId);
          await api.deletePolygon(selectedPolygonId);
          removePolygon(selectedPolygonId);
          if (existing) pushAction({ type: 'delete', polygon: existing });
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
      {batchProgress && (
        <div className="batch-overlay">
          <div className="batch-panel">
            <h3>Segmenting all frames…</h3>
            <BufferBar
              label={`Frame ${batchProgress.done} / ${batchProgress.total}`}
              progress={batchProgress.total > 0 ? batchProgress.done / batchProgress.total : 0}
            />
            <div className="batch-eta">
              {batchProgress.done === 0
                ? 'Estimating time…'
                : batchRunning
                  ? `~${formatDuration(
                      ((Date.now() - batchProgress.startedAt) / batchProgress.done) *
                        (batchProgress.total - batchProgress.done),
                    )} remaining`
                  : batchProgress.done === batchProgress.total
                    ? `Done in ${formatDuration(Date.now() - batchProgress.startedAt)}`
                    : `Stopped after ${batchProgress.done} of ${batchProgress.total} frames ` +
                      `(${formatDuration(Date.now() - batchProgress.startedAt)})`}
            </div>
            <div className="batch-panel-actions">
              {batchRunning ? (
                <button className="toolbar-danger-btn" onClick={handleStopBatch}>
                  Stop
                </button>
              ) : (
                <button onClick={() => setBatchProgress(null)}>Close</button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
