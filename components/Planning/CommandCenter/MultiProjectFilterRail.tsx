/**
 * MPCC-502: Project filter rail for the multi-project command center.
 *
 * Renders an accessible, keyboard-navigable segmented filter bar showing:
 *   - "All projects" control with total count
 *   - Per-group controls (if groups exist)
 *   - Per-project controls with color accent + label + work-item count
 *   - Stale and error indicator badges on individual projects
 *
 * Design rules:
 *   - Color is ACCENT only — never color-only meaning.  Every colored chip
 *     also carries a text label and optionally an icon badge.
 *   - WCAG 2.1 AA contrast: accents are applied as left-border + subtle bg
 *     tint so that text remains on the dark planning surface (#eff2f7).
 *   - Keyboard: Arrow keys move focus between chips; Enter/Space selects.
 *   - ARIA: role="radiogroup" + role="radio" for mutually-exclusive project
 *     selection, role="group" / role="checkbox" when multi-select is added.
 */
import { useCallback, useRef } from 'react';
import { AlertCircle, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ProjectSummary } from '@/types';

// ── Helpers ────────────────────────────────────────────────────────────────────

/** Deterministic fallback color derived from projectId. */
function fallbackColor(projectId: string): string {
  let hash = 0;
  for (let i = 0; i < projectId.length; i++) {
    hash = projectId.charCodeAt(i) + ((hash << 5) - hash);
  }
  const h = Math.abs(hash) % 360;
  return `oklch(65% 0.18 ${h})`;
}

function resolveColor(summary: ProjectSummary): string {
  return summary.displayMetadata?.color || fallbackColor(summary.projectId);
}

/** Human-readable count label. */
function countLabel(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

// ── Sub-components ─────────────────────────────────────────────────────────────

interface ProjectChipProps {
  summary: ProjectSummary;
  selected: boolean;
  onSelect: (projectId: string) => void;
}

function ProjectChip({ summary, selected, onSelect }: ProjectChipProps) {
  const color = resolveColor(summary);
  const label = summary.displayMetadata?.labelOverride || summary.name;
  const totalCount = summary.counts?.workItems ?? 0;
  const hasError = Boolean(summary.error);
  const isStale = summary.isStale === true;

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSelect(summary.projectId);
      }
    },
    [onSelect, summary.projectId],
  );

  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={() => onSelect(summary.projectId)}
      onKeyDown={handleKeyDown}
      className={cn(
        'planning-mono group relative flex items-center gap-1.5 rounded-[var(--radius-sm)] border px-2 py-1 text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--brand)] focus-visible:ring-offset-1 focus-visible:ring-offset-[color:var(--bg-0)]',
        selected
          ? 'border-[color:var(--line-2)] bg-[color:var(--bg-3)] text-[color:var(--ink-0)]'
          : 'border-[color:var(--line-1)] bg-[color:var(--bg-1)] text-[color:var(--ink-2)] hover:border-[color:var(--line-2)] hover:text-[color:var(--ink-1)]',
      )}
      style={
        selected
          ? {
              boxShadow: `inset 3px 0 0 ${color}`,
              borderLeftColor: color,
            }
          : { boxShadow: `inset 3px 0 0 ${color}20` }
      }
      title={`${label} · ${totalCount} work items${isStale ? ' · data may be stale' : ''}${hasError ? ` · error: ${summary.error}` : ''}`}
    >
      {/* Color dot — accent with label, not color-only */}
      <span
        className="inline-block h-2 w-2 shrink-0 rounded-full"
        style={{ backgroundColor: color }}
        aria-hidden
      />

      {/* Project label */}
      <span className="max-w-[120px] truncate">{label}</span>

      {/* Work item count */}
      {totalCount > 0 && (
        <span
          className="rounded px-1 text-[10px]"
          style={{
            backgroundColor: selected ? 'var(--bg-4)' : 'var(--bg-2)',
            color: 'var(--ink-3)',
          }}
          aria-label={`${totalCount} work items`}
        >
          {countLabel(totalCount)}
        </span>
      )}

      {/* Stale indicator */}
      {isStale && !hasError && (
        <Clock
          size={11}
          className="text-[color:var(--warn)] shrink-0"
          aria-label="Data may be stale"
        />
      )}

      {/* Error indicator */}
      {hasError && (
        <AlertCircle
          size={11}
          className="text-[color:var(--err)] shrink-0"
          aria-label={`Error: ${summary.error}`}
        />
      )}
    </button>
  );
}

interface GroupChipProps {
  group: string;
  count: number;
  selected: boolean;
  onSelect: (group: string) => void;
}

function GroupChip({ group, count, selected, onSelect }: GroupChipProps) {
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSelect(group);
      }
    },
    [onSelect, group],
  );

  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={() => onSelect(group)}
      onKeyDown={handleKeyDown}
      className={cn(
        'planning-mono flex items-center gap-1 rounded-[var(--radius-sm)] border px-2 py-1 text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--brand)] focus-visible:ring-offset-1 focus-visible:ring-offset-[color:var(--bg-0)]',
        selected
          ? 'border-[color:var(--line-2)] bg-[color:var(--bg-3)] text-[color:var(--ink-0)]'
          : 'border-[color:var(--line-1)] bg-[color:var(--bg-1)] text-[color:var(--ink-2)] hover:border-[color:var(--line-2)] hover:text-[color:var(--ink-1)]',
      )}
    >
      {group}
      {count > 0 && (
        <span
          className="rounded px-1 text-[10px]"
          style={{
            backgroundColor: selected ? 'var(--bg-4)' : 'var(--bg-2)',
            color: 'var(--ink-3)',
          }}
          aria-label={`${count} projects`}
        >
          {count}
        </span>
      )}
    </button>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export interface MultiProjectFilterRailProps {
  projectSummaries: ProjectSummary[];
  /** Selected project IDs. Empty = all projects. */
  selectedProjectIds: string[];
  /** Selected group label. null = all groups. */
  selectedGroup: string | null;
  onProjectSelect: (projectId: string | null) => void;
  onGroupSelect: (group: string | null) => void;
  /** Total work item count across all projects. */
  totalCount?: number;
  className?: string;
}

export function MultiProjectFilterRail({
  projectSummaries,
  selectedProjectIds,
  selectedGroup,
  onProjectSelect,
  onGroupSelect,
  totalCount,
  className,
}: MultiProjectFilterRailProps) {
  const railRef = useRef<HTMLDivElement>(null);

  // Gather distinct groups
  const groups = Array.from(
    new Set(
      projectSummaries
        .map((s) => s.displayMetadata?.group)
        .filter((g): g is string => Boolean(g)),
    ),
  );

  const showGroups = groups.length > 1;

  // Keyboard arrow navigation within the rail
  const handleRailKeyDown = useCallback((e: React.KeyboardEvent) => {
    const rail = railRef.current;
    if (!rail) return;
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    const buttons = Array.from(
      rail.querySelectorAll<HTMLButtonElement>('button[role="radio"]'),
    );
    const current = document.activeElement;
    const idx = buttons.indexOf(current as HTMLButtonElement);
    if (idx === -1) return;
    e.preventDefault();
    const next =
      e.key === 'ArrowRight'
        ? buttons[(idx + 1) % buttons.length]
        : buttons[(idx - 1 + buttons.length) % buttons.length];
    next?.focus();
  }, []);

  // "All projects" is selected when no projectId and no group is active
  const allSelected = selectedProjectIds.length === 0 && selectedGroup === null;
  const allCount = totalCount ?? projectSummaries.reduce((acc, s) => acc + (s.counts?.workItems ?? 0), 0);

  return (
    <div
      ref={railRef}
      className={cn('flex flex-wrap items-center gap-1.5', className)}
      onKeyDown={handleRailKeyDown}
      data-testid="multi-project-filter-rail"
    >
      {/* All projects */}
      <div role="radiogroup" aria-label="Project filter" className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          role="radio"
          aria-checked={allSelected}
          onClick={() => {
            onProjectSelect(null);
            onGroupSelect(null);
          }}
          className={cn(
            'planning-mono flex items-center gap-1 rounded-[var(--radius-sm)] border px-2 py-1 text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--brand)] focus-visible:ring-offset-1 focus-visible:ring-offset-[color:var(--bg-0)]',
            allSelected
              ? 'border-[color:var(--brand)] bg-[color:var(--bg-3)] text-[color:var(--ink-0)]'
              : 'border-[color:var(--line-1)] bg-[color:var(--bg-1)] text-[color:var(--ink-2)] hover:border-[color:var(--line-2)] hover:text-[color:var(--ink-1)]',
          )}
          aria-label={`All projects · ${allCount} work items`}
        >
          all
          <span
            className="rounded px-1 text-[10px]"
            style={{
              backgroundColor: allSelected ? 'var(--bg-4)' : 'var(--bg-2)',
              color: 'var(--ink-3)',
            }}
          >
            {countLabel(allCount)}
          </span>
        </button>

        {/* Group chips (only when multiple groups present) */}
        {showGroups &&
          groups.map((group) => {
            const groupProjects = projectSummaries.filter(
              (s) => s.displayMetadata?.group === group,
            );
            return (
              <GroupChip
                key={`group-${group}`}
                group={group}
                count={groupProjects.length}
                selected={selectedGroup === group && selectedProjectIds.length === 0}
                onSelect={(g) => {
                  onGroupSelect(selectedGroup === g ? null : g);
                  onProjectSelect(null);
                }}
              />
            );
          })}

        {/* Separator */}
        {projectSummaries.length > 0 && (
          <span
            className="h-4 w-px shrink-0"
            style={{ backgroundColor: 'var(--line-2)' }}
            aria-hidden
          />
        )}

        {/* Per-project chips */}
        {projectSummaries.map((summary) => (
          <ProjectChip
            key={summary.projectId}
            summary={summary}
            selected={selectedProjectIds.includes(summary.projectId)}
            onSelect={(id) =>
              onProjectSelect(selectedProjectIds.includes(id) ? null : id)
            }
          />
        ))}
      </div>
    </div>
  );
}
