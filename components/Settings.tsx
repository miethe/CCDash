import React, { useState, useEffect } from 'react';
import { Bell, Trash2, Plus, AlertCircle, Save, Settings as SettingsIcon, FolderOpen, ChevronDown, Check, RefreshCw, Monitor, Copy, Download } from 'lucide-react';
import { useData } from '../contexts/DataContext';
import { AlertConfig, Project, ProjectTestPlatformConfig, TestSourceStatus } from '../types';
import { analyticsService } from '../services/analytics';
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

const GeneralTab: React.FC = () => (
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

      <div className="mt-6 p-4 bg-slate-800/40 rounded-lg border border-slate-700/50">
        <p className="text-xs text-slate-500">
          Additional preferences will be available in future updates, including notification sound settings,
          default views, and data retention policies.
        </p>
      </div>
    </div>
  </div>
);

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
  const [sourceStatus, setSourceStatus] = useState<TestSourceStatus[]>([]);
  const [testingActionError, setTestingActionError] = useState<string | null>(null);
  const [testingActionInfo, setTestingActionInfo] = useState<string | null>(null);
  const [testingBusy, setTestingBusy] = useState(false);
  const [generatedScript, setGeneratedScript] = useState('');
  const [generatedScriptName, setGeneratedScriptName] = useState('');
  const [scriptCopied, setScriptCopied] = useState(false);
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
      setEditData({ ...project, testConfig: ensureProjectTestConfig(project.testConfig) });
      setDirtyPaths(false);
      setSaved(false);
      setError(null);
      setSourceStatus([]);
      setTestingActionError(null);
      setTestingActionInfo(null);
      setGeneratedScript('');
      setGeneratedScriptName('');
      setScriptCopied(false);
    }
  }, [selectedProjectId, projects]);

  const selectedProject = projects.find(p => p.id === selectedProjectId);

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
    try {
      // updateProject already refreshes projects + sessions/documents/tasks/features
      await updateProject(editData.id, editData);
      setSaved(true);
      setDirtyPaths(false);
    } catch (e: any) {
      setError(e.message || 'Failed to save project');
    } finally {
      setSaving(false);
      savingRef.current = false;
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
