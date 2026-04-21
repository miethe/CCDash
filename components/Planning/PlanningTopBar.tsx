import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { cn } from '@/lib/utils';
import { useData } from '@/contexts/DataContext';
import { Btn, BtnPrimary, Chip, Dot } from './primitives';

// ── Toast ─────────────────────────────────────────────────────────────────────

interface ToastEntry {
  id: string;
  message: string;
}

function useTopBarToast() {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const timersRef = useRef<number[]>([]);

  const push = useCallback((message: string) => {
    const id = `topbar-toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts((prev) => [...prev, { id, message }].slice(-3));
    const timer = window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 2800);
    timersRef.current.push(timer);
  }, []);

  useEffect(() => {
    return () => {
      timersRef.current.forEach((id) => window.clearTimeout(id));
      timersRef.current = [];
    };
  }, []);

  return { toasts, push };
}

// ── Live-agent pill ────────────────────────────────────────────────────────────

interface LiveAgentPillProps {
  running: number;
  thinking: number;
  className?: string;
}

function LiveAgentPill({ running, thinking, className }: LiveAgentPillProps) {
  const isLive = running > 0 || thinking > 0;

  return (
    <Chip
      className={cn(
        'planning-mono flex items-center gap-2 border-[color:var(--line-1)] bg-[color:var(--bg-2)] px-3 py-[5px] text-[11px] text-[color:var(--ink-2)]',
        className,
      )}
      aria-label={`Agent status: ${isLive ? 'live' : 'idle'}`}
    >
      <Dot
        tone={isLive ? 'var(--ok)' : 'var(--ink-4)'}
        aria-hidden="true"
        style={
          isLive
            ? {
                width: 7,
                height: 7,
                boxShadow: '0 0 7px var(--ok)',
                animation: 'planning-pulse 2s ease-in-out infinite',
              }
            : { width: 7, height: 7 }
        }
      />
      <span style={{ color: isLive ? 'var(--ok)' : 'var(--ink-3)' }}>{isLive ? 'live' : 'idle'}</span>
      <span style={{ color: 'var(--ink-4)' }}>·</span>
      <span>{running} running</span>
      <span style={{ color: 'var(--ink-4)' }}>·</span>
      <span>{thinking} thinking</span>
    </Chip>
  );
}

// ── Breadcrumb ─────────────────────────────────────────────────────────────────

function PlanningBreadcrumb() {
  return (
    <nav
      aria-label="Breadcrumb"
      className="planning-mono flex items-center gap-2 text-[12px]"
    >
      <span className="text-[color:var(--ink-3)]">CCDash</span>
      <span aria-hidden="true" className="text-[color:var(--ink-4)]">/</span>
      <span className="text-[color:var(--ink-2)]">CCDash · Planning</span>
      <span aria-hidden="true" className="text-[color:var(--ink-4)]">/</span>
      <span className="text-[color:var(--ink-0)] font-medium" aria-current="page">Planning Deck</span>
    </nav>
  );
}

// ── PlanningTopBar ─────────────────────────────────────────────────────────────

export interface PlanningTopBarProps {
  className?: string;
}

export function PlanningTopBar({ className }: PlanningTopBarProps) {
  const { sessions } = useData();
  const { toasts, push: pushToast } = useTopBarToast();

  // Derive live-agent counts from sessions already in context.
  // "active" sessions map to the live-agent concept; thinkingLevel signals
  // whether the agent is in a thinking pass.
  const { running, thinking } = useMemo(() => {
    const active = sessions.filter((s) => s.status === 'active');
    const thinkingSet = active.filter((s) => s.thinkingLevel != null && s.thinkingLevel !== 'low');
    return { running: active.length, thinking: thinkingSet.length };
  }, [sessions]);

  // ⌘K / Ctrl+K global keyboard handler
  const handleSearch = useCallback(() => {
    pushToast('Search coming in v2 — press ⌘K to trigger when integrated.');
  }, [pushToast]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        handleSearch();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [handleSearch]);

  const handleNewSpec = useCallback(() => {
    pushToast('New spec — coming in v2.');
  }, [pushToast]);

  return (
    <>
      <header
        className={cn(
          'flex items-center justify-between gap-4 flex-wrap',
          className,
        )}
        aria-label="Planning top bar"
      >
        {/* Left: breadcrumb */}
        <PlanningBreadcrumb />

        {/* Right: actions */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <LiveAgentPill running={running} thinking={thinking} />

          <Btn
            size="sm"
            type="button"
            onClick={handleSearch}
            aria-label="Search (⌘K)"
            className="planning-mono gap-1.5 px-3 text-[11.5px]"
          >
            <span className="text-[color:var(--ink-3)] text-[10px]">⌘K</span>
            <span>Search</span>
          </Btn>

          <BtnPrimary
            size="sm"
            type="button"
            onClick={handleNewSpec}
            aria-label="New spec"
            className="planning-mono gap-1.5 px-3 text-[11.5px]"
          >
            <span aria-hidden="true">+</span>
            <span>New spec</span>
          </BtnPrimary>
        </div>
      </header>

      {/* Top-bar toasts — rendered here so they stay scoped to the planning shell */}
      {toasts.length > 0 && (
        <div
          aria-live="polite"
          aria-atomic="false"
          className="pointer-events-none fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 flex-col items-center gap-2"
        >
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className="planning-mono pointer-events-auto flex items-center gap-2.5 rounded-[var(--radius-sm)] border border-[color:color-mix(in_oklab,var(--brand)_40%,var(--line-2))] bg-[color:var(--bg-1)] px-4 py-2.5 text-[11.5px] text-[color:var(--ink-0)] shadow-[0_14px_40px_rgba(0,0,0,0.45)]"
              style={{ backdropFilter: 'blur(8px)' }}
            >
              <Dot tone="var(--brand)" aria-hidden="true" />
              {toast.message}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
