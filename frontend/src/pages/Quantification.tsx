import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { QuantificationDataset, Series } from '../api/types';
import { FeatureTable } from '../components/quantification/FeatureTable';
import { TrackingTree } from '../components/quantification/TrackingTree';
import { TsnePlot } from '../components/quantification/TsnePlot';
import './Quantification.css';

export function Quantification() {
  const { projectId } = useParams();
  const pid = Number(projectId);
  const [datasets, setDatasets] = useState<QuantificationDataset[]>([]);
  const [featureId, setFeatureId] = useState<number | null>(null);
  const [trackingId, setTrackingId] = useState<number | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [uploadKind, setUploadKind] = useState<'features' | 'tracking'>('features');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [seriesList, setSeriesList] = useState<Series[]>([]);
  const [computeSeriesId, setComputeSeriesId] = useState<number | null>(null);
  const [fillGaps, setFillGaps] = useState(false);
  const [computing, setComputing] = useState(false);
  const [computeError, setComputeError] = useState<string | null>(null);

  async function refresh() {
    const list = await api.listDatasets(pid);
    setDatasets(list);
    const features = list.filter((d) => d.kind === 'features');
    const tracking = list.filter((d) => d.kind === 'tracking');
    if (features.length && featureId === null) setFeatureId(features[0].id);
    if (tracking.length && trackingId === null) setTrackingId(tracking[0].id);
  }

  useEffect(() => {
    refresh();
    api.listSeries(pid).then((list) => {
      setSeriesList(list);
      if (list.length && computeSeriesId === null) setComputeSeriesId(list[0].id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  async function handleCompute() {
    if (!computeSeriesId) return;
    setComputing(true);
    setComputeError(null);
    try {
      const created = await api.computeQuantification(computeSeriesId, fillGaps);
      await refresh();
      const features = created.find((d) => d.kind === 'features');
      const tracking = created.find((d) => d.kind === 'tracking');
      if (features) setFeatureId(features.id);
      if (tracking) setTrackingId(tracking.id);
    } catch (e) {
      setComputeError(e instanceof Error ? e.message : String(e));
    } finally {
      setComputing(false);
    }
  }

  async function handleUpload(file: File | null) {
    if (!file) return;
    const name = uploadName || file.name;
    setBusy(true);
    setError(null);
    try {
      const created = await api.uploadDataset(pid, name, uploadKind, file);
      await refresh();
      if (created.kind === 'features') setFeatureId(created.id);
      else setTrackingId(created.id);
      setUploadName('');
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const featureDatasets = datasets.filter((d) => d.kind === 'features');
  const trackingDatasets = datasets.filter((d) => d.kind === 'tracking');

  return (
    <div className="quant-page">
      <header className="quant-header">
        <Link to="/" className="back-link">
          ← Projects
        </Link>
        <Link to={`/project/${pid}/viewer`} className="nav-link">
          ← Viewer
        </Link>
        <h2>Quantification</h2>

        <div className="quant-compute">
          <select
            value={computeSeriesId ?? ''}
            onChange={(e) => setComputeSeriesId(e.target.value ? Number(e.target.value) : null)}
            disabled={computing}
          >
            {seriesList.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.frame_count} frame{s.frame_count === 1 ? '' : 's'})
              </option>
            ))}
          </select>
          <label className="quant-fill-gaps">
            <input
              type="checkbox"
              checked={fillGaps}
              onChange={(e) => setFillGaps(e.target.checked)}
              disabled={computing}
            />
            Fill short segmentation gaps
          </label>
          <button onClick={handleCompute} disabled={computing || !computeSeriesId}>
            {computing ? 'Computing…' : 'Compute Quantification'}
          </button>
          <span className="quant-compute-hint">
            Geometry, per-channel intensity, and (for movies) tracking -- from that series'
            saved segmentation.
            {fillGaps &&
              ' Gaps get an approximate mask copied from the nearest real frames (tagged "interpolated" in the feature table) -- not a real measurement.'}
          </span>
          {computeError && <span className="error-text">{computeError}</span>}
        </div>

        <div className="quant-upload">
          <input
            placeholder="Dataset name"
            value={uploadName}
            onChange={(e) => setUploadName(e.target.value)}
          />
          <select value={uploadKind} onChange={(e) => setUploadKind(e.target.value as 'features' | 'tracking')}>
            <option value="features">Features</option>
            <option value="tracking">Tracking</option>
          </select>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.json"
            disabled={busy}
            onChange={(e) => handleUpload(e.target.files?.[0] ?? null)}
          />
          {error && <span className="error-text">{error}</span>}
        </div>
      </header>

      <div className="quant-body">
        <section className="quant-section">
          <div className="quant-section-header">
            <h3>Feature table</h3>
            <div className="quant-section-header-controls">
              <select
                value={featureId ?? ''}
                onChange={(e) => setFeatureId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">(select dataset)</option>
                {featureDatasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
              {featureId && (
                <a
                  className="quant-download-btn"
                  href={api.datasetDownloadUrl(featureId)}
                  download
                >
                  Download CSV
                </a>
              )}
            </div>
          </div>
          <div className="quant-section-body">
            {featureId ? <FeatureTable datasetId={featureId} /> : <EmptyHint />}
          </div>
        </section>

        <section className="quant-section">
          <div className="quant-section-header">
            <h3>t-SNE</h3>
          </div>
          <div className="quant-section-body">
            {featureId ? <TsnePlot datasetId={featureId} /> : <EmptyHint />}
          </div>
        </section>

        <section className="quant-section quant-section-wide">
          <div className="quant-section-header">
            <h3>Tracking / lineage tree</h3>
            <select
              value={trackingId ?? ''}
              onChange={(e) => setTrackingId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">(select dataset)</option>
              {trackingDatasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
          <div className="quant-section-body">
            {trackingId ? <TrackingTree datasetId={trackingId} /> : <EmptyHint />}
          </div>
        </section>
      </div>
    </div>
  );
}

function EmptyHint() {
  return <div className="quant-empty-hint">Upload a dataset above to get started.</div>;
}
