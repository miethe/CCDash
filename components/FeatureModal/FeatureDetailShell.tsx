/**
 * FeatureDetailShell — reusable tab-frame shell for the CCDash feature detail modal.
 *
 * Owns:
 *   - Dialog chrome (backdrop, scroll container, aria attributes)
 *   - Header (feature ID badge, status badge slot, feature name, progress row slot,
 *             Begin Work CTA slot, Expand action, Close button)
 *   - Tab bar (ordered tab buttons, active-tab highlight, keyboard navigation)
 *   - Per-tab state rendering (TabStateView: idle / loading / error / stale / success)
 *   - Retry affordance (error banner with retry delegated to TabStateView)
 *   - Stale marker (muted refresh indicator delegated to TabStateView)
 *   - Backdrop click-to-close, Escape key handling
 *
 * Does NOT own:
 *   - Any product-specific tab content — supplied via `renderTabContent` render prop
 *   - Data fetching — caller owns load() triggers (tab-activation effect)
 *   - URL synchronization — caller owns URL state; shell calls onTabChange
 *
 * Promotion decision:
 *   Shell remains CCDash-local. See types.ts for full rationale.
 *   No concrete second consumer was found in @miethe/ui BaseArtifactModal,
 *   Tabs, TabNavigation, or VerticalTabNavigation when audited for P4-001.
 */

import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { ExternalLink, X } from 'lucide-react';

import { TabStateView } from './TabStateView';
import type { ModalTabId } from '../../services/useFeatureModalData';
import type {
  FeatureDetailShellProps,
  ShellTabConfig,
} from './types';

// ── Sub-components ────────────────────────────────────────────────────────────

interface TabButtonProps {
  tab: ShellTabConfig;
  isActive: boolean;
  panelId: string;
  onClick: () => void;
}

const TabButton: React.FC<TabButtonProps> = ({ tab, isActive, panelId, onClick }) => (
  <button
    key={tab.id}
    type="button"
    role="tab"
    id={`tab-${tab.id}-${panelId}`}
    aria-selected={isActive}
    aria-controls={`tabpanel-${tab.id}-${panelId}`}
    onClick={onClick}
    className={[
      'inline-flex min-h-9 shrink-0 items-center gap-2 rounded-md px-3 py-2 text-xs font-semibold transition-colors',
      'focus:outline-none focus-visible:ring-2 focus-visible:ring-info/60',
      isActive
        ? 'bg-panel text-panel-foreground shadow-sm'
        : 'text-muted-foreground hover:bg-hover/70 hover:text-foreground',
    ].join(' ')}
  >
    {tab.icon ? <tab.icon size={15} aria-hidden="true" /> : null}
    {tab.label}
  </button>
);

interface TabPanelProps {
  tabId: ModalTabId;
  panelId: string;
  isActive: boolean;
  children: React.ReactNode;
}

const TabPanel: React.FC<TabPanelProps> = ({ tabId, panelId, isActive, children }) => (
  <div
    role="tabpanel"
    id={`tabpanel-${tabId}-${panelId}`}
    aria-labelledby={`tab-${tabId}-${panelId}`}
    hidden={!isActive}
    tabIndex={0}
    className="focus:outline-none"
  >
    {isActive ? children : null}
  </div>
);

// ── Main export ───────────────────────────────────────────────────────────────

export const FeatureDetailShell: React.FC<FeatureDetailShellProps> = ({
  featureId,
  featureName,
  statusBadge,
  headerBadges,
  progressRow,
  tabs,
  initialTab = 'overview',
  onTabChange,
  sectionStates,
  renderTabContent,
  beginWorkAction,
  extraHeaderActions,
  onExpand,
  onClose,
}) => {
  // Unique suffix for aria id attributes — stable per instance.
  const instanceId = useId();
  // Sanitize featureId for use as an HTML id fragment.
  const sanitizedFeatureId = featureId.replace(/[^a-zA-Z0-9_-]/g, '-');
  const modalTitleId = `feature-modal-title-${sanitizedFeatureId}`;

  // ── Active tab state ────────────────────────────────────────────────────────

  const [activeTab, setActiveTab] = useState<ModalTabId>(initialTab);

  // Sync internal state when the caller changes initialTab (e.g. URL navigation).
  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  const handleTabChange = useCallback(
    (tab: ModalTabId) => {
      setActiveTab(tab);
      onTabChange?.(tab);
    },
    [onTabChange],
  );

  // ── Escape key close ────────────────────────────────────────────────────────

  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // ── Derived ─────────────────────────────────────────────────────────────────

  const enabledTabs = tabs.filter((t) => t.enabled !== false);

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-surface-overlay/90 p-3 backdrop-blur-sm animate-in fade-in duration-200 sm:p-4"
      onClick={onClose}
      aria-hidden="true"
    >
      {/* Dialog */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={modalTitleId}
        className="flex h-[88vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-panel-border bg-panel text-panel-foreground shadow-[var(--viewer-shell-shadow)]"
        onClick={(e) => e.stopPropagation()}
      >

        {/* Header */}
        <div className="border-b border-panel-border bg-surface-overlay/95 px-4 py-4 sm:px-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">

            {/* Left: identity + name + progress */}
            <div className="min-w-0 flex-1">
              {/* Feature ID badge + status badge + extra badges */}
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span
                  className="inline-flex max-w-full truncate rounded-md border border-panel-border bg-surface-muted/70 px-2 py-1 font-mono text-[11px] text-muted-foreground"
                >
                  {featureId}
                </span>
                {statusBadge}
                {headerBadges}
              </div>

              {/* Feature name */}
              <h2
                id={modalTitleId}
                className="text-balance text-2xl font-semibold leading-tight text-panel-foreground"
              >
                {featureName}
              </h2>

              {/* Progress row slot */}
              {progressRow ? (
                <div className="mt-3">{progressRow}</div>
              ) : null}
            </div>

            {/* Right: action buttons */}
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {/* Begin Work CTA — shared-shell chrome per Decision 3 */}
              {beginWorkAction}

              {/* Extra caller-provided actions */}
              {extraHeaderActions}

              {/* Expand to full planning detail */}
              {onExpand ? (
                <button
                  type="button"
                  onClick={onExpand}
                  title="Open full planning detail"
                  className="inline-flex items-center gap-1.5 rounded-md border border-panel-border bg-surface-muted/70 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-hover/70 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-info/60"
                >
                  <ExternalLink size={13} aria-hidden="true" />
                  Expand
                </button>
              ) : null}

              {/* Close */}
              <button
                type="button"
                onClick={onClose}
                aria-label="Close feature modal"
                className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-hover/70 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-info/60"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>

        {/* Tab bar */}
        <div
          className="border-b border-panel-border bg-panel px-3 py-2 sm:px-6"
          role="tablist"
          aria-label="Feature detail sections"
        >
          <div className="flex gap-1 overflow-x-auto rounded-lg border border-panel-border bg-surface-muted/70 p-1">
            {enabledTabs.map((tab) => (
              <TabButton
                key={tab.id}
                tab={tab}
                isActive={activeTab === tab.id}
                panelId={instanceId}
                onClick={() => handleTabChange(tab.id)}
              />
            ))}
          </div>
        </div>

        {/* Tab content panels */}
        <div className="flex-1 overflow-y-auto bg-surface-muted/45 p-4 sm:p-6">
          {enabledTabs.map((tab) => {
            const section = sectionStates[tab.id];
            return (
              <TabPanel
                key={tab.id}
                tabId={tab.id}
                panelId={instanceId}
                isActive={activeTab === tab.id}
              >
                {/*
                  TabStateView wraps content with loading / error / stale / empty
                  state rendering. The shell passes the section status and retry
                  callback; content is provided by the caller's render prop.

                  isEmpty is intentionally not set here — each tab's domain owner
                  knows when their content is empty and can wrap in TabStateView
                  themselves, or pass the isEmpty prop via the section data.
                  The shell-level TabStateView handles the structural status states.
                */}
                <TabStateView
                  status={section.status}
                  error={section.error?.message ?? null}
                  onRetry={section.retry}
                >
                  {renderTabContent(tab.id)}
                </TabStateView>
              </TabPanel>
            );
          })}
        </div>

      </div>
    </div>
  );
};

export default FeatureDetailShell;
