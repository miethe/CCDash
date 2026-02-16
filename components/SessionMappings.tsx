import React, { useEffect, useMemo, useState } from 'react';
import { Plus, Save, Trash2 } from 'lucide-react';

interface SessionMappingRule {
  id: string;
  label: string;
  category: string;
  pattern: string;
  transcriptLabel: string;
  enabled: boolean;
  priority: number;
}

const emptyRule = (index: number): SessionMappingRule => ({
  id: `custom-${Date.now()}-${index}`,
  label: 'Custom Rule',
  category: 'bash',
  pattern: '',
  transcriptLabel: 'Shell Command',
  enabled: true,
  priority: 10,
});

export const SessionMappings: React.FC = () => {
  const [rules, setRules] = useState<SessionMappingRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/session-mappings');
      if (!res.ok) {
        throw new Error(`Failed to load mappings (${res.status})`);
      }
      const data = await res.json();
      setRules(Array.isArray(data) ? data : []);
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

  const addRule = () => {
    setRules(prev => [...prev, emptyRule(prev.length + 1)]);
  };

  const removeRule = (id: string) => {
    setRules(prev => prev.filter(rule => rule.id !== id));
  };

  const sortedRules = useMemo(
    () => [...rules].sort((a, b) => b.priority - a.priority),
    [rules]
  );

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
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save mappings');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-3xl font-bold text-slate-100">Session Mappings</h2>
          <p className="text-sm text-slate-400 mt-2">
            Configure how shell commands are classified and labeled in session transcripts.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={addRule}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700"
          >
            <Plus size={14} />
            Add Rule
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
        <div className="rounded-xl border border-slate-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-900">
              <tr className="text-left text-slate-400">
                <th className="px-3 py-3 font-medium">Enabled</th>
                <th className="px-3 py-3 font-medium">Label</th>
                <th className="px-3 py-3 font-medium">Category</th>
                <th className="px-3 py-3 font-medium">Regex Pattern</th>
                <th className="px-3 py-3 font-medium">Transcript Label</th>
                <th className="px-3 py-3 font-medium">Priority</th>
                <th className="px-3 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {sortedRules.map(rule => (
                <tr key={rule.id} className="border-t border-slate-800 bg-slate-950/50">
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={rule.enabled}
                      onChange={e => updateRule(rule.id, { enabled: e.target.checked })}
                      className="w-4 h-4"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      value={rule.label}
                      onChange={e => updateRule(rule.id, { label: e.target.value })}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      value={rule.category}
                      onChange={e => updateRule(rule.id, { category: e.target.value })}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      value={rule.pattern}
                      onChange={e => updateRule(rule.id, { pattern: e.target.value })}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200 font-mono"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      value={rule.transcriptLabel}
                      onChange={e => updateRule(rule.id, { transcriptLabel: e.target.value })}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="number"
                      value={rule.priority}
                      onChange={e => updateRule(rule.id, { priority: Number(e.target.value || 0) })}
                      className="w-20 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200"
                    />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => removeRule(rule.id)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded border border-slate-700 text-slate-400 hover:text-rose-300 hover:border-rose-500/40"
                    >
                      <Trash2 size={13} />
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
