import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { useModelColors } from '@/contexts/ModelColorsContext';
import { extractModelIdentity, type ModelDescriptor } from '@/lib/modelIdentity';
import { resolveStablePaletteColor, toColorBadgeStyle } from '@/lib/modelColors';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center rounded-full border font-semibold whitespace-nowrap',
  {
    variants: {
      size: {
        sm: 'gap-1 px-1.5 py-0.5 text-[10px]',
        md: 'gap-1.5 px-2 py-1 text-xs',
      },
      tone: {
        neutral: 'border-panel-border bg-surface-overlay/80 text-panel-foreground',
        muted: 'border-panel-border bg-surface-muted text-muted-foreground',
        info: 'border-info-border bg-info/10 text-info-foreground',
        success: 'border-success-border bg-success/10 text-success-foreground',
        warning: 'border-warning-border bg-warning/10 text-warning-foreground',
        danger: 'border-danger-border bg-danger/10 text-danger-foreground',
        outline: 'border-panel-border bg-transparent text-panel-foreground',
      },
      mono: {
        true: 'font-mono',
        false: '',
      },
    },
    defaultVariants: {
      size: 'sm',
      tone: 'neutral',
      mono: false,
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, size, tone, mono, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(badgeVariants({ size, tone, mono }), className)}
      {...props}
    />
  ),
);
Badge.displayName = 'Badge';

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

export interface StableBadgeProps extends Omit<BadgeProps, 'children'> {
  value: string;
  namespace?: string;
  prefix?: string;
}

export const StableBadge: React.FC<StableBadgeProps> = ({
  value,
  namespace = 'badge',
  prefix,
  className,
  style,
  title,
  size,
  tone,
  mono,
  ...props
}) => {
  const normalizedValue = String(value || '').trim();
  if (!normalizedValue) return null;

  return (
    <Badge
      size={size}
      tone={tone}
      mono={mono}
      className={className}
      style={{ ...toColorBadgeStyle(resolveStablePaletteColor(normalizedValue, namespace)), ...style }}
      title={title || normalizedValue}
      {...props}
    >
      {prefix && <span className="opacity-80">{prefix}</span>}
      <span>{normalizedValue}</span>
    </Badge>
  );
};

export interface ModelBadgeProps extends Omit<BadgeProps, 'children'>, ModelDescriptor {
  showProviderGlyph?: boolean;
}

export const ModelBadge: React.FC<ModelBadgeProps> = ({
  raw,
  displayName,
  provider,
  family,
  version,
  showProviderGlyph = true,
  className,
  style,
  title,
  size,
  tone,
  mono,
  ...props
}) => {
  const { getBadgeStyleForModel } = useModelColors();
  const identity = extractModelIdentity({ raw, displayName, provider, family, version });
  const versionText = identity.version && identity.version.toLowerCase().startsWith(identity.family.toLowerCase())
    ? identity.version.slice(identity.family.length).trim()
    : identity.version;

  return (
    <Badge
      size={size}
      tone={tone}
      mono={mono}
      className={className}
      style={{ ...getBadgeStyleForModel({ model: raw || identity.displayName, family: identity.family }), ...style }}
      title={title || raw || identity.displayName}
      {...props}
    >
      {showProviderGlyph && (
        <span
          className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-sm bg-black/20"
          title={identity.provider}
          aria-label={identity.provider}
        >
          {providerGlyph(identity.provider)}
        </span>
      )}
      <span>{identity.family}</span>
      {versionText && (
        <span className="font-mono opacity-90">{versionText}</span>
      )}
    </Badge>
  );
};
