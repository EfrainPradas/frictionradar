import { useState } from 'react';

interface PositioningData {
  recommended_positioning?: string | null;
  candidate_archetype?: string | null;
  positioning_angle?: string | null;
  resume_emphasis?: string[];
  networking_angle?: string | null;
  interview_themes?: string[];
  confidence_band?: string | null;
}

interface Props {
  data: PositioningData;
}

const CONFIDENCE_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  high: { bg: 'bg-emerald-50', text: 'text-emerald-700', label: 'High confidence' },
  moderate: { bg: 'bg-amber-50', text: 'text-amber-700', label: 'Moderate confidence' },
  low: { bg: 'bg-slate-50', text: 'text-slate-500', label: 'Low confidence' },
};

export function PositioningRecommendationPanel({ data }: Props) {
  const [copied, setCopied] = useState(false);

  if (!data.recommended_positioning && !data.positioning_angle) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <h3 className="text-sm font-semibold text-slate-400 mb-2">Recommended Positioning</h3>
        <p className="text-sm text-slate-400 italic">Awaiting analysis</p>
      </div>
    );
  }

  const confidence = data.confidence_band || 'low';
  const style = CONFIDENCE_STYLES[confidence] || CONFIDENCE_STYLES.low;

  const handleCopy = () => {
    const text = [
      data.recommended_positioning,
      data.positioning_angle ? `\nAngle: ${data.positioning_angle}` : '',
      data.resume_emphasis?.length ? `\nResume emphasis:\n${data.resume_emphasis.map(e => `• ${e}`).join('\n')}` : '',
      data.networking_angle ? `\nNetworking: ${data.networking_angle}` : '',
    ].filter(Boolean).join('\n');

    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
        <h3 className="text-[13px] font-semibold text-slate-800 tracking-wide">
          Recommended Positioning
        </h3>
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${style.bg} ${style.text}`}>
          {style.label}
        </span>
      </div>

      {/* Main positioning */}
      <div className="px-5 py-4 space-y-4">
        {data.recommended_positioning && (
          <div className="rounded-md bg-slate-50 border border-slate-200 p-4">
            <p className="text-sm text-slate-800 leading-relaxed">
              {data.recommended_positioning}
            </p>
          </div>
        )}

        {data.candidate_archetype && (
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400">Archetype</span>
            <span className="text-sm font-medium text-slate-700">{data.candidate_archetype}</span>
          </div>
        )}

        {data.positioning_angle && (
          <div>
            <h4 className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-1.5">Positioning Angle</h4>
            <p className="text-sm text-slate-700 leading-relaxed">{data.positioning_angle}</p>
          </div>
        )}

        {data.resume_emphasis && data.resume_emphasis.length > 0 && (
          <div>
            <h4 className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-2">Resume Emphasis</h4>
            <ul className="space-y-1.5">
              {data.resume_emphasis.map((item, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-slate-600">
                  <span className="inline-block mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}

        {data.networking_angle && (
          <div>
            <h4 className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-1.5">Networking Positioning</h4>
            <p className="text-sm text-slate-600 leading-relaxed">{data.networking_angle}</p>
          </div>
        )}

        {data.interview_themes && data.interview_themes.length > 0 && (
          <div>
            <h4 className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-2">Interview Themes</h4>
            <ul className="space-y-1.5">
              {data.interview_themes.map((theme, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-slate-600">
                  <span className="inline-block mt-1.5 w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
                  {theme}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Copy action */}
      <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/50">
        <button
          type="button"
          onClick={handleCopy}
          className="text-[12px] font-medium text-slate-500 hover:text-slate-700 transition-colors"
        >
          {copied ? 'Copied to clipboard' : 'Copy Positioning'}
        </button>
      </div>
    </div>
  );
}