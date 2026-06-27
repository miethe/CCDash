/**
 * MPCC-501: Mode toggle that lets users switch between single-project (V1)
 * and multi-project (consolidated) command center views.
 *
 * Rendered inside CommandCenterToolbar area.  Only visible when the
 * MULTI_PROJECT_COMMAND_CENTER_ENABLED flag is on.
 */
import type { ButtonHTMLAttributes } from 'react';
import { Globe, Layers } from 'lucide-react';
import { cn } from '@/lib/utils';

export type CommandCenterMode = 'single' | 'multi';

interface MultiProjectModeToggleProps {
  mode: CommandCenterMode;
  onModeChange: (mode: CommandCenterMode) => void;
  className?: string;
}

interface ToggleBtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
}

function ToggleBtn({ active, className, children, ...rest }: ToggleBtnProps) {
  return (
    <button
      type="button"
      className={cn(
        'inline-flex h-[24px] items-center gap-1 rounded-[var(--radius-sm)] px-2 text-[10.5px] transition-colors',
        active
          ? 'bg-[color:var(--bg-3)] text-[color:var(--ink-0)]'
          : 'text-[color:var(--ink-3)] hover:text-[color:var(--ink-1)]',
        className,
      )}
      aria-pressed={active}
      {...rest}
    >
      {children}
    </button>
  );
}

export function MultiProjectModeToggle({
  mode,
  onModeChange,
  className,
}: MultiProjectModeToggleProps) {
  return (
    <div
      role="group"
      aria-label="Command center scope"
      className={cn(
        'planning-chip planning-mono flex items-center gap-0.5 border border-[color:var(--line-1)] bg-[color:var(--bg-1)] p-0.5',
        className,
      )}
    >
      <ToggleBtn
        active={mode === 'single'}
        onClick={() => onModeChange('single')}
        aria-label="Single project view"
        title="Current project only"
      >
        <Layers size={12} aria-hidden />
        project
      </ToggleBtn>
      <ToggleBtn
        active={mode === 'multi'}
        onClick={() => onModeChange('multi')}
        aria-label="All projects portfolio view"
        title="All projects consolidated"
      >
        <Globe size={12} aria-hidden />
        portfolio
      </ToggleBtn>
    </div>
  );
}
