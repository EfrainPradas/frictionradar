import type { FrictionCategory } from '../../types/scoring';

const CATEGORY_LABELS: Record<string, string> = {
  reporting_fragmentation: 'Reporting Fragmentation',
  process_inefficiency: 'Process Inefficiency',
  tooling_inconsistency: 'Tooling Inconsistency',
  scaling_strain: 'Scaling Strain',
  customer_experience_friction: 'CX Friction',
};

const CATEGORY_STYLES: Record<string, string> = {
  reporting_fragmentation: 'bg-blue-50 text-blue-700 ring-blue-200',
  process_inefficiency: 'bg-orange-50 text-orange-700 ring-orange-200',
  tooling_inconsistency: 'bg-purple-50 text-purple-700 ring-purple-200',
  scaling_strain: 'bg-green-50 text-green-700 ring-green-200',
  customer_experience_friction: 'bg-red-50 text-red-700 ring-red-200',
};

interface Props {
  type: FrictionCategory | string;
  size?: 'sm' | 'md';
}

export function FrictionTypeBadge({ type, size = 'md' }: Props) {
  // Insufficient evidence — no diagnosis available
  if (!type) {
    const sizeClass = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-xs px-2.5 py-1';
    return (
      <span
        className={`inline-flex items-center font-medium rounded ring-1 ring-inset bg-gray-50 text-gray-400 ring-gray-200 ${sizeClass}`}
      >
        Insufficient Evidence
      </span>
    );
  }

  const label = CATEGORY_LABELS[type] ?? type;
  const style = CATEGORY_STYLES[type] ?? 'bg-gray-100 text-gray-600 ring-gray-200';
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
    return (
      <span className="text-xs text-gray-400 font-medium">Not scored</span>
    );
  }
  const color =
    score >= 7
      ? 'text-red-600 bg-red-50 ring-red-200'
      : score >= 4
      ? 'text-yellow-600 bg-yellow-50 ring-yellow-200'
      : 'text-gray-600 bg-gray-100 ring-gray-200';
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
    completed: 'bg-green-50 text-green-700 ring-green-200',
    running: 'bg-blue-50 text-blue-700 ring-blue-200',
    pending: 'bg-gray-100 text-gray-600 ring-gray-200',
    failed: 'bg-red-50 text-red-700 ring-red-200',
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
