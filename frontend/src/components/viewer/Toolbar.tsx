import {
  Crosshair,
  Download,
  Eraser,
  FileArchive,
  MousePointer2,
  PenTool,
  Redo2,
  Save,
  Settings2,
  Sparkles,
  SquareStack,
  Trash,
  Trash2,
  Undo2,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { PolygonAnnotation } from '../../api/types';
import { DEFAULT_SEGMENT_SETTINGS, useViewerStore, type Tool } from '../../store/useViewerStore';
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
  const { undo, redo, canUndo, canRedo } = useUndoRedo();
  const { hasPendingDraft, saveCurrent, refineTarget } = useDraftActions();

  /** Run the panoptic model on one frame and create a polygon per detected
   * instance, keeping instance numbers (the `1000 * class + instance` label
   * scheme) from colliding with whatever's already on that frame. */
  async function segmentFrame(
    seriesId: number,
    frameIdx: number,
    existing: PolygonAnnotation[],
    signal?: AbortSignal,
  ): Promise<PolygonAnnotation[]> {
    const { predictions } = await api.predictFrame(seriesId, frameIdx, segmentSettings, signal);
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
    const controller = new AbortController();
    autoSegmentAbortRef.current = controller;
    setAutoSegmenting(true);
    try {
      const created = await segmentFrame(series.id, frameIndex, polygons, controller.signal);
      for (const p of created) upsertPolygon(p);
      if (created.length > 0) pushAction({ type: 'createMany', polygons: created });
    } catch (err) {
      if (!(err instanceof DOMException && err.name === 'AbortError')) throw err;
    } finally {
      autoSegmentAbortRef.current = null;
      setAutoSegmenting(false);
    }
  }

  function handleStopAutoSegment() {
    autoSegmentAbortRef.current?.abort();
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
          title="Auto-Segment Frame — detect every cell/instance in this frame with the panoptic model"
          onClick={handleAutoSegment}
          disabled={autoSegmenting || batchRunning}
        />
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
