import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Series } from '../api/types';
import { ContrastControls } from '../components/viewer/ContrastControls';
import { FrameNavigator } from '../components/viewer/FrameNavigator';
import { ImageCanvas } from '../components/viewer/ImageCanvas';
import { Toolbar } from '../components/viewer/Toolbar';
import { useViewerStore } from '../store/useViewerStore';
import './Viewer.css';

export function Viewer() {
  const { projectId } = useParams();
  const pid = Number(projectId);
  const [seriesList, setSeriesList] = useState<Series[]>([]);
  const [newSeriesName, setNewSeriesName] = useState('');
  const [newSeriesPath, setNewSeriesPath] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const series = useViewerStore((s) => s.series);
  const setSeries = useViewerStore((s) => s.setSeries);

  async function refreshSeries() {
    const list = await api.listSeries(pid);
    setSeriesList(list);
    return list;
  }

  useEffect(() => {
    refreshSeries();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  async function handleRegisterPath() {
    if (!newSeriesName || !newSeriesPath) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.registerSeriesPath(pid, newSeriesName, newSeriesPath);
      await refreshSeries();
      setSeries(created);
      setNewSeriesName('');
      setNewSeriesPath('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(files: FileList | null) {
    if (!files || files.length === 0) return;
    const name = newSeriesName || files[0].name;
    setBusy(true);
    setError(null);
    try {
      const created = await api.uploadSeries(pid, name, files);
      await refreshSeries();
      setSeries(created);
      setNewSeriesName('');
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="viewer-page">
      <aside className="viewer-sidebar">
        <Link to="/" className="back-link">
          ← Projects
        </Link>
        <Link to={`/project/${pid}/quantification`} className="nav-link">
          Quantification →
        </Link>

        <h3>Image series</h3>
        <ul className="series-list">
          {seriesList.map((s) => (
            <li key={s.id}>
              <button
                className={series?.id === s.id ? 'active' : ''}
                onClick={() => setSeries(s)}
                title={`${s.width}x${s.height}, ${s.frame_count} frames, ${s.dtype}`}
              >
                {s.name}
                <span className="series-meta">
                  {s.frame_count} frame{s.frame_count === 1 ? '' : 's'}
                </span>
              </button>
            </li>
          ))}
          {seriesList.length === 0 && <li className="empty-hint">No series yet</li>}
        </ul>

        <div className="add-series">
          <h4>Add series</h4>
          <input
            placeholder="Name"
            value={newSeriesName}
            onChange={(e) => setNewSeriesName(e.target.value)}
          />
          <div className="add-series-row">
            <input
              placeholder="Server-side folder or .tif path"
              value={newSeriesPath}
              onChange={(e) => setNewSeriesPath(e.target.value)}
            />
            <button onClick={handleRegisterPath} disabled={busy || !newSeriesName || !newSeriesPath}>
              Register
            </button>
          </div>
          <div className="add-series-row">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".tif,.tiff,.png,.jpg,.jpeg"
              onChange={(e) => handleUpload(e.target.files)}
              disabled={busy}
            />
          </div>
          {error && <div className="error-text">{error}</div>}
        </div>
      </aside>

      <main className="viewer-main">
        <Toolbar />
        <ContrastControls />
        <ImageCanvas />
        <FrameNavigator />
      </main>
    </div>
  );
}
