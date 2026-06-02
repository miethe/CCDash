// P5-010: New Spec modal for the planning shell.
//
// On submit: POST /api/agent/planning/specs { title, docType, projectId }
//             → { id, path, status }
// Uses createSpec() from services/specs.ts.

import {
  FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import { cn } from '@/lib/utils';
import { createSpec, CreateSpecError } from '@/services/specs';
import { Btn, BtnPrimary } from './primitives';

// ── Doc-type options ──────────────────────────────────────────────────────────

const DOC_TYPES = [
  { value: 'design-spec', label: 'Design spec' },
  { value: 'prd', label: 'PRD' },
  { value: 'implementation_plan', label: 'Implementation plan' },
  { value: 'spike', label: 'Spike' },
  { value: 'context', label: 'Context note' },
  { value: 'report', label: 'Report' },
] as const;

type DocTypeValue = (typeof DOC_TYPES)[number]['value'] | string;

// ── Field ─────────────────────────────────────────────────────────────────────

interface FieldProps {
  label: string;
  htmlFor: string;
  required?: boolean;
  children: React.ReactNode;
}

function Field({ label, htmlFor, required, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={htmlFor}
        className="planning-mono text-[11px] font-medium"
        style={{ color: 'var(--ink-2)' }}
      >
        {label}
        {required && (
          <span aria-hidden="true" style={{ color: 'var(--err)' }} className="ml-0.5">
            *
          </span>
        )}
      </label>
      {children}
    </div>
  );
}

const inputCls = cn(
  'planning-mono w-full rounded-[var(--radius-sm)] border px-3 py-2 text-[12px] outline-none transition-colors',
  'border-[color:var(--line-1)] bg-[color:var(--bg-2)] text-[color:var(--ink-0)]',
  'placeholder:text-[color:var(--ink-4)]',
  'focus:border-[color:var(--line-2)] focus:bg-[color:var(--bg-3)]',
);

// ── NewSpecModal ──────────────────────────────────────────────────────────────

export interface NewSpecModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (message: string) => void;
  projectId: string;
}

type SubmitState = 'idle' | 'submitting' | 'done' | 'error';

export function NewSpecModal({ open, onClose, onSuccess, projectId }: NewSpecModalProps) {
  const [title, setTitle] = useState('');
  const [docType, setDocType] = useState<DocTypeValue>('design-spec');
  const [submitState, setSubmitState] = useState<SubmitState>('idle');
  const [errorMsg, setErrorMsg] = useState('');

  const titleRef = useRef<HTMLInputElement>(null);

  // Reset state on open/close
  useEffect(() => {
    if (open) {
      setTitle('');
      setDocType('design-spec');
      setSubmitState('idle');
      setErrorMsg('');
      // Focus title input
      const t = window.setTimeout(() => titleRef.current?.focus(), 30);
      return () => window.clearTimeout(t);
    }
  }, [open]);

  // Escape closes
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      if (!title.trim()) return;
      if (!projectId) {
        setErrorMsg('No active project. Switch to a project before creating a spec.');
        setSubmitState('error');
        return;
      }

      setSubmitState('submitting');
      setErrorMsg('');

      try {
        const result = await createSpec({
          title: title.trim(),
          docType,
          projectId,
        });

        setSubmitState('done');
        const path = result.path || result.id;
        onSuccess(`Spec created${path ? `: ${path}` : ''}`);
        onClose();
      } catch (err) {
        const msg =
          err instanceof CreateSpecError
            ? err.message
            : err instanceof Error
            ? err.message
            : 'Spec creation failed.';
        setErrorMsg(msg);
        setSubmitState('error');
      }
    },
    [title, docType, projectId, onSuccess, onClose],
  );

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  if (!open) return null;

  const isSubmitting = submitState === 'submitting';
  const canSubmit = title.trim().length > 0 && !isSubmitting;

  return (
    /* Backdrop */
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-spec-title"
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      style={{ background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(3px)' }}
    >
      {/* Panel */}
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-md flex-col rounded-[var(--radius)] border"
        style={{
          background: 'var(--bg-1)',
          borderColor: 'var(--line-2)',
          boxShadow: '0 32px 80px rgba(0,0,0,0.6)',
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between border-b px-4 py-3"
          style={{ borderColor: 'var(--line-1)' }}
        >
          <h2
            id="new-spec-title"
            className="planning-mono text-[13px] font-semibold"
            style={{ color: 'var(--ink-0)' }}
          >
            New spec
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="planning-mono rounded p-1 text-[14px] leading-none transition-colors"
            style={{ color: 'var(--ink-3)' }}
          >
            ×
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} noValidate>
          <div className="flex flex-col gap-4 px-4 py-4">
            {/* Title */}
            <Field label="Title" htmlFor="new-spec-title-input" required>
              <input
                ref={titleRef}
                id="new-spec-title-input"
                type="text"
                required
                placeholder="e.g. Auth-refresh spec"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={isSubmitting}
                className={inputCls}
                maxLength={200}
              />
            </Field>

            {/* Doc type */}
            <Field label="Type" htmlFor="new-spec-doctype">
              <select
                id="new-spec-doctype"
                value={docType}
                onChange={(e) => setDocType(e.target.value)}
                disabled={isSubmitting}
                className={cn(inputCls, 'cursor-pointer')}
              >
                {DOC_TYPES.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </Field>

            {/* Error */}
            {submitState === 'error' && errorMsg && (
              <p
                role="alert"
                className="planning-mono rounded-[var(--radius-sm)] border px-3 py-2 text-[11.5px]"
                style={{
                  color: 'var(--err)',
                  borderColor: 'color-mix(in oklab, var(--err) 30%, var(--line-1))',
                  background: 'color-mix(in oklab, var(--err) 8%, var(--bg-2))',
                }}
              >
                {errorMsg}
              </p>
            )}
          </div>

          {/* Footer */}
          <div
            className="flex items-center justify-end gap-2 border-t px-4 py-3"
            style={{ borderColor: 'var(--line-1)' }}
          >
            <Btn
              type="button"
              size="sm"
              onClick={onClose}
              disabled={isSubmitting}
              className="planning-mono px-3 text-[11.5px]"
            >
              Cancel
            </Btn>
            <BtnPrimary
              type="submit"
              size="sm"
              disabled={!canSubmit}
              className="planning-mono min-w-[80px] px-3 text-[11.5px]"
            >
              {isSubmitting ? (
                <span className="flex items-center gap-1.5">
                  <svg
                    className="h-3 w-3 animate-spin"
                    viewBox="0 0 12 12"
                    fill="none"
                  >
                    <circle
                      cx="6"
                      cy="6"
                      r="4.5"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeDasharray="22"
                      strokeDashoffset="8"
                    />
                  </svg>
                  Creating…
                </span>
              ) : (
                'Create spec'
              )}
            </BtnPrimary>
          </div>
        </form>
      </div>
    </div>
  );
}
