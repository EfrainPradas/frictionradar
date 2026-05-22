import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { companiesService } from '../../services/companies';

interface HeaderProps {
  title: string;
  subtitle?: string;
}

export function Header({ title, subtitle }: HeaderProps) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const { data: companies } = useQuery({
    queryKey: ['companies'],
    queryFn: () => companiesService.list(),
    staleTime: 60_000,
  });

  const filtered = (companies ?? [])
    .filter((c: { name: string; domain: string | null }) =>
      c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.domain ?? '').toLowerCase().includes(searchQuery.toLowerCase())
    )
    .slice(0, 8);

  useEffect(() => {
    if (searchOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [searchOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(true);
      }
      if (e.key === 'Escape') {
        setSearchOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <>
      <header className="flex items-center justify-between px-7 border-b border-orbital-border bg-[rgba(5,6,7,0.54)] backdrop-blur-[18px] h-[76px]">
        <div className="flex items-center gap-4">
          <div>
            <div className="text-[13px] font-extrabold tracking-[.22em] uppercase text-[#edf2ef]">
              {title}
            </div>
            {subtitle && (
              <div className="text-[11px] text-[#8e9994] font-mono mt-0.5">
                {subtitle}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-[10px]">
          <button
            onClick={() => setSearchOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-[rgba(184,198,192,0.16)] bg-[rgba(255,255,255,.035)] text-[11px] text-[#8e9994] font-mono hover:text-[#edf2ef] hover:bg-[rgba(255,255,255,.06)] transition-colors"
          >
            <span className="text-[#59635f]">⌘K</span>
            <span>Search…</span>
          </button>
          <span className="flex items-center gap-1.5 border border-[rgba(184,198,192,0.16)] px-[11px] py-2 rounded-full text-[11px] font-mono text-[#8e9994] bg-[rgba(255,255,255,.035)]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#78b98f] shadow-[0_0_8px_#78b98f]" />
            CONNECTED
          </span>
        </div>
      </header>

      {/* Command palette */}
      {searchOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]" onClick={() => setSearchOpen(false)}>
          <div className="fixed inset-0 bg-black/60" />
          <div
            className="relative w-full max-w-lg bg-[#0b0f12] border border-[rgba(184,198,192,0.16)] rounded-[22px] overflow-hidden"
            style={{ boxShadow: '0 20px 80px rgba(0,0,0,.45)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 px-5 py-4 border-b border-[rgba(184,198,192,0.16)]">
              <span className="text-[#8e9994] text-sm">◉</span>
              <input
                ref={inputRef}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by name or domain…"
                className="flex-1 bg-transparent text-sm text-[#edf2ef] placeholder-[#59635f] outline-none"
                autoFocus
              />
              <kbd className="text-[10px] text-[#59635f] border border-[rgba(184,198,192,0.16)] rounded px-1.5 py-0.5 font-mono">ESC</kbd>
            </div>
            {searchQuery && filtered.length > 0 && (
              <ul className="max-h-64 overflow-y-auto py-1">
                {filtered.map((c: { id: string; name: string; domain: string | null }) => (
                  <li key={c.id}>
                    <button
                      onClick={() => { setSearchOpen(false); setSearchQuery(''); navigate(`/companies/${c.id}`); }}
                      className="w-full text-left px-5 py-3 hover:bg-[rgba(255,255,255,.04)] transition-colors flex items-center justify-between"
                    >
                      <span className="text-sm text-[#edf2ef]">{c.name}</span>
                      <span className="text-xs text-[#59635f] font-mono">{c.domain}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {searchQuery && filtered.length === 0 && (
              <div className="px-5 py-8 text-center text-xs text-[#59635f]">No companies found</div>
            )}
          </div>
        </div>
      )}
    </>
  );
}