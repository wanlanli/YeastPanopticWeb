import { useEffect, useRef } from 'react';
import { api } from '../../api/client';
import { useViewerStore } from '../../store/useViewerStore';
import './FrameNavigator.css';

export function FrameNavigator() {
  const series = useViewerStore((s) => s.series);
  const frameIndex = useViewerStore((s) => s.frameIndex);
  const isPlaying = useViewerStore((s) => s.isPlaying);
  const frameNames = useViewerStore((s) => s.frameNames);
  const setFrameIndex = useViewerStore((s) => s.setFrameIndex);
  const setIsPlaying = useViewerStore((s) => s.setIsPlaying);
  const setFrameNames = useViewerStore((s) => s.setFrameNames);
  const intervalRef = useRef<number | null>(null);

  const frameCount = series?.frame_count ?? 0;
  const maxIndex = Math.max(0, frameCount - 1);

  useEffect(() => {
    if (!series) return;
    api.getFrameNames(series.id).then((res) => setFrameNames(res.names));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series?.id]);

  useEffect(() => {
    if (!isPlaying || !series) return;
    intervalRef.current = window.setInterval(() => {
      useViewerStore.setState((state) => {
        const next = state.frameIndex + 1;
        if (next > maxIndex) return { isPlaying: false, frameIndex: maxIndex };
        return { frameIndex: next };
      });
    }, 200);
    return () => {
      if (intervalRef.current) window.clearInterval(intervalRef.current);
    };
  }, [isPlaying, series, maxIndex]);

  if (!series) return null;

  return (
    <div className="frame-navigator">
      <button onClick={() => setFrameIndex(0)} title="First frame" disabled={frameIndex === 0}>
        |&lt;
      </button>
      <button
        onClick={() => setFrameIndex(frameIndex - 1)}
        title="Previous frame"
        disabled={frameIndex === 0}
      >
        &lt;
      </button>
      <button
        onClick={() => setIsPlaying(!isPlaying)}
        title={isPlaying ? 'Pause' : 'Play'}
        className="play-btn"
      >
        {isPlaying ? '⏸' : '▶'}
      </button>
      <button
        onClick={() => setFrameIndex(frameIndex + 1)}
        title="Next frame"
        disabled={frameIndex === maxIndex}
      >
        &gt;
      </button>
      <button
        onClick={() => setFrameIndex(maxIndex)}
        title="Last frame"
        disabled={frameIndex === maxIndex}
      >
        &gt;|
      </button>

      <input
        type="range"
        min={0}
        max={maxIndex}
        value={frameIndex}
        onChange={(e) => setFrameIndex(Number(e.target.value))}
        className="frame-slider"
      />

      <span className="frame-counter">
        frame{' '}
        <input
          type="number"
          min={0}
          max={maxIndex}
          value={frameIndex}
          onChange={(e) => setFrameIndex(Number(e.target.value))}
          className="frame-input"
        />
        {' / '}
        {maxIndex}
      </span>

      {frameNames && frameNames[frameIndex] && (
        <span className="frame-filename" title={frameNames[frameIndex]}>
          {frameNames[frameIndex]}
        </span>
      )}
    </div>
  );
}
