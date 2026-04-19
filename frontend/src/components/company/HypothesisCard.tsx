import type { OpportunityHypothesis } from '../../types/hypothesis';
import { 
  generateConfidenceNarrative,
  generateObservations,
  generateFunctionalArea,
  defineTheProblem,
  whyTheyAreHiring,
  whereToAddValue,
  idealProfile,
  targetingPosition
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
  const positioning = targetingPosition(primaryFriction as any);

  // If preliminary mode, show simplified version
  if (verdictType === 'preliminary') {
    return (
      <div className="space-y-4">
        <div className="p-4 bg-yellow-50 border border-yellow-100 rounded">
          <p className="text-xs text-yellow-600 uppercase tracking-wide mb-2">Preliminary Read</p>
          
          <div className="mb-4">
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">What we know</p>
            <p className="text-sm text-gray-700">
              {signalTexts.length > 0 
                ? `We confirmed: ${signalTexts[0]}`
                : 'We confirmed the company exists with basic web presence.'
              }
            </p>
          </div>

          <div className="mb-4">
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">What we do not know yet</p>
            <p className="text-sm text-gray-600">
              We do not yet have enough evidence to determine whether the main pain is in data, operations, reporting, recruiting, or another function.
            </p>
          </div>

          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">What we need next</p>
            <p className="text-sm text-gray-600">
              We need more signals from job descriptions, about content, newsroom content, and role-specific hiring language before generating a stronger recommendation.
            </p>
          </div>
        </div>

        <div className="text-sm text-gray-500">
          <span className="text-xs text-gray-400 uppercase tracking-wide">Confidence: </span>
          Low - current evidence is limited.
        </div>
      </div>
    );
  }

  // Final mode - full hypothesis
  return (
    <div className="space-y-5">
      {/* Where the problem likely exists */}
      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">Where the problem likely exists</p>
        <p className="text-sm text-gray-700 font-medium">
          The signals suggest the challenge is likely within the company's {functionalArea}.
        </p>
      </div>

      {/* What the real problem is */}
      <div className="rounded bg-red-50 border border-red-100 px-4 py-3">
        <p className="text-xs text-red-600 uppercase tracking-wide mb-1">What the real problem is</p>
        <p className="text-sm text-gray-800">
          The company is {problem}.
        </p>
      </div>

      {/* Why they are hiring */}
      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Why they are likely hiring</p>
        <p className="text-sm text-gray-600 leading-relaxed">
          {hiringReason}
        </p>
      </div>

      {/* What we noticed */}
      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">What we noticed</p>
        <ul className="space-y-1">
          {observations.map((obs, idx) => (
            <li key={idx} className="flex items-start gap-2 text-sm text-gray-700">
              <span className="text-gray-400 mt-1">•</span>
              <span>{obs}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Why this matters */}
      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Why this matters</p>
        <p className="text-sm text-gray-600 leading-relaxed">
          Without addressing these patterns, the company may face challenges in coordination, decision-making, or efficiency as they continue growing.
        </p>
      </div>

      {/* Where you can add value */}
      <div className="rounded bg-emerald-50 border border-emerald-100 px-4 py-3">
        <p className="text-xs text-emerald-600 uppercase tracking-wide mb-1">Where you can add value</p>
        <p className="text-sm text-gray-700">{valueAdd}</p>
      </div>

      {/* Who would be valuable here */}
      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">Who would be valuable here</p>
        <p className="text-sm text-gray-600 mb-2">This environment would benefit from someone who can:</p>
        <ul className="space-y-1">
          {profile.map((skill, idx) => (
            <li key={idx} className="flex items-start gap-2 text-sm text-gray-700">
              <span className="text-emerald-500 mt-1">✓</span>
              <span>{skill}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* If you were targeting this company */}
      <div className="rounded bg-blue-50 border border-blue-100 px-4 py-3">
        <p className="text-xs text-blue-600 uppercase tracking-wide mb-1">If you were targeting this company</p>
        <p className="text-sm text-gray-700">{positioning}</p>
      </div>

      {/* Confidence level */}
      <div className="pt-3 border-t border-gray-100">
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">How confident we are</p>
        <p className="text-sm text-gray-600">{confidenceNarrative}</p>
      </div>

      {/* Full analysis */}
      <div className="pt-3 border-t border-gray-100">
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Full analysis</p>
        <p className="text-sm text-gray-700 leading-relaxed">{hypothesis.summary}</p>
      </div>

      <p className="text-xs text-gray-400">
        Generated {new Date(hypothesis.created_at).toLocaleDateString()}
      </p>
    </div>
  );
}