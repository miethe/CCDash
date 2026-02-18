import React, { useEffect, useMemo, useState } from 'react';
import { Plus, Save, Trash2 } from 'lucide-react';

type MappingType = 'bash' | 'key_command';
type MatchScope = 'command' | 'args' | 'command_and_args';

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
  mappingType: MappingType;
  label: string;
  category: string;
  pattern: string;
  transcriptLabel: string;
  sessionTypeLabel?: string;
  matchScope?: MatchScope;
  fieldMappings?: SessionFieldMapping[];
  enabled: boolean;
  priority: number;
}

const defaultKeyFields = (): SessionFieldMapping[] => ([
  { id: 'related-command', label: 'Related Command', source: 'command', enabled: true },
  { id: 'related-phases', label: 'Related Phase(s)', source: 'phases', enabled: true, joinWith: ', ' },
]);

const emptyRule = (index: number, mappingType: MappingType): SessionMappingRule => ({
  id: `custom-${Date.now()}-${index}`,
  mappingType,
  label: mappingType === 'key_command' ? 'Key Command Type' : 'Custom Rule',
  category: mappingType === 'key_command' ? 'key_command' : 'bash',
  pattern: '',
  transcriptLabel: mappingType === 'key_command' ? 'Key Command' : 'Shell Command',
  sessionTypeLabel: mappingType === 'key_command' ? 'Custom Session Type' : '',
  matchScope: 'command',
  fieldMappings: mappingType === 'key_command' ? defaultKeyFields() : [],
  enabled: true,
  priority: mappingType === 'key_command' ? 200 : 10,
});

const fieldMappingsToText = (rule: SessionMappingRule): string =>
  JSON.stringify(rule.fieldMappings || [], null, 2);

export const SessionMappings: React.FC = () => {
  const [rules, setRules] = useState<SessionMappingRule[]>([]);
  const [fieldMappingDrafts, setFieldMappingDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const seedDrafts = (items: SessionMappingRule[]) => {
    const next: Record<string, string> = {};
    items.forEach(item => {
      if (item.mappingType === 'key_command') {
        next[item.id] = fieldMappingsToText(item);
      }
    });
    setFieldMappingDrafts(next);
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/session-mappings');
      if (!res.ok) {
        throw new Error(`Failed to load mappings (${res.status})`);
      }
      const data = await res.json();
      const loaded = Array.isArray(data) ? data : [];
      setRules(loaded);
      seedDrafts(loaded);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load mappings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const updateRule = (id: string, patch: Partial<SessionMappingRule>) => {
    setRules(prev => prev.map(rule => (rule.id === id ? { ...rule, ...patch } : rule)));
  };

  const addRule = (mappingType: MappingType) => {
    const nextRule = emptyRule(rules.length + 1, mappingType);
    setRules(prev => [...prev, nextRule]);
    if (mappingType === 'key_command') {
      setFieldMappingDrafts(prev => ({ ...prev, [nextRule.id]: fieldMappingsToText(nextRule) }));
    }
  };

  const removeRule = (id: string) => {
    setRules(prev => prev.filter(rule => rule.id !== id));
    setFieldMappingDrafts(prev => {
      const { [id]: _ignore, ...rest } = prev;
      return rest;
    });
  };

  const sortedRules = useMemo(
    () => [...rules].sort((a, b) => b.priority - a.priority),
    [rules]
  );

  const parseAndApplyFieldMappings = (ruleId: string): boolean => {
    const draft = fieldMappingDrafts[ruleId];
    if (!draft) return true;
    try {
      const parsed = JSON.parse(draft);
      if (!Array.isArray(parsed)) {
        throw new Error('field mappings must be an array');
      }
      updateRule(ruleId, { fieldMappings: parsed as SessionFieldMapping[] });
      return true;
    } catch (e) {
      setError(`Invalid fieldMappings JSON for rule "${ruleId}"`);
      return false;
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);

    for (const rule of rules) {
      if (rule.mappingType === 'key_command' && !parseAndApplyFieldMappings(rule.id)) {
        setSaving(false);
        return;
      }
    }

    const payloadRules = rules.map(rule => {
      if (rule.mappingType === 'bash') {
        return {
          ...rule,
          sessionTypeLabel: '',
          matchScope: 'command',
          fieldMappings: [],
        };
      }
      return {
        ...rule,
        category: 'key_command',
        transcriptLabel: rule.transcriptLabel || rule.label,
        sessionTypeLabel: rule.sessionTypeLabel || rule.label,
        matchScope: rule.matchScope || 'command',
        fieldMappings: rule.fieldMappings || [],
      };
    });

    try {
      const res = await fetch('/api/session-mappings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mappings: payloadRules }),
      });
      if (!res.ok) {
        throw new Error(`Failed to save mappings (${res.status})`);
      }
      const data = await res.json();
      const saved = Array.isArray(data) ? data : rules;
      setRules(saved);
      seedDrafts(saved);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save mappings');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold text-slate-100">Session Mappings</h2>
          <p className="text-sm text-slate-400 mt-2">
            Configure command mappings for transcript labeling (`bash`) and key session type detection (`key_command`).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => addRule('bash')}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700"
          >
            <Plus size={14} />
            Add Bash Rule
          </button>
          <button
            onClick={() => addRule('key_command')}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-700/70 border border-emerald-500/40 text-emerald-100 hover:bg-emerald-700"
          >
            <Plus size={14} />
            Add Key Command Type
          </button>
          <button
            onClick={save}
            disabled={saving || loading}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-60"
          >
            <Save size={14} />
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 text-sm text-slate-400">
          Loading mappings...
        </div>
      ) : (
        <div className="space-y-4">
          {sortedRules.map(rule => (
            <div key={rule.id} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
              <div className="flex items-center justify-between gap-3 mb-3">
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={rule.enabled}
                    onChange={e => updateRule(rule.id, { enabled: e.target.checked })}
                    className="w-4 h-4"
                  />
                  <span className={`text-xs font-bold uppercase tracking-wider ${rule.mappingType === 'key_command' ? 'text-emerald-300' : 'text-slate-400'}`}>
                    {rule.mappingType}
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">{rule.id}</span>
                </div>
                <button
                  onClick={() => removeRule(rule.id)}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded border border-slate-700 text-slate-400 hover:text-rose-300 hover:border-rose-500/40"
                >
                  <Trash2 size={13} />
                  Remove
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                <label className="text-xs text-slate-400">
                  Label
                  <input
                    value={rule.label}
                    onChange={e => updateRule(rule.id, { label: e.target.value })}
                    className="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-200"
                  />
                </label>
                <label className="text-xs text-slate-400">
                  Mapping Type
                  <select
                    value={rule.mappingType}
                    onChange={e => updateRule(rule.id, { mappingType: e.target.value as MappingType })}
                    className="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-200"
                  >
                    <option value="bash">bash</option>
                    <option value="key_command">key_command</option>
                  </select>
                </label>
                <label className="text-xs text-slate-400">
                  Regex Pattern
                  <input
                    value={rule.pattern}
                    onChange={e => updateRule(rule.id, { pattern: e.target.value })}
                    className="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-200 font-mono"
                  />
                </label>
                <label className="text-xs text-slate-400">
                  Priority
                  <input
                    type="number"
                    value={rule.priority}
                    onChange={e => updateRule(rule.id, { priority: Number(e.target.value || 0) })}
                    className="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-200"
                  />
                </label>
              </div>

              {rule.mappingType === 'bash' ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                  <label className="text-xs text-slate-400">
                    Category
                    <input
                      value={rule.category}
                      onChange={e => updateRule(rule.id, { category: e.target.value })}
                      className="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-200"
                    />
                  </label>
                  <label className="text-xs text-slate-400">
                    Transcript Label
                    <input
                      value={rule.transcriptLabel}
                      onChange={e => updateRule(rule.id, { transcriptLabel: e.target.value })}
                      className="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-200"
                    />
                  </label>
                </div>
              ) : (
                <div className="space-y-3 mt-3">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <label className="text-xs text-slate-400">
                      Session Type Label
                      <input
                        value={rule.sessionTypeLabel || ''}
                        onChange={e => updateRule(rule.id, { sessionTypeLabel: e.target.value })}
                        className="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-200"
                      />
                    </label>
                    <label className="text-xs text-slate-400">
                      Match Scope
                      <select
                        value={rule.matchScope || 'command'}
                        onChange={e => updateRule(rule.id, { matchScope: e.target.value as MatchScope })}
                        className="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-200"
                      >
                        <option value="command">command</option>
                        <option value="args">args</option>
                        <option value="command_and_args">command + args</option>
                      </select>
                    </label>
                    <label className="text-xs text-slate-400">
                      Transcript Label
                      <input
                        value={rule.transcriptLabel}
                        onChange={e => updateRule(rule.id, { transcriptLabel: e.target.value })}
                        className="mt-1 w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-200"
                      />
                    </label>
                  </div>
                  <label className="block text-xs text-slate-400">
                    Field Mappings (JSON)
                    <textarea
                      value={fieldMappingDrafts[rule.id] ?? fieldMappingsToText(rule)}
                      onChange={e => setFieldMappingDrafts(prev => ({ ...prev, [rule.id]: e.target.value }))}
                      onBlur={() => { void parseAndApplyFieldMappings(rule.id); }}
                      className="mt-1 w-full min-h-[120px] bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-slate-200 font-mono text-[11px]"
                    />
                  </label>
                  <p className="text-[11px] text-slate-500">
                    Supported `source` values: `command`, `args`, `phaseToken`, `phases`, `featurePath`, `featureSlug`, `requestId`.
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
