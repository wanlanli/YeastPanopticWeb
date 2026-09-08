import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useViewerStore } from '../../store/useViewerStore';
import { FrameMeasurePanel } from './FrameMeasurePanel';
import { PolygonList } from './PolygonList';
import { TrackingTree } from '../quantification/TrackingTree';
import './PanelToggle.css';
import './RightPanel.css';

export function RightPanel() {
  const series = useViewerStore((s) => s.series);
  const rightPanelTab = useViewerStore((s) => s.rightPanelTab);
  const setRightPanelTab = useViewerStore((s) => s.setRightPanelTab);
  const seriesTracking = useViewerStore((s) => s.seriesTracking);
  const setSeriesTracking = useViewerStore((s) => s.setSeriesTracking);
  const [loading, setLoading] = useState(false);
  const [tracking, setTracking] = useState(false);
  const [trackingError, setTrackingError] = useState<string | null>(null);
  const [open, setOpen] = useState(true);

  const isMovie = (series?.frame_count ?? 0) > 1;

  async function refreshTracking() {
    if (!series) return;
    setLoading(true);
    try {
      const result = await api.getSeriesTracking(series.id);
      setSeriesTracking(result);
    } finally {
      setLoading(false);
    }
  }

  /** Runs CellMate's tracker for this whole movie right from the Viewer --
   * same backend pipeline as "Compute Quantification" on the Quantification
   * page, just without having to leave this page or fill in that page's
   * feature-table settings to get tracking ids. */
  async function handleRunTracking() {
    if (!series) return;
    setTracking(true);
    setTrackingError(null);
    try {
      await api.computeQuantification(series.id);
      await refreshTracking();
    } catch (err) {
      setTrackingError(err instanceof Error ? err.message : 'Tracking failed');
    } finally {
      setTracking(false);
    }
  }

  useEffect(() => {
    if (series && isMovie) refreshTracking();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series?.id]);

  return (
    <div className={`right-panel${open ? '' : ' panel-collapsed'}`}>
      {open ? (
        <div className="right-panel-tabs">
          <button
            className="panel-toggle-btn"
            onClick={() => setOpen(false)}
            title="Hide panel"
          >
            ›
          </button>
          <button
            className={rightPanelTab === 'labels' ? 'active' : ''}
            onClick={() => setRightPanelTab('labels')}
          >
            Labels
          </button>
          <button
            className={rightPanelTab === 'tracking' ? 'active' : ''}
            onClick={() => setRightPanelTab('tracking')}
            disabled={!isMovie}
            title={isMovie ? undefined : 'Tracking only applies to movies (multi-frame series)'}
          >
            Tracking
          </button>
          <button
            className={rightPanelTab === 'quantification' ? 'active' : ''}
            onClick={() => setRightPanelTab('quantification')}
          >
            Quantification
          </button>
        </div>
      ) : (
        <button className="panel-toggle-btn" onClick={() => setOpen(true)} title="Show panel">
          ‹
        </button>
      )}

      {open && (
        <div className="right-panel-body">
          {rightPanelTab === 'labels' && <PolygonList />}
          {rightPanelTab === 'quantification' && <FrameMeasurePanel />}
          {rightPanelTab === 'tracking' &&
            (isMovie ? (
              <div className="tracking-tab">
                <div className="tracking-tab-header">
                  <button
                    onClick={handleRunTracking}
                    disabled={tracking}
                    title="Run CellMate's tracker across every frame of this movie -- same cell, same id"
                  >
                    {tracking ? 'Tracking…' : seriesTracking?.dataset_id ? 'Re-run Tracking' : 'Run Tracking'}
                  </button>
                  <button onClick={refreshTracking} disabled={loading || tracking}>
                    {loading ? 'Refreshing…' : 'Refresh'}
                  </button>
                  <span className="tracking-tab-hint">
                    Same cell keeps the same id across frames. Refine masks, then Run Tracking
                    again to pick up the changes.
                  </span>
                </div>
                {trackingError && <div className="tracking-tab-error">{trackingError}</div>}
                {seriesTracking?.dataset_id ? (
                  <TrackingTree datasetId={seriesTracking.dataset_id} />
                ) : (
                  <div className="tracking-tab-empty">
                    No tracking computed yet -- click "Run Tracking" above.
                  </div>
                )}
              </div>
            ) : (
              <div className="tracking-tab-empty">Tracking only applies to movies.</div>
            ))}
        </div>
      )}
    </div>
  );
}
