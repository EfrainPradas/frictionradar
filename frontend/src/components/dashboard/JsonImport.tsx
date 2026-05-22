import { useState, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { companiesService } from '../../services/companies';
import type { CompanyCreate } from '../../types/company';

interface ParsedRow {
  name: string;
  domain?: string;
  industry?: string;
  company_size?: string;
}

function extractDomain(url: string): string {
  try {
    const u = new URL(url.startsWith('http') ? url : `https://${url}`);
    return u.hostname.replace(/^www\./, '');
  } catch {
    return url.replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0];
  }
}

function autoMap(rows: Record<string, unknown>[]): ParsedRow[] {
  const sample = rows[0] ?? {};
  const keys = Object.keys(sample);

  const find = (candidates: string[]) =>
    keys.find((k) => candidates.includes(k.toLowerCase())) ?? '';

  const nameKey =
    find(['name', 'company_name', 'companyname', 'itemlabel', 'company', 'nombre', 'empresa']) || '';
  const domainKey =
    find(['domain', 'website', 'url', 'sitio', 'web', 'homepage']) || '';
  const industryKey = find(['industry', 'sector', 'industria']) || '';
  const sizeKey = find(['company_size', 'size', 'employees', 'empleados']) || '';

  const seen = new Set<string>();

  return rows
    .map((row) => {
      const name = String(row[nameKey] ?? '').trim();
      if (!name) return null;

      const rawDomain = domainKey ? String(row[domainKey] ?? '').trim() : '';
      const domain = rawDomain ? extractDomain(rawDomain) : undefined;

      const dedupeKey = domain ?? name.toLowerCase();
      if (seen.has(dedupeKey)) return null;
      seen.add(dedupeKey);

      return {
        name,
        domain: domain || undefined,
        industry: industryKey ? String(row[industryKey] ?? '').trim() || undefined : undefined,
        company_size: sizeKey ? String(row[sizeKey] ?? '').trim() || undefined : undefined,
      } as ParsedRow;
    })
    .filter(Boolean) as ParsedRow[];
}

interface Props {
  onImportComplete?: () => void;
}

export function JsonImport({ onImportComplete }: Props) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [parsed, setParsed] = useState<ParsedRow[]>([]);
  const [fileName, setFileName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<{
    created: number;
    skipped: number;
    errors: string[];
    skipped_details?: { name: string; domain: string; matched_name: string }[];
  } | null>(null);
  const [sourceLabel, setSourceLabel] = useState('json_import');

  const reset = () => {
    setParsed([]);
    setFileName('');
    setError(null);
    setResult(null);
    if (fileRef.current) fileRef.current.value = '';
  };

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    setResult(null);
    const file = e.target.files?.[0];
    if (!file) return;

    setFileName(file.name);

    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const raw = JSON.parse(ev.target?.result as string);
        const rows: Record<string, unknown>[] = Array.isArray(raw) ? raw : [raw];
        if (rows.length === 0) {
          setError('JSON is empty');
          return;
        }
        const mapped = autoMap(rows);
        if (mapped.length === 0) {
          setError('Could not detect company names in the JSON. Expected a field like "name", "itemLabel", or "company".');
          return;
        }
        setParsed(mapped);
      } catch {
        setError('Invalid JSON file');
      }
    };
    reader.readAsText(file);
  };

  const handleImport = async () => {
    if (parsed.length === 0) return;
    setImporting(true);
    setError(null);
    setResult(null);

    const payload: CompanyCreate[] = parsed.map((r) => ({
      name: r.name,
      domain: r.domain,
      industry: r.industry,
      company_size: r.company_size,
      source_added_from: sourceLabel,
    }));

    try {
      const res = await companiesService.batchCreate(payload);
      setResult(res);
      qc.invalidateQueries({ queryKey: ['companies'] });
      onImportComplete?.();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? err.message ?? 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-[10px] tracking-wider uppercase px-3 py-1.5 rounded border border-dashed border-orbital-border text-gray-600 hover:border-gray-500 hover:text-gray-400 transition-colors"
      >
        Import JSON
      </button>
    );
  }

  return (
    <div className="rounded-lg border border-orbital-border bg-[#0b0f12]">
      <div className="border-b border-orbital-border px-5 py-3 flex items-center justify-between">
        <h3 className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500">Import Companies from JSON</h3>
        <button
          onClick={() => { setOpen(false); reset(); }}
          className="text-xs text-gray-600 hover:text-gray-400"
        >
          Close
        </button>
      </div>
      <div className="px-5 py-4 space-y-4">
        <p className="text-xs text-gray-500">
          Upload a JSON array with company records. Fields auto-detected: <code className="text-gray-400">name</code> / <code className="text-gray-400">itemLabel</code>, <code className="text-gray-400">domain</code> / <code className="text-gray-400">website</code>, <code className="text-gray-400">industry</code>, <code className="text-gray-400">employees</code>.
        </p>

        <div className="flex items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept=".json"
            onChange={handleFile}
            className="text-sm text-gray-400 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border file:border-orbital-border file:text-[10px] file:tracking-wider file:uppercase file:bg-[#080b0e] file:text-gray-400 hover:file:bg-white/5 file:cursor-pointer"
          />
          <div className="flex items-center gap-2">
            <label className="text-[10px] uppercase tracking-wider text-gray-600">Source:</label>
            <input
              type="text"
              value={sourceLabel}
              onChange={(e) => setSourceLabel(e.target.value)}
              className="text-xs border border-orbital-border bg-[#080b0e] rounded px-2 py-1 w-36 text-gray-300 focus:outline-none focus:ring-1 focus:ring-amber-500/50"
              placeholder="json_import"
            />
          </div>
        </div>

        {error && (
          <div className="text-xs text-red-400 bg-red-950/40 border border-red-900/50 px-3 py-2 rounded">{error}</div>
        )}

        {result && (
          <div className="text-xs bg-emerald-950/30 border border-emerald-900/40 px-3 py-2 rounded space-y-1">
            <p className="text-emerald-400 font-medium">
              {result.created} created, {result.skipped} skipped (duplicate domain)
            </p>
            {result.skipped_details && result.skipped_details.length > 0 && (
              <details className="text-gray-500">
                <summary className="cursor-pointer">{result.skipped_details.length} skipped details</summary>
                <ul className="mt-1 space-y-0.5 pl-3 list-disc text-xs">
                  {result.skipped_details.slice(0, 30).map((s, i) => (
                    <li key={i}>
                      <strong className="text-gray-400">{s.name}</strong> ({s.domain}) — matched existing: <em>{s.matched_name}</em>
                    </li>
                  ))}
                  {result.skipped_details.length > 30 && (
                    <li>...and {result.skipped_details.length - 30} more</li>
                  )}
                </ul>
              </details>
            )}
            {result.errors.length > 0 && (
              <details className="text-red-400">
                <summary className="cursor-pointer">{result.errors.length} errors</summary>
                <ul className="mt-1 space-y-0.5 pl-3 list-disc">
                  {result.errors.slice(0, 20).map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}

        {parsed.length > 0 && !result && (
          <>
            <div className="text-xs text-gray-500">
              {parsed.length} unique companies detected from <strong className="text-gray-300">{fileName}</strong>
            </div>

            <div className="max-h-60 overflow-auto rounded-lg border border-orbital-border bg-[#080b0e]">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="border-b border-orbital-border bg-[#080b0e]">
                    <th className="px-2 py-1.5 text-left text-[10px] tracking-wider uppercase text-gray-600 font-medium">#</th>
                    <th className="px-2 py-1.5 text-left text-[10px] tracking-wider uppercase text-gray-600 font-medium">Name</th>
                    <th className="px-2 py-1.5 text-left text-[10px] tracking-wider uppercase text-gray-600 font-medium">Domain</th>
                    <th className="px-2 py-1.5 text-left text-[10px] tracking-wider uppercase text-gray-600 font-medium">Industry</th>
                    <th className="px-2 py-1.5 text-left text-[10px] tracking-wider uppercase text-gray-600 font-medium">Size</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-orbital-border/50">
                  {parsed.slice(0, 50).map((row, i) => (
                    <tr key={i} className="hover:bg-white/[0.02]">
                      <td className="px-2 py-1 text-gray-600">{i + 1}</td>
                      <td className="px-2 py-1 text-gray-300">{row.name}</td>
                      <td className="px-2 py-1 text-gray-500 font-mono">{row.domain ?? '—'}</td>
                      <td className="px-2 py-1 text-gray-500">{row.industry ?? '—'}</td>
                      <td className="px-2 py-1 text-gray-500">{row.company_size ?? '—'}</td>
                    </tr>
                  ))}
                  {parsed.length > 50 && (
                    <tr>
                      <td colSpan={5} className="px-2 py-1 text-gray-600 text-center">
                        ... and {parsed.length - 50} more
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <button
              onClick={handleImport}
              disabled={importing}
              className="px-4 py-2 bg-amber-500/10 text-amber-400 border border-amber-500/20 text-sm rounded hover:bg-amber-500/20 disabled:opacity-50 transition-colors"
            >
              {importing ? 'Importing...' : `Import ${parsed.length} companies`}
            </button>
          </>
        )}
      </div>
    </div>
  );
}