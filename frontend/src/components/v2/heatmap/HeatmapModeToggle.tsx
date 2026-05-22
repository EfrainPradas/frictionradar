import type { HeatmapMode } from '../../../data/mockHeatmap';

interface Option {
  value: HeatmapMode;
  label: string;
  hint: string;
}

const OPTIONS: Option[] = [
  { value: 'intensity', label: 'Pain Intensity', hint: 'How acute is the friction right now' },
  { value: 'velocity', label: 'Velocity', hint: 'Is pain growing, stable, or fading' },
  { value: 'opportunity', label: 'Opportunity', hint: 'Pain weighted by buying signals' },
];

interface Props {
  value: HeatmapMode;
  onChange: (mode: HeatmapMode) => void;
}

export function HeatmapModeToggle({ value, onChange }: Props) {
  return (
    <div className="inline-flex items-center p-1 rounded-lg border border-fr-line bg-fr-paper">
      {OPTIONS.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            title={opt.hint}
            className={`px-3.5 py-1.5 text-[12px] font-medium rounded-md transition-colors ${
              active
                ? 'bg-fr-ink text-fr-paper shadow-sm'
                : 'text-fr-ink-mute hover:text-fr-ink'
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
