// ── Enums ──────────────────────────────────────────────────────────────

export type TrendDirection =
  | 'insufficient_temporal_data'
  | 'improving'
  | 'stable'
  | 'declining'
  | 'volatile';

export type Magnitude = 'negligible' | 'mild' | 'moderate' | 'strong';

export type LookbackWindow = '7d' | '30d' | '90d' | '180d';

export type VelocityWindow = 'daily' | 'weekly' | '30d_rolling' | '90d_rolling';

export type PressureState =
  | 'accelerating'
  | 'decelerating'
  | 'stable'
  | 'signal_spike'
  | 'signal_drought'
  | 'insufficient_data';

export type SignalClass = 'scored' | 'discovery';

export type TemporalDiagnosticState =
  | 'insufficient_temporal_data'
  | 'stable_low_friction'
  | 'stable_elevated_friction'
  | 'emerging_pain'
  | 'accelerating_pain'
  | 'declining_pain'
  | 'volatile_friction';

export type TemporalConfidence = 'high' | 'moderate' | 'low' | 'none';

export type EvidenceStrength = 'strong' | 'moderate' | 'weak';

// ── Delta ─────────────────────────────────────────────────────────────

export interface CategoryDelta {
  category: string;
  current_normalized: number;
  previous_normalized: number;
  delta: number;
  trend: TrendDirection;
  magnitude: Magnitude;
  evidence: string;
}

export interface OverallDelta {
  current_total: number;
  previous_total: number;
  delta: number;
  trend: TrendDirection;
  magnitude: Magnitude;
  dominant_shift: string | null;
}

export interface TemporalDeltasResponse {
  company_id: string;
  lookback_window: LookbackWindow;
  lookback_days: number;
  snapshot_count: number;
  current_computed_at: string | null;
  previous_computed_at: string | null;
  category_deltas: CategoryDelta[];
  overall: OverallDelta | null;
  insufficient_data: boolean;
}

// ── Velocity ──────────────────────────────────────────────────────────

export interface CategoryVelocity {
  category: string;
  signal_count: number;
  scored_count: number;
  discovery_count: number;
  velocity: number;
  acceleration: number;
  pressure: PressureState;
}

export interface VelocityBucket {
  bucket_start: string;
  bucket_end: string;
  total_count: number;
  scored_count: number;
  discovery_count: number;
  category_counts: Record<string, number>;
}

export interface SourceSummary {
  source_type: string;
  signal_count: number;
  latest_signal_at: string | null;
}

export interface TemporalVelocityResponse {
  company_id: string;
  window: VelocityWindow;
  window_days: number;
  total_signals: number;
  scored_signals: number;
  discovery_signals: number;
  overall_velocity: number;
  overall_acceleration: number;
  overall_pressure: PressureState;
  category_velocities: CategoryVelocity[];
  buckets: VelocityBucket[];
  source_summary: SourceSummary[];
  spike_detected: boolean;
  spike_bucket: string | null;
  drought_detected: boolean;
  drought_days: number;
  evidence: string;
  insufficient_data: boolean;
}

// ── Diagnostic ────────────────────────────────────────────────────────

export interface TopChangingCategory {
  category: string;
  delta: number;
  trend: string;
  velocity: number;
  evidence_strength: EvidenceStrength;
}

export interface ReasoningStep {
  step: string;
  condition: string;
  result: string;
}

export interface TemporalDiagnosticResponse {
  company_id: string;
  temporal_state: TemporalDiagnosticState;
  confidence: TemporalConfidence;
  evidence_strength: EvidenceStrength;
  top_changing_category: TopChangingCategory | null;
  reasoning_trace: ReasoningStep[];
  summary: string;
  score_delta_available: boolean;
  velocity_available: boolean;
  evaluation_available: boolean;
  score_snapshot_count: number;
  signal_count: number;
  scored_signal_count: number;
  insufficient_data: boolean;
}

// ── Verdict ───────────────────────────────────────────────────────────

export interface TemporalVerdictResponse {
  company_id: string;
  verdict_type: string;
  hiring_pressure: string;
  pain_clarity: string;
  diagnosis_status: string;
  confidence: string;
  what_we_know: string;
  what_we_do_not_know_yet: string | null;
  next_best_step: string | null;
  main_pain: string | null;
  where_pain_lives: string | null;
  what_the_company_needs: string | null;
  recommended_positioning: string | null;
  business_read_summary: string | null;
  evidence_quality: string | null;
  temporal_status: string | null;
  trend_direction: string | null;
  top_accelerating_pain: Record<string, unknown> | null;
  top_declining_pain: Record<string, unknown> | null;
  temporal_confidence: string | null;
  temporal_reasoning_trace: ReasoningStep[] | null;
  eligibility: {
    eligible: boolean;
    gate_passed: string;
    confidence_band: string;
    reason: string;
    temporal_gate_passed: boolean | null;
    temporal_reason: string | null;
    temporal_opportunity_type: string | null;
  } | null;
}

// ── Run-analysis (combined) ────────────────────────────────────────────

export interface TemporalRunAnalysisResponse {
  company_id: string;
  deltas: TemporalDeltasResponse | null;
  velocity: TemporalVelocityResponse | null;
  diagnostic: TemporalDiagnosticResponse;
  verdict: TemporalVerdictResponse | null;
}