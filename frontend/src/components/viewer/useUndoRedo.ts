import { api } from '../../api/client';
import type { PolygonAnnotation } from '../../api/types';
import { useViewerStore } from '../../store/useViewerStore';

/** Undo/redo for polygon create/update/delete actions on the current frame.
 * Pure store + API logic -- safe to call from multiple components (Toolbar
 * buttons, canvas keyboard shortcuts); they all operate on the same store. */
export function useUndoRedo() {
  const series = useViewerStore((s) => s.series);
  const frameIndex = useViewerStore((s) => s.frameIndex);
  const upsertPolygon = useViewerStore((s) => s.upsertPolygon);
  const removePolygon = useViewerStore((s) => s.removePolygon);
  const popUndo = useViewerStore((s) => s.popUndo);
  const popRedo = useViewerStore((s) => s.popRedo);
  const replaceTopFuture = useViewerStore((s) => s.replaceTopFuture);
  const replaceTopHistory = useViewerStore((s) => s.replaceTopHistory);
  const markSaved = useViewerStore((s) => s.markSaved);
  const canUndo = useViewerStore((s) => s.history.length > 0);
  const canRedo = useViewerStore((s) => s.future.length > 0);

  async function recreate(p: PolygonAnnotation): Promise<PolygonAnnotation> {
    const created = await api.createPolygon(series!.id, frameIndex, p.points, p.source, p.label);
    upsertPolygon(created);
    return created;
  }

  async function undo() {
    const action = popUndo();
    if (!action || !series) return;
    switch (action.type) {
      case 'create':
        await api.deletePolygon(action.polygon.id);
        removePolygon(action.polygon.id);
        break;
      case 'createMany':
        for (const p of action.polygons) {
          await api.deletePolygon(p.id);
          removePolygon(p.id);
        }
        break;
      case 'delete': {
        const recreated = await recreate(action.polygon);
        // undoing a delete assigns a new id -- fix up the redo entry to match
        replaceTopFuture({ type: 'delete', polygon: recreated });
        break;
      }
      case 'deleteMany': {
        const recreated: PolygonAnnotation[] = [];
        for (const p of action.polygons) recreated.push(await recreate(p));
        replaceTopFuture({ type: 'deleteMany', polygons: recreated });
        break;
      }
      case 'update': {
        const updated = await api.updatePolygon(action.id, action.before);
        upsertPolygon(updated);
        break;
      }
    }
    markSaved();
  }

  async function redo() {
    const action = popRedo();
    if (!action || !series) return;
    switch (action.type) {
      case 'create': {
        const created = await recreate(action.polygon);
        replaceTopHistory({ type: 'create', polygon: created });
        break;
      }
      case 'createMany': {
        const created: PolygonAnnotation[] = [];
        for (const p of action.polygons) created.push(await recreate(p));
        replaceTopHistory({ type: 'createMany', polygons: created });
        break;
      }
      case 'delete':
        await api.deletePolygon(action.polygon.id);
        removePolygon(action.polygon.id);
        break;
      case 'deleteMany':
        for (const p of action.polygons) {
          await api.deletePolygon(p.id);
          removePolygon(p.id);
        }
        break;
      case 'update': {
        const updated = await api.updatePolygon(action.id, action.after);
        upsertPolygon(updated);
        break;
      }
    }
    markSaved();
  }

  return { undo, redo, canUndo, canRedo };
}
