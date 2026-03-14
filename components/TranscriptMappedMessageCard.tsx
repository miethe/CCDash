import React from 'react';
import { Archive, CheckCircle2, Cpu, FileText, GitBranch, Layers, PlayCircle, Terminal, TestTube2, TrendingUp, Zap } from 'lucide-react';
import { TranscriptFormattedMessage } from './sessionTranscriptFormatting';

const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

export const isMappedTranscriptMessageKind = (kind: TranscriptFormattedMessage['kind']): boolean =>
  kind === 'mapped-command' || kind === 'mapped-artifact' || kind === 'mapped-action';

const fallbackMappedColor = (kind: TranscriptFormattedMessage['kind']): string => {
  if (kind === 'mapped-artifact') return '#f59e0b';
  if (kind === 'mapped-action') return '#0ea5e9';
  return '#22c55e';
};

export const mappedAccentColor = (value: string | undefined, kind: TranscriptFormattedMessage['kind']): string => {
  const color = String(value || '').trim();
  if (HEX_COLOR_PATTERN.test(color)) return color.toLowerCase();
  return fallbackMappedColor(kind);
};

export const rgbaFromHex = (hex: string, alpha: number): string => {
  const normalized = hex.replace('#', '').trim();
  const value = normalized.length === 3
    ? normalized.split('').map(char => `${char}${char}`).join('')
    : normalized;
  const r = Number.parseInt(value.slice(0, 2), 16);
  const g = Number.parseInt(value.slice(2, 4), 16);
  const b = Number.parseInt(value.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

export const mappedTranscriptIcon = (
  iconName: string | undefined,
  kind: TranscriptFormattedMessage['kind'],
  size = 12,
): React.ReactElement => {
  const token = String(iconName || '').trim().toLowerCase();
  if (token === 'archive' || token === 'box') return <Archive size={size} />;
  if (token === 'cpu' || token === 'chip') return <Cpu size={size} />;
  if (token === 'zap') return <Zap size={size} />;
  if (token === 'play-circle') return <PlayCircle size={size} />;
  if (token === 'check-circle-2') return <CheckCircle2 size={size} />;
  if (token === 'git-branch' || token === 'git-commit') return <GitBranch size={size} />;
  if (token === 'test-tube') return <TestTube2 size={size} />;
  if (token === 'clipboard-list') return <FileText size={size} />;
  if (token === 'rocket') return <TrendingUp size={size} />;
  if (token === 'settings-2') return <Layers size={size} />;
  if (kind === 'mapped-artifact') return <Archive size={size} />;
  if (kind === 'mapped-action') return <PlayCircle size={size} />;
  return <Terminal size={size} />;
};

interface TranscriptMappedMessageCardProps {
  message: TranscriptFormattedMessage;
  commandArtifactsCount?: number;
  onOpenArtifacts?: () => void;
}

export const TranscriptMappedMessageCard: React.FC<TranscriptMappedMessageCardProps> = ({
  message,
  commandArtifactsCount = 0,
  onOpenArtifacts,
}) => {
  if (!isMappedTranscriptMessageKind(message.kind) || !message.mapped) {
    return null;
  }

  const mapped = message.mapped;
  const accent = mappedAccentColor(mapped.color, message.kind);

  return (
    <div
      className="rounded-xl p-5 space-y-4 min-w-0 overflow-hidden"
      style={{
        border: `1px solid ${rgbaFromHex(accent, 0.35)}`,
        backgroundColor: rgbaFromHex(accent, 0.08),
      }}
    >
      <div className="flex items-start justify-between gap-3 min-w-0">
        <div className="space-y-1 min-w-0">
          <div className="text-[10px] uppercase tracking-widest font-bold flex items-center gap-1.5 min-w-0" style={{ color: accent }}>
            {mappedTranscriptIcon(mapped.icon, message.kind, 12)}
            <span className="truncate">{mapped.transcriptLabel || mapped.label}</span>
          </div>
          <p className="font-mono text-sm text-slate-100 whitespace-pre-wrap break-words [overflow-wrap:anywhere] min-w-0 overflow-hidden">
            {message.summary}
          </p>
        </div>
        <span
          className="text-[10px] px-2 py-1 rounded border text-slate-200 font-mono max-w-[40%] truncate shrink-0"
          style={{ borderColor: rgbaFromHex(accent, 0.35), backgroundColor: rgbaFromHex(accent, 0.12) }}
          title={mapped.mappingType}
        >
          {mapped.mappingType}
        </span>
      </div>

      {(mapped.command || mapped.args) && (
        <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3 space-y-2 min-w-0 overflow-hidden">
          {mapped.command && (
            <div className="min-w-0">
              <div className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-1">Command</div>
              <div className="font-mono text-xs text-slate-200 whitespace-pre-wrap break-words [overflow-wrap:anywhere] min-w-0">
                {mapped.command}
              </div>
            </div>
          )}
          {mapped.args && (
            <div className="min-w-0">
              <div className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-1">Args</div>
              <pre className="font-mono text-xs text-slate-300 whitespace-pre-wrap break-words [overflow-wrap:anywhere] max-h-48 overflow-auto min-w-0">
                {mapped.args}
              </pre>
            </div>
          )}
        </div>
      )}

      {mapped.matchText && (
        <div className="text-[11px] text-slate-300 min-w-0 overflow-hidden">
          <span className="text-slate-500 uppercase tracking-wider text-[10px] mr-2">Regex Match</span>
          <span className="font-mono whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{mapped.matchText}</span>
        </div>
      )}

      {commandArtifactsCount > 0 && onOpenArtifacts && (
        <button
          onClick={onOpenArtifacts}
          className="text-xs px-3 py-1.5 rounded-lg border border-amber-500/30 text-amber-300 bg-amber-500/10 hover:bg-amber-500/20"
        >
          Open Command Artifact ({commandArtifactsCount})
        </button>
      )}
    </div>
  );
};
