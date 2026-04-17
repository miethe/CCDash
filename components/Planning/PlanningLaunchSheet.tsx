/**
 * PCP-504: PlanningLaunchSheet
 *
 * Centered modal for preparing and launching a planning batch. Calls
 * prepareLaunch on mount, lets the user pick provider/model/worktree, handles
 * approval gating and 409 force-override flow, then calls startLaunch.
 *
 * PlanningLaunchSheetContent is exported as a pure, testable inner renderer.
 */
import { useCallback, useEffect, useRef, useState, type JSX } from 'react';
import { Loader2, X, AlertCircle, AlertTriangle, ChevronDown } from 'lucide-react';

import type {
  LaunchPreparation,
  LaunchProviderCapability,
  LaunchStartResponse,
  WorktreeContext,
} from '../../types';
import { prepareLaunch, startLaunch } from '../../services/execution';
import { BatchReadinessPill, StatusChip, statusVariant } from '@/components/shared/PlanningMetadata';

// ── Helpers ────────────────────────────────────────────────────────────────────

const RISK_COLORS: Record<string, string> = {
  low: 'bg-emerald-600/20 text-emerald-400',
  medium: 'bg-amber-600/20 text-amber-400',
  high: 'bg-rose-600/20 text-rose-400',
};

const APPROVAL_BADGE_COLORS: Record<string, string> = {
  none: 'bg-slate-700/60 text-slate-300',
  optional: 'bg-amber-600/20 text-amber-400',
  required: 'bg-rose-600/20 text-rose-400',
};

function riskColor(level: string): string {
  return RISK_COLORS[level] ?? 'bg-slate-700/60 text-slate-300';
}

function approvalBadgeColor(req: string): string {
  return APPROVAL_BADGE_COLORS[req] ?? 'bg-slate-700/60 text-slate-300';
}

// ── Sheet props ────────────────────────────────────────────────────────────────

export interface PlanningLaunchSheetProps {
  open: boolean;
  projectId: string;
  featureId: string;
  phaseNumber: number;
  batchId: string;
  initialWorktreeContextId?: string;
  onClose: () => void;
  onLaunched?: (result: LaunchStartResponse) => void;
}

// ── PlanningLaunchSheetContent (pure, exported for testing) ───────────────────

export interface PlanningLaunchSheetContentProps {
  preparation: LaunchPreparation;
  selectedProvider: string;
  selectedModel: string;
  worktreeMode: 'reuse' | 'create';
  selectedWorktreeId: string;
  newBranch: string;
  newWorktreePath: string;
  newBaseBranch: string;
  newNotes: string;
  commandOverride: string;
  approvalAcknowledged: boolean;
  launching: boolean;
  launchError: string | null;
  showForceButton: boolean;
  onProviderChange: (v: string) => void;
  onModelChange: (v: string) => void;
  onWorktreeModeChange: (v: 'reuse' | 'create') => void;
  onWorktreeIdChange: (v: string) => void;
  onNewBranchChange: (v: string) => void;
  onNewWorktreePathChange: (v: string) => void;
  onNewBaseBranchChange: (v: string) => void;
  onNewNotesChange: (v: string) => void;
  onCommandOverrideChange: (v: string) => void;
  onApprovalAcknowledgeChange: (v: boolean) => void;
  onLaunch: () => void;
  onForceLaunch: () => void;
}

/**
 * Pure renderer for the sheet body + footer. No async, no hooks.
 * Exported so tests can render it with renderToStaticMarkup.
 */
export function PlanningLaunchSheetContent({
  preparation,
  selectedProvider,
  selectedModel,
  worktreeMode,
  selectedWorktreeId,
  newBranch,
  newWorktreePath,
  newBaseBranch,
  newNotes,
  commandOverride,
  approvalAcknowledged,
  launching,
  launchError,
  showForceButton,
  onProviderChange,
  onModelChange,
  onWorktreeModeChange,
  onWorktreeIdChange,
  onNewBranchChange,
  onNewWorktreePathChange,
  onNewBaseBranchChange,
  onNewNotesChange,
  onCommandOverrideChange,
  onApprovalAcknowledgeChange,
  onLaunch,
  onForceLaunch,
}: PlanningLaunchSheetContentProps): JSX.Element {
  const providerCap: LaunchProviderCapability | undefined = preparation.providers.find(
    p => p.provider === selectedProvider,
  );
  const needsApprovalGate =
    preparation.approval.requirement === 'required' ||
    preparation.approval.requirement === 'optional';
  const launchDisabled =
    launching ||
    (preparation.approval.requirement === 'required' && !approvalAcknowledged);

  return (
    <>
      <div className="px-5 py-4 space-y-5">
        {/* ── Batch summary ─────────────────────────────────────────────── */}
        <section className="rounded-lg border border-panel-border/50 bg-panel/30 px-4 py-3 space-y-2">
          <div className="flex flex-wrap items-start gap-2 mb-1">
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-panel-foreground truncate">
                {preparation.batch.featureName}
              </p>
              <p className="text-[11px] text-muted-foreground truncate">
                {preparation.batch.phaseTitle} &middot;{' '}
                <span className="font-mono">{preparation.batch.batchId}</span>
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <BatchReadinessPill readinessState={preparation.batch.readinessState} />
            {preparation.batch.tasks.slice(0, 6).map(task => (
              <StatusChip
                key={task.taskId}
                label={task.status}
                variant={statusVariant(task.status)}
                tooltip={task.title}
              />
            ))}
            {preparation.batch.tasks.length > 6 && (
              <span className="text-[10px] text-muted-foreground">
                +{preparation.batch.tasks.length - 6} more
              </span>
            )}
          </div>
          {preparation.batch.owners.length > 0 && (
            <p className="text-[11px] text-muted-foreground">
              Owners: {preparation.batch.owners.join(', ')}
            </p>
          )}
          {!preparation.batch.isReady && preparation.batch.blockedReason && (
            <div className="flex items-start gap-1.5 mt-1">
              <AlertTriangle size={12} className="shrink-0 mt-0.5 text-amber-400" />
              <p className="text-[11px] text-amber-400">{preparation.batch.blockedReason}</p>
            </div>
          )}
        </section>

        {/* ── Provider picker ───────────────────────────────────────────── */}
        <div className="space-y-1.5">
          <label
            htmlFor="launch-provider-select"
            className="block text-[11px] uppercase tracking-wide text-muted-foreground"
          >
            Provider
          </label>
          <select
            id="launch-provider-select"
            value={selectedProvider}
            onChange={e => onProviderChange(e.target.value)}
            className="w-full rounded border border-panel-border/60 bg-surface-overlay/50 px-2.5 py-1.5 text-sm text-panel-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
          >
            {preparation.providers.map(p => (
              <option key={p.provider} value={p.provider} disabled={!p.supported}>
                {p.label || p.provider}
                {!p.supported && p.unsupportedReason ? ` — ${p.unsupportedReason}` : ''}
              </option>
            ))}
          </select>
          {providerCap && !providerCap.supported && providerCap.unsupportedReason && (
            <p className="text-[11px] text-rose-400/80">{providerCap.unsupportedReason}</p>
          )}
        </div>

        {/* ── Model picker ──────────────────────────────────────────────── */}
        {providerCap?.supportsModelSelection && (
          <div className="space-y-1.5">
            <label
              htmlFor="launch-model-select"
              className="block text-[11px] uppercase tracking-wide text-muted-foreground"
            >
              Model
            </label>
            <select
              id="launch-model-select"
              value={selectedModel}
              onChange={e => onModelChange(e.target.value)}
              className="w-full rounded border border-panel-border/60 bg-surface-overlay/50 px-2.5 py-1.5 text-sm text-panel-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
            >
              {(providerCap.availableModels ?? []).map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
        )}

        {/* ── Worktree selection ────────────────────────────────────────── */}
        <div className="space-y-2">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Worktree</p>
          <div className="flex rounded border border-panel-border/60 overflow-hidden w-fit">
            <button
              type="button"
              onClick={() => onWorktreeModeChange('reuse')}
              className={`px-3 py-1.5 text-xs transition-colors ${
                worktreeMode === 'reuse'
                  ? 'bg-indigo-600/30 text-indigo-200'
                  : 'text-muted-foreground hover:text-panel-foreground'
              }`}
              disabled={preparation.worktreeCandidates.length === 0}
              title={
                preparation.worktreeCandidates.length === 0
                  ? 'No existing worktree contexts'
                  : undefined
              }
            >
              Reuse existing
            </button>
            <button
              type="button"
              onClick={() => onWorktreeModeChange('create')}
              className={`px-3 py-1.5 text-xs border-l border-panel-border/60 transition-colors ${
                worktreeMode === 'create'
                  ? 'bg-indigo-600/30 text-indigo-200'
                  : 'text-muted-foreground hover:text-panel-foreground'
              }`}
            >
              Create new
            </button>
          </div>

          {worktreeMode === 'reuse' ? (
            <div className="space-y-1">
              <label
                htmlFor="launch-worktree-select"
                className="block text-[11px] text-muted-foreground"
              >
                Existing worktree context
              </label>
              <select
                id="launch-worktree-select"
                value={selectedWorktreeId}
                onChange={e => onWorktreeIdChange(e.target.value)}
                className="w-full rounded border border-panel-border/60 bg-surface-overlay/50 px-2.5 py-1.5 text-sm text-panel-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
              >
                <option value="">-- none --</option>
                {preparation.worktreeCandidates.map((wt: WorktreeContext) => (
                  <option key={wt.id} value={wt.id}>
                    {wt.branch} · {wt.worktreePath}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label htmlFor="launch-branch" className="block text-[11px] text-muted-foreground">
                  Branch
                </label>
                <input
                  id="launch-branch"
                  type="text"
                  value={newBranch}
                  onChange={e => onNewBranchChange(e.target.value)}
                  placeholder="feature/my-branch"
                  className="w-full rounded border border-panel-border/60 bg-surface-overlay/50 px-2.5 py-1.5 text-sm text-panel-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                />
              </div>
              <div className="space-y-1">
                <label htmlFor="launch-base-branch" className="block text-[11px] text-muted-foreground">
                  Base branch
                </label>
                <input
                  id="launch-base-branch"
                  type="text"
                  value={newBaseBranch}
                  onChange={e => onNewBaseBranchChange(e.target.value)}
                  placeholder="main"
                  className="w-full rounded border border-panel-border/60 bg-surface-overlay/50 px-2.5 py-1.5 text-sm text-panel-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                />
              </div>
              <div className="col-span-2 space-y-1">
                <label htmlFor="launch-worktree-path" className="block text-[11px] text-muted-foreground">
                  Worktree path
                </label>
                <input
                  id="launch-worktree-path"
                  type="text"
                  value={newWorktreePath}
                  onChange={e => onNewWorktreePathChange(e.target.value)}
                  placeholder="/path/to/worktree"
                  className="w-full rounded border border-panel-border/60 bg-surface-overlay/50 px-2.5 py-1.5 text-sm text-panel-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                />
              </div>
              <div className="col-span-2 space-y-1">
                <label htmlFor="launch-notes" className="block text-[11px] text-muted-foreground">
                  Notes
                </label>
                <input
                  id="launch-notes"
                  type="text"
                  value={newNotes}
                  onChange={e => onNewNotesChange(e.target.value)}
                  placeholder="Optional notes"
                  className="w-full rounded border border-panel-border/60 bg-surface-overlay/50 px-2.5 py-1.5 text-sm text-panel-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                />
              </div>
            </div>
          )}
        </div>

        {/* ── Approval panel ────────────────────────────────────────────── */}
        {needsApprovalGate && (
          <div className="rounded-lg border border-panel-border/50 bg-panel/30 px-4 py-3 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                Approval
              </span>
              <span
                className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${approvalBadgeColor(preparation.approval.requirement)}`}
              >
                {preparation.approval.requirement}
              </span>
              <span
                className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${riskColor(preparation.approval.riskLevel)}`}
              >
                {preparation.approval.riskLevel} risk
              </span>
            </div>
            {preparation.approval.reasonCodes.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {preparation.approval.reasonCodes.map(code => (
                  <span
                    key={code}
                    className="inline-flex items-center rounded px-2 py-0.5 text-[11px] bg-slate-700/60 text-slate-300"
                  >
                    {code}
                  </span>
                ))}
              </div>
            )}
            {preparation.approval.requirement === 'required' && (
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  id="launch-approval-ack"
                  type="checkbox"
                  checked={approvalAcknowledged}
                  onChange={e => onApprovalAcknowledgeChange(e.target.checked)}
                  className="mt-0.5 accent-indigo-500"
                />
                <span className="text-xs text-panel-foreground">
                  I acknowledge this launch requires approval
                </span>
              </label>
            )}
          </div>
        )}

        {/* ── Command override ──────────────────────────────────────────── */}
        <details className="group">
          <summary className="flex items-center gap-1.5 cursor-pointer text-[11px] uppercase tracking-wide text-muted-foreground hover:text-panel-foreground list-none">
            <ChevronDown
              size={12}
              className="transition-transform group-open:rotate-180"
            />
            Command override
          </summary>
          <div className="mt-2 space-y-1">
            <label htmlFor="launch-cmd-override" className="block text-[11px] text-muted-foreground">
              Override the default launch command (leave blank for default)
            </label>
            <textarea
              id="launch-cmd-override"
              value={commandOverride}
              onChange={e => onCommandOverrideChange(e.target.value)}
              rows={3}
              placeholder="e.g. claude --feature-id ... --phase 1"
              className="w-full rounded border border-panel-border/60 bg-surface-overlay/50 px-2.5 py-1.5 text-sm text-panel-foreground font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/40 resize-y"
            />
          </div>
        </details>

        {/* ── Warnings ──────────────────────────────────────────────────── */}
        {preparation.warnings.length > 0 && (
          <div className="rounded-lg border border-amber-600/30 bg-amber-600/10 px-4 py-3 space-y-1">
            <p className="text-[11px] uppercase tracking-wide text-amber-400">Warnings</p>
            <ul className="space-y-1">
              {preparation.warnings.map((w, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span className="text-amber-400/70 text-xs mt-0.5">•</span>
                  <span className="text-xs text-amber-300/90">{w}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* ── Inline launch error ───────────────────────────────────────── */}
        {launchError && (
          <div className="rounded-lg border border-rose-600/30 bg-rose-600/10 px-4 py-3 space-y-2">
            <div className="flex items-start gap-1.5">
              <AlertCircle size={13} className="shrink-0 mt-0.5 text-rose-400" />
              <p className="text-xs text-rose-400">{launchError}</p>
            </div>
          </div>
        )}
      </div>

      {/* ── Footer actions ─────────────────────────────────────────────── */}
      <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-panel-border/60">
        {showForceButton && (
          <button
            type="button"
            onClick={onForceLaunch}
            disabled={launching}
            className="px-3 py-1.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-200 text-xs hover:bg-amber-500/20 disabled:opacity-50 transition-colors"
          >
            Force launch (approve override)
          </button>
        )}
        <button
          type="button"
          onClick={onLaunch}
          disabled={launchDisabled}
          className="flex items-center gap-1.5 px-4 py-1.5 rounded border border-indigo-500/40 bg-indigo-600/20 text-indigo-100 text-xs hover:bg-indigo-600/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {launching && <Loader2 size={12} className="animate-spin" />}
          Launch
        </button>
      </div>
    </>
  );
}

// ── PlanningLaunchSheet (stateful shell) ──────────────────────────────────────

export function PlanningLaunchSheet({
  open,
  projectId,
  featureId,
  phaseNumber,
  batchId,
  initialWorktreeContextId,
  onClose,
  onLaunched,
}: PlanningLaunchSheetProps): JSX.Element | null {
  // ── Preparation state ──────────────────────────────────────────────────────
  const [preparation, setPreparation] = useState<LaunchPreparation | null>(null);
  const [prepLoading, setPrepLoading] = useState(true);
  const [prepError, setPrepError] = useState<string | null>(null);

  // ── Selection state ────────────────────────────────────────────────────────
  const [selectedProvider, setSelectedProvider] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [worktreeMode, setWorktreeMode] = useState<'reuse' | 'create'>('reuse');
  const [selectedWorktreeId, setSelectedWorktreeId] = useState('');
  const [newBranch, setNewBranch] = useState('');
  const [newWorktreePath, setNewWorktreePath] = useState('');
  const [newBaseBranch, setNewBaseBranch] = useState('');
  const [newNotes, setNewNotes] = useState('');
  const [commandOverride, setCommandOverride] = useState('');
  const [approvalAcknowledged, setApprovalAcknowledged] = useState(false);

  // ── Launch state ───────────────────────────────────────────────────────────
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [showForceButton, setShowForceButton] = useState(false);

  // ── Focus ref ──────────────────────────────────────────────────────────────
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const providerSelectRef = useRef<HTMLSelectElement>(null);

  // ── Fetch preparation ──────────────────────────────────────────────────────
  const fetchPreparation = useCallback(async () => {
    if (!open) return;
    setPrepLoading(true);
    setPrepError(null);
    setPreparation(null);
    setLaunchError(null);
    setShowForceButton(false);
    setApprovalAcknowledged(false);
    try {
      const result = await prepareLaunch({
        projectId,
        featureId,
        phaseNumber,
        batchId,
        worktreeContextId: initialWorktreeContextId,
      });
      setPreparation(result);
      setSelectedProvider(result.selectedProvider || (result.providers[0]?.provider ?? ''));
      const providerCap = result.providers.find(
        p => p.provider === (result.selectedProvider || result.providers[0]?.provider),
      );
      setSelectedModel(result.selectedModel || providerCap?.defaultModel || '');
      const hasCandidates = result.worktreeCandidates.length > 0;
      setWorktreeMode(hasCandidates ? 'reuse' : 'create');
      setSelectedWorktreeId(result.worktreeSelection?.worktreeContextId ?? '');
      setNewBranch(result.worktreeSelection?.branch ?? '');
      setNewWorktreePath(result.worktreeSelection?.worktreePath ?? '');
      setNewBaseBranch(result.worktreeSelection?.baseBranch ?? '');
      setNewNotes(result.worktreeSelection?.notes ?? '');
      setCommandOverride('');
    } catch (err) {
      setPrepError(err instanceof Error ? err.message : 'Failed to load launch preparation.');
    } finally {
      setPrepLoading(false);
    }
  }, [open, projectId, featureId, phaseNumber, batchId, initialWorktreeContextId]);

  useEffect(() => {
    if (open) {
      void fetchPreparation();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projectId, featureId, phaseNumber, batchId]);

  // ── Focus management ───────────────────────────────────────────────────────
  useEffect(() => {
    if (open && !prepLoading && preparation) {
      const el = providerSelectRef.current ?? closeBtnRef.current;
      el?.focus();
    } else if (open && !prepLoading) {
      closeBtnRef.current?.focus();
    }
  }, [open, prepLoading, preparation]);

  // ── ESC to close ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  // ── Build worktree selection ───────────────────────────────────────────────
  const buildWorktreeSelection = () => {
    if (worktreeMode === 'reuse') {
      return {
        worktreeContextId: selectedWorktreeId,
        createIfMissing: false,
        branch: '',
        worktreePath: '',
        baseBranch: '',
        notes: '',
      };
    }
    return {
      worktreeContextId: '',
      createIfMissing: true,
      branch: newBranch,
      worktreePath: newWorktreePath,
      baseBranch: newBaseBranch,
      notes: newNotes,
    };
  };

  // ── Launch handler ─────────────────────────────────────────────────────────
  const handleLaunch = async (approvalDecision?: 'approved') => {
    if (!preparation) return;
    setLaunching(true);
    setLaunchError(null);
    try {
      const result = await startLaunch({
        projectId,
        featureId,
        phaseNumber,
        batchId,
        provider: selectedProvider,
        model: selectedModel || undefined,
        worktree: buildWorktreeSelection(),
        commandOverride: commandOverride || undefined,
        envProfile: 'default',
        approvalDecision: approvalDecision ?? '',
        actor: 'user',
      });
      onLaunched?.(result);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to start launch.';
      setLaunchError(msg);
      if (msg.includes('(409)')) {
        setShowForceButton(true);
      }
    } finally {
      setLaunching(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label="Launch batch"
    >
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl border border-panel-border bg-surface-overlay/90 shadow-2xl">
        {/* ── Header ──────────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-panel-border/60">
          <div className="flex-1 min-w-0">
            {preparation ? (
              <>
                <p className="text-sm font-semibold text-panel-foreground truncate">
                  {preparation.batch.featureName}
                </p>
                <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
                  {preparation.batch.phaseTitle} &middot;{' '}
                  <span className="font-mono">{batchId}</span>
                </p>
              </>
            ) : (
              <>
                <p className="text-sm font-semibold text-panel-foreground truncate">Launch Batch</p>
                <p className="text-[11px] font-mono text-muted-foreground mt-0.5 truncate">{batchId}</p>
              </>
            )}
          </div>
          <button
            ref={closeBtnRef}
            onClick={onClose}
            className="shrink-0 p-1 rounded border border-panel-border/50 text-muted-foreground hover:text-panel-foreground hover:border-panel-border transition-colors"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        </div>

        {/* ── Loading skeleton ─────────────────────────────────────────────── */}
        {prepLoading && (
          <div className="px-5 py-6 space-y-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 size={13} className="animate-spin" />
              <span>Loading launch preparation…</span>
            </div>
            {[70, 50, 85, 60].map(w => (
              <div
                key={w}
                className="h-3 rounded bg-surface-muted animate-pulse"
                style={{ width: `${w}%` }}
              />
            ))}
          </div>
        )}

        {/* ── Error state ──────────────────────────────────────────────────── */}
        {!prepLoading && prepError && (
          <div className="px-5 py-6 space-y-3">
            <div className="flex items-start gap-2">
              <AlertCircle size={14} className="shrink-0 mt-0.5 text-rose-400" />
              <p className="text-xs text-rose-400">{prepError}</p>
            </div>
            <button
              onClick={() => { void fetchPreparation(); }}
              className="text-xs text-indigo-400 hover:text-indigo-200"
            >
              Retry
            </button>
          </div>
        )}

        {/* ── Main content via pure inner renderer ──────────────────────────── */}
        {!prepLoading && preparation && (
          <PlanningLaunchSheetContent
            preparation={preparation}
            selectedProvider={selectedProvider}
            selectedModel={selectedModel}
            worktreeMode={worktreeMode}
            selectedWorktreeId={selectedWorktreeId}
            newBranch={newBranch}
            newWorktreePath={newWorktreePath}
            newBaseBranch={newBaseBranch}
            newNotes={newNotes}
            commandOverride={commandOverride}
            approvalAcknowledged={approvalAcknowledged}
            launching={launching}
            launchError={launchError}
            showForceButton={showForceButton}
            onProviderChange={(v) => {
              setSelectedProvider(v);
              const cap = preparation.providers.find(p => p.provider === v);
              setSelectedModel(cap?.defaultModel ?? '');
              setLaunchError(null);
              setShowForceButton(false);
            }}
            onModelChange={setSelectedModel}
            onWorktreeModeChange={setWorktreeMode}
            onWorktreeIdChange={setSelectedWorktreeId}
            onNewBranchChange={setNewBranch}
            onNewWorktreePathChange={setNewWorktreePath}
            onNewBaseBranchChange={setNewBaseBranch}
            onNewNotesChange={setNewNotes}
            onCommandOverrideChange={setCommandOverride}
            onApprovalAcknowledgeChange={setApprovalAcknowledged}
            onLaunch={() => { void handleLaunch(); }}
            onForceLaunch={() => { void handleLaunch('approved'); }}
          />
        )}
      </div>
    </div>
  );
}
