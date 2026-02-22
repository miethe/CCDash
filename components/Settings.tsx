import React, { useState, useEffect } from 'react';
import { Bell, Trash2, Plus, AlertCircle, Save, Settings as SettingsIcon, FolderOpen, ChevronDown, Check, RefreshCw, Monitor } from 'lucide-react';
import { useData } from '../contexts/DataContext';
import { AlertConfig, Project } from '../types';
import { analyticsService } from '../services/analytics';

type SettingsTab = 'general' | 'projects' | 'alerts';

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
      setEditData({ ...project });
      setDirtyPaths(false);
      setSaved(false);
      setError(null);
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
