import {
  Check,
  Crosshair,
  Download,
  Eraser,
  Eye,
  EyeOff,
  FileArchive,
  MousePointer2,
  PenTool,
  Redo2,
  Route,
  Save,
  Settings2,
  Sparkles,
  SquareStack,
  Trash,
  Trash2,
  Undo2,
  X,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { PolygonAnnotation, SegmentSettings } from '../../api/types';
import { DEFAULT_SEGMENT_SETTINGS, useViewerStore, type Tool } from '../../store/useViewerStore';
import { BufferBar } from './BufferBar';
import { CLASS_IDS, classDisplayName, colorForClass, textColorForClass } from './colorByClass';
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

const TOOLS: { id: Tool; label: string; icon: LucideIcon; hint: string }[] = [
  {
    id: 'select',
    label: 'Select / Edit',
    icon: MousePointer2,
    hint:
      'Select / Edit — hover a polygon to select it, drag vertices to move, Alt+click (or double-click) a ' +
      'vertex to delete. Shift+click a vertex to cut: click to add points, click another vertex to finish there, ' +
      'then pick which side to keep. Right-click undoes a point, Esc cancels',
  },
  {
    id: 'draw',
    label: 'Draw Polygon',
    icon: PenTool,
    hint:
      'Draw Polygon — click to add vertices, right-click to undo a point, double-click (or Enter) to close, ' +
      'Esc to cancel',
  },
  {
    id: 'point-prompt',
    label: 'Point Prompt',
    icon: Crosshair,
    hint:
      'Point Prompt — left-click to include, right-click to exclude, refining the mask live. Enter to confirm, ' +
      'Esc to cancel. Select a polygon first to refine its shape instead of creating a new one',
  },
];

/** Icon-only toolbar button -- the icon replaces the label as the button's
 * visible content, the label/hint text only shows up as a tooltip and
 * screen-reader label (title + aria-label). */
function IconButton({
  icon: Icon,
  label,
  title,
  onClick,
  disabled,
  className,
}: {
  icon: LucideIcon;
  label: string;
  title?: string;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      className={['toolbar-icon-btn', className].filter(Boolean).join(' ')}
      onClick={onClick}
      disabled={disabled}
      title={title ?? label}
      aria-label={label}
    >
      <Icon size={16} strokeWidth={2} />
    </button>
  );
}

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
  const segmentSettings = useViewerStore((s) => s.segmentSettings);
  const setSegmentSettings = useViewerStore((s) => s.setSegmentSettings);
  const framePredictionPreview = useViewerStore((s) => s.framePredictionPreview);
  const setFramePredictionPreview = useViewerStore((s) => s.setFramePredictionPreview);
  const showMasks = useViewerStore((s) => s.showMasks);
  const toggleShowMasks = useViewerStore((s) => s.toggleShowMasks);
  const seriesTracking = useViewerStore((s) => s.seriesTracking);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const lastSavedAt = useViewerStore((s) => s.lastSavedAt);
  const markSaved = useViewerStore((s) => s.markSaved);
  const [justSaved, setJustSaved] = useState(false);
  const [autoSegmenting, setAutoSegmenting] = useState(false);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchProgress, setBatchProgress] = useState<{ done: number; total: number; startedAt: number } | null>(
    null,
  );
  const batchStopRef = useRef(false);
  const autoSegmentAbortRef = useRef<AbortController | null>(null);
  const [segmentError, setSegmentError] = useState<string | null>(null);
  const segmentErrorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (segmentErrorTimeoutRef.current) clearTimeout(segmentErrorTimeoutRef.current);
  }, []);
  const { undo, redo, canUndo, canRedo } = useUndoRedo();
  const { hasPendingDraft, saveCurrent, refineTarget } = useDraftActions();

  function showSegmentError(message: string) {
    if (segmentErrorTimeoutRef.current) clearTimeout(segmentErrorTimeoutRef.current);
    setSegmentError(message);
    segmentErrorTimeoutRef.current = setTimeout(() => setSegmentError(null), 5000);
  }

  const appliedPreviewSettingsRef = useRef<SegmentSettings | null>(null);
  const refineTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refineAbortRef = useRef<AbortController | null>(null);

  /** Run the panoptic model on one frame and immediately accept every
   * detected instance as a polygon -- used by "Segment All Frames", where
   * nobody is watching each frame to review a preview. Instance numbers
   * (the `1000 * class + instance` label scheme) are assigned by the
   * backend, scanned across the whole series, so they never collide with
   * an object on a different frame (or one a concurrent create just
   * added). */
  async function segmentFrameAndAccept(
    seriesId: number,
    frameIdx: number,
    signal?: AbortSignal,
  ): Promise<PolygonAnnotation[]> {
    const { result_id, predictions } = await api.predictFrame(seriesId, frameIdx, segmentSettings, signal);
    if (predictions.length === 0) return [];
    return api.acceptPredictions(seriesId, frameIdx, result_id, predictions, segmentSettings);
  }

  /** Run the panoptic model on the current frame. By default this saves
   * the result immediately (same one-click behavior as before previews
   * existed) -- no review step for the common case of just using the
   * default settings. Only when Advanced Settings is open (the user has
   * already indicated they want to tune score/area/etc first) does this
   * show a preview instead (see framePredictionPreview): nothing is
   * written to the database yet, further settings changes cheaply
   * re-threshold it (see the effect below) instead of re-running the
   * model, and Accept/Discard (handleAcceptPrediction/
   * handleDiscardPrediction) make the final call. */
  async function handleAutoSegment() {
    if (!series) return;
    const controller = new AbortController();
    autoSegmentAbortRef.current = controller;
    setAutoSegmenting(true);
    try {
      if (showAdvanced) {
        const result = await api.predictFrame(series.id, frameIndex, segmentSettings, controller.signal);
        appliedPreviewSettingsRef.current = segmentSettings;
        setFramePredictionPreview({
          seriesId: series.id,
          frameIndex,
          resultId: result.result_id,
          predictions: result.predictions,
        });
      } else {
        const created = await segmentFrameAndAccept(series.id, frameIndex, controller.signal);
        for (const p of created) upsertPolygon(p);
        if (created.length > 0) pushAction({ type: 'createMany', polygons: created });
      }
    } catch (err) {
      // AbortError means the user hit Stop -- not a failure, nothing to show.
      // Anything else (e.g. the model service being briefly unreachable)
      // used to fail completely silently here -- the spinner just vanished
      // with no indication anything went wrong, which read as the feature
      // being broken rather than one request having failed.
      if (!(err instanceof DOMException && err.name === 'AbortError')) {
        showSegmentError(err instanceof Error ? err.message : 'Auto-segment failed');
      }
    } finally {
      autoSegmentAbortRef.current = null;
      setAutoSegmenting(false);
    }
  }

  function handleStopAutoSegment() {
    autoSegmentAbortRef.current?.abort();
  }

  // Cheaply re-threshold the pending preview whenever Advanced Settings
  // change, instead of making the user re-click Auto-Segment Frame (which
  // would rerun the model from the original image every time). Debounced
  // so dragging a slider doesn't fire a request per intermediate value.
  useEffect(() => {
    if (!series || !framePredictionPreview) return;
    if (framePredictionPreview.seriesId !== series.id || framePredictionPreview.frameIndex !== frameIndex) return;
    if (appliedPreviewSettingsRef.current === segmentSettings) return; // the settings this preview already reflects

    refineAbortRef.current?.abort();
    if (refineTimeoutRef.current) clearTimeout(refineTimeoutRef.current);

    const controller = new AbortController();
    refineAbortRef.current = controller;
    const { seriesId, frameIndex: previewFrameIndex, resultId } = framePredictionPreview;

    refineTimeoutRef.current = setTimeout(async () => {
      try {
        // No result_id means the active model has no cache to refine from
        // (e.g. the classical-CV placeholder) -- predict-frame again
        // instead, which is cheap for that model anyway.
        const result = resultId
          ? await api.refineFrame(seriesId, previewFrameIndex, resultId, segmentSettings, controller.signal)
          : await api.predictFrame(seriesId, previewFrameIndex, segmentSettings, controller.signal);
        appliedPreviewSettingsRef.current = segmentSettings;
        setFramePredictionPreview({
          seriesId,
          frameIndex: previewFrameIndex,
          resultId: result.result_id,
          predictions: result.predictions,
        });
      } catch (err) {
        if (!(err instanceof DOMException && err.name === 'AbortError')) {
          showSegmentError(err instanceof Error ? err.message : 'Refine failed');
        }
      }
    }, 250);

    return () => {
      if (refineTimeoutRef.current) clearTimeout(refineTimeoutRef.current);
    };
    // Only re-run when the settings themselves change -- series/frameIndex/
    // framePredictionPreview are read fresh from the closure each time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [segmentSettings]);

  async function handleAcceptPrediction() {
    if (!series || !framePredictionPreview || framePredictionPreview.predictions.length === 0) {
      setFramePredictionPreview(null);
      return;
    }
    try {
      const created = await api.acceptPredictions(
        series.id,
        frameIndex,
        framePredictionPreview.resultId,
        framePredictionPreview.predictions,
        segmentSettings,
      );
      for (const p of created) upsertPolygon(p);
      if (created.length > 0) pushAction({ type: 'createMany', polygons: created });
    } catch (err) {
      showSegmentError(err instanceof Error ? err.message : 'Failed to accept predictions');
      return;
    }
    setFramePredictionPreview(null);
  }

  function handleDiscardPrediction() {
    refineAbortRef.current?.abort();
    setFramePredictionPreview(null);
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
        const created = await segmentFrameAndAccept(series.id, f);
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

  useEffect(() => {
    if (!showAdvanced) return;
    const close = () => setShowAdvanced(false);
    const onKeyDown = (e: KeyboardEvent) => e.key === 'Escape' && close();
    window.addEventListener('click', close);
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('click', close);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [showAdvanced]);

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
        <IconButton
          key={t.id}
          icon={t.icon}
          label={t.label}
          title={t.hint}
          className={tool === t.id ? 'active' : ''}
          onClick={() => setTool(t.id)}
        />
      ))}
      {(tool === 'draw' || (tool === 'point-prompt' && !refineTarget)) && (
        <select
          className="prompt-class-select"
          style={{ backgroundColor: colorForClass(promptClassId), color: textColorForClass(promptClassId) }}
          value={promptClassId}
          onChange={(e) => setPromptClassId(Number(e.target.value))}
          title="Class new polygons are labeled with"
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
        <IconButton
          icon={Sparkles}
          label="Auto-Segment Frame"
          title={
            showAdvanced
              ? 'Auto-Segment Frame — detect every cell/instance in this frame and preview the result, so you can tune Advanced Settings before Accepting'
              : 'Auto-Segment Frame — detect every cell/instance in this frame with the panoptic model and save immediately (open Advanced Settings first to preview/tune before saving)'
          }
          onClick={handleAutoSegment}
          disabled={autoSegmenting || batchRunning}
        />
      )}
      {series && framePredictionPreview && framePredictionPreview.seriesId === series.id && (
        <>
          <span className="toolbar-hint-text">
            {framePredictionPreview.predictions.length} detected (preview)
          </span>
          <IconButton
            icon={Check}
            label="Accept"
            title="Accept — save the previewed detections as polygons"
            onClick={handleAcceptPrediction}
          />
          <IconButton
            icon={X}
            label="Discard"
            title="Discard — throw away the previewed detections without saving"
            onClick={handleDiscardPrediction}
          />
        </>
      )}
      {series && series.frame_count > 1 && (
        <IconButton
          icon={SquareStack}
          label="Segment All Frames"
          title={`Segment All Frames — run the panoptic model on all ${series.frame_count} frames, one at a time`}
          onClick={handleBatchSegment}
          disabled={autoSegmenting || batchRunning}
        />
      )}
      {series && (
        <div className="advanced-settings-wrap">
          <IconButton
            icon={Settings2}
            label="Advanced Settings"
            title="Advanced Settings — auto-segment filtering settings (score/confidence/area thresholds, border cells)"
            className={showAdvanced ? 'active' : ''}
            onClick={(e) => {
              e.stopPropagation();
              setShowAdvanced((v) => !v);
            }}
          />
          {showAdvanced && (
            <div className="advanced-settings-panel" onClick={(e) => e.stopPropagation()}>
              <label>
                Score threshold
                <input
                  type="number"
                  step="0.01"
                  min={0}
                  max={1}
                  value={segmentSettings.scoreThreshold}
                  onChange={(e) => setSegmentSettings({ scoreThreshold: Number(e.target.value) })}
                  title="Minimum overall detection confidence to keep (0-1)"
                />
              </label>
              <label>
                Instance (trust) threshold
                <input
                  type="number"
                  step="0.01"
                  min={0}
                  max={1}
                  value={segmentSettings.instanceThreshold}
                  onChange={(e) => setSegmentSettings({ instanceThreshold: Number(e.target.value) })}
                  title="Minimum instance-center confidence to keep (0-1) -- how much to trust this is a real, separate cell"
                />
              </label>
              <label>
                Min area (px)
                <input
                  type="number"
                  step="1"
                  min={0}
                  value={segmentSettings.areaThreshold}
                  onChange={(e) => setSegmentSettings({ areaThreshold: Number(e.target.value) })}
                  title="Drop detections smaller than this many pixels"
                />
              </label>
              <label>
                Smoothing (max hole, px)
                <input
                  type="number"
                  step="50"
                  min={0}
                  value={segmentSettings.holeAreaThreshold}
                  onChange={(e) => setSegmentSettings({ holeAreaThreshold: Number(e.target.value) })}
                  title="Fill internal holes in a mask up to this many pixels -- higher is smoother"
                />
              </label>
              <label className="advanced-settings-checkbox">
                <input
                  type="checkbox"
                  checked={segmentSettings.keepBorderCells}
                  onChange={(e) => setSegmentSettings({ keepBorderCells: e.target.checked })}
                />
                Keep cells touching the frame edge
              </label>
              <button
                className="advanced-settings-reset"
                onClick={() => setSegmentSettings(DEFAULT_SEGMENT_SETTINGS)}
              >
                Reset to defaults
              </button>
            </div>
          )}
        </div>
      )}
      {segmentError && <span className="segment-error-text">{segmentError}</span>}
      <div className="toolbar-spacer" />
      {justSaved && <span className="saved-indicator">✓ Saved</span>}
      <IconButton
        icon={Save}
        label="Save"
        title={
          hasPendingDraft
            ? 'Save — save the polygon/mask currently being drawn (same as pressing Enter or Ctrl+S)'
            : 'Save — everything is already saved, every edit persists immediately. Click to confirm, or Ctrl+S'
        }
        onClick={handleSaveClick}
      />
      <IconButton icon={Undo2} label="Undo" title="Undo (Ctrl+Z)" onClick={undo} disabled={!canUndo} />
      <IconButton icon={Redo2} label="Redo" title="Redo (Ctrl+Shift+Z)" onClick={redo} disabled={!canRedo} />
      <IconButton
        icon={Trash2}
        label="Delete Selected"
        title="Delete Selected — delete the selected polygon"
        disabled={selectedPolygonId === null}
        onClick={async () => {
          if (selectedPolygonId === null) return;
          const existing = polygons.find((p) => p.id === selectedPolygonId);
          await api.deletePolygon(selectedPolygonId);
          removePolygon(selectedPolygonId);
          if (existing) pushAction({ type: 'delete', polygon: existing });
        }}
      />
      <IconButton
        icon={showMasks ? Eye : EyeOff}
        label={showMasks ? 'Hide Masks' : 'Show Masks'}
        title={
          showMasks
            ? 'Hide Masks — hide all polygons/masks on the canvas to see the raw image underneath'
            : 'Show Masks — show polygons/masks on the canvas again'
        }
        className={showMasks ? '' : 'active'}
        onClick={toggleShowMasks}
      />
      {series && (
        <>
          <IconButton
            icon={Eraser}
            label="Clear Frame"
            title="Clear Frame — delete all polygons on this frame"
            className="toolbar-danger-btn"
            disabled={polygons.length === 0}
            onClick={handleClearFrame}
          />
          <IconButton
            icon={Trash}
            label="Clear Movie"
            title="Clear Movie — delete all polygons across every frame of this series"
            className="toolbar-danger-btn"
            onClick={handleClearMovie}
          />
          <a
            className="toolbar-link-btn toolbar-icon-btn"
            href={api.frameMaskUrl(series.id, frameIndex)}
            title="Export Frame Mask — download this frame's polygons rasterized as a label-mask TIFF"
            aria-label="Export Frame Mask"
          >
            <Download size={16} strokeWidth={2} />
          </a>
          <a
            className="toolbar-link-btn toolbar-icon-btn"
            href={api.seriesMaskUrl(series.id)}
            title="Export Mask Stack — download every frame's polygons rasterized as label masks: one TIFF per frame (zipped) if this series came from separate image files, or a single multi-page TIFF stack if it came from one"
            aria-label="Export Mask Stack"
          >
            <FileArchive size={16} strokeWidth={2} />
          </a>
          {series.frame_count > 1 &&
            (seriesTracking?.dataset_id ? (
              <a
                className="toolbar-link-btn toolbar-icon-btn"
                href={api.seriesMaskUrl(series.id, true)}
                title="Export Mask Stack (Tracked) — same as Export Mask Stack, but each object's stable track id is burned in instead of its per-frame label, so the same cell has the same pixel value across every frame"
                aria-label="Export Mask Stack (Tracked)"
              >
                <Route size={16} strokeWidth={2} />
              </a>
            ) : (
              <IconButton
                icon={Route}
                label="Export Mask Stack (Tracked)"
                title="Export Mask Stack (Tracked) — run Tracking first (Tracking tab, right panel)"
                disabled
              />
            ))}
        </>
      )}
      </div>
      {autoSegmenting && (
        <div className="batch-overlay">
          <div className="batch-panel">
            <h3>Segmenting frame…</h3>
            <BufferBar label="Detecting instances…" />
            <div className="batch-panel-actions">
              <button className="toolbar-danger-btn" onClick={handleStopAutoSegment}>
                Stop
              </button>
            </div>
          </div>
        </div>
      )}
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
