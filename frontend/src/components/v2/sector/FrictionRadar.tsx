import type { RadarDim, SectorRadar } from '../../../data/mockSector';
import { RADAR_DIMENSIONS } from '../../../data/taxonomy';

interface Props {
  values: SectorRadar;
  centerValue?: number;
  centerLabel?: string;
  dominantDim?: RadarDim;
  onDimClick?: (dim: RadarDim) => void;
  size?: number;
}

const DIMS: RadarDim[] = ['reporting', 'process', 'tooling', 'scaling', 'cx'];

function labelFor(dim: RadarDim): string {
  return RADAR_DIMENSIONS.find((d) => d.slug === dim)?.label ?? dim;
}

export function FrictionRadar({
  values,
  centerValue,
  centerLabel,
  dominantDim,
  onDimClick,
  size = 360,
}: Props) {
  const cx = size / 2;
  const cy = size / 2;
  const radius = size * 0.36;
  const labelRadius = radius + 28;

  const angleFor = (i: number) => (Math.PI * 2 * i) / DIMS.length - Math.PI / 2;

  const point = (i: number, value: number) => {
    const a = angleFor(i);
    const r = (value / 100) * radius;
    return [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
  };

  const ringPoints = (r: number) =>
    DIMS.map((_, i) => {
      const a = angleFor(i);
      return `${cx + Math.cos(a) * r},${cy + Math.sin(a) * r}`;
    }).join(' ');

  const dataPolygon = DIMS.map((d, i) => point(i, values[d]).join(',')).join(' ');

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full h-auto" role="img" aria-label="Friction radar">
      {[0.25, 0.5, 0.75, 1].map((t) => (
        <polygon
          key={t}
          points={ringPoints(radius * t)}
          fill="none"
          stroke="var(--fr-line)"
          strokeWidth={1}
        />
      ))}

      {DIMS.map((_, i) => {
        const [x, y] = point(i, 100);
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={x}
            y2={y}
            stroke="var(--fr-line)"
            strokeWidth={1}
            strokeDasharray="2 4"
          />
        );
      })}

      <polygon
        points={dataPolygon}
        fill="rgba(164, 123, 43, 0.18)"
        stroke="var(--fr-gold)"
        strokeWidth={2}
        strokeLinejoin="round"
      />

      {DIMS.map((d, i) => {
        const [x, y] = point(i, values[d]);
        const isDom = dominantDim === d;
        return (
          <circle
            key={d}
            cx={x}
            cy={y}
            r={isDom ? 5 : 3.5}
            fill={isDom ? 'var(--fr-gold)' : 'var(--fr-paper)'}
            stroke="var(--fr-gold)"
            strokeWidth={2}
          />
        );
      })}

      {DIMS.map((d, i) => {
        const a = angleFor(i);
        const lx = cx + Math.cos(a) * labelRadius;
        const ly = cy + Math.sin(a) * labelRadius;
        const isDom = dominantDim === d;
        const anchor = Math.abs(Math.cos(a)) < 0.2 ? 'middle' : Math.cos(a) > 0 ? 'start' : 'end';
        return (
          <g
            key={d}
            transform={`translate(${lx} ${ly})`}
            style={{ cursor: onDimClick ? 'pointer' : 'default' }}
            onClick={onDimClick ? () => onDimClick(d) : undefined}
          >
            <text
              textAnchor={anchor}
              dy={4}
              className="select-none"
              fill={isDom ? 'var(--fr-ink)' : 'var(--fr-ink-mute)'}
              style={{
                fontSize: 11,
                fontWeight: isDom ? 700 : 600,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                fontFamily: 'JetBrains Mono, monospace',
              }}
            >
              {labelFor(d).toUpperCase()}
            </text>
            <text
              textAnchor={anchor}
              dy={18}
              fill="var(--fr-ink-faint)"
              style={{
                fontSize: 10,
                fontFamily: 'JetBrains Mono, monospace',
                fontWeight: 500,
              }}
            >
              {values[d]}
            </text>
          </g>
        );
      })}

      {centerValue !== undefined && (
        <g>
          <circle cx={cx} cy={cy} r={radius * 0.32} fill="var(--fr-paper)" stroke="var(--fr-line)" strokeWidth={1} />
          <text
            x={cx}
            y={cy + 4}
            textAnchor="middle"
            fill="var(--fr-ink)"
            style={{ fontSize: 30, fontWeight: 700, fontFamily: 'JetBrains Mono, monospace' }}
          >
            {centerValue}
          </text>
          {centerLabel && (
            <text
              x={cx}
              y={cy + 22}
              textAnchor="middle"
              fill="var(--fr-ink-faint)"
              style={{ fontSize: 9, fontFamily: 'JetBrains Mono, monospace', letterSpacing: '0.1em' }}
            >
              {centerLabel.toUpperCase()}
            </text>
          )}
        </g>
      )}
    </svg>
  );
}
