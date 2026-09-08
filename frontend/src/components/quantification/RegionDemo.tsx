import type { MeasurementRegion } from '../../api/types';
import './RegionDemo.css';

const REGION_LABELS: Record<MeasurementRegion, string> = {
  cytoplasm: 'Cytoplasm — whole cell area',
  membrane: 'Membrane — outline only',
  skeleton: 'Centerline — skeleton only',
};

/** Small visual explanation of exactly which pixels a region option
 * measures intensity from -- picking a region name alone doesn't make it
 * obvious whether "membrane" means the outline or the interior, so show it. */
export function RegionDemo({ region }: { region: MeasurementRegion }) {
  return (
    <div className="region-demo">
      <svg viewBox="0 0 120 80" width="90" height="60" aria-hidden="true">
        <ellipse cx="60" cy="40" rx="48" ry="28" fill="none" stroke="#555" strokeWidth="1.5" />
        {region === 'cytoplasm' && <ellipse cx="60" cy="40" rx="45" ry="25" fill="#3d63dd" fillOpacity="0.5" />}
        {region === 'membrane' && (
          <ellipse cx="60" cy="40" rx="44.5" ry="24.5" fill="none" stroke="#3d63dd" strokeWidth="6" />
        )}
        {region === 'skeleton' && (
          <line x1="16" y1="40" x2="104" y2="40" stroke="#3d63dd" strokeWidth="4" strokeLinecap="round" />
        )}
      </svg>
      <span className="region-demo-label">{REGION_LABELS[region]}</span>
    </div>
  );
}
