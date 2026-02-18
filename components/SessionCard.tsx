import React from 'react';
import { Calendar, Terminal } from 'lucide-react';

export interface SessionCardMetadata {
  sessionTypeLabel?: string;
  relatedCommand?: string;
  relatedPhases?: string[];
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
  return { sessionTypeLabel, relatedCommand, relatedPhases };
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
  status?: string;
  metadata?: SessionCardMetadata | null;
  headerRight?: React.ReactNode;
  infoBadges?: React.ReactNode;
  className?: string;
  onClick?: () => void;
  children?: React.ReactNode;
}

export const SessionCard: React.FC<SessionCardProps> = ({
  sessionId,
  title,
  model,
  startedAt,
  status,
  metadata,
  headerRight,
  infoBadges,
  className = '',
  onClick,
  children,
}) => {
  const { sessionTypeLabel, relatedCommand, relatedPhases } = extractSessionCardIndicators(metadata);
  const hasIndicators = Boolean(sessionTypeLabel || relatedCommand || relatedPhases.length > 0);
  const modelDisplay = formatModelDisplayName(model.raw, model.displayName);

  return (
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
      className={`bg-slate-900 border border-slate-800 rounded-2xl p-4 hover:border-slate-700 transition-colors ${onClick ? 'cursor-pointer focus:outline-none focus:ring-1 focus:ring-indigo-500/70' : ''} ${className}`.trim()}
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
                {relatedPhases.map(phase => (
                  <span key={`${sessionId}-phase-${phase}`} className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/40 text-amber-200 bg-amber-500/10 font-semibold">
                    {formatPhaseIndicator(phase)}
                  </span>
                ))}
                {relatedCommand && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded border border-cyan-500/35 text-cyan-200 bg-cyan-500/10 font-mono">
                    {relatedCommand}
                  </span>
                )}
              </div>
            )}
            <div className="text-sm font-semibold text-slate-200 truncate">{title}</div>
            <div className="font-mono text-[11px] text-slate-400 truncate">{sessionId}</div>
            <div className="flex flex-wrap items-center gap-2 mt-1">
              {startedAt && (
                <span className="text-[10px] text-slate-500 flex items-center gap-1">
                  <Calendar size={10} />
                  {new Date(startedAt).toLocaleDateString()}
                </span>
              )}
              <span className="text-[10px] text-slate-500 font-mono truncate" title={model.raw || modelDisplay}>
                {modelDisplay}
              </span>
              {infoBadges}
            </div>
          </div>
        </div>
        {headerRight}
      </div>
      {children}
    </div>
  );
};
