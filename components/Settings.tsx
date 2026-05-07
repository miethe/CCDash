import React, { useState, useEffect } from 'react';
import { Bell, Trash2, Plus, AlertCircle, Save, Settings as SettingsIcon, FolderOpen, ChevronDown, Check, RefreshCw, Monitor, Copy, Download, Palette, Bot, GitBranch, Info } from 'lucide-react';
import { useData } from '../contexts/DataContext';
import { useModelColors } from '../contexts/ModelColorsContext';
import {
  AlertConfig,
  GitHubCredentialValidationResponse,
  GitHubIntegrationSettingsUpdateRequest,
  GitHubPathValidationResponse,
  GitHubProbeResult,
  GitHubWriteCapabilityResponse,
  PricingCatalogEntry,
  PricingCatalogUpsertRequest,
  Project,
  ProjectPathReference,
  ProjectResolvedPathsDTO,
  ProjectTestPlatformConfig,
  SnapshotHealth,
  SkillMeatConfigValidationResponse,
  SkillMeatProbeResult,
  TelemetryExportStatus,
  TestSourceStatus,
} from '../types';
import { analyticsService } from '../services/analytics';
import { DEFAULT_SKILLMEAT_FEATURE_FLAGS, defaultSkillMeatConfig, normalizeSkillMeatConfig } from '../services/agenticIntelligence';
import { createApiClient } from '../services/apiClient';
import {
  checkGitHubWriteCapability,
  getGitHubSettings,
  getProjectResolvedPaths,
  refreshGitHubWorkspace,
  updateGitHubSettings,
  validateGitHubCredential,
  validateGitHubPath,
} from '../services/githubIntegrations';
import { pricingService } from '../services/pricing';
import {
  applyProjectPathConfigToLegacyFields,
  deriveProjectPathPreview,
  getProjectPathInputValue,
  normalizeProjectPathConfig,
  pathReferenceUsesGitHub,
  PROJECT_PATH_FIELDS,
  ProjectPathConfigKey,
  setProjectPathSourceKind,
  updateProjectPathReference,
} from '../services/projectPaths';
import { refreshSkillMeatCache, validateSkillMeatConfig } from '../services/skillmeat';
import { getTestSourcesStatus, syncTestSources } from '../services/testVisualizer';
import { ensureProjectTestConfig } from '../services/testConfigDefaults';
import { generateProjectTestSetupScript } from '../services/testSetupScript';
import { useTheme } from '../contexts/ThemeContext';
import { THEME_PREFERENCES, type ThemePreference } from '../lib/themeMode';
import { cn } from '../lib/utils';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Select } from './ui/select';
import { AlertSurface, ControlRow, Surface } from './ui/surface';

type SettingsTab = 'general' | 'projects' | 'integrations' | 'ai-platforms' | 'alerts';
type IntegrationsSubtab = 'skillmeat' | 'github';

const SKILLMEAT_SETUP_COMMANDS: string[] = [
  'pytest -v --junitxml test-results/pytest-junit.xml --cov=skillmeat --cov-report=xml --cov-report=json',
  'cd skillmeat/web && pnpm test --json --outputFile test-results/jest-results.json && pnpm test:coverage',
  'cd skillmeat/web && pnpm test:e2e',
  'python tests/performance/benchmark_api.py --output benchmark_api_results.json',
  'python tests/performance/benchmark_operations.py --output benchmark_ops_results.json',
  'cd skillmeat/web && pnpm test:lighthouse --url http://localhost:3000',
  'locust -f tests/performance/locustfile.py --headless --users 50 --spawn-rate 5 --run-time 3m --host http://localhost:8000 --html locust_report.html --csv locust_results',
  'python scripts/parse_test_failures.py --input-dir test-results --output test-failures.json',
];

const DEFAULT_SKILLMEAT_CONFIG: Project['skillMeat'] = defaultSkillMeatConfig();

const PROBE_STATE_BADGE_TONE = {
  idle: 'muted',
  success: 'success',
  warning: 'warning',
  error: 'danger',
} as const;

const SECTION_ICON_TONE_STYLES = {
  primary: 'border-info-border bg-info/10 text-info-foreground',
  accent: 'border-info-border bg-info/10 text-info-foreground',
  neutral: 'border-panel-border bg-surface-muted text-panel-foreground',
} as const;

const SectionIcon: React.FC<{
  icon: React.ElementType;
  tone?: keyof typeof SECTION_ICON_TONE_STYLES;
}> = ({ icon: Icon, tone = 'primary' }) => (
  <div className={cn('rounded-lg border p-2', SECTION_ICON_TONE_STYLES[tone])}>
    <Icon size={20} />
  </div>
);

const SectionHeading: React.FC<{
  icon: React.ElementType;
  title: string;
  description: string;
  tone?: keyof typeof SECTION_ICON_TONE_STYLES;
}> = ({ icon, title, description, tone = 'primary' }) => (
  <div className="flex items-center gap-3">
    <SectionIcon icon={icon} tone={tone} />
    <div>
      <h3 className="font-semibold text-panel-foreground">{title}</h3>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  </div>
);

const ConnectionStatusBadge: React.FC<{
  label: string;
  state: keyof typeof PROBE_STATE_BADGE_TONE;
}> = ({ label, state }) => (
  <Badge tone={PROBE_STATE_BADGE_TONE[state]} size="md" className="inline-flex max-w-full leading-none">
    <span className="truncate">{label}</span>
  </Badge>
);

const SkillMeatStatusBadge: React.FC<{
  result?: SkillMeatProbeResult | null;
  fallback: string;
}> = ({ result, fallback }) => {
  const label = result?.message || fallback;
  const state = result?.state || 'idle';
  return <ConnectionStatusBadge label={label} state={state} />;
};

const GitHubStatusBadge: React.FC<{
  result?: GitHubProbeResult | null;
  fallback: string;
}> = ({ result, fallback }) => {
  const label = result?.message || fallback;
  const state = result?.state || 'idle';
  return <ConnectionStatusBadge label={label} state={state} />;
};

const SubtabButton: React.FC<{
  active: boolean;
  label: string;
  onClick: () => void;
}> = ({ active, label, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={cn(
      'rounded-lg border px-3 py-2 text-xs font-semibold transition-colors',
      active
        ? 'border-focus/40 bg-info/10 text-info-foreground'
        : 'border-panel-border bg-surface-overlay/80 text-muted-foreground hover:border-hover hover:bg-hover/60 hover:text-panel-foreground',
    )}
  >
    {label}
  </button>
);

const ProjectPicker: React.FC<{
  projects: Project[];
  selectedProjectId: string;
  dropdownOpen: boolean;
  onToggleDropdown: () => void;
  onSelect: (projectId: string) => void;
}> = ({ projects, selectedProjectId, dropdownOpen, onToggleDropdown, onSelect }) => {
  const selectedProject = projects.find(project => project.id === selectedProjectId);
  return (
    <div className="relative">
      <label className="mb-2 block text-sm font-medium text-muted-foreground">Select Project</label>
      <button
        type="button"
        onClick={onToggleDropdown}
        className="flex w-full items-center justify-between rounded-lg border border-panel-border bg-surface-overlay/80 px-4 py-3 text-left transition-colors hover:border-hover focus:outline-none focus:border-focus"
      >
        <div className="flex flex-col min-w-0">
          <span className="truncate text-sm font-medium text-panel-foreground">
            {selectedProject?.name || 'Select a project...'}
          </span>
          {selectedProject && (
            <span className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
              {selectedProject.path}
            </span>
          )}
        </div>
        <ChevronDown size={16} className={`text-muted-foreground transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
      </button>

      {dropdownOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={onToggleDropdown} />
          <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-72 overflow-y-auto overflow-hidden rounded-lg border border-panel-border bg-surface-elevated shadow-xl">
            {projects.map(project => (
              <button
                key={project.id}
                type="button"
                onClick={() => onSelect(project.id)}
                className="flex w-full items-center justify-between border-b border-panel-border px-4 py-3 text-left transition-colors last:border-0 hover:bg-hover/60"
              >
                <div className="flex flex-col min-w-0">
                  <span className="truncate text-sm font-medium text-panel-foreground">{project.name}</span>
                  <span className="truncate font-mono text-xs text-muted-foreground">{project.path}</span>
                </div>
                {selectedProjectId === project.id && (
                  <Check size={14} className="ml-2 shrink-0 text-info-foreground" />
                )}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

const PathEditorCard: React.FC<{
  fieldKey: ProjectPathConfigKey;
  reference: ProjectPathReference;
  previewPath: string;
  validation?: GitHubPathValidationResponse | null;
  validationBusy: boolean;
  onSourceKindChange: (fieldKey: ProjectPathConfigKey, sourceKind: ProjectPathReference['sourceKind']) => void;
  onInputChange: (fieldKey: ProjectPathConfigKey, value: string) => void;
  onRepoFieldChange: (fieldKey: ProjectPathConfigKey, field: 'repoUrl' | 'branch' | 'repoSubpath', value: string) => void;
  onRepoWriteToggle: (fieldKey: ProjectPathConfigKey, enabled: boolean) => void;
  onValidate: (fieldKey: ProjectPathConfigKey) => void;
}> = ({
  fieldKey,
  reference,
  previewPath,
  validation,
  validationBusy,
  onSourceKindChange,
  onInputChange,
  onRepoFieldChange,
  onRepoWriteToggle,
  onValidate,
}) => {
  const definition = PROJECT_PATH_FIELDS.find(field => field.key === fieldKey);
  if (!definition) return null;

  const allowProjectRoot = fieldKey !== 'root';
  const inputValue = getProjectPathInputValue(reference);
  const canValidateGitHub = pathReferenceUsesGitHub(reference) && Boolean(reference.repoRef?.repoUrl?.trim());

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h5 className="text-sm font-semibold text-slate-100">{definition.label}</h5>
          <p className="text-xs text-slate-500 mt-1">{definition.description}</p>
        </div>
        {pathReferenceUsesGitHub(reference) ? (
          <GitHubStatusBadge result={validation?.status} fallback="Not validated" />
        ) : (
          <span className="rounded-full border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-400">
            Local path
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[180px,minmax(0,1fr)] gap-4">
        <label className="block">
          <span className="block text-xs uppercase tracking-wide text-slate-500 mb-2">Source</span>
          <select
            value={reference.sourceKind}
            onChange={event => onSourceKindChange(fieldKey, event.target.value as ProjectPathReference['sourceKind'])}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            {allowProjectRoot && <option value="project_root">Project root</option>}
            <option value="filesystem">Filesystem</option>
            <option value="github_repo">GitHub repo</option>
          </select>
        </label>

        <div className="space-y-3">
          {reference.sourceKind !== 'github_repo' ? (
            <label className="block">
              <span className="block text-xs uppercase tracking-wide text-slate-500 mb-2">
                {reference.sourceKind === 'project_root' ? 'Relative path' : 'Filesystem path'}
              </span>
              <input
                type="text"
                value={inputValue}
                onChange={event => onInputChange(fieldKey, event.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                placeholder={reference.sourceKind === 'project_root' ? definition.helperText : '/absolute/path'}
              />
              <p className="mt-1 text-xs text-slate-500">{definition.helperText}</p>
            </label>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="block md:col-span-2">
                <span className="mb-2 flex items-center justify-between gap-2 text-xs uppercase tracking-wide text-slate-500">
                  <span>Repository URL</span>
                  <button
                    type="button"
                    disabled={!canValidateGitHub || validationBusy}
                    onClick={() => onValidate(fieldKey)}
                    className="inline-flex items-center gap-1 rounded border border-cyan-500/35 bg-cyan-500/10 px-2 py-1 text-[11px] font-semibold text-cyan-200 disabled:opacity-50"
                  >
                    <RefreshCw size={11} className={validationBusy ? 'animate-spin' : ''} />
                    {validationBusy ? 'Checking' : 'Validate'}
                  </button>
                </span>
                <input
                  type="url"
                  value={inputValue}
                  onChange={event => onInputChange(fieldKey, event.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                  placeholder="https://github.com/org/repo or .../tree/branch/path"
                />
                <p className="mt-1 text-xs text-slate-500">Paste a repo or tree URL. CCDash will normalize branch and subpath during validation.</p>
              </label>
              <label className="block">
                <span className="block text-xs uppercase tracking-wide text-slate-500 mb-2">Branch override</span>
                <input
                  type="text"
                  value={reference.repoRef?.branch || ''}
                  onChange={event => onRepoFieldChange(fieldKey, 'branch', event.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                  placeholder="main"
                />
              </label>
              <label className="block">
                <span className="block text-xs uppercase tracking-wide text-slate-500 mb-2">Repo subpath</span>
                <input
                  type="text"
                  value={reference.repoRef?.repoSubpath || ''}
                  onChange={event => onRepoFieldChange(fieldKey, 'repoSubpath', event.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                  placeholder="packages/app"
                />
              </label>
              <label className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 md:col-span-2">
                <div>
                  <span className="block text-sm text-slate-200">Enable writes for this repo path</span>
                  <span className="block text-xs text-slate-500">Phase 6 gates plan-document write-back behind both project and integration toggles.</span>
                </div>
                <input
                  type="checkbox"
                  checked={Boolean(reference.repoRef?.writeEnabled)}
                  onChange={event => onRepoWriteToggle(fieldKey, event.target.checked)}
                  className="h-4 w-4"
                />
              </label>
            </div>
          )}

          <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2">
            <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">Effective local path</p>
            <p className="text-xs text-slate-200 font-mono break-all">{previewPath || 'Not resolved yet'}</p>
          </div>
        </div>
      </div>
    </div>
  );
};

const buildEditableProject = (project: Project): Project => (
  applyProjectPathConfigToLegacyFields(
    {
      ...project,
      testConfig: ensureProjectTestConfig(project.testConfig),
      skillMeat: normalizeSkillMeatConfig(project),
    },
    normalizeProjectPathConfig(project),
  )
);

const buildWatcherEnvOverlay = (project: Project): string => [
  `CCDASH_WORKER_PROJECT_ID=${project.id}`,
  `CCDASH_WORKER_WATCH_PROJECT_ID=${project.id}`,
  'CCDASH_WORKER_WATCH_PROBE_PORT=9466',
  'CCDASH_WORKER_STARTUP_SYNC_ENABLED=false',
  'CCDASH_WORKER_WATCH_STARTUP_SYNC_ENABLED=true',
  'CCDASH_WORKER_WATCH_FILESYSTEM_INGESTION_ENABLED=true',
  'CCDASH_INFERRED_STATUS_WRITEBACK_ENABLED=false',
  'GIT_OPTIONAL_LOCKS=0',
  'CCDASH_STARTUP_SYNC_LIGHT_MODE=true',
].join('\n');

const DEFAULT_PRICING_PLATFORM = 'Claude Code';
const PRICING_PLATFORMS = ['Claude Code', 'Codex'] as const;

const parseOptionalNumber = (value: string): number | null => {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
};

const createPricingDraft = (platformType = DEFAULT_PRICING_PLATFORM): PricingCatalogEntry => ({
  projectId: '',
  platformType,
  modelId: '',
  displayLabel: '',
  entryKind: 'model',
  familyId: '',
  contextWindowSize: null,
  inputCostPerMillion: null,
  outputCostPerMillion: null,
  cacheCreationCostPerMillion: null,
  cacheReadCostPerMillion: null,
  speedMultiplierFast: null,
  sourceType: 'manual',
  sourceUpdatedAt: '',
  overrideLocked: false,
  syncStatus: 'manual',
  syncError: '',
  derivedFrom: '',
  isPersisted: false,
  isDetected: false,
  isRequiredDefault: false,
  canDelete: false,
  createdAt: '',
  updatedAt: '',
});

const formatPricingTimestamp = (value: string): string => {
  if (!value) return 'unknown';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
};

const THEME_OPTION_LABELS: Record<ThemePreference, string> = {
  dark: 'Dark',
  light: 'Light',
  system: 'System',
};

const pricingEntryTitle = (entry: PricingCatalogEntry): string => {
  if (entry.displayLabel?.trim()) return entry.displayLabel;
  if (entry.modelId?.trim()) return entry.modelId;
  return 'Platform Default';
};

const pricingEntryMeta = (entry: PricingCatalogEntry): string => {
  const parts = [
    entry.entryKind.replace(/_/g, ' '),
    entry.sourceType || 'manual',
    entry.syncStatus || 'manual',
    `updated ${formatPricingTimestamp(entry.sourceUpdatedAt)}`,
  ];
  if (entry.isDetected && entry.derivedFrom) {
    parts.push(`derived from ${entry.derivedFrom}`);
  }
  return parts.join(' · ');
};

const formatRelativeAge = (seconds?: number | null): string => {
  if (seconds == null) return 'Unknown';
  if (seconds < 60) return `${seconds} second${seconds === 1 ? '' : 's'} ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? '' : 's'} ago`;
};

const formatOptionalTimestamp = (value?: string | null): string => {
  if (!value) return 'Unavailable';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
};

const formatOptionalCount = (value?: number | null): string => (
  value == null ? 'Unavailable' : value.toLocaleString()
);

const hasSnapshotData = (health?: SnapshotHealth | null): boolean => (
  Boolean(health && health.snapshotAgeSeconds != null)
);

// ── Tab Button ─────────────────────────────────────────────────────

const TabButton: React.FC<{
  tab: SettingsTab;
  activeTab: SettingsTab;
  icon: React.ElementType;
  label: string;
  onClick: (tab: SettingsTab) => void;
}> = ({ tab, activeTab, icon: Icon, label, onClick }) => (
  <button
    onClick={() => onClick(tab)}
    className={cn(
      'flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-all duration-200',
      activeTab === tab
        ? 'border-focus/40 bg-info/10 text-info-foreground'
        : 'border-transparent text-muted-foreground hover:border-panel-border hover:bg-hover/60 hover:text-panel-foreground',
    )}
  >
    <Icon size={16} />
    {label}
  </button>
);

// ── General Tab ────────────────────────────────────────────────────

const GeneralTab: React.FC = () => {
  const { preference, resolvedTheme, setPreference } = useTheme();
  const {
    registry,
    modelFacetsLoading,
    familyColorOverrides,
    modelColorOverrides,
    getFamilyOverrideColor,
    getModelOverrideColor,
    getColorForModel,
    setFamilyColorOverride,
    clearFamilyColorOverride,
    setModelColorOverride,
    clearModelColorOverride,
  } = useModelColors();
  const [selectedFamily, setSelectedFamily] = useState('');
  const [familyColor, setFamilyColor] = useState('#6366f1');
  const [selectedModel, setSelectedModel] = useState('');
  const [modelColor, setModelColor] = useState('#6366f1');

  useEffect(() => {
    if (selectedFamily) return;
    const firstFamily = registry.families[0]?.label || '';
    setSelectedFamily(firstFamily);
  }, [registry.families, selectedFamily]);

  useEffect(() => {
    if (selectedModel) return;
    const firstModel = registry.models[0]?.raw || '';
    setSelectedModel(firstModel);
  }, [registry.models, selectedModel]);

  useEffect(() => {
    if (!selectedFamily) return;
    const override = getFamilyOverrideColor(selectedFamily);
    setFamilyColor(override || getColorForModel({ family: selectedFamily }));
  }, [selectedFamily, getFamilyOverrideColor, getColorForModel]);

  useEffect(() => {
    if (!selectedModel) return;
    const override = getModelOverrideColor(selectedModel);
    const modelFamily = registry.modelByKey[selectedModel.trim().toLowerCase()]?.family || '';
    setModelColor(override || getColorForModel({ model: selectedModel, family: modelFamily }));
  }, [selectedModel, getModelOverrideColor, getColorForModel, registry.modelByKey]);

  const familyOverrideRows = Object.entries(familyColorOverrides).sort((a, b) => a[0].localeCompare(b[0]));
  const modelOverrideRows = Object.entries(modelColorOverrides).sort((a, b) => a[0].localeCompare(b[0]));

  return (
    <div className="space-y-6">
      <Surface tone="panel" padding="lg" className="space-y-6">
        <SectionHeading
          icon={Monitor}
          title="General Preferences"
          description="Application-wide settings and appearance."
        />

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <div>
            <label className="mb-2 block text-sm font-medium text-muted-foreground">Theme</label>
            <Select
              tone="default"
              value={preference}
              onChange={(event) => setPreference(event.target.value as ThemePreference)}
              aria-label="Theme preference"
            >
              {THEME_PREFERENCES.map((themePreference) => (
                <option key={themePreference} value={themePreference}>
                  {THEME_OPTION_LABELS[themePreference]}
                  {themePreference === 'system' ? ' (Follow OS)' : ''}
                </option>
              ))}
            </Select>
            <p className="mt-2 text-xs text-muted-foreground">
              Persists across sessions. `system` follows the browser `prefers-color-scheme` setting.
            </p>
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-muted-foreground">Polling Interval</label>
            <Select tone="default" defaultValue="30 seconds (Default)">
              <option>30 seconds (Default)</option>
              <option>15 seconds</option>
              <option>60 seconds</option>
              <option>5 minutes</option>
            </Select>
          </div>
        </div>

        <AlertSurface intent="neutral" className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-semibold text-panel-foreground">Theme debug</span>
          <Badge tone="muted" size="sm">Preference: {THEME_OPTION_LABELS[preference]}</Badge>
          <Badge tone={resolvedTheme === 'dark' ? 'info' : 'success'} size="sm">
            Resolved: {THEME_OPTION_LABELS[resolvedTheme]}
          </Badge>
          <span className="text-muted-foreground">
            Root contract: <code>data-theme="{resolvedTheme}"</code> and <code>data-theme-preference="{preference}"</code>
          </span>
        </AlertSurface>
      </Surface>

      <Surface tone="panel" padding="lg" className="space-y-6">
        <SectionHeading
          icon={Palette}
          tone="accent"
          title="Model Color Mapping"
          description="Configure color coding by model family or exact model. Model-level overrides take precedence."
        />

        {modelFacetsLoading && (
          <AlertSurface intent="neutral">
            Loading model options from ingested session data...
          </AlertSurface>
        )}

        {!modelFacetsLoading && registry.models.length === 0 && (
          <AlertSurface intent="warning">
            No model facets are available yet. Run a session sync to populate model families and models.
          </AlertSurface>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Surface tone="muted" padding="md" className="space-y-4">
            <h4 className="text-sm font-semibold text-panel-foreground">Family Override</h4>
            <div>
              <label className="mb-2 block text-xs uppercase tracking-wide text-muted-foreground">Model Family</label>
              <Select
                value={selectedFamily}
                onChange={(event) => setSelectedFamily(event.target.value)}
                tone="default"
                disabled={registry.families.length === 0}
              >
                {registry.families.map(family => (
                  <option key={family.label} value={family.label}>
                    {family.label} ({family.count})
                  </option>
                ))}
              </Select>
            </div>
            <ControlRow className="justify-between">
              <label className="text-xs uppercase tracking-wide text-muted-foreground">Color</label>
              <input
                type="color"
                value={familyColor}
                onChange={(event) => setFamilyColor(event.target.value)}
                className="h-9 w-14 rounded border border-panel-border bg-surface-overlay"
              />
              <Button
                onClick={() => selectedFamily && setFamilyColorOverride(selectedFamily, familyColor)}
                disabled={!selectedFamily}
                variant="panel"
                size="sm"
                className="border-info-border bg-info/10 text-info-foreground hover:bg-info/20 disabled:opacity-40"
              >
                Save Family Color
              </Button>
              <Button
                onClick={() => selectedFamily && clearFamilyColorOverride(selectedFamily)}
                disabled={!selectedFamily || !getFamilyOverrideColor(selectedFamily)}
                variant="panel"
                size="sm"
                className="disabled:opacity-40"
              >
                Clear
              </Button>
            </ControlRow>
          </Surface>

          <Surface tone="muted" padding="md" className="space-y-4">
            <h4 className="text-sm font-semibold text-panel-foreground">Model Override</h4>
            <div>
              <label className="mb-2 block text-xs uppercase tracking-wide text-muted-foreground">Model</label>
              <Select
                value={selectedModel}
                onChange={(event) => setSelectedModel(event.target.value)}
                tone="default"
                disabled={registry.models.length === 0}
              >
                {registry.models.map(model => (
                  <option key={model.raw} value={model.raw}>
                    {model.label} ({model.count})
                  </option>
                ))}
              </Select>
            </div>
            <ControlRow className="justify-between">
              <label className="text-xs uppercase tracking-wide text-muted-foreground">Color</label>
              <input
                type="color"
                value={modelColor}
                onChange={(event) => setModelColor(event.target.value)}
                className="h-9 w-14 rounded border border-panel-border bg-surface-overlay"
              />
              <Button
                onClick={() => selectedModel && setModelColorOverride(selectedModel, modelColor)}
                disabled={!selectedModel}
                variant="panel"
                size="sm"
                className="border-info-border bg-info/10 text-info-foreground hover:bg-info/20 disabled:opacity-40"
              >
                Save Model Color
              </Button>
              <Button
                onClick={() => selectedModel && clearModelColorOverride(selectedModel)}
                disabled={!selectedModel || !getModelOverrideColor(selectedModel)}
                variant="panel"
                size="sm"
                className="disabled:opacity-40"
              >
                Clear
              </Button>
            </ControlRow>
          </Surface>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Surface tone="muted" padding="md">
            <h4 className="mb-3 text-xs uppercase tracking-wide text-muted-foreground">Family Overrides</h4>
            <div className="space-y-2 max-h-44 overflow-y-auto pr-1">
              {familyOverrideRows.length === 0 && <div className="text-sm text-muted-foreground">None configured.</div>}
              {familyOverrideRows.map(([key, color]) => {
                const label = registry.familyLabelByKey[key] || key;
                return (
                  <div key={key} className="flex items-center justify-between gap-2 text-sm">
                    <span className="text-panel-foreground">{label}</span>
                    <div className="flex items-center gap-2">
                      <span className="h-5 w-5 rounded border border-panel-border" style={{ backgroundColor: color }} />
                      <span className="font-mono text-xs text-muted-foreground">{color}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </Surface>

          <Surface tone="muted" padding="md">
            <h4 className="mb-3 text-xs uppercase tracking-wide text-muted-foreground">Model Overrides</h4>
            <div className="space-y-2 max-h-44 overflow-y-auto pr-1">
              {modelOverrideRows.length === 0 && <div className="text-sm text-muted-foreground">None configured.</div>}
              {modelOverrideRows.map(([key, color]) => {
                const label = registry.modelByKey[key]?.label || key;
                return (
                  <div key={key} className="flex items-center justify-between gap-2 text-sm">
                    <span className="truncate text-panel-foreground" title={label}>{label}</span>
                    <div className="flex items-center gap-2">
                      <span className="h-5 w-5 rounded border border-panel-border" style={{ backgroundColor: color }} />
                      <span className="font-mono text-xs text-muted-foreground">{color}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </Surface>
        </div>

        <AlertSurface intent="neutral" className="text-xs">
          Colors are sourced from session model facets and applied across Analytics, Session cards, and other model badges.
        </AlertSurface>
      </Surface>
    </div>
  );
};

const PricingEntryCard: React.FC<{
  entry: PricingCatalogEntry;
  index: number;
  saving: boolean;
  onChange: (index: number, updater: (entry: PricingCatalogEntry) => PricingCatalogEntry) => void;
  onSave: (entry: PricingCatalogEntry, index: number) => Promise<void>;
  onReset: (entry: PricingCatalogEntry, index: number) => Promise<void>;
  onDelete: (entry: PricingCatalogEntry, index: number) => Promise<void>;
}> = ({ entry, index, saving, onChange, onSave, onReset, onDelete }) => {
  const allowModelIdEdit = !entry.isPersisted && !entry.isDetected && !entry.isRequiredDefault;
  const canRemoveDraft = !entry.isPersisted && !entry.isDetected && !entry.isRequiredDefault;
  const showDelete = entry.canDelete || canRemoveDraft;
  const showReset = entry.isPersisted;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-slate-200">{pricingEntryTitle(entry)}</div>
          <div className="text-xs text-slate-500">{pricingEntryMeta(entry)}</div>
        </div>
        <label className="inline-flex items-center gap-2 text-xs text-slate-300">
          <input
            type="checkbox"
            checked={Boolean(entry.overrideLocked)}
            onChange={e => onChange(index, current => ({ ...current, overrideLocked: e.target.checked }))}
            className="h-4 w-4"
          />
          Lock Override
        </label>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-4 gap-3">
        <label className="block">
          <span className="mb-1 block text-xs text-slate-400">Model ID / Scope</span>
          <input
            type="text"
            value={entry.modelId || ''}
            readOnly={!allowModelIdEdit}
            onChange={e => onChange(index, current => ({ ...current, modelId: e.target.value, displayLabel: '' }))}
            className={`w-full rounded-lg border px-3 py-2 text-sm font-mono ${allowModelIdEdit ? 'bg-slate-950 border-slate-700 text-slate-200 focus:outline-none focus:border-indigo-500' : 'bg-slate-900/70 border-slate-800 text-slate-400 cursor-not-allowed'}`}
            placeholder={entry.entryKind === 'platform_default' ? '(platform default)' : 'claude-sonnet-4-6'}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-slate-400">Context Window</span>
          <input
            type="number"
            value={entry.contextWindowSize ?? ''}
            onChange={e => onChange(index, current => ({ ...current, contextWindowSize: parseOptionalNumber(e.target.value) }))}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-slate-400">Input / 1M</span>
          <input
            type="number"
            step="0.0001"
            value={entry.inputCostPerMillion ?? ''}
            onChange={e => onChange(index, current => ({ ...current, inputCostPerMillion: parseOptionalNumber(e.target.value) }))}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-slate-400">Output / 1M</span>
          <input
            type="number"
            step="0.0001"
            value={entry.outputCostPerMillion ?? ''}
            onChange={e => onChange(index, current => ({ ...current, outputCostPerMillion: parseOptionalNumber(e.target.value) }))}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-slate-400">Cache Create / 1M</span>
          <input
            type="number"
            step="0.0001"
            value={entry.cacheCreationCostPerMillion ?? ''}
            onChange={e => onChange(index, current => ({ ...current, cacheCreationCostPerMillion: parseOptionalNumber(e.target.value) }))}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-slate-400">Cache Read / 1M</span>
          <input
            type="number"
            step="0.0001"
            value={entry.cacheReadCostPerMillion ?? ''}
            onChange={e => onChange(index, current => ({ ...current, cacheReadCostPerMillion: parseOptionalNumber(e.target.value) }))}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-slate-400">Fast Multiplier</span>
          <input
            type="number"
            step="0.01"
            value={entry.speedMultiplierFast ?? ''}
            onChange={e => onChange(index, current => ({ ...current, speedMultiplierFast: parseOptionalNumber(e.target.value) }))}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
          />
        </label>
      </div>

      {entry.syncError && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          {entry.syncError}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2">
        {showDelete && (
          <button
            type="button"
            onClick={() => void onDelete(entry, index)}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs font-medium text-rose-200 disabled:opacity-50"
          >
            <Trash2 size={12} />
            {entry.canDelete ? 'Delete Override' : 'Remove Draft'}
          </button>
        )}
        {showReset && (
          <button
            type="button"
            onClick={() => void onReset(entry, index)}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-300 disabled:opacity-50"
          >
            Reset
          </button>
        )}
        <button
          type="button"
          onClick={() => void onSave(entry, index)}
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-3 py-2 text-xs font-medium text-indigo-200 disabled:opacity-50"
        >
          <Save size={12} />
          {saving ? 'Saving...' : entry.isPersisted ? 'Save Override' : 'Save Pricing'}
        </button>
      </div>
    </div>
  );
};

const PricingSection: React.FC<{
  title: string;
  description: string;
  entries: Array<{ entry: PricingCatalogEntry; rowIndex: number }>;
  pricingSavingKey: string;
  onChange: (index: number, updater: (entry: PricingCatalogEntry) => PricingCatalogEntry) => void;
  onSave: (entry: PricingCatalogEntry, index: number) => Promise<void>;
  onReset: (entry: PricingCatalogEntry, index: number) => Promise<void>;
  onDelete: (entry: PricingCatalogEntry, index: number) => Promise<void>;
  emptyText: string;
}> = ({ title, description, entries, pricingSavingKey, onChange, onSave, onReset, onDelete, emptyText }) => (
  <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
    <div>
      <h4 className="text-sm font-semibold text-slate-200">{title}</h4>
      <p className="text-xs text-slate-500 mt-1">{description}</p>
    </div>

    {entries.length === 0 ? (
      <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm text-slate-500">
        {emptyText}
      </div>
    ) : (
      <div className="space-y-3">
        {entries.map(({ entry, rowIndex }) => {
          const rowKey = `${entry.modelId || 'platform-default'}:${rowIndex}`;
          return (
            <PricingEntryCard
              key={`${title}:${rowKey}`}
              entry={entry}
              index={rowIndex}
              saving={pricingSavingKey === rowKey}
              onChange={onChange}
              onSave={onSave}
              onReset={onReset}
              onDelete={onDelete}
            />
          );
        })}
      </div>
    )}
  </div>
);

const AIPlatformsTab: React.FC = () => {
  const { projects } = useData();
  const [pricingPlatform, setPricingPlatform] = useState(DEFAULT_PRICING_PLATFORM);
  const [pricingEntries, setPricingEntries] = useState<PricingCatalogEntry[]>([]);
  const [pricingLoading, setPricingLoading] = useState(false);
  const [pricingError, setPricingError] = useState<string | null>(null);
  const [pricingMessage, setPricingMessage] = useState<string | null>(null);
  const [pricingSavingKey, setPricingSavingKey] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    const loadPricing = async () => {
      setPricingLoading(true);
      setPricingError(null);
      try {
        const entries = await pricingService.getPricingCatalog(pricingPlatform);
        if (!cancelled) setPricingEntries(entries);
      } catch (e: any) {
        if (!cancelled) setPricingError(e?.message || 'Failed to load pricing catalog');
      } finally {
        if (!cancelled) setPricingLoading(false);
      }
    };
    void loadPricing();
    return () => {
      cancelled = true;
    };
  }, [pricingPlatform]);

  const updatePricingEntry = (index: number, updater: (entry: PricingCatalogEntry) => PricingCatalogEntry) => {
    setPricingEntries(prev => prev.map((entry, idx) => (idx === index ? updater(entry) : entry)));
    setPricingMessage(null);
    setPricingError(null);
  };

  const upsertPayloadFromEntry = (entry: PricingCatalogEntry): PricingCatalogUpsertRequest => ({
    platformType: entry.platformType || pricingPlatform,
    modelId: entry.modelId || '',
    contextWindowSize: entry.contextWindowSize ?? null,
    inputCostPerMillion: entry.inputCostPerMillion ?? null,
    outputCostPerMillion: entry.outputCostPerMillion ?? null,
    cacheCreationCostPerMillion: entry.cacheCreationCostPerMillion ?? null,
    cacheReadCostPerMillion: entry.cacheReadCostPerMillion ?? null,
    speedMultiplierFast: entry.speedMultiplierFast ?? null,
    sourceType: 'manual',
    sourceUpdatedAt: '',
    overrideLocked: entry.overrideLocked,
    syncStatus: 'manual',
    syncError: '',
  });

  const reloadPricingCatalog = async () => {
    const entries = await pricingService.getPricingCatalog(pricingPlatform);
    setPricingEntries(entries);
  };

  const handleSavePricingEntry = async (entry: PricingCatalogEntry, index: number) => {
    const rowKey = `${entry.modelId || 'platform-default'}:${index}`;
    setPricingSavingKey(rowKey);
    setPricingError(null);
    setPricingMessage(null);
    try {
      await pricingService.upsertPricingCatalogEntry(upsertPayloadFromEntry(entry));
      await reloadPricingCatalog();
      setPricingMessage(`Saved pricing override for ${entry.modelId || 'platform default'}.`);
    } catch (e: any) {
      setPricingError(e?.message || 'Failed to save pricing entry');
    } finally {
      setPricingSavingKey('');
    }
  };

  const handleResetPricingEntry = async (entry: PricingCatalogEntry, index: number) => {
    const rowKey = `${entry.modelId || 'platform-default'}:${index}`;
    setPricingSavingKey(rowKey);
    setPricingError(null);
    setPricingMessage(null);
    try {
      await pricingService.resetPricingCatalogEntry(entry.platformType || pricingPlatform, entry.modelId || '');
      await reloadPricingCatalog();
      setPricingMessage(`Reset pricing for ${entry.modelId || 'platform default'}.`);
    } catch (e: any) {
      setPricingError(e?.message || 'Failed to reset pricing entry');
    } finally {
      setPricingSavingKey('');
    }
  };

  const handleDeletePricingEntry = async (entry: PricingCatalogEntry, index: number) => {
    const rowKey = `${entry.modelId || 'platform-default'}:${index}`;
    setPricingSavingKey(rowKey);
    setPricingError(null);
    setPricingMessage(null);
    try {
      if (entry.canDelete) {
        await pricingService.deletePricingCatalogEntry(entry.platformType || pricingPlatform, entry.modelId || '');
        await reloadPricingCatalog();
        setPricingMessage(`Deleted pricing override for ${entry.modelId}.`);
      } else {
        setPricingEntries(prev => prev.filter((_, currentIndex) => currentIndex !== index));
      }
    } catch (e: any) {
      setPricingError(e?.message || 'Failed to delete pricing entry');
    } finally {
      setPricingSavingKey('');
    }
  };

  const handleSyncPricing = async () => {
    setPricingSavingKey('sync');
    setPricingError(null);
    setPricingMessage(null);
    try {
      const response = await pricingService.syncPricingCatalog(pricingPlatform);
      setPricingEntries(response.entries || []);
      setPricingMessage(`Synced ${response.updatedEntries} pricing rows.${response.warnings.length ? ` ${response.warnings.join(' ')}` : ''}`);
    } catch (e: any) {
      setPricingError(e?.message || 'Failed to sync pricing catalog');
    } finally {
      setPricingSavingKey('');
    }
  };

  const indexedEntries = pricingEntries.map((entry, rowIndex) => ({ entry, rowIndex }));
  const platformDefaults = indexedEntries.filter(({ entry }) => entry.entryKind === 'platform_default');
  const familyDefaults = indexedEntries.filter(({ entry }) => entry.entryKind === 'family_default');
  const exactEntries = indexedEntries.filter(({ entry }) => entry.entryKind === 'model');
  const detectedEntries = exactEntries.filter(({ entry }) => entry.isDetected && !entry.isPersisted);
  const exactOverrideEntries = exactEntries.filter(({ entry }) => !entry.isDetected);

  return (
    <div className="space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5">
        <div className="flex items-center gap-3">
          <div className="bg-cyan-500/10 p-2 rounded-lg text-cyan-300">
            <Bot size={20} />
          </div>
          <div>
            <h3 className="font-semibold text-slate-100">AI Platforms</h3>
            <p className="text-sm text-slate-400">
              Manage platform defaults, family pricing, detected exact models, and manual overrides across all configured projects.
            </p>
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-400">
          Detected rows are synthesized from synced sessions across {projects.length} configured project{projects.length === 1 ? '' : 's'}. Sync uses provider pricing when available and falls back to bundled defaults so catalog edits stay offline-safe.
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="mb-1 block text-xs text-slate-400">Platform</span>
            <select
              value={pricingPlatform}
              onChange={e => setPricingPlatform(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              {PRICING_PLATFORMS.map(platform => (
                <option key={platform} value={platform}>{platform}</option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={handleSyncPricing}
            disabled={pricingSavingKey === 'sync'}
            className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-xs font-medium text-cyan-200 disabled:opacity-50"
          >
            <RefreshCw size={12} className={pricingSavingKey === 'sync' ? 'animate-spin' : ''} />
            {pricingSavingKey === 'sync' ? 'Syncing...' : 'Sync Provider Prices'}
          </button>
          <button
            type="button"
            onClick={() => setPricingEntries(prev => [...prev, createPricingDraft(pricingPlatform)])}
            className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-200"
          >
            <Plus size={12} />
            Add Model Override
          </button>
        </div>

        {pricingMessage && (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
            {pricingMessage}
          </div>
        )}
        {pricingError && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
            {pricingError}
          </div>
        )}
      </div>

      {pricingLoading ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-400">
          Loading pricing catalog...
        </div>
      ) : (
        <div className="space-y-5">
          <PricingSection
            title="Platform Defaults"
            description="Fallback rows used when no exact model or family-specific pricing is available."
            entries={platformDefaults}
            pricingSavingKey={pricingSavingKey}
            onChange={updatePricingEntry}
            onSave={handleSavePricingEntry}
            onReset={handleResetPricingEntry}
            onDelete={handleDeletePricingEntry}
            emptyText="No platform defaults are available for this platform."
          />
          <PricingSection
            title="Model Families"
            description="Shared pricing for families like Sonnet, Opus, Haiku, and Codex."
            entries={familyDefaults}
            pricingSavingKey={pricingSavingKey}
            onChange={updatePricingEntry}
            onSave={handleSavePricingEntry}
            onReset={handleResetPricingEntry}
            onDelete={handleDeletePricingEntry}
            emptyText="No family defaults are available for this platform."
          />
          <PricingSection
            title="Detected Models"
            description="Auto-created exact models discovered in synced sessions. Save a row to pin an exact override."
            entries={detectedEntries}
            pricingSavingKey={pricingSavingKey}
            onChange={updatePricingEntry}
            onSave={handleSavePricingEntry}
            onReset={handleResetPricingEntry}
            onDelete={handleDeletePricingEntry}
            emptyText="No detected models yet. Run a session sync for projects that use this platform."
          />
          <PricingSection
            title="Exact Entries And Overrides"
            description="Persisted exact-version rows from provider sync and manual overrides. New drafts appear here until you save or remove them."
            entries={exactOverrideEntries}
            pricingSavingKey={pricingSavingKey}
            onChange={updatePricingEntry}
            onSave={handleSavePricingEntry}
            onReset={handleResetPricingEntry}
            onDelete={handleDeletePricingEntry}
            emptyText="No exact-version entries or overrides for this platform."
          />
        </div>
      )}
    </div>
  );
};

// ── Projects Tab ───────────────────────────────────────────────────

const ProjectsTab: React.FC = () => {
  const { projects, activeProject, updateProject } = useData();
  const [selectedProjectId, setSelectedProjectId] = useState<string>(activeProject?.id || '');
  const [editData, setEditData] = useState<Project | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [dirtyPaths, setDirtyPaths] = useState(false);
  const [resolvedPaths, setResolvedPaths] = useState<ProjectResolvedPathsDTO | null>(null);
  const [pathValidation, setPathValidation] = useState<Partial<Record<ProjectPathConfigKey, GitHubPathValidationResponse>>>({});
  const [pathValidationBusy, setPathValidationBusy] = useState<Partial<Record<ProjectPathConfigKey, boolean>>>({});
  const [sourceStatus, setSourceStatus] = useState<TestSourceStatus[]>([]);
  const [testingActionError, setTestingActionError] = useState<string | null>(null);
  const [testingActionInfo, setTestingActionInfo] = useState<string | null>(null);
  const [testingBusy, setTestingBusy] = useState(false);
  const [generatedScript, setGeneratedScript] = useState('');
  const [generatedScriptName, setGeneratedScriptName] = useState('');
  const [scriptCopied, setScriptCopied] = useState(false);
  const [watcherEnvCopied, setWatcherEnvCopied] = useState(false);
  const savingRef = React.useRef(false);

  useEffect(() => {
    if (!selectedProjectId && activeProject) {
      setSelectedProjectId(activeProject.id);
    }
  }, [activeProject, selectedProjectId]);

  useEffect(() => {
    if (savingRef.current) return;
    const project = projects.find(candidate => candidate.id === selectedProjectId);
    if (!project) return;

    setEditData(buildEditableProject(project));
    setSaved(false);
    setError(null);
    setDirtyPaths(false);
    setPathValidation({});
    setSourceStatus([]);
    setTestingActionError(null);
    setTestingActionInfo(null);
    setGeneratedScript('');
    setGeneratedScriptName('');
    setScriptCopied(false);
    setWatcherEnvCopied(false);

    void getProjectResolvedPaths(project.id)
      .then(setResolvedPaths)
      .catch(() => setResolvedPaths(null));
  }, [projects, selectedProjectId]);

  const selectedProject = projects.find(project => project.id === selectedProjectId);

  const updateProjectDraft = (updater: (project: Project) => Project) => {
    setEditData(current => {
      if (!current) return current;
      return updater(current);
    });
    setSaved(false);
  };

  const handleFieldChange = (field: keyof Project, value: string) => {
    updateProjectDraft(project => ({ ...project, [field]: value }));
  };

  const updatePathConfig = (updater: (project: Project) => Project) => {
    updateProjectDraft(project => {
      const next = updater(project);
      const original = selectedProject ? buildEditableProject(selectedProject) : null;
      if (original) {
        setDirtyPaths(JSON.stringify(original.pathConfig) !== JSON.stringify(next.pathConfig));
      } else {
        setDirtyPaths(true);
      }
      return next;
    });
  };

  const handlePathSourceKindChange = (fieldKey: ProjectPathConfigKey, sourceKind: ProjectPathReference['sourceKind']) => {
    updatePathConfig(project => applyProjectPathConfigToLegacyFields(
      project,
      setProjectPathSourceKind(project.pathConfig, fieldKey, sourceKind),
    ));
    setPathValidation(current => ({ ...current, [fieldKey]: undefined }));
  };

  const handlePathInputChange = (fieldKey: ProjectPathConfigKey, value: string) => {
    updatePathConfig(project => applyProjectPathConfigToLegacyFields(
      project,
      updateProjectPathReference(project.pathConfig, fieldKey, reference => {
        if (reference.sourceKind === 'project_root') {
          return { ...reference, relativePath: value, displayValue: value };
        }
        if (reference.sourceKind === 'filesystem') {
          return { ...reference, filesystemPath: value, displayValue: value };
        }
        return {
          ...reference,
          displayValue: value,
          repoRef: {
            provider: 'github',
            repoUrl: value,
            repoSlug: reference.repoRef?.repoSlug || '',
            branch: reference.repoRef?.branch || '',
            repoSubpath: reference.repoRef?.repoSubpath || '',
            writeEnabled: Boolean(reference.repoRef?.writeEnabled),
          },
        };
      }),
    ));
    if (fieldKey === 'root') {
      setPathValidation(current => ({ ...current, root: undefined, planDocs: undefined, progress: undefined }));
    } else {
      setPathValidation(current => ({ ...current, [fieldKey]: undefined }));
    }
  };

  const handleRepoFieldChange = (fieldKey: ProjectPathConfigKey, repoField: 'repoUrl' | 'branch' | 'repoSubpath', value: string) => {
    updatePathConfig(project => applyProjectPathConfigToLegacyFields(
      project,
      updateProjectPathReference(project.pathConfig, fieldKey, reference => ({
        ...reference,
        repoRef: {
          provider: 'github',
          repoUrl: reference.repoRef?.repoUrl || '',
          repoSlug: reference.repoRef?.repoSlug || '',
          branch: reference.repoRef?.branch || '',
          repoSubpath: reference.repoRef?.repoSubpath || '',
          writeEnabled: Boolean(reference.repoRef?.writeEnabled),
          [repoField]: value,
        },
      })),
    ));
    setPathValidation(current => ({ ...current, [fieldKey]: undefined }));
  };

  const handleRepoWriteToggle = (fieldKey: ProjectPathConfigKey, enabled: boolean) => {
    updatePathConfig(project => applyProjectPathConfigToLegacyFields(
      project,
      updateProjectPathReference(project.pathConfig, fieldKey, reference => ({
        ...reference,
        repoRef: {
          provider: 'github',
          repoUrl: reference.repoRef?.repoUrl || '',
          repoSlug: reference.repoRef?.repoSlug || '',
          branch: reference.repoRef?.branch || '',
          repoSubpath: reference.repoRef?.repoSubpath || '',
          writeEnabled: enabled,
        },
      })),
    ));
  };

  const updateTestConfig = (updater: (prev: Project['testConfig']) => Project['testConfig']) => {
    updateProjectDraft(project => ({ ...project, testConfig: updater(ensureProjectTestConfig(project.testConfig)) }));
  };

  const updateFlag = (key: keyof Project['testConfig']['flags'], value: boolean) => {
    updateTestConfig(prev => ({
      ...prev,
      flags: {
        ...prev.flags,
        [key]: value,
      },
    }));
  };

  const updatePlatform = (platformId: string, updater: (prev: ProjectTestPlatformConfig) => ProjectTestPlatformConfig) => {
    updateTestConfig(prev => ({
      ...prev,
      platforms: prev.platforms.map(platform => platform.id === platformId ? updater(platform) : platform),
    }));
  };

  const handleValidateGitHubPath = async (fieldKey: ProjectPathConfigKey) => {
    if (!editData) return;
    setPathValidationBusy(current => ({ ...current, [fieldKey]: true }));
    try {
      const payload = await validateGitHubPath({
        projectId: editData.id,
        reference: editData.pathConfig[fieldKey],
        rootReference: fieldKey === 'root' ? undefined : editData.pathConfig.root,
      });
      setPathValidation(current => ({ ...current, [fieldKey]: payload }));
    } catch (validationError: any) {
      setPathValidation(current => ({
        ...current,
        [fieldKey]: {
          reference: editData.pathConfig[fieldKey],
          status: {
            state: 'error',
            message: validationError?.message || 'Validation failed',
            checkedAt: new Date().toISOString(),
            path: '',
          },
          resolvedLocalPath: '',
        },
      }));
    } finally {
      setPathValidationBusy(current => ({ ...current, [fieldKey]: false }));
    }
  };

  const handleValidatePaths = async () => {
    if (!editData) return;
    setTestingBusy(true);
    setTestingActionError(null);
    setTestingActionInfo(null);
    try {
      const rows = await getTestSourcesStatus(editData.id);
      setSourceStatus(rows);
      setTestingActionInfo(`Validated ${rows.length} source configuration entries.`);
    } catch (e: any) {
      setTestingActionError(e.message || 'Failed to validate testing paths');
    } finally {
      setTestingBusy(false);
    }
  };

  const handleRunSync = async () => {
    if (!editData) return;
    setTestingBusy(true);
    setTestingActionError(null);
    setTestingActionInfo(null);
    try {
      const result = await syncTestSources(editData.id, { force: true });
      setSourceStatus(result.sources || []);
      const stats = result.stats as Record<string, number>;
      const synced = Number(stats?.synced || 0);
      const metrics = Number(stats?.metrics || 0);
      const errors = Number(stats?.errors || 0);
      setTestingActionInfo(`Sync complete: ${synced} files synced, ${metrics} metrics captured, ${errors} errors.`);
    } catch (e: any) {
      setTestingActionError(e.message || 'Failed to run test source sync');
    } finally {
      setTestingBusy(false);
    }
  };

  const handleGenerateScript = () => {
    if (!editData) return;
    const output = generateProjectTestSetupScript(editData);
    setGeneratedScript(output.content);
    setGeneratedScriptName(output.filename);
    setScriptCopied(false);
    setTestingActionInfo(`Generated setup script: ${output.filename}`);
    setTestingActionError(null);
  };

  const handleCopyScript = async () => {
    if (!generatedScript) return;
    try {
      await navigator.clipboard.writeText(generatedScript);
      setScriptCopied(true);
      setTestingActionInfo('Setup script copied to clipboard.');
      setTestingActionError(null);
    } catch (e: any) {
      setTestingActionError(e?.message || 'Failed to copy script to clipboard');
    }
  };

  const handleCopyWatcherEnv = async () => {
    if (!editData) return;
    try {
      await navigator.clipboard.writeText(buildWatcherEnvOverlay(editData));
      setWatcherEnvCopied(true);
      setTestingActionInfo('Watcher env overlay copied to clipboard.');
      setTestingActionError(null);
    } catch (e: any) {
      setTestingActionError(e?.message || 'Failed to copy watcher env overlay');
    }
  };

  const handleDownloadScript = () => {
    if (!generatedScript) return;
    try {
      const blob = new Blob([generatedScript], { type: 'text/x-shellscript;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = generatedScriptName || `${editData?.id || 'project'}-test-setup.sh`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setTestingActionInfo('Setup script downloaded.');
      setTestingActionError(null);
    } catch (e: any) {
      setTestingActionError(e?.message || 'Failed to download setup script');
    }
  };

  const handleSave = async () => {
    if (!editData) return;
    setSaving(true);
    savingRef.current = true;
    setError(null);
    try {
      await updateProject(editData.id, editData);
      setSaved(true);
      setDirtyPaths(false);
      try {
        setResolvedPaths(await getProjectResolvedPaths(editData.id));
      } catch {
        setResolvedPaths(null);
      }
    } catch (e: any) {
      setError(e.message || 'Failed to save project');
    } finally {
      setSaving(false);
      savingRef.current = false;
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="bg-indigo-500/10 p-2 rounded-lg text-indigo-400">
              <FolderOpen size={20} />
            </div>
            <div>
              <h3 className="font-semibold text-slate-100">Project Configuration</h3>
              <p className="text-sm text-slate-400">Edit project metadata, typed path sources, and test sync defaults.</p>
            </div>
          </div>
          {dirtyPaths && (
            <div className="flex items-center gap-2 text-amber-400 text-xs bg-amber-500/10 px-3 py-1.5 rounded-lg border border-amber-500/20">
              <RefreshCw size={12} />
              Path changes will trigger a rescan on save
            </div>
          )}
        </div>

        <ProjectPicker
          projects={projects}
          selectedProjectId={selectedProjectId}
          dropdownOpen={dropdownOpen}
          onToggleDropdown={() => setDropdownOpen(current => !current)}
          onSelect={(projectId) => {
            setSelectedProjectId(projectId);
            setDropdownOpen(false);
          }}
        />

        {error && (
          <div className="mt-4 rounded-lg border border-rose-700/50 bg-rose-900/30 px-3 py-2 text-sm text-rose-200">
            {error}
          </div>
        )}

        {saved && !error && (
          <div className="mt-4 rounded-lg border border-emerald-700/50 bg-emerald-900/30 px-3 py-2 text-sm text-emerald-200 flex items-center gap-2">
            <Check size={14} />
            Project saved successfully.
          </div>
        )}

        {editData && (
          <div className="mt-6 space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <label className="block">
                <span className="block text-sm font-medium text-slate-400 mb-2">Project Name</span>
                <input
                  type="text"
                  value={editData.name}
                  onChange={event => handleFieldChange('name', event.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </label>
              <label className="block">
                <span className="block text-sm font-medium text-slate-400 mb-2">Repository URL</span>
                <input
                  type="url"
                  value={editData.repoUrl}
                  onChange={event => handleFieldChange('repoUrl', event.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  placeholder="https://github.com/org/repo"
                />
              </label>
            </div>

            <label className="block">
              <span className="block text-sm font-medium text-slate-400 mb-2">Description</span>
              <textarea
                value={editData.description}
                onChange={event => handleFieldChange('description', event.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 h-20 resize-none"
              />
            </label>

            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Agent Platform</label>
              <div className="flex items-center gap-2 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5">
                <span className="text-sm text-slate-300">{editData.agentPlatforms.join(', ')}</span>
                <span className="ml-auto text-[10px] px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">LOCKED</span>
              </div>
              <p className="text-xs text-slate-500 mt-1">Only Claude Code is supported at this time.</p>
            </div>

            <div className="border-t border-slate-800 pt-5 space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h4 className="text-sm font-semibold text-slate-300 mb-1 flex items-center gap-2">
                    <GitBranch size={14} className="text-indigo-400" />
                    Path Sources
                  </h4>
                  <p className="text-xs text-slate-500">
                    Each field can resolve from the project root, a filesystem path, or a managed GitHub workspace.
                  </p>
                </div>
              </div>
              <div className="space-y-4">
                {PROJECT_PATH_FIELDS.map(field => {
                  const rootPreviewPath = pathValidation.root?.resolvedLocalPath
                    || resolvedPaths?.root.path
                    || deriveProjectPathPreview(editData.pathConfig, 'root', '', pathValidation.root?.resolvedLocalPath);
                  const resolvedPreview = field.key === 'root'
                    ? rootPreviewPath
                    : pathValidation[field.key]?.resolvedLocalPath
                      || (field.key === 'planDocs' ? resolvedPaths?.planDocs.path
                        : field.key === 'sessions' ? resolvedPaths?.sessions.path
                          : resolvedPaths?.progress.path)
                      || deriveProjectPathPreview(editData.pathConfig, field.key, rootPreviewPath, pathValidation[field.key]?.resolvedLocalPath);
                  return (
                    <PathEditorCard
                      key={field.key}
                      fieldKey={field.key}
                      reference={editData.pathConfig[field.key]}
                      previewPath={resolvedPreview}
                      validation={pathValidation[field.key]}
                      validationBusy={Boolean(pathValidationBusy[field.key])}
                      onSourceKindChange={handlePathSourceKindChange}
                      onInputChange={handlePathInputChange}
                      onRepoFieldChange={handleRepoFieldChange}
                      onRepoWriteToggle={handleRepoWriteToggle}
                      onValidate={handleValidateGitHubPath}
                    />
                  );
                })}
              </div>
            </div>

            <div className="border-t border-slate-800 pt-5 space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h4 className="text-sm font-semibold text-slate-300 mb-1 flex items-center gap-2">
                    <Monitor size={14} className="text-indigo-400" />
                    Live Ingest Binding
                  </h4>
                  <p className="text-xs text-slate-500">
                    Watcher workers bind to one project id at startup.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleCopyWatcherEnv}
                  className="inline-flex items-center gap-1 rounded border border-indigo-500/35 bg-indigo-500/10 px-2 py-1 text-[11px] font-semibold text-indigo-300 hover:bg-indigo-500/20"
                >
                  <Copy size={12} />
                  {watcherEnvCopied ? 'Copied' : 'Copy Env'}
                </button>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-4">
                <div className="rounded-lg border border-slate-700 bg-slate-950 p-3">
                  <p className="mb-2 text-xs font-semibold text-slate-300">Resolved Watch Scope</p>
                  <dl className="space-y-2 text-xs">
                    <div>
                      <dt className="text-slate-500">Project id</dt>
                      <dd className="font-mono text-slate-200 break-all">{editData.id}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">Root</dt>
                      <dd className="font-mono text-slate-200 break-all">{resolvedPaths?.root.path || editData.path || 'Not resolved yet'}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">Plans</dt>
                      <dd className="font-mono text-slate-200 break-all">{resolvedPaths?.planDocs.path || editData.planDocsPath || 'Not resolved yet'}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">Sessions</dt>
                      <dd className="font-mono text-slate-200 break-all">{resolvedPaths?.sessions.path || editData.sessionsPath || 'Not resolved yet'}</dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">Progress</dt>
                      <dd className="font-mono text-slate-200 break-all">{resolvedPaths?.progress.path || editData.progressPath || 'Not resolved yet'}</dd>
                    </div>
                  </dl>
                </div>

                <div className="rounded-lg border border-slate-700 bg-slate-950 p-3">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <p className="text-xs font-semibold text-slate-300">Watcher Env Overlay</p>
                    <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-200">
                      Restart required
                    </span>
                  </div>
                  <textarea
                    value={buildWatcherEnvOverlay(editData)}
                    readOnly
                    className="h-44 w-full resize-y rounded border border-slate-800 bg-slate-900 p-2 font-mono text-[11px] text-slate-200"
                  />
                </div>
              </div>
            </div>

            <div className="border-t border-slate-800 pt-5 space-y-5">
              <h4 className="text-sm font-semibold text-slate-300 mb-1">Testing Configuration</h4>
              <p className="text-xs text-slate-500">
                Configure test platforms, result directories, and feature flags for this project.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  ['testVisualizerEnabled', 'Test Visualizer'],
                  ['integritySignalsEnabled', 'Integrity Signals'],
                  ['liveTestUpdatesEnabled', 'Live Updates'],
                  ['semanticMappingEnabled', 'Semantic Mapping'],
                ].map(([key, label]) => (
                  <label key={key} className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                    <span className="text-sm text-slate-200">{label}</span>
                    <input
                      type="checkbox"
                      checked={(editData.testConfig?.flags as unknown as Record<string, boolean>)?.[key] ?? false}
                      onChange={event => updateFlag(key as keyof Project['testConfig']['flags'], event.target.checked)}
                      className="h-4 w-4"
                    />
                  </label>
                ))}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <label className="block">
                  <span className="block text-xs text-slate-400 mb-1">Auto Sync on Startup</span>
                  <input
                    type="checkbox"
                    checked={Boolean(editData.testConfig?.autoSyncOnStartup)}
                    onChange={event => updateTestConfig(prev => ({ ...prev, autoSyncOnStartup: event.target.checked }))}
                    className="h-4 w-4"
                  />
                </label>
                <label className="block">
                  <span className="block text-xs text-slate-400 mb-1">Max Files per Scan</span>
                  <input
                    type="number"
                    min={10}
                    max={5000}
                    value={editData.testConfig?.maxFilesPerScan ?? 500}
                    onChange={event => updateTestConfig(prev => ({ ...prev, maxFilesPerScan: Number(event.target.value || 500) }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </label>
                <label className="block">
                  <span className="block text-xs text-slate-400 mb-1">Max Parse Concurrency</span>
                  <input
                    type="number"
                    min={1}
                    max={64}
                    value={editData.testConfig?.maxParseConcurrency ?? 4}
                    onChange={event => updateTestConfig(prev => ({ ...prev, maxParseConcurrency: Number(event.target.value || 4) }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </label>
              </div>

              <div className="space-y-3">
                {(editData.testConfig?.platforms || []).map(platform => (
                  <div key={platform.id} className="rounded-lg border border-slate-700 bg-slate-950 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-semibold text-slate-200">{platform.id}</p>
                        <p className="text-xs text-slate-500">Watch: {platform.watch ? 'enabled' : 'disabled'}</p>
                      </div>
                      <div className="flex items-center gap-4">
                        <label className="text-xs text-slate-300 flex items-center gap-2">
                          Enabled
                          <input
                            type="checkbox"
                            checked={platform.enabled}
                            onChange={event => updatePlatform(platform.id, prev => ({ ...prev, enabled: event.target.checked }))}
                            className="h-4 w-4"
                          />
                        </label>
                        <label className="text-xs text-slate-300 flex items-center gap-2">
                          Watch
                          <input
                            type="checkbox"
                            checked={platform.watch}
                            onChange={event => updatePlatform(platform.id, prev => ({ ...prev, watch: event.target.checked }))}
                            className="h-4 w-4"
                          />
                        </label>
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <label>
                        <span className="block text-xs text-slate-400 mb-1">Results Dir</span>
                        <input
                          type="text"
                          value={platform.resultsDir}
                          onChange={event => updatePlatform(platform.id, prev => ({ ...prev, resultsDir: event.target.value }))}
                          className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 font-mono"
                        />
                      </label>
                      <label>
                        <span className="block text-xs text-slate-400 mb-1">Patterns (comma separated)</span>
                        <input
                          type="text"
                          value={platform.patterns.join(', ')}
                          onChange={event => updatePlatform(platform.id, prev => ({
                            ...prev,
                            patterns: event.target.value.split(',').map(item => item.trim()).filter(Boolean),
                          }))}
                          className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 font-mono"
                        />
                      </label>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  disabled={testingBusy}
                  onClick={handleValidatePaths}
                  className="rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200 hover:border-slate-600 disabled:opacity-50"
                >
                  Validate Paths
                </button>
                <button
                  type="button"
                  disabled={testingBusy}
                  onClick={handleRunSync}
                  className="rounded border border-indigo-500/40 bg-indigo-500/10 px-3 py-2 text-xs font-semibold text-indigo-300 hover:bg-indigo-500/20 disabled:opacity-50"
                >
                  Run Sync Now
                </button>
                <button
                  type="button"
                  onClick={handleGenerateScript}
                  className="rounded border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/20"
                >
                  Generate Setup Script
                </button>
              </div>

              {testingActionError && (
                <div className="rounded-lg border border-rose-600/50 bg-rose-600/10 px-3 py-2 text-xs text-rose-200">
                  {testingActionError}
                </div>
              )}
              {testingActionInfo && !testingActionError && (
                <div className="rounded-lg border border-emerald-600/40 bg-emerald-600/10 px-3 py-2 text-xs text-emerald-200">
                  {testingActionInfo}
                </div>
              )}

              {sourceStatus.length > 0 && (
                <div className="rounded-lg border border-slate-700 bg-slate-950 p-3">
                  <p className="text-xs font-semibold text-slate-300 mb-2">Source Status</p>
                  <div className="space-y-2">
                    {sourceStatus.map(row => (
                      <div key={`${row.platformId}-${row.resolvedDir}`} className="rounded border border-slate-800 px-2 py-1.5 text-xs text-slate-300">
                        <p className="font-mono text-slate-200">{row.platformId}: {row.resolvedDir}</p>
                        <p>exists={String(row.exists)} readable={String(row.readable)} matched={row.matchedFiles}</p>
                        {row.lastError && <p className="text-rose-300">{row.lastError}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {generatedScript && (
                <div className="rounded-lg border border-slate-700 bg-slate-950 p-3">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <p className="text-xs font-semibold text-slate-300">
                      Generated Script
                      {generatedScriptName ? <span className="ml-2 text-slate-500 font-mono">{generatedScriptName}</span> : null}
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleCopyScript}
                        className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[11px] text-slate-200 hover:border-slate-600"
                      >
                        <Copy size={12} />
                        {scriptCopied ? 'Copied' : 'Copy'}
                      </button>
                      <button
                        type="button"
                        onClick={handleDownloadScript}
                        className="inline-flex items-center gap-1 rounded border border-indigo-500/35 bg-indigo-500/10 px-2 py-1 text-[11px] font-semibold text-indigo-300 hover:bg-indigo-500/20"
                      >
                        <Download size={12} />
                        Export
                      </button>
                    </div>
                  </div>
                  <textarea
                    value={generatedScript}
                    readOnly
                    className="h-56 w-full resize-y rounded border border-slate-800 bg-slate-900 p-2 font-mono text-[11px] text-slate-200"
                  />
                  <p className="mt-2 text-xs text-slate-500">
                    Export this script and run it locally in the target project workspace.
                  </p>
                </div>
              )}
            </div>

            <div className="flex justify-end pt-4 border-t border-slate-800">
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? (
                  <>
                    <RefreshCw size={14} className="animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save size={14} />
                    Save Project
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const IntegrationsTab: React.FC = () => {
  const { projects, activeProject, updateProject } = useData();
  const apiClient = React.useMemo(() => createApiClient(), []);
  const [subtab, setSubtab] = useState<IntegrationsSubtab>('skillmeat');
  const [selectedProjectId, setSelectedProjectId] = useState<string>(activeProject?.id || '');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [editData, setEditData] = useState<Project | null>(null);
  const [skillMeatValidation, setSkillMeatValidation] = useState<SkillMeatConfigValidationResponse | null>(null);
  const [skillMeatValidationBusy, setSkillMeatValidationBusy] = useState(false);
  const [skillMeatValidationError, setSkillMeatValidationError] = useState<string | null>(null);
  const [skillMeatSaving, setSkillMeatSaving] = useState(false);
  const [skillMeatMessage, setSkillMeatMessage] = useState<string | null>(null);
  const [skillMeatError, setSkillMeatError] = useState<string | null>(null);
  const [githubSettings, setGitHubSettings] = useState<GitHubIntegrationSettingsUpdateRequest>({
    enabled: false,
    baseUrl: 'https://github.com',
    username: 'git',
    token: '',
    cacheRoot: '',
    writeEnabled: false,
  });
  const [maskedToken, setMaskedToken] = useState('');
  const [tokenConfigured, setTokenConfigured] = useState(false);
  const [githubMessage, setGitHubMessage] = useState<string | null>(null);
  const [githubError, setGitHubError] = useState<string | null>(null);
  const [githubSaving, setGitHubSaving] = useState(false);
  const [credentialValidation, setCredentialValidation] = useState<GitHubCredentialValidationResponse | null>(null);
  const [writeCapability, setWriteCapability] = useState<GitHubWriteCapabilityResponse | null>(null);
  const [githubBusy, setGitHubBusy] = useState(false);
  const [telemetryStatus, setTelemetryStatus] = useState<TelemetryExportStatus | null>(null);
  const [telemetryEnabledDraft, setTelemetryEnabledDraft] = useState(false);
  const [telemetryLoading, setTelemetryLoading] = useState(true);
  const [telemetrySaving, setTelemetrySaving] = useState(false);
  const [telemetryMessage, setTelemetryMessage] = useState<string | null>(null);
  const [telemetryError, setTelemetryError] = useState<string | null>(null);
  const [snapshotHealth, setSnapshotHealth] = useState<SnapshotHealth | null>(null);
  const [snapshotHealthLoading, setSnapshotHealthLoading] = useState(false);
  const [snapshotHealthError, setSnapshotHealthError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedProjectId && activeProject) {
      setSelectedProjectId(activeProject.id);
    }
  }, [activeProject, selectedProjectId]);

  useEffect(() => {
    const project = projects.find(candidate => candidate.id === selectedProjectId);
    if (!project) return;
    setEditData(buildEditableProject(project));
    setSkillMeatValidation(null);
    setSkillMeatValidationError(null);
    setSkillMeatMessage(null);
    setSkillMeatError(null);
    setSnapshotHealth(null);
    setSnapshotHealthError(null);
    setCredentialValidation(null);
    setWriteCapability(null);
  }, [projects, selectedProjectId]);

  useEffect(() => {
    void getGitHubSettings()
      .then(response => {
        setGitHubSettings({
          enabled: response.enabled,
          baseUrl: response.baseUrl,
          username: response.username,
          token: '',
          cacheRoot: response.cacheRoot,
          writeEnabled: response.writeEnabled,
        });
        setMaskedToken(response.maskedToken);
        setTokenConfigured(response.tokenConfigured);
      })
      .catch((loadError: any) => {
        setGitHubError(loadError?.message || 'Failed to load GitHub integration settings');
      });
  }, []);

  const loadTelemetryStatus = React.useCallback(async () => {
    setTelemetryLoading(true);
    try {
      const response = await apiClient.getTelemetryExportStatus();
      setTelemetryStatus(response);
      setTelemetryEnabledDraft(response.persistedEnabled);
      setTelemetryError(null);
    } catch (loadError: any) {
      setTelemetryError(loadError?.message || 'Failed to load telemetry exporter status');
    } finally {
      setTelemetryLoading(false);
    }
  }, [apiClient]);

  useEffect(() => {
    void loadTelemetryStatus();
  }, [loadTelemetryStatus]);

  const loadSnapshotDiagnostics = React.useCallback(async (projectId: string) => {
    if (!projectId) return;
    setSnapshotHealthLoading(true);
    setSnapshotHealthError(null);
    try {
      const response = await apiClient.fetchSnapshotDiagnostics(projectId);
      setSnapshotHealth(response);
    } catch (loadError: any) {
      setSnapshotHealthError(loadError?.message || 'Failed to load artifact intelligence diagnostics');
    } finally {
      setSnapshotHealthLoading(false);
    }
  }, [apiClient]);

  useEffect(() => {
    if (subtab !== 'skillmeat' || !selectedProjectId) return;
    void loadSnapshotDiagnostics(selectedProjectId);
  }, [loadSnapshotDiagnostics, selectedProjectId, subtab]);

  const updateSkillMeatConfig = (updater: (prev: Project['skillMeat']) => Project['skillMeat']) => {
    setEditData(current => {
      if (!current) return current;
      return { ...current, skillMeat: updater(current.skillMeat || DEFAULT_SKILLMEAT_CONFIG) };
    });
    setSkillMeatValidation(null);
    setSkillMeatValidationError(null);
    setSkillMeatMessage(null);
    setSkillMeatError(null);
  };

  const handleValidateSkillMeat = async () => {
    if (!editData) return;
    setSkillMeatValidationBusy(true);
    setSkillMeatValidationError(null);
    try {
      const response = await validateSkillMeatConfig(editData.skillMeat || DEFAULT_SKILLMEAT_CONFIG);
      setSkillMeatValidation(response);
    } catch (validationError: any) {
      setSkillMeatValidationError(validationError?.message || 'Failed to validate SkillMeat configuration');
    } finally {
      setSkillMeatValidationBusy(false);
    }
  };

  const handleSaveSkillMeat = async () => {
    if (!editData) return;
    setSkillMeatSaving(true);
    setSkillMeatMessage(null);
    setSkillMeatError(null);
    try {
      await updateProject(editData.id, editData);
      const skillMeatConfig = normalizeSkillMeatConfig(editData);
      if (skillMeatConfig.enabled && skillMeatConfig.baseUrl.trim()) {
        const refreshResult = await refreshSkillMeatCache(editData.id);
        const syncResult = refreshResult.sync;
        const backfillResult = refreshResult.backfill;
        const warningCount = (syncResult.warnings?.length || 0) + (backfillResult?.warnings?.length || 0);
        setSkillMeatMessage(
          `SkillMeat refresh complete: ${syncResult.totalDefinitions} definitions synced, ${backfillResult?.observationsStored ?? 0} observations rebuilt${warningCount > 0 ? `, ${warningCount} warning${warningCount === 1 ? '' : 's'}` : ''}.`,
        );
      } else {
        setSkillMeatMessage('SkillMeat settings saved.');
      }
      void loadSnapshotDiagnostics(editData.id);
    } catch (saveError: any) {
      setSkillMeatError(saveError?.message || 'Failed to save SkillMeat settings');
    } finally {
      setSkillMeatSaving(false);
    }
  };

  const handleSaveGitHubSettings = async () => {
    setGitHubSaving(true);
    setGitHubMessage(null);
    setGitHubError(null);
    try {
      const response = await updateGitHubSettings(githubSettings);
      setGitHubSettings({
        enabled: response.enabled,
        baseUrl: response.baseUrl,
        username: response.username,
        token: '',
        cacheRoot: response.cacheRoot,
        writeEnabled: response.writeEnabled,
      });
      setMaskedToken(response.maskedToken);
      setTokenConfigured(response.tokenConfigured);
      setGitHubMessage('GitHub integration settings saved.');
    } catch (saveError: any) {
      setGitHubError(saveError?.message || 'Failed to save GitHub settings');
    } finally {
      setGitHubSaving(false);
    }
  };

  const handleValidateGitHubCredential = async () => {
    if (!selectedProjectId) return;
    setGitHubBusy(true);
    setGitHubError(null);
    setGitHubMessage(null);
    try {
      const response = await validateGitHubCredential({
        projectId: selectedProjectId,
        settings: githubSettings,
      });
      setCredentialValidation(response);
      setGitHubMessage('GitHub validation completed.');
    } catch (validationError: any) {
      setGitHubError(validationError?.message || 'Failed to validate GitHub access');
    } finally {
      setGitHubBusy(false);
    }
  };

  const handleCheckWriteCapability = async () => {
    if (!editData) return;
    setGitHubBusy(true);
    setGitHubError(null);
    try {
      const response = await checkGitHubWriteCapability({
        projectId: editData.id,
        reference: editData.pathConfig.root,
      });
      setWriteCapability(response);
    } catch (capabilityError: any) {
      setGitHubError(capabilityError?.message || 'Failed to evaluate write capability');
    } finally {
      setGitHubBusy(false);
    }
  };

  const handleRefreshWorkspace = async () => {
    if (!editData) return;
    setGitHubBusy(true);
    setGitHubError(null);
    try {
      const response = await refreshGitHubWorkspace({
        projectId: editData.id,
        reference: editData.pathConfig.root,
        force: true,
      });
      setGitHubMessage(response.status.message);
    } catch (refreshError: any) {
      setGitHubError(refreshError?.message || 'Failed to refresh GitHub workspace');
    } finally {
      setGitHubBusy(false);
    }
  };

  const handleSaveTelemetry = async () => {
    setTelemetrySaving(true);
    setTelemetryMessage(null);
    setTelemetryError(null);
    try {
      const response = await apiClient.updateTelemetryExportSettings({ enabled: telemetryEnabledDraft });
      setTelemetryStatus(response);
      setTelemetryEnabledDraft(response.persistedEnabled);
      setTelemetryMessage('Telemetry export settings saved.');
    } catch (saveError: any) {
      setTelemetryError(saveError?.message || 'Failed to save telemetry exporter settings');
    } finally {
      setTelemetrySaving(false);
    }
  };

  const telemetryToggleDisabled = telemetryLoading
    || telemetrySaving
    || !telemetryStatus?.configured
    || Boolean(telemetryStatus?.envLocked);
  const telemetryDirty = Boolean(telemetryStatus) && telemetryEnabledDraft !== telemetryStatus.persistedEnabled;
  const telemetryBadgeState = telemetryLoading
    ? 'idle'
    : telemetryStatus?.enabled
      ? 'success'
      : telemetryStatus?.configured
        ? 'warning'
        : 'error';
  const telemetryBadgeLabel = telemetryLoading
    ? 'Loading'
    : telemetryStatus?.enabled
      ? 'Exporter active'
      : telemetryStatus?.envLocked
        ? 'Environment lock'
        : telemetryStatus?.configured
          ? 'Configured but off'
          : 'Not configured';
  const snapshotDataAvailable = hasSnapshotData(snapshotHealth);
  const snapshotWarnings = [
    ...(snapshotHealth?.warnings ?? []),
    editData && !editData.skillMeat?.enabled ? 'Project SkillMeat integration is disabled, so snapshot ingestion will not run for this project.' : null,
    snapshotHealth?.isStale ? 'The latest artifact snapshot is stale or has not been fetched yet.' : null,
    snapshotHealth && snapshotHealth.lastRollupExportedAt == null
      ? 'Rollup export freshness is not reported by the current diagnostics API.'
      : null,
  ].filter((warning): warning is string => Boolean(warning));

  return (
    <div className="space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="bg-indigo-500/10 p-2 rounded-lg text-indigo-400">
            <GitBranch size={20} />
          </div>
          <div>
            <h3 className="font-semibold text-slate-100">Integrations</h3>
            <p className="text-sm text-slate-400">SkillMeat remains project-scoped. GitHub credentials and workspace policy are app-scoped.</p>
          </div>
        </div>

        <ProjectPicker
          projects={projects}
          selectedProjectId={selectedProjectId}
          dropdownOpen={dropdownOpen}
          onToggleDropdown={() => setDropdownOpen(current => !current)}
          onSelect={(projectId) => {
            setSelectedProjectId(projectId);
            setDropdownOpen(false);
          }}
        />

        <div className="mt-6 flex items-center gap-2">
          <SubtabButton active={subtab === 'skillmeat'} label="SkillMeat" onClick={() => setSubtab('skillmeat')} />
          <SubtabButton active={subtab === 'github'} label="GitHub" onClick={() => setSubtab('github')} />
        </div>

        {subtab === 'skillmeat' && editData && (
          <div className="mt-6 space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="text-sm font-semibold text-slate-300 mb-1">SkillMeat Integration</h4>
                <p className="text-xs text-slate-500">
                  Configure the read-only SkillMeat source for artifacts, workflows, context modules, and bundle metadata.
                </p>
              </div>
              <button
                type="button"
                onClick={handleValidateSkillMeat}
                disabled={skillMeatValidationBusy}
                className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-xs font-medium text-cyan-200 disabled:opacity-50"
              >
                <RefreshCw size={12} className={skillMeatValidationBusy ? 'animate-spin' : ''} />
                {skillMeatValidationBusy ? 'Checking...' : 'Check Connection'}
              </button>
            </div>

            {skillMeatValidationError && (
              <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                {skillMeatValidationError}
              </div>
            )}
            {skillMeatMessage && (
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
                {skillMeatMessage}
              </div>
            )}
            {skillMeatError && (
              <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                {skillMeatError}
              </div>
            )}

            <label className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
              <span className="text-sm text-slate-200">Enable SkillMeat integration</span>
              <input
                type="checkbox"
                checked={Boolean(editData.skillMeat?.enabled)}
                onChange={event => updateSkillMeatConfig(prev => ({ ...prev, enabled: event.target.checked }))}
                className="h-4 w-4"
              />
            </label>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label className="block">
                <span className="mb-1 flex items-center justify-between gap-2 text-xs text-slate-400">
                  <span>API Base URL</span>
                  <SkillMeatStatusBadge result={skillMeatValidation?.baseUrl} fallback="Unchecked" />
                </span>
                <input
                  type="url"
                  value={editData.skillMeat?.baseUrl || ''}
                  onChange={event => updateSkillMeatConfig(prev => ({ ...prev, baseUrl: event.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  placeholder="http://127.0.0.1:8080"
                />
              </label>
              <label className="block">
                <span className="block text-xs text-slate-400 mb-1">Web App URL (optional)</span>
                <input
                  type="url"
                  value={editData.skillMeat?.webBaseUrl || ''}
                  onChange={event => updateSkillMeatConfig(prev => ({ ...prev, webBaseUrl: event.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  placeholder="http://127.0.0.1:3000"
                />
                <p className="mt-1 text-xs text-slate-500">
                  Used for deep links from CCDash to SkillMeat pages. Leave blank to hide SkillMeat hyperlinks.
                </p>
              </label>
              <label className="block">
                <span className="block text-xs text-slate-400 mb-1">Request Timeout (seconds)</span>
                <input
                  type="number"
                  min={1}
                  max={120}
                  step={0.5}
                  value={editData.skillMeat?.requestTimeoutSeconds ?? 5}
                  onChange={event => updateSkillMeatConfig(prev => ({ ...prev, requestTimeoutSeconds: Number(event.target.value || 5) }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </label>
              <label className="block">
                <span className="mb-1 flex items-center justify-between gap-2 text-xs text-slate-400">
                  <span>SkillMeat Project ID</span>
                  <SkillMeatStatusBadge result={skillMeatValidation?.projectMapping} fallback="Unchecked" />
                </span>
                <input
                  type="text"
                  value={editData.skillMeat?.projectId || ''}
                  onChange={event => updateSkillMeatConfig(prev => ({ ...prev, projectId: event.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                  placeholder="project UUID from SkillMeat"
                />
                <p className="mt-1 text-xs text-slate-500">Use the exact SkillMeat project ID from the SkillMeat UI.</p>
              </label>
              <label className="block">
                <span className="block text-xs text-slate-400 mb-1">Collection ID (optional)</span>
                <input
                  type="text"
                  value={editData.skillMeat?.collectionId || ''}
                  onChange={event => updateSkillMeatConfig(prev => ({ ...prev, collectionId: event.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                  placeholder="default"
                />
              </label>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                <div>
                  <span className="block text-sm text-slate-200">AAA enabled</span>
                  <span className="block text-xs text-slate-500">Turn this on for auth-protected SkillMeat instances.</span>
                </div>
                <input
                  type="checkbox"
                  checked={Boolean(editData.skillMeat?.aaaEnabled)}
                  onChange={event => updateSkillMeatConfig(prev => ({ ...prev, aaaEnabled: event.target.checked }))}
                  className="h-4 w-4"
                />
              </label>
              <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                <span className="mb-2 flex items-center justify-between gap-2 text-xs text-slate-400">
                  <span>Auth Status</span>
                  <SkillMeatStatusBadge result={skillMeatValidation?.auth} fallback="Unchecked" />
                </span>
                <p className="text-xs text-slate-500">
                  Local development usually runs without auth. AAA mode sends `Authorization: Bearer &lt;token&gt;`.
                </p>
              </div>
            </div>

            {editData.skillMeat?.aaaEnabled ? (
              <label className="block">
                <span className="block text-xs text-slate-400 mb-1">API Key / Bearer Token</span>
                <input
                  type="password"
                  value={editData.skillMeat?.apiKey || ''}
                  onChange={event => updateSkillMeatConfig(prev => ({ ...prev, apiKey: event.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                  placeholder="sm_pat_..."
                />
              </label>
            ) : (
              <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-slate-500">
                Local mode is selected, so CCDash will not send a credential until AAA is enabled.
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {[
                ['stackRecommendationsEnabled', 'Recommended Stack UI', 'Show evidence-backed stack suggestions in /execution.'],
                ['usageAttributionEnabled', 'Usage Attribution', 'Enable attribution views in /analytics and drill-downs.'],
                ['sessionBlockInsightsEnabled', 'Session Block Insights', 'Enable billing-block views in Session Inspector.'],
                ['workflowAnalyticsEnabled', 'Workflow Effectiveness', 'Enable workflow intelligence analytics in /analytics and /execution.'],
              ].map(([key, label, description]) => (
                <label key={key} className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <div>
                    <span className="block text-sm text-slate-200">{label}</span>
                    <span className="block text-xs text-slate-500">{description}</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={(editData.skillMeat?.featureFlags as unknown as Record<string, boolean>)?.[key] ?? true}
                    onChange={event => updateSkillMeatConfig(prev => ({
                      ...prev,
                      featureFlags: {
                        ...DEFAULT_SKILLMEAT_FEATURE_FLAGS,
                        ...(prev.featureFlags || {}),
                        [key]: event.target.checked,
                      },
                    }))}
                    className="h-4 w-4"
                  />
                </label>
              ))}
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="mb-2">
                    <ConnectionStatusBadge
                      label={editData.skillMeat?.enabled ? 'Project enabled' : 'Project disabled'}
                      state={editData.skillMeat?.enabled ? 'success' : 'warning'}
                    />
                  </div>
                  <h4 className="text-sm font-semibold text-slate-300 mb-1">SkillMeat Artifact Intelligence</h4>
                  <p className="text-xs text-slate-500">
                    Snapshot diagnostics for artifact rankings, recommendations, and identity reconciliation.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void loadSnapshotDiagnostics(editData.id)}
                  disabled={snapshotHealthLoading}
                  className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-xs font-medium text-cyan-200 disabled:opacity-50"
                >
                  <RefreshCw size={12} className={snapshotHealthLoading ? 'animate-spin' : ''} />
                  {snapshotHealthLoading ? 'Fetching...' : 'Fetch Now'}
                </button>
              </div>

              {snapshotHealthError && (
                <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                  {snapshotHealthError}
                </div>
              )}

              {!snapshotHealthError && !snapshotHealthLoading && !snapshotDataAvailable && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span>No snapshot data. Last fetched: Unknown.</span>
                    <button
                      type="button"
                      onClick={() => void loadSnapshotDiagnostics(editData.id)}
                      className="inline-flex items-center gap-1 rounded border border-amber-400/40 px-2 py-1 text-[11px] font-semibold text-amber-100 hover:bg-amber-400/10"
                    >
                      <RefreshCw size={11} />
                      Fetch Now
                    </button>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <span className="block text-xs text-slate-400 mb-1">Snapshot Age</span>
                  <p className="text-sm text-slate-200">{formatRelativeAge(snapshotHealth?.snapshotAgeSeconds)}</p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Last fetched: {formatOptionalTimestamp(snapshotHealth?.fetchedAt)}
                  </p>
                </div>
                <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <span className="block text-xs text-slate-400 mb-1">Artifact Count</span>
                  <p className="text-sm text-slate-200">{formatOptionalCount(snapshotHealth?.artifactCount)}</p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Resolved: {formatOptionalCount(snapshotHealth?.resolvedCount)}
                  </p>
                </div>
                <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <span
                    className="mb-1 flex items-center gap-1 text-xs text-slate-400"
                    title="Unresolved identities are observed CCDash artifact references that could not be mapped to the current SkillMeat artifact snapshot."
                  >
                    <span>Unresolved Identities</span>
                    <Info
                      size={12}
                      className="text-slate-500"
                      aria-label="Identity reconciliation help"
                    />
                  </span>
                  <p
                    className="text-sm text-slate-200"
                    title="Unresolved identities are observed CCDash artifact references that could not be mapped to the current SkillMeat artifact snapshot."
                  >
                    {snapshotHealth?.unresolvedCount == null
                      ? 'Identity mapping: Unavailable'
                      : snapshotHealth.unresolvedCount.toLocaleString()}
                  </p>
                </div>
                <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <span className="block text-xs text-slate-400 mb-1">Export Freshness</span>
                  <p className="text-sm text-slate-200">{formatOptionalTimestamp(snapshotHealth?.lastRollupExportedAt)}</p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    {snapshotHealth?.lastRollupExportedAt ? 'Last rollup export' : 'Not reported by diagnostics'}
                  </p>
                </div>
              </div>

              <label className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                <div>
                  <span className="block text-sm text-slate-200">Artifact intelligence runtime flag</span>
                  <span className="block text-xs text-slate-500">
                    `CCDASH_ARTIFACT_INTELLIGENCE_ENABLED` is managed by backend environment configuration. Settings has no safe write endpoint for this flag.
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={false}
                  disabled
                  readOnly
                  className="h-4 w-4"
                  aria-label="Artifact intelligence runtime flag is environment-managed"
                />
              </label>

              {snapshotWarnings.length > 0 && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                  <p className="mb-1 font-semibold">Warnings</p>
                  <ul className="list-disc space-y-1 pl-4">
                    {snapshotWarnings.map(warning => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="mb-2">
                    <ConnectionStatusBadge label={telemetryBadgeLabel} state={telemetryBadgeState} />
                  </div>
                  <h4 className="text-sm font-semibold text-slate-300 mb-1">Enterprise Telemetry Export</h4>
                  <p className="text-xs text-slate-500">
                    App-scoped exporter settings for pushing anonymized workflow metrics to SAM. The toggle persists in CCDash settings, but environment configuration can still force the exporter off.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void loadTelemetryStatus()}
                  disabled={telemetryLoading}
                  className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-xs font-medium text-cyan-200 disabled:opacity-50"
                >
                  <RefreshCw size={12} className={telemetryLoading ? 'animate-spin' : ''} />
                  {telemetryLoading ? 'Refreshing...' : 'Refresh Status'}
                </button>
              </div>

              {telemetryError && (
                <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                  {telemetryError}
                </div>
              )}
              {telemetryMessage && !telemetryError && (
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
                  {telemetryMessage}
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <span className="block text-xs text-slate-400 mb-1">SAM Endpoint</span>
                  <p className="text-sm text-slate-200 break-all">{telemetryStatus?.samEndpointMasked || 'Not configured'}</p>
                </div>
                <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <span className="block text-xs text-slate-400 mb-1">Last Push</span>
                  <p className="text-sm text-slate-200">
                    {telemetryStatus?.lastPushTimestamp ? new Date(telemetryStatus.lastPushTimestamp).toLocaleString() : 'Never'}
                  </p>
                </div>
                <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <span className="block text-xs text-slate-400 mb-1">Queue Snapshot</span>
                  <p className="text-sm text-slate-200">
                    {telemetryStatus
                      ? `${telemetryStatus.queueStats.pending} pending, ${telemetryStatus.queueStats.failed} failed, ${telemetryStatus.queueStats.abandoned} abandoned`
                      : 'Loading queue state...'}
                  </p>
                </div>
              </div>

              <label className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                <div>
                  <span className="block text-sm text-slate-200">Enable enterprise telemetry export</span>
                  <span className="block text-xs text-slate-500">
                    Uses the persisted app setting when SAM endpoint + API key are configured and the environment does not lock the exporter off.
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={telemetryEnabledDraft}
                  onChange={event => {
                    setTelemetryEnabledDraft(event.target.checked);
                    setTelemetryMessage(null);
                    setTelemetryError(null);
                  }}
                  disabled={telemetryToggleDisabled}
                  className="h-4 w-4"
                  aria-label="Enable enterprise telemetry export"
                />
              </label>

              {!telemetryStatus?.configured && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                  Configure `CCDASH_SAM_ENDPOINT` and `CCDASH_SAM_API_KEY` in the backend environment before enabling telemetry export from the UI.
                </div>
              )}
              {telemetryStatus?.envLocked && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                  Environment lock detected: `CCDASH_TELEMETRY_EXPORT_ENABLED=false` currently forces the exporter off even if the persisted setting is enabled.
                </div>
              )}
              {telemetryStatus?.lastError && (
                <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-300">
                  <span className="font-semibold text-slate-200">Recent exporter error:</span> {telemetryStatus.lastError}
                </div>
              )}

              <div className="flex justify-end pt-2">
                <button
                  type="button"
                  onClick={handleSaveTelemetry}
                  disabled={telemetrySaving || telemetryLoading || !telemetryDirty || telemetryToggleDisabled}
                  className="flex items-center gap-2 rounded-lg border border-indigo-500/40 bg-indigo-500/10 px-4 py-2 text-xs font-semibold text-indigo-200 hover:bg-indigo-500/20 disabled:opacity-50"
                >
                  {telemetrySaving ? (
                    <>
                      <RefreshCw size={12} className="animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save size={12} />
                      Save Telemetry Settings
                    </>
                  )}
                </button>
              </div>
            </div>

            <div className="rounded-lg border border-slate-700 bg-slate-950 p-3">
              <p className="text-xs font-semibold text-slate-300 mb-2">SkillMeat Setup Instructions</p>
              <div className="space-y-1.5">
                {SKILLMEAT_SETUP_COMMANDS.map(cmd => (
                  <code key={cmd} className="block rounded bg-slate-900 px-2 py-1 text-[11px] text-indigo-200 overflow-x-auto">{cmd}</code>
                ))}
              </div>
            </div>

            <div className="flex justify-end pt-4 border-t border-slate-800">
              <button
                type="button"
                onClick={handleSaveSkillMeat}
                disabled={skillMeatSaving}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {skillMeatSaving ? (
                  <>
                    <RefreshCw size={14} className="animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save size={14} />
                    Save SkillMeat Settings
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {subtab === 'github' && (
          <div className="mt-6 space-y-4">
            {githubError && (
              <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                {githubError}
              </div>
            )}
            {githubMessage && !githubError && (
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
                {githubMessage}
              </div>
            )}

            <label className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
              <div>
                <span className="block text-sm text-slate-200">Enable GitHub integration</span>
                <span className="block text-xs text-slate-500">Managed workspaces stay disabled until this is turned on.</span>
              </div>
              <input
                type="checkbox"
                checked={githubSettings.enabled}
                onChange={event => setGitHubSettings(current => ({ ...current, enabled: event.target.checked }))}
                className="h-4 w-4"
              />
            </label>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label className="block">
                <span className="block text-xs text-slate-400 mb-1">GitHub Base URL</span>
                <input
                  type="url"
                  value={githubSettings.baseUrl}
                  onChange={event => setGitHubSettings(current => ({ ...current, baseUrl: event.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </label>
              <label className="block">
                <span className="block text-xs text-slate-400 mb-1">Username</span>
                <input
                  type="text"
                  value={githubSettings.username}
                  onChange={event => setGitHubSettings(current => ({ ...current, username: event.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </label>
              <label className="block">
                <span className="block text-xs text-slate-400 mb-1">Token</span>
                <input
                  type="password"
                  value={githubSettings.token}
                  onChange={event => setGitHubSettings(current => ({ ...current, token: event.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                  placeholder={tokenConfigured ? 'Leave blank to keep existing token' : 'ghp_...'}
                />
                {tokenConfigured && (
                  <p className="mt-1 text-xs text-slate-500">Stored token: {maskedToken || 'configured'}</p>
                )}
              </label>
              <label className="block">
                <span className="block text-xs text-slate-400 mb-1">Workspace Cache Root</span>
                <input
                  type="text"
                  value={githubSettings.cacheRoot}
                  onChange={event => setGitHubSettings(current => ({ ...current, cacheRoot: event.target.value }))}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                />
              </label>
            </div>

            <label className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
              <div>
                <span className="block text-sm text-slate-200">Enable repo writes</span>
                <span className="block text-xs text-slate-500">Plan-document write-back still also requires the project root or target ref to allow writes.</span>
              </div>
              <input
                type="checkbox"
                checked={githubSettings.writeEnabled}
                onChange={event => setGitHubSettings(current => ({ ...current, writeEnabled: event.target.checked }))}
                className="h-4 w-4"
              />
            </label>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                <span className="mb-2 flex items-center justify-between gap-2 text-xs text-slate-400">
                  <span>Auth</span>
                  <GitHubStatusBadge result={credentialValidation?.auth} fallback="Unchecked" />
                </span>
                <p className="text-xs text-slate-500">Checks stored credentials and disabled-state handling.</p>
              </div>
              <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                <span className="mb-2 flex items-center justify-between gap-2 text-xs text-slate-400">
                  <span>Repo Access</span>
                  <GitHubStatusBadge result={credentialValidation?.repoAccess} fallback="Unchecked" />
                </span>
                <p className="text-xs text-slate-500">Uses the selected project root when it is GitHub-backed.</p>
              </div>
              <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                <span className="mb-2 flex items-center justify-between gap-2 text-xs text-slate-400">
                  <span>Write Capability</span>
                  <GitHubStatusBadge result={writeCapability?.status} fallback="Unchecked" />
                </span>
                <p className="text-xs text-slate-500">Confirms phase 6 gating before document write-back is enabled.</p>
              </div>
            </div>

            {editData && (
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <h4 className="text-sm font-semibold text-slate-200 mb-1">Selected project root</h4>
                <p className="text-xs text-slate-500 mb-3">
                  Path-source selection lives in the Projects tab. GitHub validation here uses the current root reference.
                </p>
                <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2">
                  <p className="text-xs text-slate-200 font-mono break-all">{getProjectPathInputValue(editData.pathConfig.root) || 'No root configured'}</p>
                  <p className="text-[11px] text-slate-500 mt-1">Source: {editData.pathConfig.root.sourceKind}</p>
                </div>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={handleSaveGitHubSettings}
                disabled={githubSaving}
                className="rounded border border-indigo-500/40 bg-indigo-500/10 px-3 py-2 text-xs font-semibold text-indigo-300 hover:bg-indigo-500/20 disabled:opacity-50"
              >
                {githubSaving ? 'Saving...' : 'Save GitHub Settings'}
              </button>
              <button
                type="button"
                onClick={handleValidateGitHubCredential}
                disabled={githubBusy}
                className="rounded border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
              >
                {githubBusy ? 'Working...' : 'Validate Access'}
              </button>
              <button
                type="button"
                onClick={handleRefreshWorkspace}
                disabled={githubBusy || !editData || editData.pathConfig.root.sourceKind !== 'github_repo'}
                className="rounded border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200 hover:border-slate-600 disabled:opacity-50"
              >
                Refresh Workspace
              </button>
              <button
                type="button"
                onClick={handleCheckWriteCapability}
                disabled={githubBusy || !editData}
                className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-200 hover:bg-amber-500/20 disabled:opacity-50"
              >
                Check Write Capability
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ── Alerts Tab ─────────────────────────────────────────────────────

const AlertsTab: React.FC = () => {
  const { alerts: apiAlerts, refreshAll } = useData();
  const [alerts, setAlerts] = useState<AlertConfig[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAlerts(apiAlerts);
  }, [apiAlerts]);

  const toggleAlert = async (id: string) => {
    const target = alerts.find(a => a.id === id);
    if (!target) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await analyticsService.updateAlert(id, { isActive: !target.isActive });
      setAlerts(alerts.map(a => a.id === id ? updated : a));
      await refreshAll();
    } catch (err: any) {
      setError(err?.message || 'Failed to update alert');
    } finally {
      setSaving(false);
    }
  };

  const deleteAlert = async (id: string) => {
    setSaving(true);
    setError(null);
    try {
      await analyticsService.deleteAlert(id);
      setAlerts(alerts.filter(a => a.id !== id));
      await refreshAll();
    } catch (err: any) {
      setError(err?.message || 'Failed to delete alert');
    } finally {
      setSaving(false);
    }
  };

  const createAlert = async () => {
    setSaving(true);
    setError(null);
    try {
      const created = await analyticsService.createAlert({
        name: `Alert ${alerts.length + 1}`,
        metric: 'total_tokens',
        operator: '>',
        threshold: 1000,
        isActive: true,
        scope: 'session',
      });
      setAlerts([created, ...alerts]);
      await refreshAll();
    } catch (err: any) {
      setError(err?.message || 'Failed to create alert');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <Surface tone="panel" padding="none" className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-panel-border p-6">
          <SectionHeading
            icon={Bell}
            title="Alert Configuration"
            description="Define conditions for system notifications."
          />
          <Button
            onClick={createAlert}
            disabled={saving}
            size="sm"
          >
            <Plus size={16} />
            New Alert
          </Button>
        </div>

        {error && (
          <AlertSurface intent="danger" className="rounded-none border-x-0 border-t-0">
            {error}
          </AlertSurface>
        )}

        <div className="divide-y divide-panel-border">
          {alerts.map((alert) => (
            <div key={alert.id} className="group flex items-center justify-between p-6 transition-colors hover:bg-hover/30">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-1">
                  <h4 className="font-medium text-panel-foreground">{alert.name}</h4>
                  <Badge tone={alert.isActive ? 'success' : 'muted'}>
                    {alert.isActive ? 'ACTIVE' : 'INACTIVE'}
                  </Badge>
                </div>

                <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
                  <Badge tone="info" mono>{alert.scope}</Badge>
                  <span>if</span>
                  <span className="font-mono text-panel-foreground">{alert.metric}</span>
                  <span>is</span>
                  <span className="font-bold text-panel-foreground">{alert.operator} {alert.threshold}</span>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <div className="flex flex-col items-end gap-1">
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      checked={alert.isActive}
                      onChange={() => void toggleAlert(alert.id)}
                    />
                    <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
                  </label>
                </div>
                <button
                  onClick={() => void deleteAlert(alert.id)}
                  className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-danger/10 hover:text-danger-foreground"
                >
                  <Trash2 size={18} />
                </button>
              </div>
            </div>
          ))}

          {alerts.length === 0 && (
            <div className="flex flex-col items-center p-8 text-center text-muted-foreground">
              <AlertCircle size={32} className="mb-2 opacity-50" />
              <p>No alerts configured.</p>
            </div>
          )}
        </div>
      </Surface>
    </div>
  );
};

// ── Main Settings Component ────────────────────────────────────────

export const Settings: React.FC = () => {
  const [activeTab, setActiveTab] = useState<SettingsTab>('projects');

  return (
    <div className="settings-legacy-theme mx-auto max-w-4xl space-y-6">
      <div>
        <h2 className="text-3xl font-bold text-app-foreground">Settings</h2>
        <p className="mt-2 text-muted-foreground">Manage projects, AI platforms, alerts, and application preferences.</p>
      </div>

      {/* Tab Bar */}
      <Surface tone="overlay" padding="sm" shadow="none" className="flex items-center gap-2">
        <TabButton tab="general" activeTab={activeTab} icon={SettingsIcon} label="General" onClick={setActiveTab} />
        <TabButton tab="projects" activeTab={activeTab} icon={FolderOpen} label="Projects" onClick={setActiveTab} />
        <TabButton tab="integrations" activeTab={activeTab} icon={GitBranch} label="Integrations" onClick={setActiveTab} />
        <TabButton tab="ai-platforms" activeTab={activeTab} icon={Bot} label="AI Platforms" onClick={setActiveTab} />
        <TabButton tab="alerts" activeTab={activeTab} icon={Bell} label="Alerts" onClick={setActiveTab} />
      </Surface>

      {/* Tab Content */}
      {activeTab === 'general' && <GeneralTab />}
      {activeTab === 'projects' && <ProjectsTab />}
      {activeTab === 'integrations' && <IntegrationsTab />}
      {activeTab === 'ai-platforms' && <AIPlatformsTab />}
      {activeTab === 'alerts' && <AlertsTab />}
    </div>
  );
};
