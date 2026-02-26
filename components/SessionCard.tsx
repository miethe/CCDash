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
  provider?: string;
  family?: string;
  version?: string;
}

export interface SessionCardDetailSection {
  id: string;
  label: string;
  items: string[];
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

const extractModelIdentity = (
  model: SessionCardModel,
): { displayName: string; provider: string; family: string; version: string } => {
  const displayName = formatModelDisplayName(model.raw, model.displayName);
  const raw = (model.raw || '').toLowerCase();
  const providedProvider = (model.provider || '').trim();
  const providedFamily = (model.family || '').trim();
  const providedVersion = (model.version || '').trim();

  const provider = providedProvider || (
    raw.includes('claude')
      ? 'Claude'
      : raw.includes('gpt') || raw.includes('openai')
        ? 'OpenAI'
        : raw.includes('gemini')
          ? 'Gemini'
          : displayName.split(/\s+/)[0] || 'Model'
  );

  let family = providedFamily;
  if (!family) {
    if (raw.includes('opus')) family = 'Opus';
    else if (raw.includes('sonnet')) family = 'Sonnet';
    else if (raw.includes('haiku')) family = 'Haiku';
    else if (raw.includes('gpt-5')) family = 'GPT-5';
    else if (raw.includes('gpt-4o')) family = 'GPT-4o';
    else if (raw.includes('gpt-4')) family = 'GPT-4';
    else if (raw.includes('gemini')) family = 'Gemini';
  }

  let version = providedVersion;
  if (!version) {
    const claudeNamed = raw.match(/(?:opus|sonnet|haiku)-(\d+)-(\d+)/);
    const claudeNumeric = raw.match(/claude-(\d+)-(\d+)-(?:opus|sonnet|haiku)/);
    const gpt = raw.match(/gpt-(\d+(?:\.\d+)?[a-z0-9-]*)/);
    if (claudeNumeric) version = `${claudeNumeric[1]}.${claudeNumeric[2]}`;
    else if (claudeNamed) version = `${claudeNamed[1]}.${claudeNamed[2]}`;
    else if (gpt) version = gpt[1].toUpperCase();
  }

  if (!family) family = provider;
  if (!version && providedVersion) version = providedVersion;

  return {
    displayName,
    provider,
    family,
    version,
  };
};

const providerGlyph = (provider: string) => {
  const normalized = (provider || '').toLowerCase();
  if (normalized.includes('claude') || normalized.includes('anthropic')) {
    return (
      <svg viewBox="0 0 16 16" className="h-3 w-3 fill-current" aria-hidden="true">
        <path d="M8 2 13 14h-2l-1.1-2.8H6.1L5 14H3L8 2Zm0 3.2L6.8 8.6h2.4L8 5.2Z" />
      </svg>
    );
  }
  if (normalized.includes('openai') || normalized.includes('gpt')) {
    return (
      <svg viewBox="0 0 16 16" className="h-3 w-3 fill-none stroke-current stroke-[1.4]" aria-hidden="true">
        <path d="M8 2.2 12.5 4.8V10.9L8 13.8 3.5 10.9V4.8L8 2.2Z" />
        <path d="M5.3 6.1 8 4.6l2.7 1.5v3.1L8 10.8 5.3 9.2V6.1Z" />
      </svg>
    );
  }
  if (normalized.includes('gemini')) {
    return (
      <svg viewBox="0 0 16 16" className="h-3 w-3 fill-current" aria-hidden="true">
        <path d="m8 1.8 1.4 3.2 3.2 1.4-3.2 1.4L8 11 6.6 7.8 3.4 6.4 6.6 5 8 1.8Z" />
        <circle cx="12.5" cy="11.8" r="1.2" />
      </svg>
    );
  }
  return <span className="inline-block h-2 w-2 rounded-full bg-current" aria-hidden="true" />;
};

const modelBadgeTone = (model: SessionCardModel, provider: string): string => {
  const raw = (model.raw || '').toLowerCase();
  if (raw.includes('claude') && raw.includes('opus')) return 'border-rose-500/45 bg-rose-500/12 text-rose-200';
  if (raw.includes('claude') && raw.includes('sonnet')) return 'border-amber-500/45 bg-amber-500/12 text-amber-200';
  if (raw.includes('claude') && raw.includes('haiku')) return 'border-teal-500/45 bg-teal-500/12 text-teal-200';
  if (raw.includes('gpt-5')) return 'border-emerald-500/45 bg-emerald-500/12 text-emerald-200';
  if (raw.includes('gpt-4o')) return 'border-cyan-500/45 bg-cyan-500/12 text-cyan-200';
  if (raw.includes('gpt-4')) return 'border-sky-500/45 bg-sky-500/12 text-sky-200';
  if (raw.includes('gemini') && raw.includes('flash')) return 'border-blue-500/45 bg-blue-500/12 text-blue-200';
  if (raw.includes('gemini')) return 'border-indigo-500/45 bg-indigo-500/12 text-indigo-200';
  if ((provider || '').toLowerCase().includes('claude')) return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
  if ((provider || '').toLowerCase().includes('openai')) return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200';
  if ((provider || '').toLowerCase().includes('gemini')) return 'border-blue-500/40 bg-blue-500/10 text-blue-200';
  return 'border-slate-600/80 bg-slate-800/70 text-slate-300';
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
  models?: SessionCardModel[];
  agentBadges?: string[];
  skillBadges?: string[];
  detailSections?: SessionCardDetailSection[];
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
  models,
  agentBadges = [],
  skillBadges = [],
  detailSections = [],
  headerRight,
  infoBadges,
  threadToggle,
  className = '',
  onClick,
  children,
}) => {
  const [openDetailsId, setOpenDetailsId] = React.useState<string | null>(null);
  const detailsContainerRef = React.useRef<HTMLDivElement | null>(null);

  const { sessionTypeLabel, relatedCommand, relatedPhases, relatedFilePath } = extractSessionCardIndicators(metadata);
  const relatedFileName = fileNameFromPath(relatedFilePath);
  const hasIndicators = Boolean(sessionTypeLabel || relatedCommand || relatedPhases.length > 0 || relatedFileName);
  const modelDisplay = formatModelDisplayName(model.raw, model.displayName);
  const modelBadges = React.useMemo(() => {
    const source = Array.isArray(models) && models.length > 0 ? models : [model];
    const seen = new Set<string>();
    return source
      .map(item => ({ ...item, raw: (item.raw || '').trim() }))
      .filter(item => {
        if (!item.raw) return false;
        const key = item.raw.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
  }, [model, models]);
  const completedValue = dates?.completedAt?.value || endedAt;
  const startedValue = dates?.startedAt?.value || startedAt;
  const updatedValue = dates?.updatedAt?.value || updatedAt;
  const primaryDateLabel = status === 'completed' ? 'Completed' : 'Started';
  const primaryDateValue = status === 'completed' ? (completedValue || startedValue) : startedValue;
  const primaryConfidence = status === 'completed' ? dates?.completedAt?.confidence : dates?.startedAt?.confidence;
  const hasThreadToggle = Boolean(threadToggle);
  const threadToggleLabel = (threadToggle?.label || 'Sub-Threads').trim() || 'Sub-Threads';
  const normalizedDetailSections = detailSections.filter(section => Array.isArray(section.items) && section.items.length > 0);
  const hasFooterBadges = agentBadges.length > 0 || skillBadges.length > 0 || normalizedDetailSections.length > 0;

  React.useEffect(() => {
    if (!openDetailsId) return;
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (detailsContainerRef.current?.contains(target)) return;
      setOpenDetailsId(null);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [openDetailsId]);

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
                {updatedValue && (
                  <span className="text-[10px] text-slate-600">
                    Updated {new Date(updatedValue).toLocaleDateString()}
                  </span>
                )}
                {infoBadges}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {modelBadges.length > 0 ? modelBadges.map((entry) => {
                  const identity = extractModelIdentity(entry);
                  const tone = modelBadgeTone(entry, identity.provider);
                  const versionText = identity.version && identity.version.toLowerCase().startsWith(identity.family.toLowerCase())
                    ? identity.version.slice(identity.family.length).trim()
                    : identity.version;
                  return (
                    <span
                      key={`${sessionId}-model-${entry.raw}`}
                      className={`inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold ${tone}`}
                      title={entry.raw || identity.displayName}
                    >
                      <span
                        className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-sm bg-black/20"
                        title={identity.provider}
                        aria-label={identity.provider}
                      >
                        {providerGlyph(identity.provider)}
                      </span>
                      <span>{identity.family}</span>
                      {versionText && (
                        <span className="font-mono opacity-90">{versionText}</span>
                      )}
                    </span>
                  );
                }) : (
                  <span className="text-[10px] text-slate-500 font-mono truncate" title={model.raw || modelDisplay}>
                    {modelDisplay}
                  </span>
                )}
              </div>
            </div>
          </div>
          {headerRight}
        </div>
        {children}
        {hasFooterBadges && (
          <div className="mt-3 pt-3 border-t border-slate-800/70 space-y-2" ref={detailsContainerRef}>
            {agentBadges.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                {agentBadges.map(agent => (
                  <span
                    key={`${sessionId}-agent-${agent}`}
                    className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded border border-fuchsia-500/35 text-fuchsia-200 bg-fuchsia-500/10"
                    title={agent}
                  >
                    Agent: {agent}
                  </span>
                ))}
              </div>
            )}
            {skillBadges.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                {skillBadges.map(skill => (
                  <span
                    key={`${sessionId}-skill-${skill}`}
                    className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded border border-emerald-500/35 text-emerald-200 bg-emerald-500/10"
                    title={skill}
                  >
                    Skill: {skill}
                  </span>
                ))}
              </div>
            )}
            {normalizedDetailSections.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                {normalizedDetailSections.map(section => {
                  const isOpen = openDetailsId === section.id;
                  return (
                    <div key={`${sessionId}-details-${section.id}`} className="relative">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          setOpenDetailsId(prev => (prev === section.id ? null : section.id));
                        }}
                        className={`inline-flex items-center text-[10px] px-1.5 py-0.5 rounded border transition-colors ${
                          isOpen
                            ? 'border-cyan-400/60 bg-cyan-500/20 text-cyan-100'
                            : 'border-cyan-500/35 bg-cyan-500/10 text-cyan-200 hover:bg-cyan-500/20'
                        }`}
                      >
                        {section.label} ({section.items.length})
                      </button>
                      {isOpen && (
                        <div
                          role="dialog"
                          className="absolute z-30 left-0 mt-1 w-72 rounded-lg border border-slate-700 bg-slate-950/95 shadow-xl p-3"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <div className="text-[10px] font-semibold uppercase tracking-wide text-cyan-200 mb-2">
                            {section.label}
                          </div>
                          <div className="max-h-48 overflow-y-auto space-y-1">
                            {section.items.map(item => (
                              <div
                                key={`${sessionId}-${section.id}-${item}`}
                                className="text-[11px] text-slate-300 rounded border border-slate-800 bg-slate-900/70 px-2 py-1 break-words"
                              >
                                {item}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
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
