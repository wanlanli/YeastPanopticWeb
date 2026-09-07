import { api } from '../../api/client';
import { useViewerStore } from '../../store/useViewerStore';
import { classFromLabel } from './colorByClass';

/** Finish/cancel the in-progress draw or point-prompt draft. Shared so both
 * the canvas (Enter key, click-to-close gestures) and the Toolbar's Save
 * button can trigger the same "commit what I have right now" action. */
export function useDraftActions() {
  const series = useViewerStore((s) => s.series);
  const frameIndex = useViewerStore((s) => s.frameIndex);
  const polygons = useViewerStore((s) => s.polygons);
  const selectedPolygonId = useViewerStore((s) => s.selectedPolygonId);
  const draftPoints = useViewerStore((s) => s.draftPoints);
  const setDraftPoints = useViewerStore((s) => s.setDraftPoints);
  const promptPreview = useViewerStore((s) => s.promptPreview);
  const promptClassId = useViewerStore((s) => s.promptClassId);
  const setPromptPoints = useViewerStore((s) => s.setPromptPoints);
  const setPromptPreview = useViewerStore((s) => s.setPromptPreview);
  const upsertPolygon = useViewerStore((s) => s.upsertPolygon);
  const pushAction = useViewerStore((s) => s.pushAction);

  async function finishDraft() {
    if (!series || draftPoints.length < 3) {
      setDraftPoints([]);
      return;
    }
    const created = await api.createPolygon(series.id, frameIndex, draftPoints, 'manual');
    upsertPolygon(created);
    pushAction({ type: 'create', polygon: created });
    setDraftPoints([]);
  }

  /** Refine target: a polygon selected before entering point-prompt (see
   * useViewerStore's setTool) -- finishing replaces its shape instead of
   * creating a new polygon. */
  const refineTarget = selectedPolygonId !== null ? polygons.find((p) => p.id === selectedPolygonId) : undefined;

  async function finishPrompt() {
    if (series && promptPreview) {
      if (refineTarget) {
        const updated = await api.updatePolygon(refineTarget.id, { points: promptPreview });
        upsertPolygon(updated);
        pushAction({
          type: 'update',
          id: refineTarget.id,
          before: { points: refineTarget.points, label: refineTarget.label },
          after: { points: updated.points, label: updated.label },
        });
      } else {
        // keep instance numbers (the `1000 * class + instance` label scheme)
        // from colliding with whatever's already on this frame
        const nextInstanceByClass = new Map<number, number>();
        for (const p of polygons) {
          const classId = classFromLabel(p.label);
          if (classId === null) continue;
          const instance = Number(p.label) - classId * 1000;
          nextInstanceByClass.set(classId, Math.max(nextInstanceByClass.get(classId) ?? 0, instance));
        }
        const nextInstance = (nextInstanceByClass.get(promptClassId) ?? 0) + 1;
        const label = String(promptClassId * 1000 + nextInstance);
        const created = await api.createPolygon(series.id, frameIndex, promptPreview, 'model', label);
        upsertPolygon(created);
        pushAction({ type: 'create', polygon: created });
      }
    }
    setPromptPoints([]);
    setPromptPreview(null);
  }

  function cancelPrompt() {
    setPromptPoints([]);
    setPromptPreview(null);
  }

  // Independent of the currently active tool: a draft survives switching
  // tools away from it (see ImageCanvas), so Save/hasPendingDraft must too.
  const hasPendingDraft = draftPoints.length >= 3 || promptPreview !== null;

  async function saveCurrent() {
    if (draftPoints.length >= 3) await finishDraft();
    else if (promptPreview !== null) await finishPrompt();
  }

  return { finishDraft, finishPrompt, cancelPrompt, hasPendingDraft, saveCurrent, refineTarget };
}
