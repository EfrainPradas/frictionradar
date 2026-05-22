import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import type { Company } from '../../types/company';
import type { FrictionScore } from '../../types/scoring';
import { FrictionTypeBadge, ScoreBadge } from '../common/Badge';
import { InfoTip } from '../common/InfoTip';
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
    recommended_positioning: string;
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

function ScoreBar({ score }: { score: number | null }) {
  if (score == null) {
    return (
      <div className="w-[72px] h-[5px] rounded-full bg-white/[0.06]">
        <div className="w-0 h-full rounded-full bg-gray-600" />
      </div>
    );
  }
  const pct = Math.min(score / 10, 1) * 100;
  const color =
    score >= 7 ? 'bg-red-400' :
    score >= 4 ? 'bg-amber-400' :
    'bg-emerald-400';
  return (
    <div className="w-[72px] h-[5px] rounded-full bg-white/[0.06]">
      <div className={`h-full rounded-full ${color} transition-all duration-500`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function CompanyTable({ companies, latestScores, companyStats = {} }: Props) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('score');
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

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
    if (!confirm('Are you sure you want to delete this company and all its data?')) return;
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

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);

  return (
    <div className="space-y-3">
      {/* ── Filter bar ─────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Search name or domain…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            className="w-full pl-9 pr-3 py-1.5 bg-[#080b0e] border border-orbital-border rounded text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-amber-500/40 focus:border-amber-500/40"
          />
        </div>
        <select
          value={filterType}
          onChange={(e) => { setFilterType(e.target.value); setPage(0); }}
          className="text-xs border border-orbital-border bg-[#080b0e] rounded px-2 py-1.5 text-gray-400 focus:outline-none focus:ring-1 focus:ring-amber-500/40"
        >
          <option value="">All types</option>
          {FRICTION_TYPES.map((t) => (
            <option key={t} value={t}>
              {t === 'insufficient_evidence' ? 'Insufficient Evidence' : t.replaceAll('_', ' ')}
            </option>
          ))}
        </select>
        <select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          className="text-xs border border-orbital-border bg-[#080b0e] rounded px-2 py-1.5 text-gray-400 focus:outline-none focus:ring-1 focus:ring-amber-500/40"
        >
          <option value="score">By Score</option>
          <option value="signals">By Signals</option>
          <option value="updated">By Recent</option>
          <option value="name">By Name</option>
        </select>
        <span className="text-[10px] font-mono text-gray-600 ml-auto">
          {filtered.length}/{companies.length}
        </span>
      </div>

      {/* ── Intelligence Feed ─────────────────────────────────────── */}
      <div className="rounded-lg border border-orbital-border bg-[#0b0f12] overflow-hidden">
        {/* Table header */}
        <div className="grid grid-cols-[minmax(220px,1fr)_150px_120px_80px_96px_112px] gap-3 px-4 py-2.5 bg-[#080b0e] border-b border-orbital-border text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500">
          <span className="inline-flex items-center gap-1.5">
            Position
            <InfoTip text="Company under analysis — name and primary domain." align="left" />
          </span>
          <span className="inline-flex items-center gap-1.5">
            Friction
            <InfoTip text="Dominant friction category: where the most evidence concentrates (Reporting, Process, Tooling, Scaling, CX)." align="left" />
          </span>
          <span className="inline-flex items-center justify-end gap-1.5">
            <InfoTip text="Total friction score 0–10, weighted across all categories. Green ≤4, amber 4–7, red ≥7." />
            Score
          </span>
          <span className="inline-flex items-center justify-end gap-1.5">
            <InfoTip text="Total captured signals — job postings, careers signals, ATS detections." />
            Signals
          </span>
          <span className="inline-flex items-center justify-end gap-1.5">
            <InfoTip text="Date of last scoring computation. Older dates suggest a refresh is due." />
            Last
          </span>
          <span className="inline-flex items-center justify-end gap-1.5">
            <InfoTip text="Quick actions per row — C: collect signals · S: score · H: generate hypothesis · ×: delete." />
            Ops
          </span>
        </div>

        {/* Rows */}
        {filtered.length === 0 && (
          <div className="py-16 text-center">
            <p className="text-sm text-gray-600">No companies match current filters.</p>
          </div>
        )}

        <div className="divide-y divide-orbital-border/50">
          {filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map((company) => {
            const score = latestScores[company.id];
            const stats = companyStats[company.id];
            const scoreVal = score?.total_score ?? null;

            return (
              <div
                key={company.id}
                onClick={() => navigate(`/companies/${company.id}`)}
                className="grid grid-cols-[minmax(220px,1fr)_150px_120px_80px_96px_112px] gap-3 px-4 py-3 items-center hover:bg-white/[0.02] cursor-pointer transition-colors group"
              >
                {/* Position */}
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-200 truncate group-hover:text-amber-400/90 transition-colors">
                    {company.name}
                  </p>
                  <p className="text-[11px] font-mono text-gray-600 truncate">
                    {company.domain ?? '—'}
                  </p>
                </div>

                {/* Friction type */}
                <div>
                  {score ? (
                    <FrictionTypeBadge type={score.dominant_friction_type} size="sm" />
                  ) : (
                    <span className="text-[10px] text-gray-700">—</span>
                  )}
                </div>

                {/* Score */}
                <div className="flex items-center justify-end gap-2">
                  <ScoreBar score={scoreVal} />
                  <span className="text-xs font-mono text-gray-300 w-7 text-right tabular-nums">
                    {scoreVal != null ? scoreVal.toFixed(1) : '—'}
                  </span>
                </div>

                {/* Signals */}
                <div className="text-right">
                  <span className={`text-xs font-mono tabular-nums ${stats && stats.signalsCount > 0 ? 'text-gray-200' : 'text-gray-700'}`}>
                    {stats?.signalsCount ?? '—'}
                  </span>
                </div>

                {/* Last scored */}
                <div className="text-right text-[11px] font-mono text-gray-500 tabular-nums">
                  {stats?.lastScoredAt
                    ? new Date(stats.lastScoredAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
                    : '—'
                  }
                </div>

                {/* Ops */}
                <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                  {([
                    { action: 'collect' as const, label: 'C' },
                    { action: 'score' as const, label: 'S' },
                    { action: 'hypothesis' as const, label: 'H' },
                  ]).map(({ action, label }) => {
                    const isLoading = loadingId === `${company.id}-${action}`;
                    return (
                      <button
                        key={action}
                        onClick={(e) => handleAction(e, company.id, action)}
                        disabled={!!loadingId}
                        title={action === 'collect' ? 'Collect' : action === 'score' ? 'Score' : 'Hypothesis'}
                        className="w-6 h-6 flex items-center justify-center text-[10px] font-mono rounded border border-orbital-border/60 text-gray-500 hover:text-amber-400/90 hover:border-amber-500/40 disabled:opacity-20 transition-colors"
                      >
                        {isLoading ? '…' : label}
                      </button>
                    );
                  })}
                  <button
                    onClick={(e) => handleDelete(e, company.id)}
                    title="Delete"
                    className="w-6 h-6 flex items-center justify-center text-[12px] leading-none rounded border border-red-900/30 text-red-400/40 hover:text-red-400 hover:border-red-900/60 transition-colors"
                  >
                    ×
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-2 border-t border-orbital-border bg-[#080b0e]">
            <span className="text-[10px] font-mono text-gray-600">
              {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-2 py-1 text-[10px] text-gray-500 border border-orbital-border/50 rounded disabled:opacity-20 hover:bg-white/5"
              >
                ←
              </button>
              {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                const pageNum = totalPages <= 7 ? i :
                  page < 3 ? i :
                  page > totalPages - 4 ? totalPages - 7 + i :
                  page - 3 + i;
                return (
                  <button
                    key={pageNum}
                    onClick={() => setPage(pageNum)}
                    className={`px-2 py-1 text-[10px] rounded border ${
                      page === pageNum
                        ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                        : 'text-gray-600 border-orbital-border/50 hover:bg-white/5'
                    }`}
                  >
                    {pageNum + 1}
                  </button>
                );
              })}
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-2 py-1 text-[10px] text-gray-500 border border-orbital-border/50 rounded disabled:opacity-20 hover:bg-white/5"
              >
                →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}