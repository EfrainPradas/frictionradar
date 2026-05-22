import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { analysisService } from '../../services/analysis';

const INDUSTRIES = [
  'Auto-detect',
  'Retail / Consumer Goods',
  'E-commerce / Marketplace',
  'Logistics / Supply Chain',
  'Manufacturing / Industrial',
  'Technology / SaaS',
  'Financial Services / Fintech',
  'Healthcare / Healthtech',
  'Insurance',
  'Real Estate / PropTech',
  'Energy / Utilities',
  'Telecommunications',
  'Media / Entertainment',
  'Education / EdTech',
  'Travel / Hospitality',
  'Food / Beverage',
  'Professional Services / Consulting',
  'Staffing / Recruiting',
  'Job Board / Talent Marketplace',
  'Government / Public Sector',
  'Nonprofit',
  'Other / Unknown',
];

interface AnalysisFormProps {
  onAnalysisComplete?: (companyId: string) => void;
}

export function AnalysisForm({ onAnalysisComplete }: AnalysisFormProps) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const [domain, setDomain] = useState('');
  const [name, setName] = useState('');
  const [industry, setIndustry] = useState('Auto-detect');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!domain.trim()) {
      setError('Domain is required');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const result = await analysisService.analyzeCompany({
        domain: domain.trim(),
        name: name.trim() || undefined,
        industry: industry === 'Auto-detect' ? undefined : industry,
      });

      const companyId = result.company.id;

      if (onAnalysisComplete) {
        onAnalysisComplete(companyId);
      } else {
        navigate(`/companies/${companyId}`);
      }
    } catch (err: any) {
      setError(err.message || 'Analysis failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="rounded-lg border border-orbital-border bg-[#0b0f12] overflow-hidden">
        {/* Command bar */}
        <div className="flex items-center gap-0">
          <div className="flex-1 flex items-center">
            <span className="px-4 text-amber-500/60 text-sm font-mono select-none">❯</span>
            <input
              type="text"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="Enter domain to analyze (e.g., nike.com)"
              className="flex-1 py-3 bg-transparent text-sm text-gray-200 placeholder-gray-600 focus:outline-none"
            />
          </div>
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="px-3 py-3 text-[10px] tracking-wider uppercase text-gray-600 hover:text-gray-400 transition-colors border-l border-orbital-border"
          >
            {expanded ? 'Less' : 'More'}
          </button>
          <button
            type="submit"
            disabled={isLoading || !domain.trim()}
            className="px-5 py-3 bg-amber-500/10 text-amber-400 border-l border-orbital-border text-sm font-medium hover:bg-amber-500/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Scanning…
              </span>
            ) : (
              'Analyze'
            )}
          </button>
        </div>

        {/* Expanded fields */}
        {expanded && (
          <div className="border-t border-orbital-border px-4 py-3 grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-600 mb-1.5">
                Company Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Optional"
                className="w-full px-3 py-1.5 bg-[#080b0e] border border-orbital-border rounded text-sm text-gray-200 placeholder-gray-700 focus:outline-none focus:ring-1 focus:ring-amber-500/40"
              />
            </div>
            <div>
              <label className="block text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-600 mb-1.5">
                Industry
              </label>
              <select
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                className="w-full px-3 py-1.5 bg-[#080b0e] border border-orbital-border rounded text-sm text-gray-300 focus:outline-none focus:ring-1 focus:ring-amber-500/40"
              >
                {INDUSTRIES.map((ind) => (
                  <option key={ind} value={ind}>{ind}</option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="border-t border-red-900/50 bg-red-950/30 px-4 py-2 text-xs text-red-400">
            {error}
          </div>
        )}
      </div>
    </form>
  );
}