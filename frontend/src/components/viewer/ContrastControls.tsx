import { useEffect, useState } from 'react';
import { useViewerStore } from '../../store/useViewerStore';
import './ContrastControls.css';

function maxForDtype(dtype: string): number {
  if (dtype.includes('16')) return 65535;
  if (dtype.includes('32')) return 65535; // treat float/32-bit as a wide window; user can still type exact values
  return 255;
}

export function ContrastControls() {
  const series = useViewerStore((s) => s.series);
  const vmin = useViewerStore((s) => s.vmin);
  const vmax = useViewerStore((s) => s.vmax);
  const setContrast = useViewerStore((s) => s.setContrast);
  const requestResetView = useViewerStore((s) => s.requestResetView);

  const rangeMax = series ? maxForDtype(series.dtype) : 255;
  const [localMin, setLocalMin] = useState(vmin ?? 0);
  const [localMax, setLocalMax] = useState(vmax ?? rangeMax);

  useEffect(() => {
    setLocalMin(vmin ?? 0);
    setLocalMax(vmax ?? rangeMax);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series?.id]);

  if (!series) return null;

  function commit(min: number, max: number) {
    setLocalMin(min);
    setLocalMax(max);
    setContrast(min, max);
  }

  return (
    <div className="contrast-controls">
      <div className="contrast-title">Contrast</div>
      <label>
        min
        <input
          type="range"
          min={0}
          max={rangeMax}
          value={localMin}
          onChange={(e) => commit(Number(e.target.value), Math.max(localMax, Number(e.target.value) + 1))}
        />
        <input
          type="number"
          value={localMin}
          onChange={(e) => commit(Number(e.target.value), localMax)}
        />
      </label>
      <label>
        max
        <input
          type="range"
          min={0}
          max={rangeMax}
          value={localMax}
          onChange={(e) => commit(Math.min(localMin, Number(e.target.value) - 1), Number(e.target.value))}
        />
        <input
          type="number"
          value={localMax}
          onChange={(e) => commit(localMin, Number(e.target.value))}
        />
      </label>
      <button onClick={() => setContrast(null, null)}>Auto</button>
      <button onClick={requestResetView} title="Re-center the image and reset zoom to fill the window">
        Fit to Window
      </button>
    </div>
  );
}
