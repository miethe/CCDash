import React, { useMemo } from 'react';

interface HealthGaugeProps {
  passRate: number;
  integrityScore?: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

const SIZE_PX = {
  sm: 64,
  md: 88,
  lg: 120,
} as const;

const STROKE_PX = {
  sm: 6,
  md: 8,
  lg: 10,
} as const;

const clamp01 = (value: number): number => {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
};

const healthColorClass = (value: number): string => {
  if (value >= 0.9) return 'text-success-foreground';
  if (value >= 0.75) return 'text-info-foreground';
  if (value >= 0.5) return 'text-warning-foreground';
  return 'text-danger-foreground';
};

export const HealthGauge: React.FC<HealthGaugeProps> = ({
  passRate,
  integrityScore = 1,
  size = 'md',
  showLabel = true,
  className = '',
}) => {
  const normalizedPass = clamp01(passRate);
  const normalizedIntegrity = clamp01(integrityScore);
  const healthScore = clamp01(normalizedPass * normalizedIntegrity);

  const dimension = SIZE_PX[size];
  const stroke = STROKE_PX[size];
  const radius = (dimension - stroke) / 2;
  const circumference = 2 * Math.PI * radius;

  const dashOffset = useMemo(() => circumference * (1 - healthScore), [circumference, healthScore]);
  const pctValue = Math.round(healthScore * 100);

  return (
    <div className={`inline-flex flex-col items-center gap-2 ${className}`.trim()}>
      <div className="relative" style={{ width: dimension, height: dimension }}>
        <svg width={dimension} height={dimension} viewBox={`0 0 ${dimension} ${dimension}`}>
          <circle
            cx={dimension / 2}
            cy={dimension / 2}
            r={radius}
            fill="transparent"
            stroke="currentColor"
            strokeWidth={stroke}
            className="text-panel-border"
          />
          <circle
            cx={dimension / 2}
            cy={dimension / 2}
            r={radius}
            fill="transparent"
            stroke="currentColor"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            className={`${healthColorClass(healthScore)} transition-all duration-300 ease-out`}
            transform={`rotate(-90 ${dimension / 2} ${dimension / 2})`}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={`font-bold ${size === 'lg' ? 'text-xl' : 'text-sm'} ${healthColorClass(healthScore)}`}>
            {pctValue}%
          </span>
        </div>
      </div>
      {showLabel && <span className="text-xs text-muted-foreground">Health</span>}
    </div>
  );
};

export type { HealthGaugeProps };
