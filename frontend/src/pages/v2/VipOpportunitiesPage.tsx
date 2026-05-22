import { useState, useEffect, useCallback } from 'react';
import { VIPOpportunityFeed } from '../../components/v2/vip/VIPOpportunityFeed';
import { useNavigate } from 'react-router-dom';
import { getVipOpportunities, generateVipOpportunities, type VipOpportunity } from '../../services/intelligence';

const VIP_USER_ID = import.meta.env.VITE_VIP_USER_ID || '';

export function VipOpportunitiesPage() {
  const navigate = useNavigate();
  const [opportunities, setOpportunities] = useState<VipOpportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  const fetchOpportunities = useCallback(async () => {
    if (!VIP_USER_ID) { setLoading(false); return; }
    try {
      const data = await getVipOpportunities(VIP_USER_ID);
      setOpportunities(data);
    } catch (err) {
      console.error('[VIP] Fetch failed:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchOpportunities(); }, [fetchOpportunities]);

  const handleGenerate = async () => {
    if (!VIP_USER_ID) return;
    setGenerating(true);
    try {
      const data = await generateVipOpportunities(VIP_USER_ID);
      setOpportunities(data);
    } catch {
      // silent
    } finally {
      setGenerating(false);
    }
  };

  const handleCompanyClick = (companyId: string) => {
    navigate(`/company/${companyId}`);
  };

  return (
    <div className="p-7 max-w-3xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] font-mono tracking-[0.12em] uppercase text-fr-ink-faint mb-1">Intelligence · Career Positioning</div>
          <h1 className="text-[22px] font-semibold text-fr-ink leading-tight">VIP Opportunities</h1>
          <p className="text-[13px] text-fr-ink-mute mt-1.5 max-w-md leading-relaxed">
            Companies where your experience solves their organizational pain. Expand any card to see your fit — then dive into the full analysis.
          </p>
        </div>
        {VIP_USER_ID && (
          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating}
            className="shrink-0 text-[12px] font-semibold text-fr-paper bg-fr-ink rounded-md px-3.5 py-2 hover:bg-fr-ink-soft transition-colors disabled:opacity-50"
          >
            {generating ? 'Refreshing...' : 'Refresh'}
          </button>
        )}
      </div>

      {!VIP_USER_ID && !loading && (
        <div className="rounded-lg border border-fr-line bg-fr-paper-2 p-6 text-center">
          <p className="text-sm text-fr-ink-mute">Set <code className="text-[11px] font-mono bg-fr-overlay px-1.5 py-0.5 rounded">VITE_VIP_USER_ID</code> to enable VIP intelligence.</p>
        </div>
      )}

      {loading && (
        <div className="rounded-lg border border-fr-line bg-fr-paper p-8 text-center">
          <div className="text-sm text-fr-ink-mute">Loading your opportunities...</div>
        </div>
      )}

      {!loading && opportunities.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-lg border border-fr-line bg-fr-paper p-4 text-center">
            <div className="text-2xl font-semibold text-fr-ink">{opportunities.length}</div>
            <div className="text-[11px] text-fr-ink-faint mt-1">Opportunities</div>
          </div>
          <div className="rounded-lg border border-fr-line bg-fr-paper p-4 text-center">
            <div className="text-2xl font-semibold text-emerald-600">
              {opportunities.filter(o => o.opportunity_type === 'stable_fit').length}
            </div>
            <div className="text-[11px] text-fr-ink-faint mt-1">Strong Fits</div>
          </div>
          <div className="rounded-lg border border-fr-line bg-fr-paper p-4 text-center">
            <div className="text-2xl font-semibold text-amber-600">
              {opportunities.filter(o => o.opportunity_type === 'accelerated_positioning').length}
            </div>
            <div className="text-[11px] text-fr-ink-faint mt-1">Accelerated</div>
          </div>
        </div>
      )}

      <VIPOpportunityFeed
        opportunities={opportunities}
        onCompanyClick={handleCompanyClick}
      />
    </div>
  );
}