import { useState } from 'react';
import { api } from '../../api/client';
import { useViewerStore } from '../../store/useViewerStore';
import './FrameMeasurePanel.css';

function toCsv(columns: string[], rows: Record<string, unknown>[]): string {
  const escape = (v: unknown) => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [columns.map(escape).join(',')];
  for (const row of rows) {
    lines.push(columns.map((c) => escape(row[c])).join(','));
  }
  return lines.join('\n');
}

/** Strip a file extension, if any (e.g. "cell_003.tif" -> "cell_003"). */
function stripExt(name: string): string {
  const i = name.lastIndexOf('.');
  return i > 0 ? name.slice(0, i) : name;
}

// columns that are inherently whole numbers (ids), never physical
// measurements -- shown as plain integers regardless of resolution
const INTEGER_COLUMNS = new Set(['label']);

function formatCell(column: string, value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value !== 'number') return String(value);
  return INTEGER_COLUMNS.has(column) ? String(Math.round(value)) : value.toFixed(2);
}

export function FrameMeasurePanel() {
  const series = useViewerStore((s) => s.series);
  const frameIndex = useViewerStore((s) => s.frameIndex);
  const frameNames = useViewerStore((s) => s.frameNames);
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [measuredFrame, setMeasuredFrame] = useState<number | null>(null);
  const [resolution, setResolution] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleMeasure() {
    if (!series) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.measureFrame(series.id, frameIndex, resolution);
      setColumns(result.columns);
      setRows(result.rows);
      setMeasuredFrame(frameIndex);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function handleOutput() {
    if (!series || rows.length === 0) return;
    const sourceName =
      (measuredFrame !== null && frameNames?.[measuredFrame] && stripExt(frameNames[measuredFrame])) ||
      (series.original_filename && stripExt(series.original_filename)) ||
      series.name;
    const csv = toCsv(columns, rows);
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${sourceName}_frame${measuredFrame}_measurements.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const stale = measuredFrame !== null && measuredFrame !== frameIndex;

  return (
    <div className="frame-measure-panel">
      <div className="frame-measure-header">
        <button onClick={handleMeasure} disabled={!series || loading}>
          {loading ? 'Measuring…' : 'Measure'}
        </button>
        <button onClick={handleOutput} disabled={rows.length === 0}>
          Output CSV
        </button>
        <label className="frame-measure-resolution">
          Resolution
          <input
            type="number"
            step="any"
            min={0}
            value={resolution}
            onChange={(e) => setResolution(Number(e.target.value))}
            title="Physical size of one pixel (e.g. um/px) -- area/length columns are scaled by it. Leave at 1 for raw pixel units."
          />
        </label>
        <span className="frame-measure-hint">
          Basic geometry (area, skeleton lengths, ...) for this frame's saved objects -- no
          intensity, no tracking. Click Measure after editing the frame.
        </span>
      </div>

      {error && <div className="frame-measure-error">{error}</div>}
      {stale && !loading && (
        <div className="frame-measure-stale">
          Showing frame {measuredFrame} -- click Measure to update for frame {frameIndex}.
        </div>
      )}

      <div className="frame-measure-table-scroll">
        {rows.length > 0 ? (
          <table>
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {columns.map((c) => (
                    <td key={c}>{formatCell(c, row[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          !loading && <div className="frame-measure-empty">Click Measure to compute this frame's object measurements.</div>
        )}
      </div>
    </div>
  );
}
