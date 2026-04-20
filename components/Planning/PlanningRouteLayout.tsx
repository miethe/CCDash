import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { Outlet } from 'react-router-dom';

import '../../planning-tokens.css';
import { cn } from '@/lib/utils';
import { Btn, BtnGhost } from './primitives';

export const PLANNING_DENSITY_STORAGE_KEY = 'planning_density_preference';

export type PlanningDensity = 'comfortable' | 'compact';

interface HeadLinkDescriptor {
  key: string;
  rel: 'preconnect' | 'stylesheet';
  href: string;
  crossOrigin?: 'anonymous';
}

interface PlanningRouteContextValue {
  density: PlanningDensity;
  setDensity: (density: PlanningDensity) => void;
  toggleDensity: () => void;
}

const DEFAULT_DENSITY: PlanningDensity = 'comfortable';

const PLANNING_HEAD_LINKS: HeadLinkDescriptor[] = [
  {
    key: 'planning-fonts-googleapis',
    rel: 'preconnect',
    href: 'https://fonts.googleapis.com',
  },
  {
    key: 'planning-fonts-gstatic',
    rel: 'preconnect',
    href: 'https://fonts.gstatic.com',
    crossOrigin: 'anonymous',
  },
  {
    key: 'planning-fonts-stylesheet',
    rel: 'stylesheet',
    href: 'https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Fraunces:opsz,wght@9..144,400;9..144,500&display=swap',
  },
];

const PlanningRouteContext = createContext<PlanningRouteContextValue | null>(null);

export function normalizePlanningDensityPreference(value: string | null | undefined): PlanningDensity {
  return value === 'compact' ? 'compact' : DEFAULT_DENSITY;
}

export function getPlanningHeadLinks(): HeadLinkDescriptor[] {
  return PLANNING_HEAD_LINKS;
}

function readStoredPlanningDensity(): PlanningDensity {
  if (typeof window === 'undefined') {
    return DEFAULT_DENSITY;
  }

  try {
    return normalizePlanningDensityPreference(window.localStorage.getItem(PLANNING_DENSITY_STORAGE_KEY));
  } catch {
    return DEFAULT_DENSITY;
  }
}

function ensureHeadLink({ key, rel, href, crossOrigin }: HeadLinkDescriptor): () => void {
  const selector = `link[data-planning-head="${key}"]`;
  const existing = document.head.querySelector<HTMLLinkElement>(selector);
  if (existing) {
    return () => undefined;
  }

  const link = document.createElement('link');
  link.setAttribute('data-planning-head', key);
  link.rel = rel;
  link.href = href;
  if (crossOrigin) {
    link.crossOrigin = crossOrigin;
  }
  document.head.appendChild(link);

  return () => {
    link.remove();
  };
}

export function usePlanningRoute(): PlanningRouteContextValue {
  const context = useContext(PlanningRouteContext);
  if (!context) {
    throw new Error('usePlanningRoute must be used within PlanningRouteLayout.');
  }
  return context;
}

export function PlanningDensityToggle({ className }: { className?: string }) {
  const { density, setDensity } = usePlanningRoute();

  return (
    <div
      className={cn(
        'planning-chip planning-mono border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-1 text-[10.5px]',
        className,
      )}
      role="group"
      aria-label="Planning density"
    >
      <BtnGhost
        type="button"
        size="xs"
        aria-pressed={density === 'comfortable'}
        onClick={() => setDensity('comfortable')}
        className={cn(
          'min-w-[88px] justify-center px-2.5',
          density === 'comfortable' && 'border-[color:var(--line-2)] bg-[color:var(--bg-3)] text-[color:var(--ink-0)]',
        )}
      >
        Comfortable
      </BtnGhost>
      <Btn
        type="button"
        size="xs"
        aria-pressed={density === 'compact'}
        onClick={() => setDensity('compact')}
        className={cn(
          'min-w-[72px] justify-center px-2.5',
          density !== 'compact' && 'border-transparent bg-transparent text-[color:var(--ink-2)] hover:bg-[color:var(--bg-2)]',
        )}
      >
        Compact
      </Btn>
    </div>
  );
}

export function PlanningRouteLayout() {
  const [density, setDensity] = useState<PlanningDensity>(() => readStoredPlanningDensity());

  useEffect(() => {
    const cleanups = getPlanningHeadLinks().map((descriptor) => ensureHeadLink(descriptor));
    return () => {
      cleanups.forEach((cleanup) => cleanup());
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    try {
      window.localStorage.setItem(PLANNING_DENSITY_STORAGE_KEY, density);
    } catch {
      // Ignore storage failures; density still works for the current session.
    }
  }, [density]);

  const value = useMemo<PlanningRouteContextValue>(
    () => ({
      density,
      setDensity,
      toggleDensity: () => setDensity((current) => (current === 'comfortable' ? 'compact' : 'comfortable')),
    }),
    [density],
  );

  return (
    <PlanningRouteContext.Provider value={value}>
      <div
        className={cn('planning-route min-h-full planning-density-comfortable', density === 'compact' && 'planning-density-compact')}
        data-planning-density={density}
      >
        <Outlet />
      </div>
    </PlanningRouteContext.Provider>
  );
}
