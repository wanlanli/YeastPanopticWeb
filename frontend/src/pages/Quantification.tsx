import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { MeasurementRegion, QuantificationDataset, Series } from '../api/types';
import { FeatureTable } from '../components/quantification/FeatureTable';
import { RegionDemo } from '../components/quantification/RegionDemo';
import './Quantification.css';

const REGIONS: MeasurementRegion[] = ['cytoplasm', 'membrane', 'skeleton'];

export function Quantification() {
  const { projectId } = useParams();
  const pid = Number(projectId);

  const [seriesList, setSeriesList] = useState<Series[]>([]);
  const [seriesId, setSeriesId] = useState<number | null>(null);
  const series = seriesList.find((s) => s.id === seriesId) ?? null;

  const [datasets, setDatasets] = useState<QuantificationDataset[]>([]);
  const [featureId, setFeatureId] = useState<number | null>(null);

  const [channelIndex, setChannelIndex] = useState<number | null>(null);
  const [region, setRegion] = useState<MeasurementRegion>('cytoplasm');
  const [resolution, setResolution] = useState(1);
  const [measuring, setMeasuring] = useState(false);
  const [measureError, setMeasureError] = useState<string | null>(null);

  const [uploadName, setUploadName] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.listSeries(pid).then((list) => {
      setSeriesList(list);
      if (list.length) setSeriesId(list[0].id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  async function refreshDatasets() {
    const list = await api.listDatasets(pid);
    setDatasets(list);
  }

  useEffect(() => {
    refreshDatasets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  // channels available to measure from -- every imaging channel except the
  // one used for segmentation (DIC); reset the selection whenever the
  // series changes since a different series has different channels
  const channelOptions =
    series && series.channel_names
      ? series.channel_names
          .map((name, i) => ({ index: i, name }))
          .filter((c) => c.index !== (series.dic_channel_index ?? 0))
      : [];

  useEffect(() => {
    setChannelIndex(channelOptions.length ? channelOptions[0].index : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seriesId]);

  // this series' own feature datasets (from Measure, or hand-uploaded) --
  // scoped to the series selected at the top of the page
  const seriesFeatureDatasets = datasets.filter((d) => d.kind === 'features' && d.series_id === seriesId);

  useEffect(() => {
    setFeatureId(seriesFeatureDatasets.length ? seriesFeatureDatasets[0].id : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seriesId, datasets]);

  async function handleMeasure() {
    if (!seriesId || channelIndex === null) return;
    setMeasuring(true);
    setMeasureError(null);
    try {
      const [created] = await api.measureRegionIntensity(seriesId, channelIndex, region, resolution);
      await refreshDatasets();
      if (created) setFeatureId(created.id);
    } catch (e) {
      setMeasureError(e instanceof Error ? e.message : String(e));
    } finally {
      setMeasuring(false);
    }
  }

  async function handleUpload(file: File | null) {
    if (!file || !seriesId) return;
    const name = uploadName || file.name;
    setBusy(true);
    setUploadError(null);
    try {
      const created = await api.uploadDataset(pid, name, 'features', file, seriesId);
      await refreshDatasets();
      setFeatureId(created.id);
      setUploadName('');
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

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

        <select
          className="quant-series-select"
          value={seriesId ?? ''}
          onChange={(e) => setSeriesId(e.target.value ? Number(e.target.value) : null)}
        >
          {seriesList.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} ({s.frame_count} frame{s.frame_count === 1 ? '' : 's'})
            </option>
          ))}
        </select>
      </header>

      <section className="quant-measure">
        <h3>Measure</h3>
        {channelOptions.length === 0 ? (
          <span className="quant-measure-hint">
            This series has no separate fluorescent channels to measure intensity from.
          </span>
        ) : (
          <>
            <label className="quant-measure-field">
              Channel
              <select
                value={channelIndex ?? ''}
                onChange={(e) => setChannelIndex(Number(e.target.value))}
                disabled={measuring}
              >
                {channelOptions.map((c) => (
                  <option key={c.index} value={c.index}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="quant-measure-field">
              Measure from
              <select value={region} onChange={(e) => setRegion(e.target.value as MeasurementRegion)} disabled={measuring}>
                {REGIONS.map((r) => (
                  <option key={r} value={r}>
                    {r === 'cytoplasm' ? 'Cytoplasm (whole area)' : r === 'membrane' ? 'Membrane (outline)' : 'Centerline (skeleton)'}
                  </option>
                ))}
              </select>
            </label>
            <RegionDemo region={region} />
            <label className="quant-measure-field">
              Resolution
              <input
                type="number"
                step="any"
                min={0}
                value={resolution}
                onChange={(e) => setResolution(Number(e.target.value))}
                disabled={measuring}
                title="Physical size of one pixel (e.g. um/px) -- area/length columns are scaled by it. Leave at 1 for raw pixel units."
              />
            </label>
            <button onClick={handleMeasure} disabled={measuring || !seriesId || channelIndex === null}>
              {measuring ? 'Measuring…' : 'Measure'}
            </button>
            {measureError && <span className="error-text">{measureError}</span>}
          </>
        )}
      </section>

      <div className="quant-body">
        <section className="quant-section">
          <div className="quant-section-header">
            <h3>Quantification table</h3>
            <div className="quant-section-header-controls">
              <select
                value={featureId ?? ''}
                onChange={(e) => setFeatureId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">(select dataset)</option>
                {seriesFeatureDatasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
              {featureId && (
                <a className="quant-download-btn" href={api.datasetDownloadUrl(featureId)} download>
                  Download CSV
                </a>
              )}
            </div>
          </div>
          <div className="quant-section-body">
            {featureId ? (
              <FeatureTable datasetId={featureId} />
            ) : (
              <div className="quant-empty-hint">
                Click "Measure" above, or upload a features CSV/JSON for this series below.
              </div>
            )}
          </div>
        </section>
      </div>

      <div className="quant-upload">
        <input placeholder="Dataset name" value={uploadName} onChange={(e) => setUploadName(e.target.value)} />
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.json"
          disabled={busy || !seriesId}
          onChange={(e) => handleUpload(e.target.files?.[0] ?? null)}
        />
        <span className="quant-upload-hint">Upload your own features CSV/JSON for the selected series</span>
        {uploadError && <span className="error-text">{uploadError}</span>}
      </div>
    </div>
  );
}
