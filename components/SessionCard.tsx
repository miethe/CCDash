import React from 'react';
import { Calendar, ChevronDown, ChevronRight, Terminal } from 'lucide-react';

export interface SessionCardMetadata {
  sessionTypeLabel?: string;
  relatedCommand?: string;
  relatedPhases?: string[];
  relatedFilePath?: string;
  fields?: Array<{ id: string; label: string; value: string }>;
}

export interface SessionCardModel {
  raw: string;
  displayName?: string;
}

const titleCase = (value: string): string =>
  value
    .split(/\s+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

export const formatModelDisplayName = (rawModel: string, provided?: string): string => {
  const providedLabel = (provided || '').trim();
  if (providedLabel) return providedLabel;

  const raw = (rawModel || '').trim();
  if (!raw) return 'Unknown Model';
  const tokens = raw.toLowerCase().split(/[-_\s]+/).filter(Boolean);
  if (tokens.length === 0) return raw;

  const provider = tokens[0] === 'claude'
    ? 'Claude'
    : tokens[0] === 'gpt' || tokens[0] === 'openai'
      ? 'OpenAI'
      : tokens[0] === 'gemini'
        ? 'Gemini'
        : titleCase(tokens[0]);
  const family = tokens[1] ? titleCase(tokens[1]) : '';

  let version = '';
  const nums = tokens.slice(2).filter(token => /^\d+$/.test(token));
  if (nums.length >= 2) {
    version = `${nums[0]}.${nums[1]}`;
  } else if (nums.length === 1) {
    version = nums[0];
  }

  if (family && version) return `${provider} ${family} ${version}`;
  if (family) return `${provider} ${family}`;
  return provider || raw;
};

export const formatPhaseIndicator = (phase: string): string => {
  const normalized = (phase || '').trim();
  if (!normalized) return '';
  if (normalized.toLowerCase() === 'all') return 'All Phases';
  return /^\d+$/.test(normalized) ? `Phase ${normalized}` : `Phase ${normalized}`;
};

export const extractSessionCardIndicators = (metadata?: SessionCardMetadata | null): {
  sessionTypeLabel: string;
  relatedCommand: string;
  relatedPhases: string[];
  relatedFilePath: string;
} => {
  const sessionTypeLabel = (metadata?.sessionTypeLabel || '').trim();
  const fields = Array.isArray(metadata?.fields) ? metadata?.fields : [];
  const fieldById = (fieldId: string): string => {
    const field = fields.find(item => item.id === fieldId);
    return (field?.value || '').trim();
  };

  const relatedCommand = ((metadata?.relatedCommand || '').trim() || fieldById('related-command'));
  const relatedPhasesRaw = Array.isArray(metadata?.relatedPhases) ? metadata?.relatedPhases : [];
  const relatedPhasesFallback = fieldById('related-phases')
    .split(',')
    .map(token => token.trim())
    .filter(Boolean);
  const relatedPhases = Array.from(new Set((relatedPhasesRaw.length > 0 ? relatedPhasesRaw : relatedPhasesFallback).filter(Boolean)));
  const relatedFilePath = (
    metadata?.relatedFilePath
    || fieldById('feature-path')
    || fieldById('related-file-path')
  ).trim();

  return { sessionTypeLabel, relatedCommand, relatedPhases, relatedFilePath };
};

const fileNameFromPath = (path: string): string => {
  const normalized = (path || '').replace(/\\/g, '/').trim();
  if (!normalized) return '';
  const parts = normalized.split('/').filter(Boolean);
  return parts[parts.length - 1] || normalized;
};

export const deriveSessionCardTitle = (sessionId: string, explicitTitle?: string, metadata?: SessionCardMetadata | null): string => {
  const title = (explicitTitle || '').trim();
  if (title) return title;

  const { sessionTypeLabel, relatedPhases } = extractSessionCardIndicators(metadata);
  if (sessionTypeLabel && relatedPhases.length > 0) {
    const phaseText = relatedPhases.map(formatPhaseIndicator).join(', ');
    return `${sessionTypeLabel} - ${phaseText}`;
  }
  if (sessionTypeLabel) return sessionTypeLabel;
  return sessionId;
};

interface SessionCardProps {
  sessionId: string;
  title: string;
  model: SessionCardModel;
  startedAt?: string;
  endedAt?: string;
  updatedAt?: string;
  status?: string;
  dates?: {
    startedAt?: { value: string; confidence: string };
    completedAt?: { value: string; confidence: string };
    updatedAt?: { value: string; confidence: string };
  };
  metadata?: SessionCardMetadata | null;
  headerRight?: React.ReactNode;
  infoBadges?: React.ReactNode;
  threadToggle?: {
    expanded: boolean;
    childCount: number;
    onToggle: () => void;
    label?: string;
  };
  className?: string;
  onClick?: () => void;
  children?: React.ReactNode;
}

export const SessionCard: React.FC<SessionCardProps> = ({
  sessionId,
  title,
  model,
  startedAt,
  endedAt,
  updatedAt,
  status,
  dates,
  metadata,
  headerRight,
  infoBadges,
  threadToggle,
  className = '',
  onClick,
  children,
}) => {
  const { sessionTypeLabel, relatedCommand, relatedPhases, relatedFilePath } = extractSessionCardIndicators(metadata);
  const relatedFileName = fileNameFromPath(relatedFilePath);
  const hasIndicators = Boolean(sessionTypeLabel || relatedCommand || relatedPhases.length > 0 || relatedFileName);
  const modelDisplay = formatModelDisplayName(model.raw, model.displayName);
  const completedValue = dates?.completedAt?.value || endedAt;
  const startedValue = dates?.startedAt?.value || startedAt;
  const updatedValue = dates?.updatedAt?.value || updatedAt;
  const primaryDateLabel = status === 'completed' ? 'Completed' : 'Started';
  const primaryDateValue = status === 'completed' ? (completedValue || startedValue) : startedValue;
  const primaryConfidence = status === 'completed' ? dates?.completedAt?.confidence : dates?.startedAt?.confidence;
  const hasThreadToggle = Boolean(threadToggle);
  const threadToggleLabel = (threadToggle?.label || 'Sub-Threads').trim() || 'Sub-Threads';

  return (
    <div className="space-y-0">
      <div
        role={onClick ? 'button' : undefined}
        tabIndex={onClick ? 0 : undefined}
        onClick={onClick}
        onKeyDown={(event) => {
          if (!onClick) return;
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onClick();
          }
        }}
        className={`bg-slate-900 border border-slate-800 rounded-2xl p-4 hover:border-slate-700 transition-colors ${onClick ? 'cursor-pointer focus:outline-none focus:ring-1 focus:ring-indigo-500/70' : ''} ${className} ${hasThreadToggle ? 'rounded-b-none border-b-0' : ''}`.trim()}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className={`p-2 rounded-lg ${status === 'active' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-slate-800 text-slate-400'}`}>
              <Terminal size={16} />
            </div>
            <div className="min-w-0">
              {hasIndicators && (
                <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                  {sessionTypeLabel && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded border border-emerald-500/40 text-emerald-200 bg-emerald-500/10 font-semibold uppercase tracking-wide">
                      {sessionTypeLabel}
                    </span>
                  )}
                  {relatedCommand && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded border border-cyan-500/35 text-cyan-200 bg-cyan-500/10 font-mono">
                      {relatedCommand}
                    </span>
                  )}
                  {relatedPhases.map(phase => (
                    <span key={`${sessionId}-phase-${phase}`} className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/40 text-amber-200 bg-amber-500/10 font-semibold">
                      {formatPhaseIndicator(phase)}
                    </span>
                  ))}
                  {relatedFileName && (
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded border border-fuchsia-500/35 text-fuchsia-200 bg-fuchsia-500/10 font-mono"
                      title={relatedFilePath}
                    >
                      {relatedFileName}
                    </span>
                  )}
                </div>
              )}
              <div className="text-sm font-semibold text-slate-200 truncate">{title}</div>
              <div className="font-mono text-[11px] text-slate-400 truncate">{sessionId}</div>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                {primaryDateValue && (
                  <span className="text-[10px] text-slate-500 flex items-center gap-1">
                    <Calendar size={10} />
                    {primaryDateLabel} {new Date(primaryDateValue).toLocaleDateString()}
                    {primaryConfidence && (
                      <span className="uppercase text-[9px] text-slate-600">({primaryConfidence})</span>
                    )}
                  </span>
                )}
                <span className="text-[10px] text-slate-500 font-mono truncate" title={model.raw || modelDisplay}>
                  {modelDisplay}
                </span>
                {updatedValue && (
                  <span className="text-[10px] text-slate-600">
                    Updated {new Date(updatedValue).toLocaleDateString()}
                  </span>
                )}
                {infoBadges}
              </div>
            </div>
          </div>
          {headerRight}
        </div>
        {children}
      </div>
      {threadToggle && (
        <button
          type="button"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            threadToggle.onToggle();
          }}
          className="w-full flex items-center justify-between text-left px-3 py-2 rounded-b-2xl border border-slate-800 bg-slate-900/95 hover:border-slate-700 transition-colors"
          aria-expanded={threadToggle.expanded}
          aria-label={`${threadToggle.expanded ? 'Collapse' : 'Expand'} ${threadToggleLabel}`}
        >
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
            {threadToggle.expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {threadToggle.expanded ? `Hide ${threadToggleLabel}` : `Expand ${threadToggleLabel}`}
          </span>
          <span className="text-[11px] text-slate-500">{threadToggle.childCount}</span>
        </button>
      )}
    </div>
  );
};
