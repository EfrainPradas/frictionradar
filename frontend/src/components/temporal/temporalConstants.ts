import type {
  TemporalDiagnosticState,
  TemporalConfidence,
  EvidenceStrength,
  TrendDirection,
  PressureState,
  Magnitude,
} from '../../types/temporal';
import type { FrictionCategory } from '../../types/scoring';

// ── Diagnostic state display (dark theme) ────────────────────────────

export const DIAGNOSTIC_LABELS: Record<TemporalDiagnosticState, string> = {
  insufficient_temporal_data: 'INSUFFICIENT DATA',
  stable_low_friction: 'STABLE · LOW',
  stable_elevated_friction: 'STABLE · ELEVATED',
  emerging_pain: 'EMERGING PAIN',
  accelerating_pain: 'ACCELERATING',
  declining_pain: 'DECLINING',
  volatile_friction: 'VOLATILE',
};

export const DIAGNOSTIC_STYLES: Record<TemporalDiagnosticState, string> = {
  insufficient_temporal_data: 'bg-gray-500/10 text-gray-400 ring-gray-500/20',
  stable_low_friction: 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/20',
  stable_elevated_friction: 'bg-amber-500/10 text-amber-400 ring-amber-500/20',
  emerging_pain: 'bg-amber-500/15 text-amber-300 ring-amber-500/30',
  accelerating_pain: 'bg-red-500/10 text-red-400 ring-red-500/20',
  declining_pain: 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/20',
  volatile_friction: 'bg-orange-500/10 text-orange-400 ring-orange-500/20',
};

export const DIAGNOSTIC_DESCRIPTIONS: Record<TemporalDiagnosticState, string> = {
  insufficient_temporal_data: 'Not enough historical data to detect temporal patterns.',
  stable_low_friction: 'Friction is low and has remained stable over the lookback window.',
  stable_elevated_friction: 'Friction is elevated but stable — not worsening or improving.',
  emerging_pain: 'Signs of friction are beginning to appear that weren\'t present before.',
  accelerating_pain: 'Friction is increasing rapidly. The situation is getting worse.',
  declining_pain: 'Friction is decreasing. The company may be resolving operational pain.',
  volatile_friction: 'Friction levels are fluctuating unpredictably. No clear trend.',
};

// ── Diagnostic state animations ──────────────────────────────────────

export const DIAGNOSTIC_ANIMATIONS: Record<TemporalDiagnosticState, string> = {
  insufficient_temporal_data: '',
  stable_low_friction: '',
  stable_elevated_friction: '',
  emerging_pain: 'animate-state-emerging',
  accelerating_pain: 'animate-state-accelerating',
  declining_pain: '',
  volatile_friction: 'animate-state-volatile',
};

// ── Confidence display ─────────────────────────────────────────────

export const CONFIDENCE_LABELS: Record<TemporalConfidence, string> = {
  high: 'HIGH',
  moderate: 'MODERATE',
  low: 'LOW',
  none: 'NONE',
};

export const CONFIDENCE_STYLES: Record<TemporalConfidence, string> = {
  high: 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/20',
  moderate: 'bg-blue-500/10 text-blue-400 ring-blue-500/20',
  low: 'bg-amber-500/10 text-amber-400 ring-amber-500/20',
  none: 'bg-gray-500/10 text-gray-500 ring-gray-500/20',
};

// ── Trend direction ────────────────────────────────────────────────

export const TREND_LABELS: Record<TrendDirection, string> = {
  insufficient_temporal_data: 'NO TREND DATA',
  improving: 'IMPROVING',
  stable: 'STABLE',
  declining: 'DECLINING',
  volatile: 'VOLATILE',
};

export const TREND_STYLES: Record<TrendDirection, string> = {
  insufficient_temporal_data: 'text-gray-600',
  improving: 'text-emerald-400',
  stable: 'text-blue-400',
  declining: 'text-red-400',
  volatile: 'text-orange-400',
};

export const TREND_ARROWS: Record<TrendDirection, string> = {
  insufficient_temporal_data: '—',
  improving: '↓',
  stable: '→',
  declining: '↑',
  volatile: '↕',
};

// ── Pressure state ──────────────────────────────────────────────────

export const PRESSURE_LABELS: Record<PressureState, string> = {
  accelerating: 'ACCELERATING',
  decelerating: 'DECELERATING',
  stable: 'STEADY',
  signal_spike: 'SPIKE',
  signal_drought: 'DROUGHT',
  insufficient_data: 'NO DATA',
};

export const PRESSURE_STYLES: Record<PressureState, string> = {
  accelerating: 'bg-red-500/10 text-red-400 ring-red-500/20',
  decelerating: 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/20',
  stable: 'bg-blue-500/10 text-blue-400 ring-blue-500/20',
  signal_spike: 'bg-amber-500/10 text-amber-400 ring-amber-500/20',
  signal_drought: 'bg-gray-500/10 text-gray-400 ring-gray-500/20',
  insufficient_data: 'bg-gray-500/5 text-gray-600 ring-gray-500/10',
};

// ── Magnitude ───────────────────────────────────────────────────────

export const MAGNITUDE_LABELS: Record<Magnitude, string> = {
  negligible: 'NEGLIGIBLE',
  mild: 'MILD',
  moderate: 'MODERATE',
  strong: 'STRONG',
};

// ── Evidence strength ───────────────────────────────────────────────

export const EVIDENCE_STYLES: Record<EvidenceStrength, string> = {
  strong: 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/20',
  moderate: 'bg-blue-500/10 text-blue-400 ring-blue-500/20',
  weak: 'bg-amber-500/10 text-amber-400 ring-amber-500/20',
};

// ── Friction category display ───────────────────────────────────────

export const CATEGORY_LABELS: Record<FrictionCategory, string> = {
  reporting_fragmentation: 'Reporting',
  process_inefficiency: 'Process',
  tooling_inconsistency: 'Tooling',
  scaling_strain: 'Scaling',
  customer_experience_friction: 'CX',
};

export const CATEGORY_STYLES: Record<FrictionCategory, string> = {
  reporting_fragmentation: 'bg-blue-500/10 text-blue-400',
  process_inefficiency: 'bg-amber-500/10 text-amber-400',
  tooling_inconsistency: 'bg-violet-500/10 text-violet-400',
  scaling_strain: 'bg-teal-500/10 text-teal-400',
  customer_experience_friction: 'bg-red-500/10 text-red-400',
};

// ── Shared badge class ──────────────────────────────────────────────

export const BADGE_BASE = 'inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold tracking-wider uppercase ring-1 ring-inset';