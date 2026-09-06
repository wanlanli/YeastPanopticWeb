import { interpolateRgbBasis, scaleLinear, scaleOrdinal } from 'd3';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { TsneResult } from '../../api/types';
import { CATEGORICAL, INK, SEQUENTIAL_BLUE } from './palette';
import './TsnePlot.css';

interface Props {
  datasetId: number;
}

const MARGIN = { top: 16, right: 16, bottom: 16, left: 16 };

export function TsnePlot({ datasetId }: Props) {
  const [columns, setColumns] = useState<string[]>([]);
  const [colorBy, setColorBy] = useState<string>('');
  const [perplexity, setPerplexity] = useState(30);
  const [result, setResult] = useState<TsneResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 480, height: 420 });

  useEffect(() => {
    api.getFeatures(datasetId, 0, 1).then((page) => setColumns(page.columns));
  }, [datasetId]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .getTsne(datasetId, perplexity, colorBy || undefined)
      .then(setResult)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [datasetId, perplexity, colorBy]);

  const width = size.width;
  const height = size.height;
  const innerW = Math.max(10, width - MARGIN.left - MARGIN.right);
  const innerH = Math.max(10, height - MARGIN.top - MARGIN.bottom);

  const xScale = useMemo(() => {
    if (!result || result.x.length === 0) return scaleLinear().domain([0, 1]).range([0, innerW]);
    const [lo, hi] = [Math.min(...result.x), Math.max(...result.x)];
    return scaleLinear().domain([lo, hi]).nice().range([0, innerW]);
  }, [result, innerW]);

  const yScale = useMemo(() => {
    if (!result || result.y.length === 0) return scaleLinear().domain([0, 1]).range([innerH, 0]);
    const [lo, hi] = [Math.min(...result.y), Math.max(...result.y)];
    return scaleLinear().domain([lo, hi]).nice().range([innerH, 0]);
  }, [result, innerH]);

  const colorInfo = useMemo(() => {
    if (!result?.color_values) return null;
    const values = result.color_values;
    const isNumeric = values.every((v) => v === null || typeof v === 'number');
    if (isNumeric) {
      const nums = values.filter((v): v is number => typeof v === 'number');
      const lo = Math.min(...nums);
      const hi = Math.max(...nums);
      const scale = scaleLinear().domain([lo, hi]).range([0, 1]);
      const interpolate = interpolateRgbBasis(SEQUENTIAL_BLUE);
      return {
        kind: 'sequential' as const,
        lo,
        hi,
        colorFor: (v: unknown) => (typeof v === 'number' ? interpolate(scale(v)) : INK.muted),
      };
    }
    const unique = Array.from(new Set(values.map((v) => String(v)))).slice(0, 8);
    const ordinal = scaleOrdinal<string, string>().domain(unique).range(CATEGORICAL);
    return {
      kind: 'categorical' as const,
      categories: unique,
      colorFor: (v: unknown) =>
        v === null || !unique.includes(String(v)) ? INK.muted : ordinal(String(v)),
    };
  }, [result]);

  return (
    <div className="tsne-panel">
      <div className="tsne-controls">
        <label>
          Color by
          <select value={colorBy} onChange={(e) => setColorBy(e.target.value)}>
            <option value="">(none)</option>
            {columns.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label>
          Perplexity
          <input
            type="number"
            min={2}
            max={100}
            value={perplexity}
            onChange={(e) => setPerplexity(Number(e.target.value))}
          />
        </label>
        {loading && <span className="tsne-loading">computing…</span>}
        {error && <span className="tsne-error">{error}</span>}
      </div>

      <div className="tsne-plot-area" ref={containerRef}>
        {result && (
          <svg width={width} height={height}>
            <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
              {result.x.map((x, i) => {
                const y = result.y[i];
                const colorValue = result.color_values ? result.color_values[i] : undefined;
                const fill = colorInfo ? colorInfo.colorFor(colorValue) : CATEGORICAL[0];
                return (
                  <circle
                    key={i}
                    cx={xScale(x)}
                    cy={yScale(y)}
                    r={hoverIdx === i ? 6 : 4}
                    fill={fill}
                    stroke={hoverIdx === i ? INK.primary : 'rgba(0,0,0,0.3)'}
                    strokeWidth={hoverIdx === i ? 1.5 : 0.5}
                    onMouseEnter={() => setHoverIdx(i)}
                    onMouseLeave={() => setHoverIdx((cur) => (cur === i ? null : cur))}
                  />
                );
              })}
            </g>
          </svg>
        )}

        {result && hoverIdx !== null && (
          <div className="tsne-tooltip">
            <div>
              <strong>id:</strong> {String(result.ids[hoverIdx])}
            </div>
            {result.color_by && (
              <div>
                <strong>{result.color_by}:</strong> {String(result.color_values?.[hoverIdx])}
              </div>
            )}
          </div>
        )}
      </div>

      {colorInfo?.kind === 'categorical' && (
        <div className="tsne-legend">
          {colorInfo.categories.map((cat, i) => (
            <span key={cat} className="tsne-legend-item">
              <span className="tsne-swatch" style={{ background: CATEGORICAL[i % CATEGORICAL.length] }} />
              {cat}
            </span>
          ))}
        </div>
      )}
      {colorInfo?.kind === 'sequential' && (
        <div className="tsne-legend tsne-legend-sequential">
          <span>{colorInfo.lo.toFixed(2)}</span>
          <span className="tsne-gradient" />
          <span>{colorInfo.hi.toFixed(2)}</span>
        </div>
      )}
    </div>
  );
}
