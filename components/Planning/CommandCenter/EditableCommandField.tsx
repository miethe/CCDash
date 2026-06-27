import { RotateCcw } from 'lucide-react';

import { BtnGhost } from '../primitives';

interface EditableCommandFieldProps {
  value: string;
  originalValue: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}

export function EditableCommandField({
  value,
  originalValue,
  disabled = false,
  onChange,
}: EditableCommandFieldProps) {
  const isEdited = value !== originalValue;

  return (
    <div className="space-y-2" data-testid="command-center-editable-command">
      <div className="flex items-center justify-between gap-2">
        <label className="planning-caps text-[10px] text-[color:var(--ink-3)]" htmlFor="command-center-command-input">
          next command
        </label>
        <BtnGhost
          size="xs"
          disabled={!isEdited || disabled}
          onClick={() => onChange(originalValue)}
          aria-label="Reset command"
        >
          <RotateCcw size={12} aria-hidden />
          reset
        </BtnGhost>
      </div>
      <textarea
        id="command-center-command-input"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.currentTarget.value)}
        className="planning-mono min-h-[74px] w-full resize-y rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-0)] px-3 py-2 text-[11px] leading-relaxed text-[color:var(--ink-1)] outline-none transition-colors focus:border-[color:var(--brand)] disabled:cursor-not-allowed disabled:opacity-60"
      />
      {isEdited ? (
        <p className="planning-mono text-[10px] text-[color:var(--warn)]">
          local edit only; launch/copy uses this value
        </p>
      ) : null}
    </div>
  );
}
