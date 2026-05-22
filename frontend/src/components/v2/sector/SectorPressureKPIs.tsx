import type { SectorAggregate } from '../../../data/mockSector';

interface Props {
  sector: SectorAggregate;
}

function pressureBand(p: number): string {
  if (p >= 80) return 'Critical to Sustain';
  if (p >= 65) return 'Elevated to Sustain';
  if (p >= 50) return 'Manageable to Sustain';
  return 'Stable';
}

export function SectorPressureKPIs({ sector }: Props) {
  const velSign = sector.velocityPct >= 0 ? '+' : '';
  const velTone = sector.velocityPct > 5 ? 'text-orange-600' : sector.velocityPct < -5 ? 'text-emerald-600' : 'text-fr-ink-soft';
  return (
    <div className="grid grid-cols-3 gap-3">
      <KPI label="Sector Pressure" value={sector.pressure} hint={pressureBand(sector.pressure)} />
      <KPI label="Signal Velocity" value={`${velSign}${sector.velocityPct}%`} hint="Last 30 days" tone={velTone} />
      <KPI label="Companies Tracked" value={sector.companiesTracked} hint="In current quarter" />
    </div>
  );
}

function KPI({ label, value, hint, tone }: { label: string; value: number | string; hint: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-fr-line bg-fr-paper px-4 py-3">
      <div className="text-[10px] font-mono tracking-[0.12em] uppercase text-fr-ink-faint">{label}</div>
      <div className={`mt-1 text-[24px] font-semibold tabular-nums ${tone ?? 'text-fr-ink'}`}>{value}</div>
      <div className="text-[11px] text-fr-ink-mute mt-0.5">{hint}</div>
    </div>
  );
}
