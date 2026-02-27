import React, { useMemo, useState } from 'react';
import { AgentSession, SessionArtifact, SessionLog } from '../types';
import { ChevronRight, Database, HardDrive, Link as LinkIcon, Scroll, Terminal, X } from 'lucide-react';

const toEpoch = (timestamp?: string): number => {
  if (!timestamp) return 0;
  const ms = Date.parse(timestamp);
  return Number.isFinite(ms) ? ms : 0;
};

const fileNameFromPath = (path: string): string => {
  const normalized = (path || '').replace(/\\/g, '/').trim();
  const parts = normalized.split('/');
  return parts[parts.length - 1] || normalized;
};

const parseToolArgs = (raw: string | undefined): Record<string, unknown> | null => {
  if (!raw || !raw.trim()) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
};

const takeString = (...values: unknown[]): string | null => {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return null;
};

const asRecord = (value: unknown): Record<string, any> => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, any>
    : {}
);

const asStringArray = (value: unknown): string[] => (
  Array.isArray(value)
    ? value
      .map(item => (typeof item === 'string' ? item.trim() : String(item ?? '').trim()))
      .filter(Boolean)
    : []
);

const extractTaskSubagentName = (toolArgs: string | undefined): string | null => {
  const args = parseToolArgs(toolArgs);
  if (!args) {
    return null;
  }

  const nestedConfig =
    (typeof args.agent_config === 'object' && args.agent_config ? args.agent_config : null) ||
    (typeof args.agentConfig === 'object' && args.agentConfig ? args.agentConfig : null);

  return takeString(
    args.subagent_type,
    args.subagentType,
    args.agent_name,
    args.agentName,
    nestedConfig && (nestedConfig as Record<string, unknown>).name,
    nestedConfig && (nestedConfig as Record<string, unknown>).id,
    nestedConfig && (nestedConfig as Record<string, unknown>).type,
  );
};

const getThreadDisplayName = (thread: AgentSession, subagentNameBySessionId: Map<string, string>): string => {
  return (
    subagentNameBySessionId.get(thread.id) ||
    (thread.agentId ? `agent-${thread.agentId}` : '') ||
    thread.sessionType ||
    'thread'
  );
};

const makeArtifactGroupKey = (artifact: SessionArtifact): string => {
  const type = (artifact.type || '').trim().toLowerCase();
  const title = (artifact.title || '').trim().toLowerCase();
  const source = (artifact.source || '').trim().toLowerCase();
  const url = (artifact.url || '').trim().toLowerCase();
  return `${type}::${title}::${source}::${url}`;
};

interface ArtifactGroup {
  key: string;
  type: string;
  title: string;
  source: string;
  description?: string;
  url?: string;
  artifactIds: string[];
  artifacts: SessionArtifact[];
  sourceLogIds: string[];
  sourceToolNames: string[];
  relatedToolLogs: SessionLog[];
  linkedThreads: AgentSession[];
}

const ArtifactDetailsModal: React.FC<{
  group: ArtifactGroup;
  onClose: () => void;
  onOpenThread: (sessionId: string) => void;
  subagentNameBySessionId: Map<string, string>;
}> = ({ group, onClose, onOpenThread, subagentNameBySessionId }) => {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-200" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]" onClick={e => e.stopPropagation()}>
        <div className="p-5 border-b border-slate-800 flex justify-between items-start bg-slate-950">
          <div>
            <h3 className="text-lg font-bold text-slate-100">{group.title}</h3>
            <p className="text-xs text-slate-500 mt-1">
              {group.type} • {group.source} • {group.artifacts.length} merged artifacts
            </p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-6 overflow-y-auto">
          <div className="bg-slate-950/70 rounded-lg border border-slate-800 p-4 text-sm text-slate-300">
            {group.description || 'No artifact description available.'}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Source Log IDs</h4>
              <div className="flex flex-wrap gap-2">
                {group.sourceLogIds.length === 0 && <span className="text-xs text-slate-500">None</span>}
                {group.sourceLogIds.map(sourceLogId => (
                  <span key={sourceLogId} className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700 font-mono">
                    {sourceLogId}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Source Tools</h4>
              <div className="flex flex-wrap gap-2">
                {group.sourceToolNames.length === 0 && <span className="text-xs text-slate-500">None</span>}
                {group.sourceToolNames.map(sourceToolName => (
                  <span key={sourceToolName} className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700 font-mono">
                    {sourceToolName}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div>
            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Related Tool Calls</h4>
            <div className="space-y-2">
              {group.relatedToolLogs.length === 0 && (
                <div className="text-xs text-slate-500">No related tool calls found.</div>
              )}
              {group.relatedToolLogs.map(log => (
                <div key={log.id} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-mono text-slate-200">{log.toolCall?.name || 'tool'}</div>
                    <div className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-bold ${log.toolCall?.status === 'error' ? 'bg-rose-500/10 text-rose-400' : 'bg-emerald-500/10 text-emerald-400'}`}>
                      {log.toolCall?.status || 'success'}
                    </div>
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">
                    {log.id} • {log.timestamp}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Linked Sub-agent Threads</h4>
            <div className="space-y-2">
              {group.linkedThreads.length === 0 && (
                <div className="text-xs text-slate-500">No linked sub-agent threads found.</div>
              )}
              {group.linkedThreads.map(thread => (
                <div key={thread.id} className="rounded-lg border border-slate-800 bg-slate-950 p-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm text-indigo-300 font-mono">{thread.id}</div>
                    <div className="text-[10px] text-slate-500 mt-1">{getThreadDisplayName(thread, subagentNameBySessionId)}</div>
                  </div>
                  <button
                    onClick={() => onOpenThread(thread.id)}
                    className="text-xs px-3 py-1.5 rounded-lg border border-indigo-500/30 text-indigo-300 bg-indigo-500/10 hover:bg-indigo-500/20"
                  >
                    Open Sub-agent Transcript
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Merged Artifact IDs</h4>
            <div className="flex flex-wrap gap-2">
              {group.artifactIds.map(id => (
                <span key={id} className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700 font-mono">
                  {id}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export const SessionArtifactsView: React.FC<{
  session: AgentSession;
  threadSessions: AgentSession[];
  subagentNameBySessionId: Map<string, string>;
  onOpenThread: (sessionId: string) => void;
  highlightedSourceLogId?: string | null;
}> = ({ session, threadSessions, subagentNameBySessionId, onOpenThread, highlightedSourceLogId }) => {
  const [selectedGroup, setSelectedGroup] = useState<ArtifactGroup | null>(null);
  const [activeSubTab, setActiveSubTab] = useState<'commands' | 'skills' | 'agents' | 'tools'>('commands');
  const commandTagArtifactTypes = useMemo(
    () => new Set(['command_path', 'feature_slug', 'command_phase', 'request']),
    [],
  );

  const groupedArtifacts = useMemo(() => {
    const artifacts = session.linkedArtifacts || [];
    if (artifacts.length === 0) {
      return [];
    }

    const logsById = new Map(session.logs.map(log => [log.id, log]));
    const threadsById = new Map(threadSessions.map(thread => [thread.id, thread]));

    type MutableArtifactGroup = ArtifactGroup & {
      sourceLogIdSet: Set<string>;
      sourceToolNameSet: Set<string>;
      relatedToolLogIds: Set<string>;
      linkedThreadIds: Set<string>;
    };

    const groups = new Map<string, MutableArtifactGroup>();

    const ensureGroup = (artifact: SessionArtifact): MutableArtifactGroup => {
      const key = makeArtifactGroupKey(artifact);
      const existing = groups.get(key);
      if (existing) {
        return existing;
      }
      const created: MutableArtifactGroup = {
        key,
        type: artifact.type || 'document',
        title: artifact.title,
        source: artifact.source,
        description: artifact.description,
        url: artifact.url,
        artifactIds: [],
        artifacts: [],
        sourceLogIds: [],
        sourceToolNames: [],
        relatedToolLogs: [],
        linkedThreads: [],
        sourceLogIdSet: new Set<string>(),
        sourceToolNameSet: new Set<string>(),
        relatedToolLogIds: new Set<string>(),
        linkedThreadIds: new Set<string>(),
      };
      groups.set(key, created);
      return created;
    };

    const attachFromLog = (group: MutableArtifactGroup, log: SessionLog | undefined) => {
      if (!log) {
        return;
      }
      if (log.type === 'tool' && !group.relatedToolLogIds.has(log.id)) {
        group.relatedToolLogIds.add(log.id);
        group.relatedToolLogs.push(log);
      }
      if (log.linkedSessionId && threadsById.has(log.linkedSessionId) && !group.linkedThreadIds.has(log.linkedSessionId)) {
        group.linkedThreadIds.add(log.linkedSessionId);
        group.linkedThreads.push(threadsById.get(log.linkedSessionId)!);
      }
    };

    for (const artifact of artifacts) {
      if (commandTagArtifactTypes.has((artifact.type || '').trim().toLowerCase())) {
        continue;
      }
      const group = ensureGroup(artifact);
      group.artifacts.push(artifact);
      if (!group.artifactIds.includes(artifact.id)) {
        group.artifactIds.push(artifact.id);
      }
      if (artifact.description && !group.description) {
        group.description = artifact.description;
      }
      if (artifact.url && !group.url) {
        group.url = artifact.url;
      }

      if (artifact.sourceLogId) {
        group.sourceLogIdSet.add(artifact.sourceLogId);
      }
      if (artifact.sourceToolName) {
        group.sourceToolNameSet.add(artifact.sourceToolName);
      }
    }

    for (const group of groups.values()) {
      for (const sourceLogId of group.sourceLogIdSet) {
        const sourceLog = logsById.get(sourceLogId);
        attachFromLog(group, sourceLog);
      }
      if (group.type === 'agent') {
        for (const log of session.logs) {
          if (log.type !== 'tool' || log.toolCall?.name !== 'Task') {
            continue;
          }
          const taskSubagentName = extractTaskSubagentName(log.toolCall?.args);
          const linkedThreadName = log.linkedSessionId ? subagentNameBySessionId.get(log.linkedSessionId) : null;
          if (taskSubagentName === group.title || linkedThreadName === group.title) {
            attachFromLog(group, log);
          }
        }
      }
    }

    const groupedArray = Array.from(groups.values());
    const namedThreadIds = new Set<string>();
    for (const group of groupedArray) {
      if (group.type !== 'agent' || /^agent-/i.test(group.title)) {
        continue;
      }
      for (const thread of group.linkedThreads) {
        namedThreadIds.add(thread.id);
      }
    }

    return groupedArray
      .filter(group => {
        if (group.type !== 'agent' || !/^agent-/i.test(group.title)) {
          return true;
        }
        return !group.linkedThreads.some(thread => namedThreadIds.has(thread.id));
      })
      .map(group => ({
        key: group.key,
        type: group.type,
        title: group.title,
        source: group.source,
        description: group.description,
        url: group.url,
        artifactIds: group.artifactIds,
        artifacts: group.artifacts,
        sourceLogIds: Array.from(group.sourceLogIdSet),
        sourceToolNames: Array.from(group.sourceToolNameSet),
        relatedToolLogs: group.relatedToolLogs,
        linkedThreads: group.linkedThreads,
      }))
      .sort((a, b) => {
        if (b.artifacts.length !== a.artifacts.length) {
          return b.artifacts.length - a.artifacts.length;
        }
        return a.title.localeCompare(b.title);
      });
  }, [commandTagArtifactTypes, session.linkedArtifacts, session.logs, subagentNameBySessionId, threadSessions]);

  const commandEntries = useMemo(() => {
    const artifactsByLogId = new Map<string, SessionArtifact[]>();
    for (const artifact of session.linkedArtifacts || []) {
      if (!artifact.sourceLogId) continue;
      const existing = artifactsByLogId.get(artifact.sourceLogId) || [];
      existing.push(artifact);
      artifactsByLogId.set(artifact.sourceLogId, existing);
    }

    return session.logs
      .filter(log => log.type === 'command')
      .map(log => {
        const metadata = asRecord(log.metadata);
        const parsedCommand = asRecord(metadata.parsedCommand);
        const phaseValues = asStringArray(parsedCommand.phases);
        const phaseToken = takeString(parsedCommand.phaseToken);
        if (phaseToken && !phaseValues.includes(phaseToken)) {
          phaseValues.push(phaseToken);
        }

        const taggedArtifacts = (artifactsByLogId.get(log.id) || [])
          .filter(artifact => commandTagArtifactTypes.has((artifact.type || '').trim().toLowerCase()));
        for (const artifact of taggedArtifacts) {
          if (artifact.type === 'command_phase' && artifact.title && !phaseValues.includes(artifact.title)) {
            phaseValues.push(artifact.title);
          }
        }

        return {
          logId: log.id,
          timestamp: log.timestamp,
          commandName: log.content,
          args: takeString(metadata.args),
          phases: phaseValues,
          featurePath: takeString(parsedCommand.featurePath),
          featureSlug: takeString(parsedCommand.featureSlug),
          requestId: takeString(parsedCommand.requestId),
          taggedArtifactsCount: taggedArtifacts.length,
        };
      })
      .sort((a, b) => toEpoch(b.timestamp) - toEpoch(a.timestamp));
  }, [commandTagArtifactTypes, session.linkedArtifacts, session.logs]);

  const skillGroups = useMemo(
    () => groupedArtifacts.filter(group => (group.type || '').trim().toLowerCase() === 'skill'),
    [groupedArtifacts],
  );
  const taskGroups = useMemo(
    () => groupedArtifacts.filter(group => (group.type || '').trim().toLowerCase() === 'task'),
    [groupedArtifacts],
  );
  const agentGroups = useMemo(
    () => groupedArtifacts.filter(group => {
      const type = (group.type || '').trim().toLowerCase();
      return type === 'agent';
    }),
    [groupedArtifacts],
  );
  const toolGroups = useMemo(
    () => groupedArtifacts.filter(group => {
      const type = (group.type || '').trim().toLowerCase();
      if (type === 'skill' || type === 'agent' || type === 'task' || type === 'command') return false;
      return group.relatedToolLogs.length > 0 || group.sourceToolNames.length > 0;
    }),
    [groupedArtifacts],
  );

  const visibleGroups = useMemo(() => {
    if (activeSubTab === 'skills') return skillGroups;
    if (activeSubTab === 'agents') return agentGroups;
    if (activeSubTab === 'tools') return toolGroups;
    return [];
  }, [activeSubTab, agentGroups, skillGroups, toolGroups]);

  const hasAnyData = commandEntries.length > 0 || skillGroups.length > 0 || agentGroups.length > 0 || toolGroups.length > 0;

  if (!hasAnyData) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-500">
        <LinkIcon size={48} className="mb-4 opacity-20" />
        <p>No linked artifacts found.</p>
        {taskGroups.length > 0 && (
          <p className="text-xs mt-1 text-slate-600">Task links are shown on the Features tab.</p>
        )}
      </div>
    );
  }

  return (
    <>
      <div className="mb-4 flex items-center gap-2 border border-slate-800 rounded-lg bg-slate-900 p-1 w-fit">
        {[
          { id: 'commands', label: `Commands (${commandEntries.length})` },
          { id: 'skills', label: `Skills (${skillGroups.length})` },
          { id: 'agents', label: `Agents (${agentGroups.length})` },
          { id: 'tools', label: `Tools (${toolGroups.length})` },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveSubTab(tab.id as 'commands' | 'skills' | 'agents' | 'tools')}
            className={`px-3 py-1.5 text-xs rounded-md transition-colors ${activeSubTab === tab.id
              ? 'bg-indigo-600 text-white'
              : 'text-slate-400 hover:text-slate-200'
              }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeSubTab === 'commands' && (
        <div className="space-y-3">
          {commandEntries.length === 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-500">
              No command activity found.
            </div>
          )}
          {commandEntries.map(entry => (
            <div
              key={entry.logId}
              className={`rounded-xl border p-4 ${highlightedSourceLogId && entry.logId === highlightedSourceLogId ? 'border-indigo-500/50 bg-indigo-500/5' : 'border-slate-800 bg-slate-900/40'}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-emerald-300/90 font-semibold mb-1 flex items-center gap-1.5">
                    <Terminal size={11} /> Command
                  </div>
                  <p className="font-mono text-sm text-slate-200 break-all">{entry.commandName}</p>
                  {entry.args && (
                    <p className="mt-2 text-xs text-slate-400 whitespace-pre-wrap break-words">{entry.args}</p>
                  )}
                </div>
                <div className="text-[10px] text-slate-500">{new Date(entry.timestamp).toLocaleString()}</div>
              </div>

              <div className="mt-3 flex flex-wrap gap-1.5">
                {entry.phases.map(phase => (
                  <span key={`${entry.logId}-phase-${phase}`} className="text-[10px] px-1.5 py-0.5 rounded border border-indigo-500/30 bg-indigo-500/10 text-indigo-300">
                    Phase {phase}
                  </span>
                ))}
                {entry.featureSlug && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800/70 text-slate-300">
                    Feature {entry.featureSlug}
                  </span>
                )}
                {entry.requestId && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-300 font-mono">
                    {entry.requestId}
                  </span>
                )}
                {entry.featurePath && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800/70 text-slate-400 font-mono">
                    {fileNameFromPath(entry.featurePath)}
                  </span>
                )}
                {entry.taggedArtifactsCount > 0 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
                    {entry.taggedArtifactsCount} normalized tags
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {activeSubTab !== 'commands' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {visibleGroups.length === 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-500 md:col-span-2 lg:col-span-3">
              No {activeSubTab} artifacts found.
            </div>
          )}
          {visibleGroups.map(group => (
            <button
              key={group.key}
              onClick={() => setSelectedGroup(group)}
              className={`text-left bg-slate-900 border rounded-xl p-6 hover:border-indigo-500/50 transition-all group ${highlightedSourceLogId && group.sourceLogIds.includes(highlightedSourceLogId) ? 'border-indigo-500/50 bg-indigo-500/5' : 'border-slate-800'}`}
            >
              <div className="flex justify-between items-start mb-4">
                <div className={`p-2 rounded-lg ${group.type === 'memory' ? 'bg-purple-500/10 text-purple-400' :
                  group.type === 'request_log' ? 'bg-amber-500/10 text-amber-400' :
                    'bg-blue-500/10 text-blue-400'
                  }`}>
                  {group.type === 'memory' ? <HardDrive size={20} /> :
                    group.type === 'request_log' ? <Scroll size={20} /> :
                      <Database size={20} />}
                </div>
                <span className="text-[10px] bg-slate-800 text-slate-500 px-2 py-0.5 rounded uppercase font-bold tracking-wider">
                  {group.source}
                </span>
              </div>

              <h3 className="font-bold text-slate-200 mb-2 group-hover:text-indigo-400 transition-colors">{group.title}</h3>
              <p className="text-sm text-slate-400 mb-4 line-clamp-3">{group.description}</p>

              <div className="flex flex-wrap gap-2 mb-4">
                <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700">
                  {group.artifacts.length} merged
                </span>
                <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700">
                  {group.relatedToolLogs.length} tool calls
                </span>
                <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700">
                  {group.linkedThreads.length} sub-threads
                </span>
              </div>

              <div className="pt-4 border-t border-slate-800 flex justify-between items-center">
                <span className="text-xs font-mono text-slate-500">{group.artifactIds[0]}</span>
                <span className="text-xs flex items-center gap-1 text-indigo-400 group-hover:text-indigo-300">
                  View Details <ChevronRight size={12} />
                </span>
              </div>
            </button>
          ))}
        </div>
      )}

      {selectedGroup && (
        <ArtifactDetailsModal
          group={selectedGroup}
          onClose={() => setSelectedGroup(null)}
          onOpenThread={onOpenThread}
          subagentNameBySessionId={subagentNameBySessionId}
        />
      )}
    </>
  );
};
