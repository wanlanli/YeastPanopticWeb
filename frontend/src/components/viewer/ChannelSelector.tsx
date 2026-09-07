import { useState } from 'react';
import { api } from '../../api/client';
import { useViewerStore } from '../../store/useViewerStore';
import './ChannelSelector.css';

function channelLabel(names: string[] | null, index: number): string {
  return names?.[index] ?? `Channel ${index + 1}`;
}

export function ChannelSelector() {
  const series = useViewerStore((s) => s.series);
  const setSeries = useViewerStore((s) => s.setSeries);
  const viewChannel = useViewerStore((s) => s.viewChannel);
  const setViewChannel = useViewerStore((s) => s.setViewChannel);
  const [saving, setSaving] = useState(false);

  if (!series || series.channel_count <= 1) return null;

  const dicIndex = series.dic_channel_index;
  const channels = Array.from({ length: series.channel_count }, (_, i) => i);

  async function setSegmentationChannel(index: number) {
    if (!series) return;
    setSaving(true);
    try {
      const updated = await api.setSeriesChannel(series.id, index);
      setSeries(updated);
      setViewChannel(index);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="channel-selector">
      <label>
        Viewing
        <select value={viewChannel} onChange={(e) => setViewChannel(Number(e.target.value))}>
          {channels.map((i) => (
            <option key={i} value={i}>
              {channelLabel(series.channel_names, i)}
              {i === dicIndex ? ' (segmentation)' : ''}
            </option>
          ))}
        </select>
      </label>

      {dicIndex === null ? (
        <span className="channel-selector-warning">
          Pick the segmentation channel (usually DIC/brightfield) below -- it couldn't be
          auto-detected from this file's metadata.
        </span>
      ) : null}

      <label>
        Segmentation channel
        <select
          value={dicIndex ?? ''}
          disabled={saving}
          onChange={(e) => setSegmentationChannel(Number(e.target.value))}
        >
          {dicIndex === null && <option value="" disabled></option>}
          {channels.map((i) => (
            <option key={i} value={i}>
              {channelLabel(series.channel_names, i)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
