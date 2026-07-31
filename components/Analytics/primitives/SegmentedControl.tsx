/**
 * SegmentedControl — accessible N-way switcher for the analytics interactive
 * chart pattern (T-004, analytics-provider-views quick feature).
 *
 * Modelled on the pill-container idiom at
 * `components/Analytics/AnalyticsDashboard.tsx` L1303-1315 (bg-surface-overlay
 * wrapper, bg-primary active state) and the a11y attributes from
 * `components/Planning/CommandCenter/CommandCenterToolbar.tsx` L146-175
 * (`role="group"` + per-button `aria-pressed`/`aria-disabled`).
 *
 * Uses the analytics semantic tokens (bg-surface-overlay / bg-panel /
 * border-panel-border / bg-primary / text-primary-foreground) — NOT the
 * `planning-tokens.css` CSS variables, which are scoped to `.planning-route`
 * and will not resolve on analytics surfaces.
 */
import React from 'react';

import { cn } from '../../../lib/utils';

export interface SegmentedControlOption<TId extends string = string> {
  id: TId;
  label: string;
  icon?: React.ComponentType<{ size?: number; className?: string; 'aria-hidden'?: boolean }>;
  disabled?: boolean;
}

export type SegmentedControlSize = 'sm' | 'md';

export interface SegmentedControlProps<TId extends string = string> {
  options: SegmentedControlOption<TId>[];
  value: TId;
  onChange: (id: TId) => void;
  size?: SegmentedControlSize;
  /** Accessible name for the group (required — this control has no visible label by default). */
  ariaLabel: string;
  className?: string;
}

const SIZE_CLASSES: Record<SegmentedControlSize, string> = {
  sm: 'px-2 py-1 text-[11px] gap-1',
  md: 'px-3 py-1.5 text-xs gap-1.5',
};

export function SegmentedControl<TId extends string = string>({
  options,
  value,
  onChange,
  size = 'md',
  ariaLabel,
  className,
}: SegmentedControlProps<TId>) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn(
        'inline-flex items-center bg-surface-overlay rounded-lg p-0.5 border border-panel-border',
        className,
      )}
    >
      {options.map((option) => {
        const isActive = option.id === value;
        const isDisabled = option.disabled ?? false;
        const Icon = option.icon;
        return (
          <button
            key={option.id}
            type="button"
            onClick={isDisabled ? undefined : () => onChange(option.id)}
            disabled={isDisabled}
            aria-pressed={isActive}
            aria-disabled={isDisabled}
            title={option.label}
            className={cn(
              'inline-flex items-center font-semibold rounded transition-colors',
              SIZE_CLASSES[size],
              isDisabled
                ? 'cursor-not-allowed opacity-40 text-muted-foreground'
                : isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-panel-foreground',
            )}
          >
            {Icon ? <Icon size={size === 'sm' ? 11 : 13} aria-hidden /> : null}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
