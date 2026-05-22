import type { HeatmapMode } from '../../../data/mockHeatmap';
import { colorForIntensity, colorForOpportunity, colorForVelocity } from './palette';

interface Props {
  mode: HeatmapMode;
}

export function HeatmapLegend({ mode }: Props) {
  if (mode === 'velocity') {
    return (
      <div className="flex items-center gap-3 text-[11px] text-fr-ink-mute">
        <span className="font-mono tracking-wide text-fr-ink-faint">Pain fading</span>
        <div className="flex h-2.5 w-[180px] rounded-sm overflow-hidden border border-fr-line">
          {[-1, -0.66, -0.33, 0, 0.33, 0.66, 1].map((v) => (
            <div key={v} className="flex-1" style={{ background: colorForVelocity(v) }} />
          ))}
        </div>
        <span className="font-mono tracking-wide text-fr-ink-faint">Pain growing</span>
      </div>
    );
  }

  const colorFn = mode === 'opportunity' ? colorForOpportunity : colorForIntensity;
  const labelLow = mode === 'opportunity' ? 'Low fit' : 'Low pain';
  const labelHigh = mode === 'opportunity' ? 'High fit' : 'High pain';

  return (
    <div className="flex items-center gap-3 text-[11px] text-fr-ink-mute">
      <span className="font-mono tracking-wide text-fr-ink-faint">{labelLow}</span>
      <div className="flex h-2.5 w-[180px] rounded-sm overflow-hidden border border-fr-line">
        {[0, 16, 33, 50, 66, 83, 100].map((v) => (
          <div key={v} className="flex-1" style={{ background: colorFn(v) }} />
        ))}
      </div>
      <span className="font-mono tracking-wide text-fr-ink-faint">{labelHigh}</span>
    </div>
  );
}
