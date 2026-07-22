import { useMemo } from 'react';
import type { ElementType, ReactNode } from 'react';
import {
  AlertCircle,
  BarChart3,
  Bot,
  FileText,
  Gauge,
  Layers,
  Loader2,
  Network,
  ShieldCheck,
  Sparkles,
  Wrench,
} from 'lucide-react';

import { buildFeatureAnalyticsSummary, flattenPlanningSessionCards } from '../../lib/sessionAnalytics';
import { cn } from '../../lib/utils';
import {
  usePlanningCommandCenterQuery,
  usePlanningFeatureSessionBoardQuery,
} from '../../services/queries/planning';
import type {
  FeaturePlanningContext,
  PlanningAgentSessionBoard,
  PlanningAgentSessionCard,
  PlanningCommandCenterItem,
} from '../../types';

export interface FeatureAnalyticsPanelProps {
  projectId: string;
  featureId: string;
  featureContext?: FeaturePlanningContext | null;
  className?: string;
}

type UnknownRecord = Record<string, unknown>;

interface DenseRow {
  id: string;
  label: string;
  count?: number | null;
  tokens?: number | null;
  share?: number | null;
  state?: string | null;
  detail?: string | null;
}

interface ComparisonRow {
  id: string;
  label: string;
  planned: boolean;
  observed: boolean;
  plannedCount?: number | null;
  observedCount?: number | null;
  detail?: string | null;
}

interface AvailabilityRow {
  id: string;
  label: string;
  available: boolean | null;
  plannedCount?: number | null;
  observedCount?: number | null;
  detail?: string | null;
}

interface ConfidenceRow {
  id: string;
  label: string;
  count?: number | null;
  share?: number | null;
  detail?: string | null;
}

const MAX_ROWS = 8;

function asRecord(value: unknown): UnknownRecord | null {
  return value != null && typeof value === 'object' && !Array.isArray(value)
    ? value as UnknownRecord
    : null;
}

function asRows(value: unknown): UnknownRecord[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const record = asRecord(item);
    return record ? [record] : [];
  });
}

function firstValue(record: UnknownRecord | null | undefined, keys: string[]): unknown {
  if (!record) return undefined;
  for (const key of keys) {
    const value = record[key];
    if (value != null && value !== '') return value;
  }
  return undefined;
}

function stringValue(record: UnknownRecord | null | undefined, keys: string[]): string | null {
  const value = firstValue(record, keys);
  if (typeof value === 'string' && value.trim()) return value;
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return null;
}

function numberValue(record: UnknownRecord | null | undefined, keys: string[]): number | null {
  const value = firstValue(record, keys);
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function boolValue(record: UnknownRecord | null | undefined, keys: string[]): boolean | null {
  const value = firstValue(record, keys);
  return typeof value === 'boolean' ? value : null;
}

function nestedRecord(record: UnknownRecord, keys: string[]): UnknownRecord {
  for (const key of keys) {
    const nested = asRecord(record[key]);
    if (nested) return nested;
  }
  return {};
}

function nestedRows(record: UnknownRecord, keys: string[]): UnknownRecord[] {
  for (const key of keys) {
    const rows = asRows(record[key]);
    if (rows.length > 0) return rows;
  }
  return [];
}

function formatInteger(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString() : '0';
}

function formatTokens(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '0';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 10_000) return `${Math.round(value / 1_000).toLocaleString()}k`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return value.toLocaleString();
}

function formatPercent(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '0%';
  const normalized = value > 1 ? value : value * 100;
  return `${Math.round(normalized)}%`;
}

function normalizeLabel(value: string | number | null | undefined, fallback: string): string {
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  if (typeof value === 'string' && value.trim()) return value;
  return fallback;
}

function cardTokenTotal(card: PlanningAgentSessionCard): number {
  return card.tokenSummary?.totalTokens ?? 0;
}

function allCards(board: PlanningAgentSessionBoard | null): PlanningAgentSessionCard[] {
  return board?.groups.flatMap((group) => group.cards) ?? [];
}

function sumBoardTokens(board: PlanningAgentSessionBoard | null): number {
  return allCards(board).reduce((sum, card) => sum + cardTokenTotal(card), 0);
}

function uniqueCount(values: Iterable<string | null | undefined>): number {
  const seen = new Set<string>();
  for (const value of values) {
    if (value?.trim()) seen.add(value);
  }
  return seen.size;
}

function tableRowsFromRecords(records: UnknownRecord[], fallbackPrefix: string): DenseRow[] {
  return records.map((record, index) => {
    const label = normalizeLabel(
      stringValue(record, ['label', 'name', 'phaseLabel', 'phase', 'model', 'agent', 'agentName', 'key', 'id']),
      `${fallbackPrefix} ${index + 1}`,
    );
    return {
      id: stringValue(record, ['id', 'key', 'label', 'name']) ?? `${fallbackPrefix}-${index}`,
      label,
      count: numberValue(record, ['count', 'sessions', 'sessionCount', 'observedCount', 'logCount']),
      tokens: numberValue(record, ['totalTokens', 'tokens', 'tokenTotal', 'workloadTokens', 'observedTokens', 'value']),
      share: numberValue(record, ['share', 'pct', 'percent']),
      state: stringValue(record, ['state', 'status', 'confidence']),
      detail: stringValue(record, ['detail', 'description', 'summary']),
    };
  });
}

function groupBoardBy(
  board: PlanningAgentSessionBoard | null,
  getKey: (card: PlanningAgentSessionCard) => string | null | undefined,
  fallbackLabel: string,
): DenseRow[] {
  const groups = new Map<string, { count: number; tokens: number }>();
  for (const card of allCards(board)) {
    const key = getKey(card)?.trim() || fallbackLabel;
    const current = groups.get(key) ?? { count: 0, tokens: 0 };
    current.count += 1;
    current.tokens += cardTokenTotal(card);
    groups.set(key, current);
  }
  const totalTokens = Array.from(groups.values()).reduce((sum, row) => sum + row.tokens, 0);
  return Array.from(groups.entries())
    .map(([label, row]) => ({
      id: label,
      label,
      count: row.count,
      tokens: row.tokens,
      share: totalTokens > 0 ? row.tokens / totalTokens : null,
    }))
    .sort((a, b) => (b.tokens ?? 0) - (a.tokens ?? 0));
}

function phaseRowsFromBoard(board: PlanningAgentSessionBoard | null): DenseRow[] {
  if (!board) return [];
  if (board.grouping === 'phase') {
    const totalTokens = sumBoardTokens(board);
    return board.groups
      .filter((group) => group.cardCount > 0 || group.cards.length > 0)
      .map((group) => {
        const tokens = group.cards.reduce((sum, card) => sum + cardTokenTotal(card), 0);
        return {
          id: group.groupKey,
          label: group.groupLabel || group.groupKey || 'Unassigned phase',
          count: group.cardCount || group.cards.length,
          tokens,
          share: totalTokens > 0 ? tokens / totalTokens : null,
        };
      })
      .sort((a, b) => (b.tokens ?? 0) - (a.tokens ?? 0));
  }
  return groupBoardBy(
    board,
    (card) => card.correlation?.phaseTitle ?? (
      card.correlation?.phaseNumber != null ? `Phase ${card.correlation.phaseNumber}` : null
    ),
    'Unassigned phase',
  );
}

function normalizeDenseRows(
  summary: UnknownRecord,
  keys: string[],
  fallbackRows: DenseRow[],
  fallbackPrefix: string,
): DenseRow[] {
  const records = nestedRows(summary, keys);
  const rows = records.length > 0 ? tableRowsFromRecords(records, fallbackPrefix) : fallbackRows;
  return rows.filter((row) => row.count || row.tokens || row.label).slice(0, MAX_ROWS);
}

function valuesFromRecords(records: UnknownRecord[], keys: string[]): Set<string> {
  const values = new Set<string>();
  for (const record of records) {
    for (const key of keys) {
      const value = record[key];
      if (typeof value === 'string' && value.trim()) values.add(value);
      if (Array.isArray(value)) {
        for (const item of value) {
          if (typeof item === 'string' && item.trim()) values.add(item);
        }
      }
    }
  }
  return values;
}

function comparisonRowsFromSets(
  planned: Set<string>,
  observed: Set<string>,
  emptyLabel: string,
): ComparisonRow[] {
  const labels = Array.from(new Set([...planned, ...observed])).sort((a, b) => a.localeCompare(b));
  if (labels.length === 0) {
    return [{
      id: `${emptyLabel}-empty`,
      label: 'No data',
      planned: false,
      observed: false,
    }];
  }
  return labels.slice(0, MAX_ROWS).map((label) => ({
    id: label,
    label,
    planned: planned.has(label),
    observed: observed.has(label),
  }));
}

function comparisonRowsFromRecords(records: UnknownRecord[], fallbackId: string): ComparisonRow[] {
  return records.slice(0, MAX_ROWS).map((record, index) => {
    const plannedCount = numberValue(record, ['plannedCount', 'planned', 'expectedCount']);
    const observedCount = numberValue(record, ['observedCount', 'observed', 'actualCount']);
    return {
      id: stringValue(record, ['id', 'key', 'label', 'name']) ?? `${fallbackId}-${index}`,
      label: normalizeLabel(stringValue(record, ['label', 'name', 'key', 'id']), `${fallbackId} ${index + 1}`),
      planned: boolValue(record, ['planned', 'expected', 'isPlanned']) ?? (plannedCount != null ? plannedCount > 0 : false),
      observed: boolValue(record, ['observed', 'actual', 'isObserved']) ?? (observedCount != null ? observedCount > 0 : false),
      plannedCount,
      observedCount,
      detail: stringValue(record, ['detail', 'description', 'summary', 'state', 'status']),
    };
  });
}

function comparisonGroup(
  summary: UnknownRecord,
  groupKey: string,
  fallbackRows: ComparisonRow[],
): ComparisonRow[] {
  const plannedObserved = nestedRecord(summary, ['plannedVsObserved', 'plannedObserved', 'comparison']);
  const group = asRecord(plannedObserved[groupKey]);
  const rows = asRows(group?.items ?? plannedObserved[groupKey]);
  if (rows.length > 0) return comparisonRowsFromRecords(rows, groupKey);
  const directRows = nestedRows(summary, [`${groupKey}Comparison`, `${groupKey}Rows`]);
  if (directRows.length > 0) return comparisonRowsFromRecords(directRows, groupKey);
  return fallbackRows;
}

function availabilityRowsFromRecords(records: UnknownRecord[], fallbackId: string): AvailabilityRow[] {
  return records.slice(0, MAX_ROWS).map((record, index) => {
    const observedCount = numberValue(record, ['observedCount', 'observed', 'availableCount', 'actualCount', 'sessionCount', 'count']);
    return {
      id: stringValue(record, ['id', 'key', 'path', 'label', 'name']) ?? `${fallbackId}-${index}`,
      label: normalizeLabel(
        stringValue(record, ['label', 'name', 'path', 'tool', 'artifactId', 'docType']),
        `${fallbackId} ${index + 1}`,
      ),
      available: boolValue(record, ['available', 'exists', 'observed', 'present'])
        ?? (observedCount != null ? observedCount > 0 : null),
      plannedCount: numberValue(record, ['plannedCount', 'planned', 'expectedCount']),
      observedCount,
      detail: stringValue(record, ['detail', 'description', 'summary', 'status', 'docType']),
    };
  });
}

function availabilityGroup(
  summary: UnknownRecord,
  key: string,
  fallbackRows: AvailabilityRow[],
): AvailabilityRow[] {
  const availability = nestedRecord(summary, ['availability', 'resourceAvailability']);
  const rows = asRows(availability[key]);
  if (rows.length > 0) return availabilityRowsFromRecords(rows, key);
  const summaryRows = asRows(summary[key]);
  if (summaryRows.length > 0) return availabilityRowsFromRecords(summaryRows, key);
  const directRows = nestedRows(summary, [`${key}Availability`, `${key}Rows`]);
  if (directRows.length > 0) return availabilityRowsFromRecords(directRows, key);
  return fallbackRows;
}

function confidenceRows(summary: UnknownRecord, board: PlanningAgentSessionBoard | null): ConfidenceRow[] {
  const confidence = nestedRecord(summary, ['attributionConfidence', 'confidence', 'confidenceSummary']);
  const explicitRows = asRows(confidence.rows ?? summary.confidenceRows);
  if (explicitRows.length > 0) {
    return explicitRows.slice(0, MAX_ROWS).map((record, index) => ({
      id: stringValue(record, ['id', 'key', 'label', 'confidence']) ?? `confidence-${index}`,
      label: normalizeLabel(stringValue(record, ['label', 'confidence', 'tier', 'key']), `Confidence ${index + 1}`),
      count: numberValue(record, ['count', 'sessions', 'sessionCount']),
      share: numberValue(record, ['share', 'pct', 'percent']),
      detail: stringValue(record, ['detail', 'description', 'summary']),
    }));
  }

  const tiers = new Map<string, number>();
  for (const card of allCards(board)) {
    const tier = card.correlation?.confidence ?? 'unknown';
    tiers.set(tier, (tiers.get(tier) ?? 0) + 1);
  }
  const total = Array.from(tiers.values()).reduce((sum, count) => sum + count, 0);
  return ['high', 'medium', 'low', 'unknown']
    .map((tier) => {
      const count = tiers.get(tier) ?? 0;
      return {
        id: tier,
        label: tier,
        count,
        share: total > 0 ? count / total : null,
      };
    })
    .filter((row) => row.count > 0 || row.id === 'unknown');
}

function findFeatureItem(
  items: PlanningCommandCenterItem[] | undefined,
  featureId: string,
): PlanningCommandCenterItem | null {
  const normalized = featureId.trim().toLowerCase();
  if (!normalized) return null;
  return (items ?? []).find((item) => {
    const candidates = [
      item.feature.featureId,
      item.feature.featureSlug,
      item.feature.name,
    ].map((value) => value.trim().toLowerCase());
    return candidates.includes(normalized);
  }) ?? null;
}

function fallbackComparisonGroups(
  board: PlanningAgentSessionBoard | null,
  item: PlanningCommandCenterItem | null,
  sessionRows: UnknownRecord[],
) {
  const cards = allCards(board);
  const plannedAgents = new Set<string>();
  const plannedSkills = new Set<string>();
  const plannedModels = new Set<string>();
  const plannedTasks = new Set<string>();

  for (const row of item?.phaseRows ?? []) {
    for (const agent of row.agents ?? []) plannedAgents.add(agent);
    if (row.model) plannedModels.add(row.model);
    if (row.name) plannedTasks.add(row.name);
  }
  for (const agent of item?.launchBatch?.agents ?? []) {
    plannedAgents.add(agent.label || agent.agentId);
    for (const skill of agent.skills ?? []) plannedSkills.add(skill);
  }

  const observedAgents = new Set(cards.map((card) => card.agentName).filter(Boolean) as string[]);
  const observedModels = new Set(cards.map((card) => card.model).filter(Boolean) as string[]);
  const observedTasks = new Set(
    cards
      .map((card) => card.correlation?.taskTitle ?? card.correlation?.taskId)
      .filter(Boolean) as string[],
  );
  const observedSkills = valuesFromRecords(sessionRows, ['skill', 'skills', 'skillName', 'skillsUsed']);

  return {
    agents: comparisonRowsFromSets(plannedAgents, observedAgents, 'agents'),
    skills: comparisonRowsFromSets(plannedSkills, observedSkills, 'skills'),
    models: comparisonRowsFromSets(plannedModels, observedModels, 'models'),
    tasks: comparisonRowsFromSets(plannedTasks, observedTasks, 'tasks'),
  };
}

function fallbackAvailability(item: PlanningCommandCenterItem | null, board: PlanningAgentSessionBoard | null) {
  const artifacts: AvailabilityRow[] = (item?.artifacts ?? []).slice(0, MAX_ROWS).map((artifact) => ({
    id: artifact.artifactId || artifact.path,
    label: artifact.title || artifact.path || artifact.artifactId,
    available: artifact.exists ?? null,
    detail: artifact.docType || artifact.status,
  }));

  const files: AvailabilityRow[] = (item?.relatedFiles ?? []).slice(0, MAX_ROWS).map((file) => ({
    id: file.path,
    label: file.path,
    available: file.addable ? false : true,
    detail: file.docType,
  }));

  const observedTools = new Set(
    allCards(board).flatMap((card) =>
      card.activityMarkers
        .filter((marker) => marker.markerType === 'tool_call' || marker.markerType === 'command')
        .map((marker) => marker.label),
    ),
  );
  const plannedTools = new Set(
    (item?.launchBatch?.agents ?? []).flatMap((agent) => agent.tools ?? []),
  );
  const tools = Array.from(new Set([...plannedTools, ...observedTools]))
    .slice(0, MAX_ROWS)
    .map((tool) => ({
      id: tool,
      label: tool,
      available: observedTools.has(tool),
      plannedCount: plannedTools.has(tool) ? 1 : 0,
      observedCount: observedTools.has(tool) ? 1 : 0,
      detail: plannedTools.has(tool) && observedTools.has(tool)
        ? 'planned and observed'
        : plannedTools.has(tool)
          ? 'planned'
          : 'observed',
    }));

  return { artifacts, files, tools };
}

function statusClass(value: string | null | undefined): string {
  const normalized = value?.toLowerCase() ?? '';
  if (normalized.includes('high') || normalized.includes('matched') || normalized.includes('available')) {
    return 'border-ok/30 bg-ok/10 text-ok';
  }
  if (normalized.includes('low') || normalized.includes('missing') || normalized.includes('failed')) {
    return 'border-err/30 bg-err/10 text-err';
  }
  if (normalized.includes('medium') || normalized.includes('partial')) {
    return 'border-warn/30 bg-warn/10 text-warn';
  }
  return 'border-border/40 bg-surface-0 text-muted-foreground';
}

function confidenceBarClass(value: string | null | undefined): string {
  const normalized = value?.toLowerCase() ?? '';
  if (normalized.includes('high') || normalized.includes('matched')) return 'bg-ok';
  if (normalized.includes('medium') || normalized.includes('partial')) return 'bg-warn';
  if (normalized.includes('low') || normalized.includes('missing') || normalized.includes('failed')) return 'bg-err';
  return 'bg-muted-foreground/30';
}

function StateChip({ children, tone }: { children: string; tone?: string | null }) {
  return (
    <span className={cn('rounded-sm border px-1.5 py-0.5 text-[10px] font-medium capitalize', statusClass(tone ?? children))}>
      {children}
    </span>
  );
}

function SectionPanel({
  icon: Icon,
  title,
  children,
  className,
}: {
  icon: ElementType;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('rounded-lg border border-border/40 bg-surface-1', className)}>
      <div className="flex items-center gap-2 border-b border-border/30 px-3 py-2">
        <Icon size={13} className="text-muted-foreground" aria-hidden="true" />
        <h2 className="text-xs font-semibold uppercase text-muted-foreground">{title}</h2>
      </div>
      <div className="p-3">{children}</div>
    </section>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string | null }) {
  return (
    <div className="rounded-md border border-border/30 bg-surface-0 px-3 py-2">
      <div className="text-[10px] font-medium uppercase text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-lg font-semibold tabular-nums">{value}</div>
      {detail && <div className="mt-0.5 truncate text-[10px] text-muted-foreground/70">{detail}</div>}
    </div>
  );
}

function TokenTable({ rows, emptyLabel }: { rows: DenseRow[]; emptyLabel: string }) {
  if (rows.length === 0) {
    return <p className="py-4 text-center text-xs text-muted-foreground">{emptyLabel}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[360px] text-xs">
        <thead className="text-[10px] uppercase text-muted-foreground/70">
          <tr>
            <th className="pb-2 text-left font-medium">Name</th>
            <th className="pb-2 text-right font-medium">Sessions</th>
            <th className="pb-2 text-right font-medium">Tokens</th>
            <th className="pb-2 text-right font-medium">Share</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/30">
          {rows.map((row) => (
            <tr key={row.id}>
              <td className="max-w-[220px] py-2 pr-3">
                <div className="truncate font-medium">{row.label}</div>
                {row.detail && <div className="truncate text-[10px] text-muted-foreground/60">{row.detail}</div>}
              </td>
              <td className="py-2 text-right font-mono tabular-nums text-muted-foreground">
                {formatInteger(row.count)}
              </td>
              <td className="py-2 text-right font-mono tabular-nums">{formatTokens(row.tokens)}</td>
              <td className="py-2 text-right font-mono tabular-nums text-muted-foreground">
                {row.share != null ? formatPercent(row.share) : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ComparisonTable({ rows }: { rows: ComparisonRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[320px] text-xs">
        <thead className="text-[10px] uppercase text-muted-foreground/70">
          <tr>
            <th className="pb-2 text-left font-medium">Name</th>
            <th className="pb-2 text-right font-medium">Planned</th>
            <th className="pb-2 text-right font-medium">Observed</th>
            <th className="pb-2 text-right font-medium">State</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/30">
          {rows.map((row) => {
            const state = row.planned && row.observed
              ? 'matched'
              : row.planned
                ? 'missing'
                : row.observed
                  ? 'unplanned'
                  : 'none';
            return (
              <tr key={row.id}>
                <td className="max-w-[180px] py-2 pr-3">
                  <div className="truncate font-medium">{row.label}</div>
                  {row.detail && <div className="truncate text-[10px] text-muted-foreground/60">{row.detail}</div>}
                </td>
                <td className="py-2 text-right font-mono tabular-nums">
                  {row.plannedCount != null ? formatInteger(row.plannedCount) : row.planned ? 'yes' : '-'}
                </td>
                <td className="py-2 text-right font-mono tabular-nums">
                  {row.observedCount != null ? formatInteger(row.observedCount) : row.observed ? 'yes' : '-'}
                </td>
                <td className="py-2 text-right">
                  <StateChip tone={state}>{state}</StateChip>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function AvailabilityTable({ rows, emptyLabel }: { rows: AvailabilityRow[]; emptyLabel: string }) {
  if (rows.length === 0) {
    return <p className="py-4 text-center text-xs text-muted-foreground">{emptyLabel}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[320px] text-xs">
        <thead className="text-[10px] uppercase text-muted-foreground/70">
          <tr>
            <th className="pb-2 text-left font-medium">Name</th>
            <th className="pb-2 text-right font-medium">Observed</th>
            <th className="pb-2 text-right font-medium">State</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/30">
          {rows.map((row) => {
            const state = row.available === true ? 'available' : row.available === false ? 'missing' : 'unknown';
            return (
              <tr key={row.id}>
                <td className="max-w-[220px] py-2 pr-3">
                  <div className="truncate font-medium">{row.label}</div>
                  {row.detail && <div className="truncate text-[10px] text-muted-foreground/60">{row.detail}</div>}
                </td>
                <td className="py-2 text-right font-mono tabular-nums">
                  {row.observedCount != null ? formatInteger(row.observedCount) : row.available === true ? 'yes' : '-'}
                </td>
                <td className="py-2 text-right">
                  <StateChip tone={state}>{state}</StateChip>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ConfidenceTable({ rows }: { rows: ConfidenceRow[] }) {
  return (
    <div className="space-y-2">
      {rows.map((row) => (
        <div key={row.id} className="grid grid-cols-[96px_1fr_64px] items-center gap-2 text-xs">
          <div className="truncate capitalize text-muted-foreground">{row.label}</div>
          <div className="h-2 overflow-hidden rounded-full bg-surface-0">
            <div
              className={cn('h-full rounded-full', confidenceBarClass(row.label))}
              style={{ width: row.share != null ? formatPercent(row.share) : row.count ? '100%' : '0%' }}
            />
          </div>
          <div className="text-right font-mono tabular-nums">
            {row.share != null ? formatPercent(row.share) : formatInteger(row.count)}
          </div>
        </div>
      ))}
    </div>
  );
}

export function FeatureAnalyticsPanel({ projectId, featureId, featureContext = null, className }: FeatureAnalyticsPanelProps) {
  const sessionBoardQuery = usePlanningFeatureSessionBoardQuery({
    projectId: projectId || null,
    featureId: featureId || null,
    grouping: 'phase',
    limit: 500,
    enabled: Boolean(projectId && featureId),
  });

  const commandCenterQuery = usePlanningCommandCenterQuery({
    projectId: projectId || null,
    q: featureId,
    page: 1,
    pageSize: 50,
    hideDone: false,
    enabled: Boolean(projectId && featureId),
  });

  const board = sessionBoardQuery.data ?? null;
  const featureItem = useMemo(
    () => findFeatureItem(commandCenterQuery.data?.items, featureId),
    [commandCenterQuery.data?.items, featureId],
  );

  const sessionCards = useMemo<PlanningAgentSessionCard[]>(() => {
    if (!board) return [];
    return flattenPlanningSessionCards(board);
  }, [board]);

  const sessionRows = useMemo<UnknownRecord[]>(() => asRows(sessionCards), [sessionCards]);

  const summary = useMemo<UnknownRecord>(() => {
    if (!board) return {};
    return asRecord(buildFeatureAnalyticsSummary({
      featureContext,
      sessionCards,
      commandCenterItem: featureItem,
    })) ?? {};
  }, [board, featureContext, featureItem, sessionCards]);

  if (!projectId) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <Network size={24} className="text-muted-foreground/50" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">No active project selected.</p>
      </div>
    );
  }

  if (sessionBoardQuery.isLoading && !board) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground" role="status">
        <Loader2 size={16} className="animate-spin" aria-hidden="true" />
        <span className="text-xs">Loading feature analytics...</span>
      </div>
    );
  }

  if (sessionBoardQuery.isError && !board) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle size={24} className="text-err" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          {sessionBoardQuery.error instanceof Error
            ? sessionBoardQuery.error.message
            : 'Failed to load feature analytics.'}
        </p>
      </div>
    );
  }

  const executive = nestedRecord(summary, ['executiveSummary', 'summary', 'totals']);
  const boardCards = allCards(board);
  const totalSessions = numberValue(executive, ['totalSessions', 'sessionCount', 'sessions'])
    ?? board?.totalCardCount
    ?? boardCards.length;
  const activeSessions = numberValue(executive, ['activeSessions', 'activeSessionCount', 'activeCount'])
    ?? board?.activeCount
    ?? 0;
  const completedSessions = numberValue(executive, ['completedSessions', 'completedSessionCount', 'completedCount'])
    ?? board?.completedCount
    ?? 0;
  const totalTokens = numberValue(executive, ['totalTokens', 'tokens', 'observedTokens'])
    ?? numberValue(summary, ['totalTokens', 'tokens'])
    ?? sumBoardTokens(board);

  const plannedObservedFallback = fallbackComparisonGroups(board, featureItem, sessionRows);
  const availabilityFallback = fallbackAvailability(featureItem, board);

  const phaseRows = normalizeDenseRows(summary, ['tokensByPhase', 'phaseTokens', 'byPhase', 'phases'], phaseRowsFromBoard(board), 'Phase');
  const modelRows = normalizeDenseRows(
    summary,
    ['tokensByModel', 'modelTokens', 'byModel'],
    groupBoardBy(board, (card) => card.model, 'Unknown model'),
    'Model',
  );
  const agentRows = normalizeDenseRows(
    summary,
    ['tokensByAgent', 'agentTokens', 'byAgent'],
    groupBoardBy(board, (card) => card.agentName, 'Unknown agent'),
    'Agent',
  );

  const agentComparison = comparisonGroup(summary, 'agents', plannedObservedFallback.agents);
  const skillComparison = comparisonGroup(summary, 'skills', plannedObservedFallback.skills);
  const modelComparison = comparisonGroup(summary, 'models', plannedObservedFallback.models);
  const taskComparison = comparisonGroup(summary, 'tasks', plannedObservedFallback.tasks);

  const artifactAvailability = availabilityGroup(summary, 'artifacts', availabilityFallback.artifacts);
  const fileAvailability = availabilityGroup(summary, 'files', availabilityFallback.files);
  const toolAvailability = availabilityGroup(summary, 'tools', availabilityFallback.tools);
  const attributionRows = confidenceRows(summary, board);

  const observedAgentCount = uniqueCount(boardCards.map((card) => card.agentName));
  const observedModelCount = uniqueCount(boardCards.map((card) => card.model));
  const plannedAgentCount = uniqueCount([
    ...((featureItem?.phaseRows ?? []).flatMap((row) => row.agents ?? [])),
    ...((featureItem?.launchBatch?.agents ?? []).map((agent) => agent.label || agent.agentId)),
  ]);
  const plannedModelCount = uniqueCount((featureItem?.phaseRows ?? []).map((row) => row.model));

  return (
    <div className={cn('space-y-4', className)} data-testid="feature-analytics-panel">
      {commandCenterQuery.isError && (
        <div className="flex items-start gap-2 rounded-md border border-warn/30 bg-warn/5 px-3 py-2 text-xs text-warn">
          <AlertCircle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>Planning command center data is unavailable; planned rows are limited.</span>
        </div>
      )}

      <SectionPanel icon={Sparkles} title="Executive Summary">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Sessions" value={formatInteger(totalSessions)} detail={`${formatInteger(activeSessions)} active`} />
          <Metric label="Completed" value={formatInteger(completedSessions)} detail={`${formatInteger(totalSessions - completedSessions)} open`} />
          <Metric label="Tokens" value={formatTokens(totalTokens)} detail="observed session usage" />
          <Metric
            label="Planned vs Observed"
            value={`${formatInteger(plannedAgentCount)}/${formatInteger(observedAgentCount)}`}
            detail={`${formatInteger(plannedModelCount)}/${formatInteger(observedModelCount)} models`}
          />
        </div>
      </SectionPanel>

      <div className="grid gap-4 xl:grid-cols-3">
        <SectionPanel icon={BarChart3} title="Tokens by Phase">
          <TokenTable rows={phaseRows} emptyLabel="No phase token rows." />
        </SectionPanel>
        <SectionPanel icon={Gauge} title="Tokens by Model">
          <TokenTable rows={modelRows} emptyLabel="No model token rows." />
        </SectionPanel>
        <SectionPanel icon={Bot} title="Tokens by Agent">
          <TokenTable rows={agentRows} emptyLabel="No agent token rows." />
        </SectionPanel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <SectionPanel icon={Bot} title="Agents">
          <ComparisonTable rows={agentComparison} />
        </SectionPanel>
        <SectionPanel icon={Sparkles} title="Skills">
          <ComparisonTable rows={skillComparison} />
        </SectionPanel>
        <SectionPanel icon={Gauge} title="Models">
          <ComparisonTable rows={modelComparison} />
        </SectionPanel>
        <SectionPanel icon={FileText} title="Tasks">
          <ComparisonTable rows={taskComparison} />
        </SectionPanel>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <SectionPanel icon={Layers} title="Artifacts Availability">
          <AvailabilityTable rows={artifactAvailability} emptyLabel="No artifact rows." />
        </SectionPanel>
        <SectionPanel icon={FileText} title="Files Availability">
          <AvailabilityTable rows={fileAvailability} emptyLabel="No file rows." />
        </SectionPanel>
        <SectionPanel icon={Wrench} title="Tools Availability">
          <AvailabilityTable rows={toolAvailability} emptyLabel="No tool rows." />
        </SectionPanel>
      </div>

      <SectionPanel icon={ShieldCheck} title="Attribution Confidence">
        <ConfidenceTable rows={attributionRows} />
      </SectionPanel>
    </div>
  );
}

export default FeatureAnalyticsPanel;
