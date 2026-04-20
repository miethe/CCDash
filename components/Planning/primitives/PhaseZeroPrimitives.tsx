import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react';

import { cn } from '@/lib/utils';

type PrimitiveTone = 'default' | 'ghost' | 'primary';
type ButtonSize = 'xs' | 'sm' | 'md';
type StatusToken =
  | 'idea'
  | 'shaping'
  | 'ready'
  | 'draft'
  | 'approved'
  | 'in-progress'
  | 'in_progress'
  | 'blocked'
  | 'completed'
  | 'superseded'
  | 'future'
  | 'deprecated';

type ArtifactToken =
  | 'spec'
  | 'spike'
  | 'prd'
  | 'implementation_plan'
  | 'plan'
  | 'progress'
  | 'context'
  | 'tracker'
  | 'report';

interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  size?: ButtonSize;
  tone?: PrimitiveTone;
}

interface DotProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: string;
}

interface StatusPillProps extends HTMLAttributes<HTMLSpanElement> {
  status: StatusToken | string;
  size?: 'sm' | 'md';
}

interface ArtifactChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type'> {
  kind: ArtifactToken | string;
  label?: string;
  count?: number;
  active?: boolean;
  size?: 'sm' | 'md';
}

interface MetricTileProps extends HTMLAttributes<HTMLDivElement> {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  accent?: string;
  big?: boolean;
}

interface SectionHeaderProps extends HTMLAttributes<HTMLDivElement> {
  eyebrow?: string;
  heading: ReactNode;
  glyph?: ReactNode;
  actions?: ReactNode;
}

interface SparkProps {
  data: number[];
  color?: string;
  width?: number;
  height?: number;
}

interface ExecBtnProps extends Omit<BtnProps, 'tone' | 'children'> {
  label?: string;
  compact?: boolean;
}

const BUTTON_SIZE_CLASSNAMES: Record<ButtonSize, string> = {
  xs: 'min-h-[24px] px-2 py-0.5 text-[10.5px]',
  sm: 'min-h-[30px] px-2.5 py-1.5 text-[12px]',
  md: 'min-h-[34px] px-3 py-2 text-[12px]',
};

const STATUS_TOKENS: Record<string, { color: string; label: string }> = {
  idea: { color: 'var(--ink-2)', label: 'idea' },
  shaping: { color: 'var(--info)', label: 'shaping' },
  ready: { color: 'var(--spec)', label: 'ready' },
  draft: { color: 'var(--ink-2)', label: 'draft' },
  approved: { color: 'var(--prd)', label: 'approved' },
  'in-progress': { color: 'var(--plan)', label: 'in-progress' },
  in_progress: { color: 'var(--plan)', label: 'in-progress' },
  blocked: { color: 'var(--err)', label: 'blocked' },
  completed: { color: 'var(--ok)', label: 'completed' },
  superseded: { color: 'var(--ink-3)', label: 'superseded' },
  future: { color: 'var(--ink-3)', label: 'future' },
  deprecated: { color: 'var(--ink-3)', label: 'deprecated' },
};

const ARTIFACT_TOKENS: Record<string, { short: string; glyph: string; color: string }> = {
  spec: { short: 'SPEC', glyph: '◇', color: 'var(--spec)' },
  spike: { short: 'SPIKE', glyph: '✦', color: 'var(--spk)' },
  prd: { short: 'PRD', glyph: '▣', color: 'var(--prd)' },
  implementation_plan: { short: 'PLAN', glyph: '▤', color: 'var(--plan)' },
  plan: { short: 'PLAN', glyph: '▤', color: 'var(--plan)' },
  progress: { short: 'PROG', glyph: '◫', color: 'var(--prog)' },
  context: { short: 'CTX', glyph: '◌', color: 'var(--ctx)' },
  tracker: { short: 'TRK', glyph: '⚑', color: 'var(--trk)' },
  report: { short: 'REP', glyph: '◎', color: 'var(--rep)' },
};

function resolveStatusToken(status: string) {
  return STATUS_TOKENS[status] ?? { color: 'var(--ink-2)', label: status };
}

function resolveArtifactToken(kind: string) {
  return ARTIFACT_TOKENS[kind] ?? ARTIFACT_TOKENS.report;
}

function resolveToneClassName(tone: PrimitiveTone) {
  switch (tone) {
    case 'ghost':
      return 'planning-btn-ghost';
    case 'primary':
      return 'planning-btn-primary';
    default:
      return '';
  }
}

export function Panel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('planning-panel', className)} {...props} />;
}

export function Tile({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('planning-tile', className)} {...props} />;
}

export function Chip({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn('planning-chip', className)} {...props} />;
}

export function Btn({
  className,
  size = 'sm',
  tone = 'default',
  type = 'button',
  ...props
}: BtnProps) {
  return (
    <button
      type={type}
      className={cn('planning-btn', BUTTON_SIZE_CLASSNAMES[size], resolveToneClassName(tone), className)}
      {...props}
    />
  );
}

export function BtnGhost(props: BtnProps) {
  return <Btn tone="ghost" {...props} />;
}

export function BtnPrimary(props: BtnProps) {
  return <Btn tone="primary" {...props} />;
}

export function Dot({ className, tone = 'var(--brand)', style, ...props }: DotProps) {
  return <span className={cn('planning-dot', className)} style={{ background: tone, ...style }} {...props} />;
}

export function StatusPill({ className, status, size = 'sm', style, ...props }: StatusPillProps) {
  const token = resolveStatusToken(status);

  return (
    <span
      className={cn('planning-pill planning-tnum', className)}
      style={{
        background: `color-mix(in oklab, ${token.color} 15%, transparent)`,
        border: `1px solid color-mix(in oklab, ${token.color} 30%, transparent)`,
        color: token.color,
        padding: size === 'md' ? '3px 8px' : '2px 6px',
        ...style,
      }}
      {...props}
    >
      <Dot tone={token.color} />
      {token.label}
    </span>
  );
}

export function ArtifactChip({
  className,
  kind,
  label,
  count,
  active = false,
  size = 'sm',
  disabled,
  ...props
}: ArtifactChipProps) {
  const token = resolveArtifactToken(kind);
  const Component = props.onClick ? 'button' : 'span';
  const sizeStyle = size === 'md' ? { padding: '4px 10px', fontSize: 11.5 } : { padding: '2px 8px', fontSize: 10.5 };

  return (
    <Component
      className={cn(
        'planning-chip planning-mono border-[color:var(--line-1)] bg-[color:var(--bg-2)]',
        props.onClick && 'transition-colors hover:border-[color:var(--line-2)] hover:bg-[color:var(--bg-3)]',
        disabled && 'cursor-not-allowed opacity-60',
        className,
      )}
      disabled={disabled}
      style={{
        ...sizeStyle,
        background: active
          ? `color-mix(in oklab, ${token.color} 22%, var(--bg-2))`
          : `color-mix(in oklab, ${token.color} 10%, var(--bg-2))`,
        borderColor: `color-mix(in oklab, ${token.color} 35%, var(--line-1))`,
        color: `color-mix(in oklab, ${token.color} 90%, white)`,
      }}
      {...props}
    >
      <span aria-hidden="true" style={{ color: token.color, fontSize: 10 }}>
        {token.glyph}
      </span>
      <span>{label ?? token.short}</span>
      {typeof count === 'number' ? (
        <span
          className="planning-tnum rounded-full px-1.5 py-0.5"
          style={{ background: 'color-mix(in oklab, white 8%, transparent)', color: 'var(--ink-0)' }}
        >
          {count}
        </span>
      ) : null}
    </Component>
  );
}

export function MetricTile({
  className,
  label,
  value,
  sub,
  accent = 'var(--ink-0)',
  big = false,
  ...props
}: MetricTileProps) {
  return (
    <Tile
      className={cn('flex flex-col gap-1.5 px-4 py-3', className)}
      {...props}
    >
      <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">{label}</div>
      <div
        className="planning-tnum"
        style={{
          color: accent,
          fontFamily: 'var(--sans)',
          fontWeight: 600,
          fontSize: big ? 34 : 24,
          letterSpacing: '-0.02em',
          lineHeight: 1,
        }}
      >
        {value}
      </div>
      {sub ? <div className="text-[11px] text-[color:var(--ink-3)]">{sub}</div> : null}
    </Tile>
  );
}

export function SectionHeader({
  className,
  eyebrow,
  heading,
  glyph,
  actions,
  ...props
}: SectionHeaderProps) {
  return (
    <div className={cn('flex flex-wrap items-end justify-between gap-4', className)} {...props}>
      <div>
        {eyebrow ? (
          <div className="planning-caps mb-1.5 text-[10px] text-[color:var(--ink-3)]">{eyebrow}</div>
        ) : null}
        <div className="flex items-center gap-2">
          {glyph ? <span className="text-[color:var(--brand)]">{glyph}</span> : null}
          <h2 className="planning-serif m-0 text-[22px] font-medium tracking-[-0.01em] text-[color:var(--ink-0)]">
            {heading}
          </h2>
        </div>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Spark({ data, color = 'var(--brand)', width = 80, height = 22 }: SparkProps) {
  const safeData = data.length > 1 ? data : [0, ...data];
  const max = Math.max(...safeData, 1);
  const stepX = width / (safeData.length - 1);
  const points = safeData
    .map((value, index) => `${(index * stepX).toFixed(1)},${(height - (value / max) * (height - 2) - 1).toFixed(1)}`)
    .join(' ');

  return (
    <svg width={width} height={height} aria-hidden="true">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function ExecBtn({ className, compact = false, label = 'run', size, ...props }: ExecBtnProps) {
  return (
    <BtnPrimary
      size={size ?? (compact ? 'xs' : 'sm')}
      className={cn('planning-mono tracking-[0.02em]', className)}
      {...props}
    >
      <span aria-hidden="true">▶</span>
      {!compact ? <span>{label}</span> : null}
    </BtnPrimary>
  );
}
