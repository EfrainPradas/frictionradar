import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import type { Company } from '../../types/company';
import type { FrictionScore } from '../../types/scoring';
import { FrictionTypeBadge, ScoreBadge } from '../common/Badge';
import { collectionService } from '../../services/collection';
import { scoringService } from '../../services/scoring';
import { hypothesisService } from '../../services/hypothesis';
import { companiesService } from '../../services/companies';

interface CompanyVerdict {
  company_type: string;
  analysis_mode: string;
  target_fit: string;
  company_type_reason: string;
  final_verdict: {
    main_pain: string;
    where_pain_lives: string;
    what_the_company_needs: string;
    best_attack_angle: string;
  };
}

interface Props {
  companies: Company[];
  latestScores: Record<string, FrictionScore | null>;
  companyStats?: Record<string, { signalsCount: number; lastCollectedAt?: string; lastScoredAt?: string }>;
  verdicts?: Record<string, CompanyVerdict>;
}

type SortKey = 'name' | 'score' | 'signals' | 'updated';

const FRICTION_TYPES = [
  'reporting_fragmentation',
  'process_inefficiency',
  'tooling_inconsistency',
  'scaling_strain',
  'customer_experience_friction',
  'insufficient_evidence',
] as const;

export function CompanyTable({ companies, latestScores, companyStats = {} }: Props) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('score');
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 100;

  const invalidate = (id: string) => {
    qc.invalidateQueries({ queryKey: ['score-latest', id] });
    qc.invalidateQueries({ queryKey: ['companies'] });
    qc.invalidateQueries({ queryKey: ['signals', id] });
    qc.invalidateQueries({ queryKey: ['collection-runs', id] });
  };

  const handleAction = async (
    e: React.MouseEvent,
    id: string,
    action: 'collect' | 'score' | 'hypothesis'
  ) => {
    e.stopPropagation();
    setLoadingId(`${id}-${action}`);
    try {
      if (action === 'collect') await collectionService.trigger(id);
      if (action === 'score') await scoringService.trigger(id);
      if (action === 'hypothesis') await hypothesisService.trigger(id);
      invalidate(id);
    } finally {
      setLoadingId(null);
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this company and all its data?')) {
      return;
    }
    try {
      await companiesService.delete(id);
      qc.invalidateQueries({ queryKey: ['companies'] });
    } catch (err) {
      console.error('Failed to delete company:', err);
    }
  };

  const filtered = companies
    .filter((c) => {
      const term = search.toLowerCase();
      const matchSearch =
        !term ||
        c.name.toLowerCase().includes(term) ||
        (c.domain ?? '').toLowerCase().includes(term);
      const matchType =
        !filterType ||
        (filterType === 'insufficient_evidence'
          ? latestScores[c.id]?.dominant_friction_type === null
          : latestScores[c.id]?.dominant_friction_type === filterType);
      return matchSearch && matchType;
    })
    .sort((a, b) => {
      if (sortKey === 'name') return a.name.localeCompare(b.name);
      if (sortKey === 'signals') {
        const sa = companyStats[a.id]?.signalsCount ?? 0;
        const sb = companyStats[b.id]?.signalsCount ?? 0;
        return sb - sa;
      }
      if (sortKey === 'updated') {
        const ua = companyStats[a.id]?.lastScoredAt ?? a.updated_at;
        const ub = companyStats[b.id]?.lastScoredAt ?? b.updated_at;
        return new Date(ub).getTime() - new Date(ua).getTime();
      }
      const sa = latestScores[a.id]?.total_score ?? -1;
      const sb = latestScores[b.id]?.total_score ?? -1;
      return sb - sa;
    });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 flex-wrap">
        <input
          type="text"
          placeholder="Search by name or domain…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0); }}
          className="text-sm border border-gray-200 rounded px-3 py-1.5 w-56 focus:outline-none focus:ring-1 focus:ring-gray-400 bg-white"
        />
        <select
          value={filterType}
          onChange={(e) => { setFilterType(e.target.value); setPage(0); }}
          className="text-sm border border-gray-200 rounded px-3 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-gray-400"
        >
          <option value="">All friction types</option>
          {FRICTION_TYPES.map((t) => (
            <option key={t} value={t}>
              {t === 'insufficient_evidence' ? 'Insufficient Evidence' : t.replaceAll('_', ' ')}
            </option>
          ))}
        </select>
        <select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          className="text-sm border border-gray-200 rounded px-3 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-gray-400"
        >
          <option value="score">Highest Score</option>
          <option value="signals">Most Signals</option>
          <option value="updated">Recently Updated</option>
          <option value="name">Company Name</option>
        </select>
        <span className="text-xs text-gray-400 ml-auto">
          {filtered.length} of {companies.length}
        </span>
      </div>

      {/* Pagination controls */}
      {(() => {
        const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
        if (totalPages <= 1) return null;
        return (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-2 py-1 rounded border border-gray-200 disabled:opacity-30 hover:bg-gray-50"
            >
              Prev
            </button>
            {Array.from({ length: totalPages }, (_, i) => (
              <button
                key={i}
                onClick={() => setPage(i)}
                className={`px-2 py-1 rounded border ${page === i ? 'bg-gray-800 text-white border-gray-800' : 'border-gray-200 hover:bg-gray-50'}`}
              >
                {i + 1}
              </button>
            ))}
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-2 py-1 rounded border border-gray-200 disabled:opacity-30 hover:bg-gray-50"
            >
              Next
            </button>
            <span className="ml-2 text-gray-400">
              {page * PAGE_SIZE + 1}-{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
            </span>
          </div>
        );
      })()}

      <div className="rounded border border-gray-200 bg-white overflow-hidden">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              {['Company', 'Domain', 'Signals', 'Score', 'Friction', 'Updated', 'Actions'].map((h) => (
                <th
                  key={h}
                  className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-sm text-gray-400">
                  No companies match your filters.
                </td>
              </tr>
            )}
            {filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map((company) => {
              const score = latestScores[company.id];
              const stats = companyStats[company.id];
              
              return (
                <tr
                  key={company.id}
                  onClick={() => navigate(`/companies/${company.id}`)}
                  className="hover:bg-gray-50 cursor-pointer transition-colors"
                >
                  <td className="px-3 py-3 font-medium text-gray-900">
                    {company.name}
                  </td>
                  <td className="px-3 py-3 text-gray-500 font-mono text-xs">
                    {company.domain ?? '—'}
                  </td>
                  <td className="px-3 py-3 text-gray-600 tabular-nums">
                    <span className={stats && stats.signalsCount > 0 ? 'font-medium' : 'text-gray-400'}>
                      {stats?.signalsCount ?? '—'}
                    </span>
                  </td>
                  <td className="px-3 py-3">
                    <ScoreBadge score={score?.total_score ?? null} />
                  </td>
                  <td className="px-3 py-3">
                    {score ? (
                      <FrictionTypeBadge
                        type={score.dominant_friction_type}
                        size="sm"
                      />
                    ) : (
                      <span className="text-xs text-gray-400">—</span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-gray-400 text-xs">
                    {stats?.lastScoredAt ? new Date(stats.lastScoredAt).toLocaleDateString() : '—'}
                  </td>
                  <td className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center gap-1">
                      {([
                        { action: 'collect' as const, label: 'Collect' },
                        { action: 'score' as const, label: 'Score' },
                        { action: 'hypothesis' as const, label: 'Hypothesis' },
                      ]).map(({ action, label }) => {
                        const isLoading = loadingId === `${company.id}-${action}`;
                        return (
                          <button
                            key={action}
                            onClick={(e) => handleAction(e, company.id, action)}
                            disabled={!!loadingId}
                            className="text-xs px-2 py-1 rounded border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition-colors"
                          >
                            {isLoading ? '…' : label}
                          </button>
                        );
                      })}
                      <button
                        onClick={(e) => handleDelete(e, company.id)}
                        className="text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50 transition-colors ml-1"
                        title="Delete company"
                      >
                        ×
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}