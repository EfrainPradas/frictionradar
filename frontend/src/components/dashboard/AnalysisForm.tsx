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

      // Navigate to company detail
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
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Analyze a Company</h3>
      
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Domain <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="nike.com"
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <p className="text-xs text-gray-500 mt-1">Enter domain (e.g., nike.com, roberthalf.com)</p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Company Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Nike"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Industry
            </label>
            <select
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white"
            >
              {INDUSTRIES.map((ind) => (
                <option key={ind} value={ind}>
                  {ind}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && (
          <div className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={isLoading || !domain.trim()}
          className="w-full py-2.5 px-4 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Analyzing...
            </span>
          ) : (
            'Run Analysis'
          )}
        </button>
      </form>
    </div>
  );
}