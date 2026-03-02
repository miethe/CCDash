import React, { useEffect, useMemo, useState } from 'react';
import { Check, LayoutGrid, List, Pencil, Plus, Save, Trash2, X } from 'lucide-react';

type MatchScope = 'command' | 'args' | 'command_and_args';
type ViewMode = 'table' | 'cards';

interface SessionFieldMapping {
  id: string;
  label: string;
  source: 'command' | 'args' | 'phaseToken' | 'phases' | 'featurePath' | 'featureSlug' | 'requestId';
  enabled: boolean;
  joinWith?: string;
  includeEmpty?: boolean;
}

interface SessionMappingRule {
  id: string;
  mappingType: string;
  label: string;
  category: string;
  pattern: string;
  transcriptLabel: string;
  sessionTypeLabel?: string;
  matchScope?: MatchScope;
  fieldMappings?: SessionFieldMapping[];
  platforms?: string[];
  commandMarker?: string;
  enabled: boolean;
  priority: number;
  [key: string]: any;
}

interface SessionMappingDiagnosticsRow {
  id: string;
  label: string;
  mappingType: string;
  enabled: boolean;
  priority: number;
  platforms: string[];
  matchCount: number;
}

interface SessionMappingsDiagnostics {
  workflowCommands: string[];
  nonConsequentialCommands: string[];
  uncoveredWorkflowCommands: string[];
  neverMatchedMappings: string[];
  mappingMatches: SessionMappingDiagnosticsRow[];
  evaluatedSessions: number;
}

const KNOWN_TYPES = ['key_command', 'bash'];
const KNOWN_PLATFORMS = ['claude_code', 'codex'];

const defaultKeyFields = (): SessionFieldMapping[] => ([
  { id: 'related-command', label: 'Related Command', source: 'command', enabled: true },
  { id: 'related-phases', label: 'Related Phase(s)', source: 'phases', enabled: true, joinWith: ', ' },
]);

const normalizePlatforms = (values: unknown): string[] => {
  if (!Array.isArray(values)) return ['all'];
  const normalized = values
    .map(value => String(value || '').trim().toLowerCase().replace(/\s+/g, '_'))
    .filter(Boolean);
  if (normalized.length === 0) return ['all'];
  if (normalized.includes('all')) return ['all'];
  return Array.from(new Set(normalized));
};

const mappingAppliesToPlatform = (rule: SessionMappingRule, platform: string): boolean => {
  if (!platform || platform === 'all') return true;
  const platforms = normalizePlatforms(rule.platforms);
  if (platforms.includes('all')) return true;
  return platforms.includes(platform);
};

const emptyRule = (index: number, mappingType: string): SessionMappingRule => {
  const type = String(mappingType || 'bash').trim().toLowerCase() || 'bash';
  const isKey = type === 'key_command';
  return {
    id: `custom-${Date.now()}-${index}`,
    mappingType: type,
    label: isKey ? 'Key Command Type' : 'Custom Mapping',
    category: isKey ? 'key_command' : type,
    pattern: '',
    transcriptLabel: isKey ? 'Key Command' : 'Shell Command',
    sessionTypeLabel: isKey ? 'Custom Session Type' : '',
    matchScope: 'command',
    fieldMappings: isKey ? defaultKeyFields() : [],
    platforms: ['all'],
    commandMarker: '',
    enabled: true,
    priority: isKey ? 200 : 10,
  };
};

const fieldMappingsToText = (rule: SessionMappingRule): string =>
  JSON.stringify(rule.fieldMappings || [], null, 2);

const cloneRule = (rule: SessionMappingRule): SessionMappingRule => JSON.parse(JSON.stringify(rule));

export const SessionMappings: React.FC = () => {
  const [rules, setRules] = useState<SessionMappingRule[]>([]);
  const [diagnostics, setDiagnostics] = useState<SessionMappingsDiagnostics | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('table');
  const [activeType, setActiveType] = useState<string>('all');
  const [platformFilter, setPlatformFilter] = useState<string>('all');
  const [query, setQuery] = useState('');

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editorMode, setEditorMode] = useState<'create' | 'edit'>('create');
  const [editorDraft, setEditorDraft] = useState<SessionMappingRule | null>(null);
  const [editorFieldDraft, setEditorFieldDraft] = useState('[]');
  const [editorError, setEditorError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [mappingsRes, diagnosticsRes] = await Promise.all([
        fetch('/api/session-mappings'),
        fetch('/api/session-mappings/diagnostics'),
      ]);
      if (!mappingsRes.ok) {
        throw new Error(`Failed to load mappings (${mappingsRes.status})`);
      }
      const mappingsData = await mappingsRes.json();
      const loaded = Array.isArray(mappingsData) ? mappingsData : [];
      setRules(loaded);

      if (diagnosticsRes.ok) {
        const diagData = await diagnosticsRes.json();
        setDiagnostics(diagData as SessionMappingsDiagnostics);
      } else {
        setDiagnostics(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load mappings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const typeTabs = useMemo(() => {
    const fromRules = Array.from(new Set(rules.map(rule => String(rule.mappingType || '').trim().toLowerCase()).filter(Boolean)));
    const ordered = [
      ...KNOWN_TYPES.filter(type => fromRules.includes(type)),
      ...fromRules.filter(type => !KNOWN_TYPES.includes(type)).sort(),
    ];
    return ['all', ...ordered];
  }, [rules]);

  const platformOptions = useMemo(() => {
    const dynamic = new Set<string>();
    rules.forEach(rule => normalizePlatforms(rule.platforms).forEach(platform => dynamic.add(platform)));
    const sortedDynamic = Array.from(dynamic).filter(value => value !== 'all').sort();
    return ['all', ...Array.from(new Set([...KNOWN_PLATFORMS, ...sortedDynamic]))];
  }, [rules]);

  const sortedRules = useMemo(
    () => [...rules].sort((a, b) => {
      const priorityDelta = (b.priority || 0) - (a.priority || 0);
      if (priorityDelta !== 0) return priorityDelta;
      return String(a.label || '').localeCompare(String(b.label || ''));
    }),
    [rules],
  );

  const filteredRules = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sortedRules.filter(rule => {
      const type = String(rule.mappingType || '').trim().toLowerCase();
      if (activeType !== 'all' && type !== activeType) return false;
      if (!mappingAppliesToPlatform(rule, platformFilter)) return false;
      if (!q) return true;

      const searchable = [
        rule.id,
        rule.label,
        rule.category,
        rule.pattern,
        rule.transcriptLabel,
        rule.sessionTypeLabel,
        rule.commandMarker,
      ].join(' ').toLowerCase();
      return searchable.includes(q);
    });
  }, [activeType, platformFilter, query, sortedRules]);

  const summary = useMemo(() => {
    const total = rules.length;
    const enabled = rules.filter(rule => rule.enabled).length;
    const keyCommands = rules.filter(rule => String(rule.mappingType || '').toLowerCase() === 'key_command').length;
    const bash = rules.filter(rule => String(rule.mappingType || '').toLowerCase() === 'bash').length;
    return { total, enabled, keyCommands, bash };
  }, [rules]);

  const openCreateEditor = () => {
    const defaultType = activeType !== 'all' ? activeType : (typeTabs.find(type => type !== 'all') || 'bash');
    const draft = emptyRule(rules.length + 1, defaultType);
    setEditorMode('create');
    setEditorDraft(draft);
    setEditorFieldDraft(fieldMappingsToText(draft));
    setEditorError(null);
    setEditorOpen(true);
  };

  const openEditEditor = (rule: SessionMappingRule) => {
    const draft = cloneRule(rule);
    draft.platforms = normalizePlatforms(draft.platforms);
    setEditorMode('edit');
    setEditorDraft(draft);
    setEditorFieldDraft(fieldMappingsToText(draft));
    setEditorError(null);
    setEditorOpen(true);
  };

  const closeEditor = () => {
    setEditorOpen(false);
    setEditorDraft(null);
    setEditorFieldDraft('[]');
    setEditorError(null);
  };

  const removeRule = (id: string) => {
    setRules(prev => prev.filter(rule => rule.id !== id));
  };

  const updateEditorDraft = (patch: Partial<SessionMappingRule>) => {
    setEditorDraft(prev => (prev ? { ...prev, ...patch } : prev));
  };

  const toggleDraftPlatform = (platform: string) => {
    if (!editorDraft) return;
    const current = normalizePlatforms(editorDraft.platforms);
    if (platform === 'all') {
      updateEditorDraft({ platforms: ['all'] });
      return;
    }

    const withoutAll = current.filter(value => value !== 'all');
    const exists = withoutAll.includes(platform);
    const next = exists
      ? withoutAll.filter(value => value !== platform)
      : [...withoutAll, platform];
    updateEditorDraft({ platforms: next.length > 0 ? next : ['all'] });
  };

  const applyEditor = () => {
    if (!editorDraft) return;
    setEditorError(null);

    const normalizedType = String(editorDraft.mappingType || '').trim().toLowerCase() || 'bash';
    const nextDraft: SessionMappingRule = {
      ...editorDraft,
      mappingType: normalizedType,
      category: String(editorDraft.category || (normalizedType === 'key_command' ? 'key_command' : normalizedType)).trim() || normalizedType,
      platforms: normalizePlatforms(editorDraft.platforms),
      priority: Number(editorDraft.priority || 0),
      enabled: Boolean(editorDraft.enabled),
      pattern: String(editorDraft.pattern || '').trim(),
      label: String(editorDraft.label || '').trim(),
      transcriptLabel: String(editorDraft.transcriptLabel || '').trim(),
      commandMarker: String(editorDraft.commandMarker || '').trim(),
    };

    if (!nextDraft.label) {
      setEditorError('Label is required.');
      return;
    }
    if (!nextDraft.pattern) {
      setEditorError('Pattern is required.');
      return;
    }

    if (normalizedType === 'key_command') {
      try {
        const parsed = JSON.parse(editorFieldDraft);
        if (!Array.isArray(parsed)) {
          setEditorError('Field mappings must be a JSON array.');
          return;
        }
        nextDraft.sessionTypeLabel = String(nextDraft.sessionTypeLabel || nextDraft.label || '').trim();
        nextDraft.matchScope = (nextDraft.matchScope || 'command') as MatchScope;
        nextDraft.fieldMappings = parsed as SessionFieldMapping[];
      } catch {
        setEditorError('Field mappings JSON is invalid.');
        return;
      }
    } else {
      nextDraft.sessionTypeLabel = '';
      nextDraft.matchScope = 'command';
      nextDraft.fieldMappings = [];
      nextDraft.commandMarker = '';
    }

    if (editorMode === 'create') {
      setRules(prev => [...prev, nextDraft]);
    } else {
      setRules(prev => prev.map(rule => (rule.id === nextDraft.id ? nextDraft : rule)));
    }

    closeEditor();
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch('/api/session-mappings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mappings: rules }),
      });
      if (!res.ok) {
        throw new Error(`Failed to save mappings (${res.status})`);
      }
      const data = await res.json();
      setRules(Array.isArray(data) ? data : rules);
      const diagnosticsRes = await fetch('/api/session-mappings/diagnostics');
      if (diagnosticsRes.ok) {
        setDiagnostics(await diagnosticsRes.json());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save mappings');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-3xl font-bold text-slate-100">Session Mappings</h2>
            <p className="mt-2 text-sm text-slate-400">
              Unified mapping registry for command labeling and session-type detection across parser, API, and linking.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={openCreateEditor}
              className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-200 hover:bg-emerald-500/20"
            >
              <Plus size={14} />
              New Mapping
            </button>
            <button
              onClick={save}
              disabled={saving || loading}
              className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
            >
              <Save size={14} />
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-500">Total</p>
            <p className="mt-1 text-xl font-semibold text-slate-100">{summary.total}</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-500">Enabled</p>
            <p className="mt-1 text-xl font-semibold text-emerald-300">{summary.enabled}</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-500">Key Commands</p>
            <p className="mt-1 text-xl font-semibold text-indigo-300">{summary.keyCommands}</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-500">Bash Rules</p>
            <p className="mt-1 text-xl font-semibold text-cyan-300">{summary.bash}</p>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}

      {diagnostics && (
        <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">Coverage Diagnostics</h3>
            <p className="text-xs text-slate-500">Evaluated sessions: {diagnostics.evaluatedSessions}</p>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {diagnostics.workflowCommands.map(command => (
              <span key={command} className="rounded-md border border-indigo-500/30 bg-indigo-500/10 px-2 py-1 text-xs font-mono text-indigo-200">
                {command}
              </span>
            ))}
          </div>
          {diagnostics.uncoveredWorkflowCommands.length > 0 && (
            <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
              Uncovered workflow commands: {diagnostics.uncoveredWorkflowCommands.join(', ')}
            </div>
          )}
          {diagnostics.neverMatchedMappings.length > 0 && (
            <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/70 p-3">
              <p className="text-xs text-slate-400">Enabled mappings with no recent matches</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {diagnostics.neverMatchedMappings.map(mappingId => (
                  <span key={mappingId} className="rounded border border-slate-700 px-2 py-1 text-[11px] font-mono text-slate-300">
                    {mappingId}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
        <div className="flex flex-wrap items-center gap-2">
          {typeTabs.map(type => {
            const active = activeType === type;
            return (
              <button
                key={type}
                onClick={() => setActiveType(type)}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                  active
                    ? 'border-indigo-500/40 bg-indigo-500/15 text-indigo-200'
                    : 'border-slate-800 bg-slate-900 text-slate-300 hover:border-slate-700'
                }`}
              >
                {type}
              </button>
            );
          })}
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="Search id, label, pattern..."
              className="w-64 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500"
            />
            <select
              value={platformFilter}
              onChange={event => setPlatformFilter(event.target.value)}
              className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-200"
            >
              {platformOptions.map(platform => (
                <option key={platform} value={platform}>{platform}</option>
              ))}
            </select>
          </div>

          <div className="inline-flex items-center rounded-lg border border-slate-800 bg-slate-900 p-1">
            <button
              onClick={() => setViewMode('table')}
              className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs ${viewMode === 'table' ? 'bg-slate-800 text-slate-100' : 'text-slate-400'}`}
            >
              <List size={13} /> Table
            </button>
            <button
              onClick={() => setViewMode('cards')}
              className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs ${viewMode === 'cards' ? 'bg-slate-800 text-slate-100' : 'text-slate-400'}`}
            >
              <LayoutGrid size={13} /> Cards
            </button>
          </div>
        </div>

        {loading ? (
          <div className="mt-4 rounded-lg border border-slate-800 bg-slate-900/60 p-6 text-sm text-slate-400">Loading mappings...</div>
        ) : filteredRules.length === 0 ? (
          <div className="mt-4 rounded-lg border border-slate-800 bg-slate-900/60 p-6 text-sm text-slate-400">No mappings found for current filters.</div>
        ) : viewMode === 'table' ? (
          <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800">
            <table className="min-w-full divide-y divide-slate-800 text-sm">
              <thead className="bg-slate-900/90">
                <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
                  <th className="px-3 py-2">Mapping</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Platforms</th>
                  <th className="px-3 py-2">Pattern</th>
                  <th className="px-3 py-2">Priority</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 bg-slate-950/80">
                {filteredRules.map(rule => (
                  <tr key={rule.id} className="hover:bg-slate-900/60">
                    <td className="px-3 py-2 align-top">
                      <button onClick={() => openEditEditor(rule)} className="text-left">
                        <p className="font-medium text-slate-100">{rule.label}</p>
                        <p className="text-[11px] font-mono text-slate-500">{rule.id}</p>
                      </button>
                    </td>
                    <td className="px-3 py-2 align-top text-slate-300">{rule.mappingType}</td>
                    <td className="px-3 py-2 align-top">
                      <div className="flex flex-wrap gap-1">
                        {normalizePlatforms(rule.platforms).map(platform => (
                          <span key={`${rule.id}-${platform}`} className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] font-mono text-slate-300">
                            {platform}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-2 align-top font-mono text-[11px] text-cyan-200">{rule.pattern}</td>
                    <td className="px-3 py-2 align-top text-slate-300">{rule.priority}</td>
                    <td className="px-3 py-2 align-top">
                      <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs ${rule.enabled ? 'bg-emerald-500/15 text-emerald-300' : 'bg-slate-800 text-slate-500'}`}>
                        {rule.enabled ? <Check size={12} /> : <X size={12} />} {rule.enabled ? 'Enabled' : 'Disabled'}
                      </span>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => openEditEditor(rule)}
                          className="rounded border border-slate-700 p-1.5 text-slate-300 hover:border-indigo-500/40 hover:text-indigo-200"
                          title="Edit mapping"
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={() => removeRule(rule.id)}
                          className="rounded border border-slate-700 p-1.5 text-slate-300 hover:border-rose-500/40 hover:text-rose-200"
                          title="Remove mapping"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
            {filteredRules.map(rule => (
              <div key={rule.id} className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-base font-semibold text-slate-100">{rule.label}</p>
                    <p className="text-[11px] font-mono text-slate-500">{rule.id}</p>
                  </div>
                  <span className={`rounded px-2 py-0.5 text-xs ${rule.enabled ? 'bg-emerald-500/15 text-emerald-300' : 'bg-slate-800 text-slate-500'}`}>
                    {rule.enabled ? 'enabled' : 'disabled'}
                  </span>
                </div>

                <div className="mt-3 space-y-2 text-xs text-slate-300">
                  <p><span className="text-slate-500">Type:</span> {rule.mappingType}</p>
                  <p><span className="text-slate-500">Priority:</span> {rule.priority}</p>
                  <p className="font-mono text-cyan-200">{rule.pattern}</p>
                </div>

                <div className="mt-3 flex flex-wrap gap-1">
                  {normalizePlatforms(rule.platforms).map(platform => (
                    <span key={`${rule.id}-${platform}`} className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] font-mono text-slate-300">
                      {platform}
                    </span>
                  ))}
                </div>

                <div className="mt-4 flex items-center justify-end gap-1">
                  <button
                    onClick={() => openEditEditor(rule)}
                    className="rounded border border-slate-700 p-1.5 text-slate-300 hover:border-indigo-500/40 hover:text-indigo-200"
                    title="Edit mapping"
                  >
                    <Pencil size={13} />
                  </button>
                  <button
                    onClick={() => removeRule(rule.id)}
                    className="rounded border border-slate-700 p-1.5 text-slate-300 hover:border-rose-500/40 hover:text-rose-200"
                    title="Remove mapping"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {editorOpen && editorDraft && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={closeEditor}>
          <div className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-2xl border border-slate-700 bg-slate-950 p-5" onClick={event => event.stopPropagation()}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-xl font-semibold text-slate-100">{editorMode === 'create' ? 'Create Mapping' : 'Edit Mapping'}</h3>
                <p className="text-xs text-slate-500">Configure type, platform scope, and matching behavior from one form.</p>
              </div>
              <button onClick={closeEditor} className="rounded border border-slate-700 p-1.5 text-slate-300 hover:text-slate-100">
                <X size={14} />
              </button>
            </div>

            {editorError && (
              <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
                {editorError}
              </div>
            )}

            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
              <label className="text-xs text-slate-400">
                Label
                <input
                  value={editorDraft.label}
                  onChange={event => updateEditorDraft({ label: event.target.value })}
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-200"
                />
              </label>

              <label className="text-xs text-slate-400">
                Mapping Type
                <select
                  value={editorDraft.mappingType}
                  onChange={event => {
                    const nextType = event.target.value;
                    const base = emptyRule(rules.length + 1, nextType);
                    updateEditorDraft({
                      mappingType: nextType,
                      category: nextType === 'key_command' ? 'key_command' : nextType,
                      transcriptLabel: nextType === 'key_command' ? (editorDraft.transcriptLabel || 'Key Command') : (editorDraft.transcriptLabel || 'Shell Command'),
                      sessionTypeLabel: nextType === 'key_command' ? (editorDraft.sessionTypeLabel || editorDraft.label || 'Session Type') : '',
                      matchScope: nextType === 'key_command' ? (editorDraft.matchScope || 'command') : 'command',
                      fieldMappings: nextType === 'key_command' ? (editorDraft.fieldMappings && editorDraft.fieldMappings.length > 0 ? editorDraft.fieldMappings : base.fieldMappings) : [],
                      commandMarker: nextType === 'key_command' ? (editorDraft.commandMarker || '') : '',
                    });
                    setEditorFieldDraft(nextType === 'key_command' ? JSON.stringify(editorDraft.fieldMappings?.length ? editorDraft.fieldMappings : base.fieldMappings, null, 2) : '[]');
                  }}
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-200"
                >
                  {Array.from(new Set([...KNOWN_TYPES, ...typeTabs.filter(type => type !== 'all')])).map(type => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </label>

              <label className="text-xs text-slate-400">
                Priority
                <input
                  type="number"
                  value={editorDraft.priority}
                  onChange={event => updateEditorDraft({ priority: Number(event.target.value || 0) })}
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-200"
                />
              </label>

              <label className="text-xs text-slate-400 md:col-span-2 lg:col-span-3">
                Regex Pattern
                <input
                  value={editorDraft.pattern}
                  onChange={event => updateEditorDraft({ pattern: event.target.value })}
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-slate-200"
                />
              </label>

              <label className="text-xs text-slate-400">
                Category
                <input
                  value={editorDraft.category}
                  onChange={event => updateEditorDraft({ category: event.target.value })}
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-200"
                />
              </label>

              <label className="text-xs text-slate-400">
                Transcript Label
                <input
                  value={editorDraft.transcriptLabel}
                  onChange={event => updateEditorDraft({ transcriptLabel: event.target.value })}
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-200"
                />
              </label>

              <label className="flex items-center gap-2 self-end text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={editorDraft.enabled}
                  onChange={event => updateEditorDraft({ enabled: event.target.checked })}
                  className="h-4 w-4"
                />
                Enabled
              </label>
            </div>

            <div className="mt-4 rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Platform Scope</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {Array.from(new Set(['all', ...platformOptions.filter(platform => platform !== 'all')])).map(platform => {
                  const selected = normalizePlatforms(editorDraft.platforms).includes(platform);
                  return (
                    <button
                      key={platform}
                      onClick={() => toggleDraftPlatform(platform)}
                      className={`rounded border px-2 py-1 text-xs font-mono ${selected ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200' : 'border-slate-700 text-slate-400'}`}
                    >
                      {platform}
                    </button>
                  );
                })}
              </div>
            </div>

            {editorDraft.mappingType === 'key_command' && (
              <div className="mt-4 space-y-3 rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                  <label className="text-xs text-slate-400">
                    Session Type Label
                    <input
                      value={editorDraft.sessionTypeLabel || ''}
                      onChange={event => updateEditorDraft({ sessionTypeLabel: event.target.value })}
                      className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-200"
                    />
                  </label>
                  <label className="text-xs text-slate-400">
                    Match Scope
                    <select
                      value={editorDraft.matchScope || 'command'}
                      onChange={event => updateEditorDraft({ matchScope: event.target.value as MatchScope })}
                      className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-200"
                    >
                      <option value="command">command</option>
                      <option value="args">args</option>
                      <option value="command_and_args">command + args</option>
                    </select>
                  </label>
                  <label className="text-xs text-slate-400">
                    Command Marker
                    <input
                      value={editorDraft.commandMarker || ''}
                      onChange={event => updateEditorDraft({ commandMarker: event.target.value })}
                      placeholder="/dev:execute-phase"
                      className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-slate-200"
                    />
                  </label>
                </div>
                <label className="block text-xs text-slate-400">
                  Field Mappings (JSON)
                  <textarea
                    value={editorFieldDraft}
                    onChange={event => setEditorFieldDraft(event.target.value)}
                    className="mt-1 min-h-[140px] w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-[11px] text-slate-200"
                  />
                </label>
              </div>
            )}

            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                onClick={closeEditor}
                className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:text-slate-100"
              >
                Cancel
              </button>
              <button
                onClick={applyEditor}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-500"
              >
                <Check size={14} />
                {editorMode === 'create' ? 'Add Mapping' : 'Apply Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
