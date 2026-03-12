import React, { useState, useEffect } from 'react';
import { Bell, Trash2, Plus, AlertCircle, Save, Settings as SettingsIcon, FolderOpen, ChevronDown, Check, RefreshCw, Monitor, Copy, Download, Palette } from 'lucide-react';
import { useData } from '../contexts/DataContext';
import { useModelColors } from '../contexts/ModelColorsContext';
import { AlertConfig, PricingCatalogEntry, PricingCatalogUpsertRequest, Project, ProjectTestPlatformConfig, SkillMeatConfigValidationResponse, SkillMeatProbeResult, TestSourceStatus } from '../types';
import { analyticsService } from '../services/analytics';
import { DEFAULT_SKILLMEAT_FEATURE_FLAGS, defaultSkillMeatConfig, normalizeSkillMeatConfig } from '../services/agenticIntelligence';
import { pricingService } from '../services/pricing';
import { refreshSkillMeatCache, validateSkillMeatConfig } from '../services/skillmeat';
import { getTestSourcesStatus, syncTestSources } from '../services/testVisualizer';
import { ensureProjectTestConfig } from '../services/testConfigDefaults';
import { generateProjectTestSetupScript } from '../services/testSetupScript';

type SettingsTab = 'general' | 'projects' | 'alerts';

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

const SKILLMEAT_STATUS_STYLES: Record<SkillMeatProbeResult['state'], string> = {
  idle: 'border-slate-700 text-slate-400 bg-slate-900',
  success: 'border-emerald-500/30 text-emerald-300 bg-emerald-500/10',
  warning: 'border-amber-500/30 text-amber-300 bg-amber-500/10',
  error: 'border-rose-500/30 text-rose-300 bg-rose-500/10',
};

const SkillMeatStatusBadge: React.FC<{
  result?: SkillMeatProbeResult | null;
  fallback: string;
}> = ({ result, fallback }) => {
  const label = result?.message || fallback;
  const state = result?.state || 'idle';
  return (
    <span className={`inline-flex max-w-full items-center rounded-full border px-2 py-1 text-[11px] leading-none ${SKILLMEAT_STATUS_STYLES[state]}`}>
      <span className="truncate">{label}</span>
    </span>
  );
};

const DEFAULT_PRICING_PLATFORM = 'Claude Code';

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
  createdAt: '',
  updatedAt: '',
});

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
    className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${activeTab === tab
      ? 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/30'
      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
      }`}
  >
    <Icon size={16} />
    {label}
  </button>
);

// ── General Tab ────────────────────────────────────────────────────

const GeneralTab: React.FC = () => {
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
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="bg-indigo-500/10 p-2 rounded-lg text-indigo-400">
            <Monitor size={20} />
          </div>
          <div>
            <h3 className="font-semibold text-slate-100">General Preferences</h3>
            <p className="text-sm text-slate-400">Application-wide settings and appearance.</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-slate-400 mb-2">Theme</label>
            <select className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition-colors">
              <option>Dark (Default)</option>
              <option>Light</option>
              <option>System</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-400 mb-2">Polling Interval</label>
            <select className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition-colors">
              <option>30 seconds (Default)</option>
              <option>15 seconds</option>
              <option>60 seconds</option>
              <option>5 minutes</option>
            </select>
          </div>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
        <div className="flex items-center gap-3">
          <div className="bg-cyan-500/10 p-2 rounded-lg text-cyan-300">
            <Palette size={20} />
          </div>
          <div>
            <h3 className="font-semibold text-slate-100">Model Color Mapping</h3>
            <p className="text-sm text-slate-400">
              Configure color coding by model family or exact model. Model-level overrides take precedence.
            </p>
          </div>
        </div>

        {modelFacetsLoading && (
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm text-slate-400">
            Loading model options from ingested session data...
          </div>
        )}

        {!modelFacetsLoading && registry.models.length === 0 && (
          <div className="rounded-lg border border-amber-700/40 bg-amber-900/10 px-3 py-2 text-sm text-amber-200">
            No model facets are available yet. Run a session sync to populate model families and models.
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4 space-y-4">
            <h4 className="text-sm font-semibold text-slate-200">Family Override</h4>
            <div>
              <label className="block text-xs uppercase tracking-wide text-slate-500 mb-2">Model Family</label>
              <select
                value={selectedFamily}
                onChange={(event) => setSelectedFamily(event.target.value)}
                disabled={registry.families.length === 0}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-cyan-500 disabled:opacity-50"
              >
                {registry.families.map(family => (
                  <option key={family.label} value={family.label}>
                    {family.label} ({family.count})
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-3">
              <label className="text-xs uppercase tracking-wide text-slate-500">Color</label>
              <input
                type="color"
                value={familyColor}
                onChange={(event) => setFamilyColor(event.target.value)}
                className="h-9 w-14 rounded border border-slate-700 bg-slate-950"
              />
              <button
                onClick={() => selectedFamily && setFamilyColorOverride(selectedFamily, familyColor)}
                disabled={!selectedFamily}
                className="px-3 py-1.5 rounded-md text-xs font-medium border border-cyan-500/40 bg-cyan-500/15 text-cyan-200 disabled:opacity-40"
              >
                Save Family Color
              </button>
              <button
                onClick={() => selectedFamily && clearFamilyColorOverride(selectedFamily)}
                disabled={!selectedFamily || !getFamilyOverrideColor(selectedFamily)}
                className="px-3 py-1.5 rounded-md text-xs font-medium border border-slate-700 bg-slate-900 text-slate-300 disabled:opacity-40"
              >
                Clear
              </button>
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4 space-y-4">
            <h4 className="text-sm font-semibold text-slate-200">Model Override</h4>
            <div>
              <label className="block text-xs uppercase tracking-wide text-slate-500 mb-2">Model</label>
              <select
                value={selectedModel}
                onChange={(event) => setSelectedModel(event.target.value)}
                disabled={registry.models.length === 0}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-cyan-500 disabled:opacity-50"
              >
                {registry.models.map(model => (
                  <option key={model.raw} value={model.raw}>
                    {model.label} ({model.count})
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-3">
              <label className="text-xs uppercase tracking-wide text-slate-500">Color</label>
              <input
                type="color"
                value={modelColor}
                onChange={(event) => setModelColor(event.target.value)}
                className="h-9 w-14 rounded border border-slate-700 bg-slate-950"
              />
              <button
                onClick={() => selectedModel && setModelColorOverride(selectedModel, modelColor)}
                disabled={!selectedModel}
                className="px-3 py-1.5 rounded-md text-xs font-medium border border-cyan-500/40 bg-cyan-500/15 text-cyan-200 disabled:opacity-40"
              >
                Save Model Color
              </button>
              <button
                onClick={() => selectedModel && clearModelColorOverride(selectedModel)}
                disabled={!selectedModel || !getModelOverrideColor(selectedModel)}
                className="px-3 py-1.5 rounded-md text-xs font-medium border border-slate-700 bg-slate-900 text-slate-300 disabled:opacity-40"
              >
                Clear
              </button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
            <h4 className="text-xs uppercase tracking-wide text-slate-500 mb-3">Family Overrides</h4>
            <div className="space-y-2 max-h-44 overflow-y-auto pr-1">
              {familyOverrideRows.length === 0 && <div className="text-sm text-slate-500">None configured.</div>}
              {familyOverrideRows.map(([key, color]) => {
                const label = registry.familyLabelByKey[key] || key;
                return (
                  <div key={key} className="flex items-center justify-between gap-2 text-sm">
                    <span className="text-slate-300">{label}</span>
                    <div className="flex items-center gap-2">
                      <span className="h-5 w-5 rounded border border-slate-700" style={{ backgroundColor: color }} />
                      <span className="font-mono text-xs text-slate-400">{color}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
            <h4 className="text-xs uppercase tracking-wide text-slate-500 mb-3">Model Overrides</h4>
            <div className="space-y-2 max-h-44 overflow-y-auto pr-1">
              {modelOverrideRows.length === 0 && <div className="text-sm text-slate-500">None configured.</div>}
              {modelOverrideRows.map(([key, color]) => {
                const label = registry.modelByKey[key]?.label || key;
                return (
                  <div key={key} className="flex items-center justify-between gap-2 text-sm">
                    <span className="text-slate-300 truncate" title={label}>{label}</span>
                    <div className="flex items-center gap-2">
                      <span className="h-5 w-5 rounded border border-slate-700" style={{ backgroundColor: color }} />
                      <span className="font-mono text-xs text-slate-400">{color}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 text-xs text-slate-500">
          Colors are sourced from session model facets and applied across Analytics, Session cards, and other model badges.
        </div>
      </div>
    </div>
  );
};

// ── Projects Tab ───────────────────────────────────────────────────

const ProjectsTab: React.FC = () => {
  const { projects, activeProject, updateProject, switchProject } = useData();
  const [selectedProjectId, setSelectedProjectId] = useState<string>(activeProject?.id || '');
  const [editData, setEditData] = useState<Project | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [dirtyPaths, setDirtyPaths] = useState(false);
  const [sourceStatus, setSourceStatus] = useState<TestSourceStatus[]>([]);
  const [testingActionError, setTestingActionError] = useState<string | null>(null);
  const [testingActionInfo, setTestingActionInfo] = useState<string | null>(null);
  const [testingBusy, setTestingBusy] = useState(false);
  const [generatedScript, setGeneratedScript] = useState('');
  const [generatedScriptName, setGeneratedScriptName] = useState('');
  const [scriptCopied, setScriptCopied] = useState(false);
  const [skillMeatValidation, setSkillMeatValidation] = useState<SkillMeatConfigValidationResponse | null>(null);
  const [skillMeatValidationBusy, setSkillMeatValidationBusy] = useState(false);
  const [skillMeatValidationError, setSkillMeatValidationError] = useState<string | null>(null);
  const [skillMeatRefreshMessage, setSkillMeatRefreshMessage] = useState<string | null>(null);
  const [skillMeatRefreshError, setSkillMeatRefreshError] = useState<string | null>(null);
  const [pricingPlatform, setPricingPlatform] = useState(DEFAULT_PRICING_PLATFORM);
  const [pricingEntries, setPricingEntries] = useState<PricingCatalogEntry[]>([]);
  const [pricingLoading, setPricingLoading] = useState(false);
  const [pricingError, setPricingError] = useState<string | null>(null);
  const [pricingMessage, setPricingMessage] = useState<string | null>(null);
  const [pricingSavingKey, setPricingSavingKey] = useState<string>('');
  const savingRef = React.useRef(false);

  // Initialize selection
  useEffect(() => {
    if (!selectedProjectId && activeProject) {
      setSelectedProjectId(activeProject.id);
    }
  }, [activeProject, selectedProjectId]);

  // Load project data when selection changes
  useEffect(() => {
    // Skip resetting state if we're in the middle of a save
    // (updateProject triggers refreshProjects which updates the projects array)
    if (savingRef.current) return;

    const project = projects.find(p => p.id === selectedProjectId);
    if (project) {
      setEditData({
        ...project,
        testConfig: ensureProjectTestConfig(project.testConfig),
        skillMeat: normalizeSkillMeatConfig(project),
      });
      setDirtyPaths(false);
      setSaved(false);
      setError(null);
      setSourceStatus([]);
      setTestingActionError(null);
      setTestingActionInfo(null);
      setGeneratedScript('');
      setGeneratedScriptName('');
      setScriptCopied(false);
      setSkillMeatValidation(null);
      setSkillMeatValidationError(null);
      setSkillMeatRefreshMessage(null);
      setSkillMeatRefreshError(null);
      setPricingError(null);
      setPricingMessage(null);
    }
  }, [selectedProjectId, projects]);

  const selectedProject = projects.find(p => p.id === selectedProjectId);
  const pricingEnabled = Boolean(activeProject && selectedProjectId === activeProject.id);

  useEffect(() => {
    if (!pricingEnabled) {
      setPricingEntries([]);
      return;
    }
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
  }, [pricingEnabled, pricingPlatform]);

  const handleFieldChange = (field: keyof Project, value: string) => {
    if (!editData) return;
    setEditData({ ...editData, [field]: value });
    setSaved(false);
    // Track if directory paths changed
    if (['path', 'planDocsPath', 'sessionsPath', 'progressPath'].includes(field)) {
      const orig = selectedProject;
      if (orig && value !== (orig as any)[field]) {
        setDirtyPaths(true);
      }
    }
  };

  const updateTestConfig = (updater: (prev: Project['testConfig']) => Project['testConfig']) => {
    if (!editData) return;
    const nextConfig = updater(ensureProjectTestConfig(editData.testConfig));
    setEditData({ ...editData, testConfig: nextConfig });
    setSaved(false);
  };

  const updateSkillMeatConfig = (updater: (prev: Project['skillMeat']) => Project['skillMeat']) => {
    if (!editData) return;
    const nextConfig = updater(editData.skillMeat || DEFAULT_SKILLMEAT_CONFIG);
    setEditData({ ...editData, skillMeat: nextConfig });
    setSaved(false);
    setSkillMeatValidation(null);
    setSkillMeatValidationError(null);
  };

  const handleValidateSkillMeat = async () => {
    if (!editData) return;
    setSkillMeatValidationBusy(true);
    setSkillMeatValidationError(null);
    try {
      const response = await validateSkillMeatConfig(editData.skillMeat || DEFAULT_SKILLMEAT_CONFIG);
      setSkillMeatValidation(response);
    } catch (e: any) {
      setSkillMeatValidationError(e?.message || 'Failed to validate SkillMeat configuration');
    } finally {
      setSkillMeatValidationBusy(false);
    }
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
      const synced = Number((result.stats as any)?.synced || 0);
      const metrics = Number((result.stats as any)?.metrics || 0);
      const errors = Number((result.stats as any)?.errors || 0);
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
    setSkillMeatRefreshMessage(null);
    setSkillMeatRefreshError(null);
    try {
      // updateProject already refreshes projects + sessions/documents/tasks/features
      await updateProject(editData.id, editData);
      setSaved(true);
      setDirtyPaths(false);

      const skillMeatConfig = normalizeSkillMeatConfig(editData);
      if (skillMeatConfig.enabled && skillMeatConfig.baseUrl.trim()) {
        try {
          const refreshResult = await refreshSkillMeatCache(editData.id);
          const syncResult = refreshResult.sync;
          const backfillResult = refreshResult.backfill;
          const warningCount = (syncResult.warnings?.length || 0) + (backfillResult?.warnings?.length || 0);
          setSkillMeatRefreshMessage(
            `SkillMeat refresh complete: ${syncResult.totalDefinitions} definitions synced, ${backfillResult?.observationsStored ?? 0} observations rebuilt${warningCount > 0 ? `, ${warningCount} warning${warningCount === 1 ? '' : 's'}` : ''}.`,
          );
        } catch (skillMeatError: any) {
          setSkillMeatRefreshError(skillMeatError?.message || 'Project saved, but SkillMeat refresh failed.');
        }
      }
    } catch (e: any) {
      setError(e.message || 'Failed to save project');
    } finally {
      setSaving(false);
      savingRef.current = false;
    }
  };

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
    sourceType: entry.sourceType || 'manual',
    sourceUpdatedAt: entry.sourceUpdatedAt || '',
    overrideLocked: entry.overrideLocked,
    syncStatus: entry.syncStatus || 'manual',
    syncError: entry.syncError || '',
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
      setPricingMessage(`Saved pricing for ${entry.modelId || 'platform default'}.`);
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

  return (
    <div className="space-y-6">
      {/* Project Selector */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="bg-indigo-500/10 p-2 rounded-lg text-indigo-400">
              <FolderOpen size={20} />
            </div>
            <div>
              <h3 className="font-semibold text-slate-100">Project Configuration</h3>
              <p className="text-sm text-slate-400">Select a project to view and edit its settings.</p>
            </div>
          </div>

          {dirtyPaths && (
            <div className="flex items-center gap-2 text-amber-400 text-xs bg-amber-500/10 px-3 py-1.5 rounded-lg border border-amber-500/20">
              <RefreshCw size={12} />
              Directory changes will trigger a rescan on save
            </div>
          )}
        </div>

        {/* Custom Dropdown */}
        <div className="relative mb-6">
          <label className="block text-sm font-medium text-slate-400 mb-2">Select Project</label>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="w-full flex items-center justify-between bg-slate-950 border border-slate-700 rounded-lg px-4 py-3 text-left hover:border-slate-600 focus:outline-none focus:border-indigo-500 transition-colors"
          >
            <div className="flex flex-col">
              <span className="text-sm font-medium text-slate-200">
                {selectedProject?.name || 'Select a project...'}
              </span>
              {selectedProject && (
                <span className="text-xs text-slate-500 mt-0.5 font-mono truncate">
                  {selectedProject.path}
                </span>
              )}
            </div>
            <ChevronDown size={16} className={`text-slate-400 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
          </button>

          {dropdownOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setDropdownOpen(false)} />
              <div className="absolute top-full left-0 right-0 mt-1 bg-slate-800 rounded-lg shadow-xl border border-slate-700 z-50 overflow-hidden max-h-72 overflow-y-auto">
                {projects.map(p => (
                  <button
                    key={p.id}
                    onClick={() => {
                      setSelectedProjectId(p.id);
                      setDropdownOpen(false);
                    }}
                    className="w-full text-left px-4 py-3 hover:bg-slate-700 flex items-center justify-between transition-colors border-b border-slate-700/50 last:border-0"
                  >
                    <div className="flex flex-col">
                      <span className="text-sm text-slate-200 font-medium">{p.name}</span>
                      <span className="text-xs text-slate-500 font-mono truncate">{p.path}</span>
                    </div>
                    {selectedProjectId === p.id && (
                      <Check size={14} className="text-indigo-400 shrink-0 ml-2" />
                    )}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-900/30 border border-red-700/50 text-red-300 rounded-lg text-sm">
            {error}
          </div>
        )}

        {saved && !error && (
          <div className="mb-4 p-3 bg-emerald-900/30 border border-emerald-700/50 text-emerald-300 rounded-lg text-sm flex items-center gap-2">
            <Check size={14} />
            Project saved successfully{dirtyPaths ? ' — data rescanned' : ''}.
          </div>
        )}

        {skillMeatRefreshMessage && !error && (
          <div className="mb-4 p-3 bg-sky-900/30 border border-sky-700/50 text-sky-200 rounded-lg text-sm">
            {skillMeatRefreshMessage}
          </div>
        )}

        {skillMeatRefreshError && !error && (
          <div className="mb-4 p-3 bg-amber-900/30 border border-amber-700/50 text-amber-200 rounded-lg text-sm">
            {skillMeatRefreshError}
          </div>
        )}

        {/* Edit Form */}
        {editData && (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-5">
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">Project Name</label>
                <input
                  type="text"
                  value={editData.name}
                  onChange={e => handleFieldChange('name', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition-colors"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">Repository URL</label>
                <input
                  type="url"
                  value={editData.repoUrl}
                  onChange={e => handleFieldChange('repoUrl', e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition-colors"
                  placeholder="https://github.com/..."
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Description</label>
              <textarea
                value={editData.description}
                onChange={e => handleFieldChange('description', e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 transition-colors h-20 resize-none"
              />
            </div>

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
                  <h4 className="text-sm font-semibold text-slate-300 mb-1">Pricing Catalog</h4>
                  <p className="text-xs text-slate-500">
                    Configure project-scoped platform defaults, model overrides, sync state, and freshness metadata for display-cost recalculation.
                  </p>
                </div>
                {!pricingEnabled && activeProject && selectedProjectId !== activeProject.id && (
                  <button
                    type="button"
                    onClick={() => void switchProject(selectedProjectId)}
                    className="inline-flex items-center gap-2 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-3 py-2 text-xs font-medium text-indigo-200"
                  >
                    <RefreshCw size={12} />
                    Switch Active Project
                  </button>
                )}
              </div>

              {!pricingEnabled ? (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                  Pricing catalog edits are scoped to the active project. Select the active project above or switch it before editing pricing.
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <label className="block">
                      <span className="mb-1 block text-xs text-slate-400">Platform</span>
                      <select
                        value={pricingPlatform}
                        onChange={e => setPricingPlatform(e.target.value)}
                        className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                      >
                        <option value={DEFAULT_PRICING_PLATFORM}>{DEFAULT_PRICING_PLATFORM}</option>
                      </select>
                    </label>
                    <button
                      type="button"
                      onClick={handleSyncPricing}
                      disabled={pricingSavingKey === 'sync'}
                      className="mt-5 inline-flex items-center gap-2 rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-xs font-medium text-cyan-200 disabled:opacity-50"
                    >
                      <RefreshCw size={12} className={pricingSavingKey === 'sync' ? 'animate-spin' : ''} />
                      {pricingSavingKey === 'sync' ? 'Syncing...' : 'Sync Platform Prices'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setPricingEntries(prev => [...prev, createPricingDraft(pricingPlatform)])}
                      className="mt-5 inline-flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-200"
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
                  {pricingLoading ? (
                    <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm text-slate-400">
                      Loading pricing catalog...
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {pricingEntries.map((entry, index) => {
                        const rowKey = `${entry.modelId || 'platform-default'}:${index}`;
                        const savingRow = pricingSavingKey === rowKey;
                        return (
                          <div key={rowKey} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-3">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div>
                                <div className="text-sm font-medium text-slate-200">{entry.modelId || 'Platform Default'}</div>
                                <div className="text-xs text-slate-500">
                                  {entry.sourceType || 'manual'} · {entry.syncStatus || 'manual'} · updated {entry.sourceUpdatedAt || 'unknown'}
                                </div>
                              </div>
                              <label className="inline-flex items-center gap-2 text-xs text-slate-300">
                                <input
                                  type="checkbox"
                                  checked={Boolean(entry.overrideLocked)}
                                  onChange={e => updatePricingEntry(index, current => ({ ...current, overrideLocked: e.target.checked }))}
                                  className="h-4 w-4"
                                />
                                Lock Override
                              </label>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-4 gap-3">
                              <label className="block">
                                <span className="mb-1 block text-xs text-slate-400">Model ID</span>
                                <input
                                  type="text"
                                  value={entry.modelId || ''}
                                  onChange={e => updatePricingEntry(index, current => ({ ...current, modelId: e.target.value }))}
                                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                                  placeholder="claude-sonnet-4-5"
                                />
                              </label>
                              <label className="block">
                                <span className="mb-1 block text-xs text-slate-400">Context Window</span>
                                <input
                                  type="number"
                                  value={entry.contextWindowSize ?? ''}
                                  onChange={e => updatePricingEntry(index, current => ({ ...current, contextWindowSize: parseOptionalNumber(e.target.value) }))}
                                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                                />
                              </label>
                              <label className="block">
                                <span className="mb-1 block text-xs text-slate-400">Input / 1M</span>
                                <input
                                  type="number"
                                  step="0.0001"
                                  value={entry.inputCostPerMillion ?? ''}
                                  onChange={e => updatePricingEntry(index, current => ({ ...current, inputCostPerMillion: parseOptionalNumber(e.target.value) }))}
                                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                                />
                              </label>
                              <label className="block">
                                <span className="mb-1 block text-xs text-slate-400">Output / 1M</span>
                                <input
                                  type="number"
                                  step="0.0001"
                                  value={entry.outputCostPerMillion ?? ''}
                                  onChange={e => updatePricingEntry(index, current => ({ ...current, outputCostPerMillion: parseOptionalNumber(e.target.value) }))}
                                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                                />
                              </label>
                              <label className="block">
                                <span className="mb-1 block text-xs text-slate-400">Cache Create / 1M</span>
                                <input
                                  type="number"
                                  step="0.0001"
                                  value={entry.cacheCreationCostPerMillion ?? ''}
                                  onChange={e => updatePricingEntry(index, current => ({ ...current, cacheCreationCostPerMillion: parseOptionalNumber(e.target.value) }))}
                                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                                />
                              </label>
                              <label className="block">
                                <span className="mb-1 block text-xs text-slate-400">Cache Read / 1M</span>
                                <input
                                  type="number"
                                  step="0.0001"
                                  value={entry.cacheReadCostPerMillion ?? ''}
                                  onChange={e => updatePricingEntry(index, current => ({ ...current, cacheReadCostPerMillion: parseOptionalNumber(e.target.value) }))}
                                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                                />
                              </label>
                              <label className="block">
                                <span className="mb-1 block text-xs text-slate-400">Fast Multiplier</span>
                                <input
                                  type="number"
                                  step="0.01"
                                  value={entry.speedMultiplierFast ?? ''}
                                  onChange={e => updatePricingEntry(index, current => ({ ...current, speedMultiplierFast: parseOptionalNumber(e.target.value) }))}
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
                              <button
                                type="button"
                                onClick={() => void handleResetPricingEntry(entry, index)}
                                disabled={savingRow}
                                className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-300 disabled:opacity-50"
                              >
                                Reset
                              </button>
                              <button
                                type="button"
                                onClick={() => void handleSavePricingEntry(entry, index)}
                                disabled={savingRow}
                                className="inline-flex items-center gap-2 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-3 py-2 text-xs font-medium text-indigo-200 disabled:opacity-50"
                              >
                                <Save size={12} />
                                {savingRow ? 'Saving...' : 'Save Pricing'}
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="border-t border-slate-800 pt-5">
              <h4 className="text-sm font-semibold text-slate-300 mb-4 flex items-center gap-2">
                <FolderOpen size={14} className="text-indigo-400" />
                Directory Paths
              </h4>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">Project Root Path</label>
                  <input
                    type="text"
                    value={editData.path}
                    onChange={e => handleFieldChange('path', e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500 transition-colors"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">Plan Documents Path</label>
                  <input
                    type="text"
                    value={editData.planDocsPath}
                    onChange={e => handleFieldChange('planDocsPath', e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500 transition-colors"
                    placeholder="docs/project_plans/"
                  />
                  <p className="text-xs text-slate-500 mt-1">Relative to project root</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Sessions Path
                    <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 font-normal">CLAUDE</span>
                  </label>
                  <input
                    type="text"
                    value={editData.sessionsPath}
                    onChange={e => handleFieldChange('sessionsPath', e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500 transition-colors"
                    placeholder="~/.claude/projects/<hash>/"
                  />
                  <p className="text-xs text-slate-500 mt-1">Absolute path to the directory containing Claude session JSONL files. Leave empty to use default (~/.claude/sessions).</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">Progress/Tasks Path</label>
                  <input
                    type="text"
                    value={editData.progressPath}
                    onChange={e => handleFieldChange('progressPath', e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500 transition-colors"
                    placeholder="progress"
                  />
                  <p className="text-xs text-slate-500 mt-1">Relative to project root</p>
                </div>
              </div>
            </div>

            <div className="border-t border-slate-800 pt-5 space-y-4">
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

              <label className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                <span className="text-sm text-slate-200">Enable SkillMeat integration</span>
                <input
                  type="checkbox"
                  checked={Boolean(editData.skillMeat?.enabled)}
                  onChange={e => updateSkillMeatConfig(prev => ({ ...prev, enabled: e.target.checked }))}
                  className="h-4 w-4"
                />
              </label>

              {skillMeatValidationError && (
                <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                  {skillMeatValidationError}
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <label className="block">
                  <span className="mb-1 flex items-center justify-between gap-2 text-xs text-slate-400">
                    <span>Base URL</span>
                    <SkillMeatStatusBadge
                      result={skillMeatValidation?.baseUrl}
                      fallback="Unchecked"
                    />
                  </span>
                  <input
                    type="url"
                    value={editData.skillMeat?.baseUrl || ''}
                    onChange={e => updateSkillMeatConfig(prev => ({ ...prev, baseUrl: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    placeholder="http://127.0.0.1:8080"
                  />
                </label>
                <label className="block">
                  <span className="block text-xs text-slate-400 mb-1">Request Timeout (seconds)</span>
                  <input
                    type="number"
                    min={1}
                    max={120}
                    step={0.5}
                    value={editData.skillMeat?.requestTimeoutSeconds ?? 5}
                    onChange={e => updateSkillMeatConfig(prev => ({ ...prev, requestTimeoutSeconds: Number(e.target.value || 5) }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 flex items-center justify-between gap-2 text-xs text-slate-400">
                    <span>SkillMeat Project ID</span>
                    <SkillMeatStatusBadge
                      result={skillMeatValidation?.projectMapping}
                      fallback="Unchecked"
                    />
                  </span>
                  <input
                    type="text"
                    value={editData.skillMeat?.projectId || ''}
                    onChange={e => updateSkillMeatConfig(prev => ({ ...prev, projectId: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                    placeholder="project UUID from SkillMeat"
                  />
                  <p className="mt-1 text-xs text-slate-500">Use the exact SkillMeat project ID, typically the UUID shown in the project details URL. Project names and local filesystem paths are not used here.</p>
                </label>
                <label className="block">
                  <span className="block text-xs text-slate-400 mb-1">Collection ID (optional)</span>
                  <input
                    type="text"
                    value={editData.skillMeat?.collectionId || ''}
                    onChange={e => updateSkillMeatConfig(prev => ({ ...prev, collectionId: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
                    placeholder="default"
                  />
                  <p className="mt-1 text-xs text-slate-500">Use this when bundle or artifact context should be scoped to a specific collection.</p>
                </label>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <label className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <div>
                    <span className="block text-sm text-slate-200">AAA enabled</span>
                    <span className="block text-xs text-slate-500">Turn this on for auth-protected SkillMeat instances.</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={Boolean(editData.skillMeat?.aaaEnabled)}
                    onChange={e => updateSkillMeatConfig(prev => ({ ...prev, aaaEnabled: e.target.checked }))}
                    className="h-4 w-4"
                  />
                </label>
                <div className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <span className="mb-2 flex items-center justify-between gap-2 text-xs text-slate-400">
                    <span>Auth Status</span>
                    <SkillMeatStatusBadge
                      result={skillMeatValidation?.auth}
                      fallback="Unchecked"
                    />
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
                    onChange={e => updateSkillMeatConfig(prev => ({ ...prev, apiKey: e.target.value }))}
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
                <label className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <div>
                    <span className="block text-sm text-slate-200">Recommended Stack UI</span>
                    <span className="block text-xs text-slate-500">Show evidence-backed stack suggestions in `/execution`.</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={editData.skillMeat?.featureFlags?.stackRecommendationsEnabled ?? true}
                    onChange={e => updateSkillMeatConfig(prev => ({
                      ...prev,
                      featureFlags: {
                        ...DEFAULT_SKILLMEAT_FEATURE_FLAGS,
                        ...(prev.featureFlags || {}),
                        stackRecommendationsEnabled: e.target.checked,
                      },
                    }))}
                    className="h-4 w-4"
                  />
                </label>
                <label className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <div>
                    <span className="block text-sm text-slate-200">Usage Attribution</span>
                    <span className="block text-xs text-slate-500">Enable attribution views in `/analytics` and session analytics drill-downs.</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={editData.skillMeat?.featureFlags?.usageAttributionEnabled ?? true}
                    onChange={e => updateSkillMeatConfig(prev => ({
                      ...prev,
                      featureFlags: {
                        ...DEFAULT_SKILLMEAT_FEATURE_FLAGS,
                        ...(prev.featureFlags || {}),
                        usageAttributionEnabled: e.target.checked,
                      },
                    }))}
                    className="h-4 w-4"
                  />
                </label>
                <label className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <div>
                    <span className="block text-sm text-slate-200">Session Block Insights</span>
                    <span className="block text-xs text-slate-500">Enable long-session burn-rate and billing-block views in Session Inspector analytics.</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={editData.skillMeat?.featureFlags?.sessionBlockInsightsEnabled ?? true}
                    onChange={e => updateSkillMeatConfig(prev => ({
                      ...prev,
                      featureFlags: {
                        ...DEFAULT_SKILLMEAT_FEATURE_FLAGS,
                        ...(prev.featureFlags || {}),
                        sessionBlockInsightsEnabled: e.target.checked,
                      },
                    }))}
                    className="h-4 w-4"
                  />
                </label>
                <label className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5">
                  <div>
                    <span className="block text-sm text-slate-200">Workflow Effectiveness</span>
                    <span className="block text-xs text-slate-500">Enable workflow intelligence analytics in `/analytics` and `/execution`.</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={editData.skillMeat?.featureFlags?.workflowAnalyticsEnabled ?? true}
                    onChange={e => updateSkillMeatConfig(prev => ({
                      ...prev,
                      featureFlags: {
                        ...DEFAULT_SKILLMEAT_FEATURE_FLAGS,
                        ...(prev.featureFlags || {}),
                        workflowAnalyticsEnabled: e.target.checked,
                      },
                    }))}
                    className="h-4 w-4"
                  />
                </label>
              </div>
            </div>

            <div className="border-t border-slate-800 pt-5 space-y-5">
              <h4 className="text-sm font-semibold text-slate-300 mb-1">Testing Configuration</h4>
              <p className="text-xs text-slate-500">
                Configure test platforms, result directories, and feature flags for this project.
              </p>

              <div className="grid grid-cols-2 gap-4">
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
                      checked={(editData.testConfig?.flags as any)?.[key] ?? false}
                      onChange={e => updateFlag(key as keyof Project['testConfig']['flags'], e.target.checked)}
                      className="h-4 w-4"
                    />
                  </label>
                ))}
              </div>

              <div className="grid grid-cols-3 gap-4">
                <label className="block">
                  <span className="block text-xs text-slate-400 mb-1">Auto Sync on Startup</span>
                  <input
                    type="checkbox"
                    checked={Boolean(editData.testConfig?.autoSyncOnStartup)}
                    onChange={e => updateTestConfig(prev => ({ ...prev, autoSyncOnStartup: e.target.checked }))}
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
                    onChange={e => updateTestConfig(prev => ({ ...prev, maxFilesPerScan: Number(e.target.value || 500) }))}
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
                    onChange={e => updateTestConfig(prev => ({ ...prev, maxParseConcurrency: Number(e.target.value || 4) }))}
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
                            onChange={e => updatePlatform(platform.id, prev => ({ ...prev, enabled: e.target.checked }))}
                            className="h-4 w-4"
                          />
                        </label>
                        <label className="text-xs text-slate-300 flex items-center gap-2">
                          Watch
                          <input
                            type="checkbox"
                            checked={platform.watch}
                            onChange={e => updatePlatform(platform.id, prev => ({ ...prev, watch: e.target.checked }))}
                            className="h-4 w-4"
                          />
                        </label>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <label>
                        <span className="block text-xs text-slate-400 mb-1">Results Dir</span>
                        <input
                          type="text"
                          value={platform.resultsDir}
                          onChange={e => updatePlatform(platform.id, prev => ({ ...prev, resultsDir: e.target.value }))}
                          className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 font-mono"
                        />
                      </label>
                      <label>
                        <span className="block text-xs text-slate-400 mb-1">Patterns (comma separated)</span>
                        <input
                          type="text"
                          value={platform.patterns.join(', ')}
                          onChange={e => updatePlatform(platform.id, prev => ({
                            ...prev,
                            patterns: e.target.value.split(',').map(item => item.trim()).filter(Boolean),
                          }))}
                          className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 font-mono"
                        />
                      </label>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-3">
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

              <div className="rounded-lg border border-slate-700 bg-slate-950 p-3">
                <p className="text-xs font-semibold text-slate-300 mb-2">SkillMeat Setup Instructions</p>
                <p className="text-xs text-slate-500 mb-2">
                  Configure your SkillMeat project to emit machine-readable test artifacts:
                </p>
                <div className="space-y-1.5">
                  {SKILLMEAT_SETUP_COMMANDS.map(cmd => (
                    <code key={cmd} className="block rounded bg-slate-900 px-2 py-1 text-[11px] text-indigo-200 overflow-x-auto">{cmd}</code>
                  ))}
                </div>
              </div>
            </div>

            {/* Save Button */}
            <div className="flex justify-end pt-4 border-t border-slate-800">
              <button
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
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="p-6 border-b border-slate-800 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="bg-indigo-500/10 p-2 rounded-lg text-indigo-400">
              <Bell size={20} />
            </div>
            <div>
              <h3 className="font-semibold text-slate-100">Alert Configuration</h3>
              <p className="text-sm text-slate-400">Define conditions for system notifications.</p>
            </div>
          </div>
          <button
            onClick={createAlert}
            disabled={saving}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            <Plus size={16} />
            New Alert
          </button>
        </div>

        {error && (
          <div className="px-6 py-3 bg-red-900/30 border-b border-red-700/50 text-red-300 text-sm">
            {error}
          </div>
        )}

        <div className="divide-y divide-slate-800">
          {alerts.map((alert) => (
            <div key={alert.id} className="p-6 flex items-center justify-between group hover:bg-slate-800/30 transition-colors">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-1">
                  <h4 className="font-medium text-slate-200">{alert.name}</h4>
                  <span className={`text-[10px] px-2 py-0.5 rounded border ${alert.isActive
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    : 'bg-slate-800 text-slate-500 border-slate-700'
                    }`}>
                    {alert.isActive ? 'ACTIVE' : 'INACTIVE'}
                  </span>
                </div>

                <div className="flex items-center gap-2 text-sm text-slate-400 mt-2">
                  <span className="font-mono text-indigo-400 bg-indigo-500/10 px-1.5 rounded">{alert.scope}</span>
                  <span>if</span>
                  <span className="font-mono text-slate-300">{alert.metric}</span>
                  <span>is</span>
                  <span className="font-bold text-slate-200">{alert.operator} {alert.threshold}</span>
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
                  className="p-2 text-slate-500 hover:text-rose-500 hover:bg-rose-500/10 rounded-lg transition-colors"
                >
                  <Trash2 size={18} />
                </button>
              </div>
            </div>
          ))}

          {alerts.length === 0 && (
            <div className="p-8 text-center text-slate-500 flex flex-col items-center">
              <AlertCircle size={32} className="mb-2 opacity-50" />
              <p>No alerts configured.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ── Main Settings Component ────────────────────────────────────────

export const Settings: React.FC = () => {
  const [activeTab, setActiveTab] = useState<SettingsTab>('projects');

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h2 className="text-3xl font-bold text-slate-100">Settings</h2>
        <p className="text-slate-400 mt-2">Manage projects, alerts, and application preferences.</p>
      </div>

      {/* Tab Bar */}
      <div className="flex items-center gap-2 p-1 bg-slate-900/50 border border-slate-800 rounded-xl">
        <TabButton tab="general" activeTab={activeTab} icon={SettingsIcon} label="General" onClick={setActiveTab} />
        <TabButton tab="projects" activeTab={activeTab} icon={FolderOpen} label="Projects" onClick={setActiveTab} />
        <TabButton tab="alerts" activeTab={activeTab} icon={Bell} label="Alerts" onClick={setActiveTab} />
      </div>

      {/* Tab Content */}
      {activeTab === 'general' && <GeneralTab />}
      {activeTab === 'projects' && <ProjectsTab />}
      {activeTab === 'alerts' && <AlertsTab />}
    </div>
  );
};
