import type { OpportunityHypothesis } from '../../types/hypothesis';
import {
  generateConfidenceNarrative,
  generateObservations,
  generateFunctionalArea,
  defineTheProblem,
  whyTheyAreHiring,
  whereToAddValue,
  idealProfile,
  positioningGuidance
} from '../../services/insightComposer';

interface Props {
  hypothesis: OpportunityHypothesis;
  signalCount?: number;
  collectionRunCount?: number;
  signalTexts?: string[];
  verdictType?: 'preliminary' | 'final';
}

export function HypothesisCard({
  hypothesis,
  signalCount = 0,
  collectionRunCount = 0,
  signalTexts = [],
  verdictType = 'final'
}: Props) {
  const primaryFriction = hypothesis.friction_type;

  const hasRepeatedSignals = signalCount > 3;
  const confidenceNarrative = generateConfidenceNarrative({ signalCount, collectionRunCount, hasRepeatedSignals });

  const observations = generateObservations(signalTexts);
  const functionalArea = generateFunctionalArea(signalTexts, primaryFriction as any);
  const problem = defineTheProblem(primaryFriction as any);
  const hiringReason = whyTheyAreHiring(signalTexts);
  const valueAdd = whereToAddValue(primaryFriction as any);
  const profile = idealProfile(primaryFriction as any);
  const positioning = positioningGuidance(primaryFriction as any);

  if (verdictType === 'preliminary') {
    return (
      <div className="space-y-4">
        <div className="p-4 bg-amber-500/5 border border-amber-500/20 rounded-lg">
          <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-amber-400 mb-2">Preliminary Read</p>

          <div className="mb-4">
            <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">What we know</p>
            <p className="text-sm text-gray-300">
              {signalTexts.length > 0
                ? `We confirmed: ${signalTexts[0]}`
                : 'We confirmed the company exists with basic web presence.'
              }
            </p>
          </div>

          <div className="mb-4">
            <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">What we do not know yet</p>
            <p className="text-sm text-gray-400">
              We do not yet have enough evidence to determine whether the main pain is in data, operations, reporting, recruiting, or another function.
            </p>
          </div>

          <div>
            <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">What we need next</p>
            <p className="text-sm text-gray-400">
              We need more signals from job descriptions, about content, newsroom content, and role-specific hiring language before generating a stronger recommendation.
            </p>
          </div>
        </div>

        <div className="text-sm text-gray-500">
          <span className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-600">Confidence: </span>
          Low — current evidence is limited.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Where the problem likely exists */}
      <div>
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-2">Where the problem likely exists</p>
        <p className="text-sm text-gray-200 font-medium">
          The signals suggest the challenge is likely within the company's {functionalArea}.
        </p>
      </div>

      {/* What the real problem is */}
      <div className="rounded bg-red-500/5 border border-red-500/20 px-4 py-3">
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-red-400 mb-1">What the real problem is</p>
        <p className="text-sm text-gray-300">
          The company is {problem}.
        </p>
      </div>

      {/* Why they are hiring */}
      <div>
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">Why they are likely hiring</p>
        <p className="text-sm text-gray-400 leading-relaxed">
          {hiringReason}
        </p>
      </div>

      {/* What we noticed */}
      <div>
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-2">What we noticed</p>
        <ul className="space-y-1">
          {observations.map((obs, idx) => (
            <li key={idx} className="flex items-start gap-2 text-sm text-gray-300">
              <span className="text-gray-600 mt-1 shrink-0">•</span>
              <span>{obs}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Why this matters */}
      <div>
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">Why this matters</p>
        <p className="text-sm text-gray-400 leading-relaxed">
          Without addressing these patterns, the company may face challenges in coordination, decision-making, or efficiency as they continue growing.
        </p>
      </div>

      {/* Where you can add value */}
      <div className="rounded bg-emerald-500/5 border border-emerald-500/20 px-4 py-3">
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-emerald-400 mb-1">Where you can add value</p>
        <p className="text-sm text-gray-300">{valueAdd}</p>
      </div>

      {/* Who would be valuable here */}
      <div>
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-2">Who would be valuable here</p>
        <p className="text-sm text-gray-400 mb-2">This environment would benefit from someone who can:</p>
        <ul className="space-y-1">
          {profile.map((skill, idx) => (
            <li key={idx} className="flex items-start gap-2 text-sm text-gray-300">
              <span className="text-emerald-400/70 mt-1 shrink-0">✓</span>
              <span>{skill}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* How to position yourself with this company */}
      <div className="rounded bg-blue-500/5 border border-blue-500/20 px-4 py-3">
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-blue-400 mb-1">How to position yourself with this company</p>
        <p className="text-sm text-gray-300">{positioning}</p>
      </div>

      {/* Confidence level */}
      <div className="pt-3 border-t border-orbital-border">
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">How confident we are</p>
        <p className="text-sm text-gray-400">{confidenceNarrative}</p>
      </div>

      {/* Full analysis */}
      <div className="pt-3 border-t border-orbital-border">
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">Full analysis</p>
        <p className="text-sm text-gray-300 leading-relaxed">{hypothesis.summary}</p>
      </div>

      <p className="text-[10px] text-gray-600">
        Generated {new Date(hypothesis.created_at).toLocaleDateString()}
      </p>
    </div>
  );
}