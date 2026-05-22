import { useState, useRef, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';

interface Props {
  text: string;
  align?: 'left' | 'right' | 'center';
}

export function InfoTip({ text, align = 'right' }: Props) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);

  const TOOLTIP_W = 240;

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const top = rect.bottom + 8;
    let left: number;
    if (align === 'left') left = rect.left;
    else if (align === 'center') left = rect.left + rect.width / 2 - TOOLTIP_W / 2;
    else left = rect.right - TOOLTIP_W;
    const clampedLeft = Math.max(8, Math.min(left, window.innerWidth - TOOLTIP_W - 8));
    setCoords({ top, left: clampedLeft });
  }, [open, align]);

  return (
    <>
      <span
        ref={triggerRef}
        aria-label={text}
        tabIndex={0}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full border border-[rgba(184,198,192,0.28)] text-[9px] font-mono leading-none text-[#8e9994] hover:text-[#d7b46a] hover:border-[#d7b46a]/60 focus:outline-none focus:text-[#d7b46a] focus:border-[#d7b46a]/60 cursor-help transition-colors align-middle"
      >
        i
      </span>
      {open && coords && createPortal(
        <div
          role="tooltip"
          style={{ position: 'fixed', top: coords.top, left: coords.left, width: TOOLTIP_W, zIndex: 9999 }}
          className="rounded-lg border border-[rgba(210,184,113,0.32)] bg-[#0b0f12]/95 backdrop-blur-md px-3 py-2 text-[11px] leading-snug text-[#d4dad7] shadow-[0_10px_40px_rgba(0,0,0,0.6)] normal-case tracking-normal font-sans pointer-events-none"
        >
          {text}
        </div>,
        document.body,
      )}
    </>
  );
}
