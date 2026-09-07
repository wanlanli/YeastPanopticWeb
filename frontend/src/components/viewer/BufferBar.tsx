import './BufferBar.css';

interface Props {
  label: string;
  /** 0-1. Omit for an indeterminate (unknown-duration) bar. */
  progress?: number;
}

export function BufferBar({ label, progress }: Props) {
  return (
    <div className="buffer-bar">
      <div className="buffer-bar-label">{label}</div>
      <div className="buffer-bar-track">
        {progress === undefined ? (
          <div className="buffer-bar-fill buffer-bar-indeterminate" />
        ) : (
          <div
            className="buffer-bar-fill"
            style={{ width: `${Math.round(Math.max(0, Math.min(1, progress)) * 100)}%` }}
          />
        )}
      </div>
    </div>
  );
}
