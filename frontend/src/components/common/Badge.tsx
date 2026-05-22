import type { FrictionCategory } from '../../types/scoring';

const CATEGORY_LABELS: Record<string, string> = {
  reporting_fragmentation: 'Reporting',
  process_inefficiency: 'Process',
  tooling_inconsistency: 'Tooling',
  scaling_strain: 'Scaling',
  customer_experience_friction: 'CX',
};

const CATEGORY_STYLES: Record<string, string> = {
  reporting_fragmentation: 'bg-blue-500/10 text-blue-400 ring-blue-500/20',
  process_inefficiency: 'bg-amber-500/10 text-amber-400 ring-amber-500/20',
  tooling_inconsistency: 'bg-violet-500/10 text-violet-400 ring-violet-500/20',
  scaling_strain: 'bg-teal-500/10 text-teal-400 ring-teal-500/20',
  customer_experience_friction: 'bg-red-500/10 text-red-400 ring-red-500/20',
};

interface Props {
  type: FrictionCategory | string;
  size?: 'sm' | 'md';
}

export function FrictionTypeBadge({ type, size = 'md' }: Props) {
  if (!type) {
    const sizeClass = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-xs px-2.5 py-1';
    return (
      <span
        className={`inline-flex items-center font-medium rounded ring-1 ring-inset bg-white/5 text-gray-500 ring-white/10 ${sizeClass}`}
      >
        Insufficient Evidence
      </span>
    );
  }

  const label = CATEGORY_LABELS[type] ?? type;
  const style = CATEGORY_STYLES[type] ?? 'bg-white/5 text-gray-400 ring-white/10';
  const sizeClass = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-xs px-2.5 py-1';

  return (
    <span
      className={`inline-flex items-center font-medium rounded ring-1 ring-inset ${style} ${sizeClass}`}
    >
      {label}
    </span>
  );
}

interface ScoreBadgeProps {
  score: number | null | undefined;
}

export function ScoreBadge({ score }: ScoreBadgeProps) {
  if (score == null) {
    return <span className="text-xs text-gray-600 font-mono">—</span>;
  }
  const color =
    score >= 7
      ? 'text-red-400 bg-red-500/10 ring-red-500/20'
      : score >= 4
      ? 'text-amber-400 bg-amber-500/10 ring-amber-500/20'
      : 'text-gray-400 bg-white/5 ring-white/10';
  return (
    <span
      className={`inline-flex items-center text-sm font-semibold rounded px-2 py-0.5 ring-1 ring-inset ${color}`}
    >
      {score.toFixed(1)}
    </span>
  );
}

interface CollectionStatusBadgeProps {
  status: string;
}

export function CollectionStatusBadge({ status }: CollectionStatusBadgeProps) {
  const styles: Record<string, string> = {
    completed: 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/20',
    running: 'bg-blue-500/10 text-blue-400 ring-blue-500/20',
    pending: 'bg-white/5 text-gray-400 ring-white/10',
    failed: 'bg-red-500/10 text-red-400 ring-red-500/20',
  };
  const style = styles[status] ?? styles.pending;
  return (
    <span
      className={`inline-flex items-center text-xs font-medium rounded px-2 py-0.5 ring-1 ring-inset ${style}`}
    >
      {status}
    </span>
  );
}