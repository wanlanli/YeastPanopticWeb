import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { useViewerStore } from '../../store/useViewerStore';
import { PolygonList } from './PolygonList';
import { TrackingTree } from '../quantification/TrackingTree';
import './RightPanel.css';

export function RightPanel() {
  const series = useViewerStore((s) => s.series);
  const rightPanelTab = useViewerStore((s) => s.rightPanelTab);
  const setRightPanelTab = useViewerStore((s) => s.setRightPanelTab);
  const seriesTracking = useViewerStore((s) => s.seriesTracking);
  const setSeriesTracking = useViewerStore((s) => s.setSeriesTracking);
  const [loading, setLoading] = useState(false);

  const isMovie = (series?.frame_count ?? 0) > 1;

  async function refreshTracking() {
    if (!series) return;
    setLoading(true);
    try {
      const tracking = await api.getSeriesTracking(series.id);
      setSeriesTracking(tracking);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (series && isMovie) refreshTracking();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series?.id]);

  return (
    <div className="right-panel">
      <div className="right-panel-tabs">
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
      </div>

      <div className="right-panel-body">
        {rightPanelTab === 'labels' && <PolygonList />}
        {rightPanelTab === 'tracking' &&
          (isMovie ? (
            <div className="tracking-tab">
              <div className="tracking-tab-header">
                <button onClick={refreshTracking} disabled={loading}>
                  {loading ? 'Refreshing…' : 'Refresh'}
                </button>
                <span className="tracking-tab-hint">
                  Same cell keeps the same id across frames. Refine masks, then Refresh here after
                  recomputing quantification.
                </span>
              </div>
              {seriesTracking?.dataset_id ? (
                <TrackingTree datasetId={seriesTracking.dataset_id} />
              ) : (
                <div className="tracking-tab-empty">
                  No tracking computed yet -- run "Compute Quantification" for this series from the
                  Quantification page.
                </div>
              )}
            </div>
          ) : (
            <div className="tracking-tab-empty">Tracking only applies to movies.</div>
          ))}
      </div>
    </div>
  );
}
