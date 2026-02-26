import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useData, type SessionFilters } from '../contexts/DataContext';
import { AgentSession, SessionLog, LogType, SessionArtifact, PlanDocument, SessionActivityItem, SessionFileAggregateRow, SessionFileUpdate } from '../types';
import { Clock, Database, Terminal, CheckCircle2, XCircle, Search, Edit3, GitCommit, GitBranch, ArrowLeft, Bot, Activity, Archive, PlayCircle, Cpu, Zap, Box, ChevronRight, MessageSquare, Code, ChevronDown, Calendar, BarChart2, PieChart as PieChartIcon, Users, TrendingUp, FileDiff, ShieldAlert, Check, FileText, ExternalLink, Link as LinkIcon, HardDrive, Scroll, Maximize2, X, MoreHorizontal, Layers, RefreshCw, LayoutGrid } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, LineChart, Line, Legend, ComposedChart, ReferenceLine } from 'recharts';
import { DocumentModal } from './DocumentModal';
import { TranscriptFormattedMessage, parseTranscriptMessage, getReadableTagName } from './sessionTranscriptFormatting';
import { SessionCard, SessionCardDetailSection, deriveSessionCardTitle, formatModelDisplayName } from './SessionCard';
import { analyticsService } from '../services/analytics';
import { SidebarFiltersPortal, SidebarFiltersSection } from './SidebarFilters';

const MAIN_SESSION_AGENT = 'Main Session';
const SHORT_COMMIT_LENGTH = 7;
const LIVE_IN_FLIGHT_WINDOW_MS = 10 * 60 * 1000;

const toShortCommitHash = (hash: string): string => hash.slice(0, SHORT_COMMIT_LENGTH);

const collectSessionCommitHashes = (session: AgentSession): string[] => {
    const commits: string[] = [];
    if (session.gitCommitHash && session.gitCommitHash.trim()) {
        commits.push(session.gitCommitHash.trim());
    }
    (session.gitCommitHashes || []).forEach(commit => {
        if (typeof commit === 'string' && commit.trim()) {
            commits.push(commit.trim());
        }
    });
    return Array.from(new Set(commits));
};

const normalizePath = (path: string): string => path.replace(/\\/g, '/').replace(/^\.\/+/, '').trim();

const fileNameFromPath = (path: string): string => {
    const normalized = normalizePath(path);
    const parts = normalized.split('/');
    return parts[parts.length - 1] || normalized;
};

const resolveLocalPath = (filePath: string, projectRoot?: string | null): string => {
    const normalizedFilePath = normalizePath(filePath);
    if (normalizedFilePath.startsWith('/')) return normalizedFilePath;
    if (!projectRoot) return normalizedFilePath;
    return `${projectRoot.replace(/\/+$/, '')}/${normalizedFilePath}`;
};

const toEpoch = (timestamp?: string): number => {
    if (!timestamp) return 0;
    const ms = Date.parse(timestamp);
    return Number.isFinite(ms) ? ms : 0;
};

const sessionLastActivityEpoch = (session: AgentSession): number => {
    const candidates = [
        session.dates?.lastActivityAt?.value,
        session.updatedAt,
        session.endedAt,
        session.startedAt,
    ];
    for (const candidate of candidates) {
        const epoch = toEpoch(candidate);
        if (epoch > 0) return epoch;
    }
    return 0;
};

const isSessionLiveInFlight = (session: AgentSession, nowMs: number): boolean => {
    if ((session.status || '').toLowerCase() !== 'active') return false;
    const activityEpoch = sessionLastActivityEpoch(session);
    if (activityEpoch <= 0) return false;
    const ageMs = Math.max(0, nowMs - activityEpoch);
    return ageMs <= LIVE_IN_FLIGHT_WINDOW_MS;
};

const parseLogIndex = (logId?: string): number => {
    if (!logId) return -1;
    const match = /^log-(\d+)$/.exec(logId.trim());
    return match ? Number.parseInt(match[1], 10) : -1;
};

type CommitEvent = {
    hash: string;
    logIndex: number;
    timestampMs: number;
};

const collectCommitEvents = (session: AgentSession): CommitEvent[] => {
    const events: CommitEvent[] = [];
    const seen = new Set<string>();

    session.logs.forEach(log => {
        const hashesRaw = log.metadata?.commitHashes;
        if (!Array.isArray(hashesRaw)) return;
        const logIndex = parseLogIndex(log.id);
        const timestampMs = toEpoch(log.timestamp);
        hashesRaw.forEach(hash => {
            if (typeof hash !== 'string' || !hash.trim()) return;
            const cleanHash = hash.trim();
            const key = `${cleanHash}::${logIndex}::${timestampMs}`;
            if (seen.has(key)) return;
            seen.add(key);
            events.push({ hash: cleanHash, logIndex, timestampMs });
        });
    });

    events.sort((a, b) => {
        if (a.logIndex !== b.logIndex) return a.logIndex - b.logIndex;
        return a.timestampMs - b.timestampMs;
    });
    return events;
};

const toGitHubBlobUrl = (repoUrl: string, commitHash: string, filePath: string, projectRoot?: string | null): string | null => {
    const trimmedRepo = repoUrl.trim();
    if (!trimmedRepo || !commitHash.trim()) return null;
    let base = trimmedRepo.replace(/\.git$/i, '').replace(/\/+$/, '');
    if (!/^https?:\/\/github\.com\/[^/]+\/[^/]+$/i.test(base)) return null;

    const normalizedFilePath = normalizePath(filePath);
    const relativePath = projectRoot && normalizedFilePath.startsWith(normalizePath(projectRoot) + '/')
        ? normalizedFilePath.slice(normalizePath(projectRoot).length + 1)
        : normalizedFilePath;
    const encodedSegments = relativePath.split('/').filter(Boolean).map(encodeURIComponent).join('/');
    if (!encodedSegments) return null;
    base = base.replace(/^http:\/\//i, 'https://');
    return `${base}/blob/${encodeURIComponent(commitHash.trim())}/${encodedSegments}`;
};

const normalizeFileAction = (action: string | undefined, sourceToolName?: string): 'read' | 'create' | 'update' | 'delete' | 'other' => {
    const normalized = (action || '').trim().toLowerCase();
    if (normalized === 'read') return 'read';
    if (normalized === 'create') return 'create';
    if (normalized === 'update' || normalized === 'write') return 'update';
    if (normalized === 'delete' || normalized === 'remove') return 'delete';

    const tool = (sourceToolName || '').trim().toLowerCase();
    if (tool === 'read' || tool === 'readfile') return 'read';
    if (tool === 'write' || tool === 'writefile' || tool === 'edit' || tool === 'multiedit') return 'update';
    if (tool === 'delete' || tool === 'deletefile') return 'delete';
    return 'other';
};

const formatAction = (action: string): string => {
    const normalized = (action || '').trim();
    if (!normalized) return 'Unknown';
    return normalized.charAt(0).toUpperCase() + normalized.slice(1);
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

const asNumber = (value: unknown, fallback = 0): number => {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
};

const asCountEntries = (value: unknown, limit = 8): Array<{ key: string; count: number }> => {
    const record = asRecord(value);
    return Object.entries(record)
        .map(([key, rawCount]) => ({ key, count: asNumber(rawCount, 0) }))
        .filter(item => item.key.trim() && item.count > 0)
        .sort((a, b) => b.count - a.count)
        .slice(0, limit);
};

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

interface SessionFeatureLink {
    featureId: string;
    featureName: string;
    featureStatus: string;
    featureCategory: string;
    featureUpdatedAt: string;
    totalTasks: number;
    completedTasks: number;
    confidence: number;
    isPrimaryLink: boolean;
    linkStrategy: string;
    reasons: string[];
    signals: Array<Record<string, unknown>>;
    commands: string[];
    commitHashes: string[];
    ambiguityShare: number;
}

const formatSessionReason = (reason: string): string => {
    const normalized = (reason || '').trim();
    if (!normalized) return 'related';
    if (normalized === 'task_frontmatter') return 'task linkage';
    if (normalized === 'session_evidence') return 'session evidence';
    if (normalized === 'command_args_path') return 'command path';
    if (normalized === 'file_write') return 'file write';
    if (normalized === 'shell_reference') return 'shell reference';
    if (normalized === 'search_reference') return 'search reference';
    if (normalized === 'file_read') return 'file read';
    return normalized.replace(/_/g, ' ');
};

interface SessionThreadNode {
    session: AgentSession;
    children: SessionThreadNode[];
}

const threadNodeHasLiveSession = (node: SessionThreadNode, nowMs: number): boolean => {
    if (isSessionLiveInFlight(node.session, nowMs)) return true;
    return node.children.some(child => threadNodeHasLiveSession(child, nowMs));
};

const isSubthread = (session: AgentSession): boolean => {
    if (session.parentSessionId) return true;
    return (session.sessionType || '').toLowerCase() === 'subagent';
};

const sessionTimeValue = (session: AgentSession): number => {
    const parsed = Date.parse(session.startedAt || '');
    return Number.isFinite(parsed) ? parsed : 0;
};

const compareSessionsByTime = (a: AgentSession, b: AgentSession): number =>
    sessionTimeValue(b) - sessionTimeValue(a);

const sortSessionThreadNodes = (nodes: SessionThreadNode[]): SessionThreadNode[] =>
    [...nodes]
        .sort((a, b) => compareSessionsByTime(a.session, b.session))
        .map(node => ({
            ...node,
            children: sortSessionThreadNodes(node.children),
        }));

const countSessionThreadNodes = (nodes: SessionThreadNode[]): number =>
    nodes.reduce((sum, node) => sum + 1 + countSessionThreadNodes(node.children), 0);

const buildSessionThreadForest = (sessions: AgentSession[]): SessionThreadNode[] => {
    const nodes = new Map<string, SessionThreadNode>();
    sessions.forEach(session => {
        nodes.set(session.id, { session, children: [] });
    });

    const attached = new Set<string>();
    sessions.forEach(session => {
        if (!isSubthread(session)) return;
        const candidateParents = [
            session.parentSessionId || '',
            session.rootSessionId && session.rootSessionId !== session.id ? session.rootSessionId : '',
        ];
        const parentId = candidateParents.find(id => !!id && nodes.has(id));
        if (!parentId || parentId === session.id) return;
        const parentNode = nodes.get(parentId);
        const node = nodes.get(session.id);
        if (!parentNode || !node) return;
        parentNode.children.push(node);
        attached.add(session.id);
    });

    const roots: SessionThreadNode[] = [];
    sessions.forEach(session => {
        if (!attached.has(session.id)) {
            const node = nodes.get(session.id);
            if (node) roots.push(node);
        }
    });
    return sortSessionThreadNodes(roots);
};

// --- Sub-Components ---

const LogItemBlurb: React.FC<{
    log: SessionLog;
    formattedMessage?: TranscriptFormattedMessage;
    isSelected: boolean;
    onClick: () => void;
    fileCount?: number;
    artifactCount?: number;
    onShowFiles?: () => void;
    onShowArtifacts?: () => void;
    onOpenThread?: (threadId: string) => void;
}> = ({ log, formattedMessage, isSelected, onClick, fileCount = 0, artifactCount = 0, onShowFiles, onShowArtifacts, onOpenThread }) => {
    const isAgent = log.speaker === 'agent';
    const isUser = log.speaker === 'user';
    const isSystem = log.speaker === 'system';

    const renderMessagePreview = () => {
        const parsed = formattedMessage || parseTranscriptMessage(log.content);

        if (parsed.kind === 'claude-command') {
            const commandLabel = parsed.command?.name || parsed.command?.message || 'Command';
            return (
                <div className="space-y-1">
                    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-emerald-300/90 font-semibold">
                        <Terminal size={11} /> Command Invocation
                    </div>
                    <p className="font-mono text-xs line-clamp-1 break-all">{commandLabel}</p>
                    {parsed.command?.args && (
                        <p className="text-xs text-slate-400 whitespace-pre-wrap line-clamp-2 break-words">{parsed.command.args}</p>
                    )}
                </div>
            );
        }

        if (parsed.kind === 'claude-local-command-caveat') {
            return (
                <div className="space-y-1">
                    <div className="text-[10px] uppercase tracking-wider text-amber-300/90 font-semibold">Local Command Caveat</div>
                    <p className="text-xs leading-relaxed line-clamp-3 whitespace-pre-wrap break-words">{parsed.text || 'Caveat metadata'}</p>
                </div>
            );
        }

        if (parsed.kind === 'claude-local-command-stdout') {
            return (
                <div className="space-y-1">
                    <div className="text-[10px] uppercase tracking-wider text-sky-300/90 font-semibold">Local Command Output</div>
                    <p className="text-xs font-mono whitespace-pre-wrap line-clamp-2 break-words">
                        {parsed.text && parsed.text.trim() ? parsed.text : '(empty stdout)'}
                    </p>
                </div>
            );
        }

        if (parsed.kind === 'tagged') {
            return (
                <div className="space-y-2">
                    <div className="flex flex-wrap gap-1">
                        {parsed.tags.slice(0, 3).map(tag => (
                            <span key={`${log.id}-${tag.tag}-${tag.start}`} className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-slate-700 bg-slate-900/80 text-slate-400">
                                {getReadableTagName(tag.tag)}
                            </span>
                        ))}
                        {parsed.tags.length > 3 && (
                            <span className="text-[10px] text-slate-500">+{parsed.tags.length - 3} more</span>
                        )}
                    </div>
                    <p className="text-xs leading-relaxed whitespace-pre-wrap line-clamp-2 break-words">
                        {parsed.text || parsed.summary}
                    </p>
                </div>
            );
        }

        return <p className="line-clamp-3 leading-relaxed whitespace-pre-wrap break-words">{log.content}</p>;
    };

    if (log.type === 'message') {
        return (
            <div
                onClick={onClick}
                className={`group cursor-pointer flex gap-4 mb-4 px-2 py-1 rounded-xl transition-all ${isUser ? 'flex-row-reverse' : 'flex-row'} ${isSelected ? 'bg-indigo-500/10 ring-1 ring-indigo-500/30' : 'hover:bg-slate-800/30'
                    }`}
            >
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 border transition-colors ${isSelected
                    ? 'border-indigo-500 bg-indigo-500/20 text-indigo-400'
                    : isUser
                        ? 'bg-slate-800 border-slate-700 text-slate-400'
                        : isSystem
                            ? 'bg-slate-900 border-slate-700 text-slate-300'
                        : 'bg-indigo-500/10 border-indigo-500/20 text-indigo-400'
                    }`}>
                    {isUser ? <span className="text-xs font-bold">U</span> : isSystem ? <span className="text-xs font-bold">S</span> : <Bot size={16} />}
                </div>

                <div className={`flex flex-col min-w-0 flex-1 ${isUser ? 'items-end' : 'items-start'}`}>
                    {isAgent && log.agentName && (
                        <span className={`text-[10px] font-mono mb-1 px-1.5 py-0.5 rounded transition-colors ${isSelected ? 'text-indigo-300 bg-indigo-500/20' : 'text-indigo-400 bg-indigo-500/5'}`}>
                            {log.agentName}
                        </span>
                    )}
                    <div className={`p-3 rounded-xl text-sm transition-all border max-w-full ${isSelected
                        ? 'bg-transparent border-transparent text-indigo-100'
                        : isUser
                            ? 'bg-slate-800 border-slate-700 text-slate-300'
                            : isSystem
                                ? 'bg-slate-900/60 border-slate-700 text-slate-300'
                            : 'bg-slate-900 border-slate-800 text-slate-300'
                        }`}>
                        {renderMessagePreview()}
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                        {fileCount > 0 && (
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onShowFiles?.();
                                }}
                                className="text-[10px] px-2 py-0.5 rounded border border-blue-500/30 text-blue-300 bg-blue-500/10 hover:bg-blue-500/20"
                            >
                                Files: {fileCount}
                            </button>
                        )}
                        {artifactCount > 0 && (
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onShowArtifacts?.();
                                }}
                                className="text-[10px] px-2 py-0.5 rounded border border-amber-500/30 text-amber-300 bg-amber-500/10 hover:bg-amber-500/20"
                            >
                                Artifacts: {artifactCount}
                            </button>
                        )}
                    </div>
                </div>
            </div>
        );
    }

    const icons = {
        tool: <Terminal size={12} className="text-amber-500" />,
        subagent: <Zap size={12} className="text-purple-400" />,
        skill: <Cpu size={12} className="text-blue-400" />,
        thought: <MessageSquare size={12} className="text-slate-300" />,
        system: <ShieldAlert size={12} className="text-slate-400" />,
        command: <Terminal size={12} className="text-emerald-400" />,
        subagent_start: <Zap size={12} className="text-purple-300" />,
    };

    const label = log.type === 'tool' ? `Used Tool: ${log.toolCall?.name}` :
        log.type === 'subagent_start' ? `Sub-thread Started` :
            log.type === 'thought' ? 'Agent Thought' :
                log.type === 'system' ? 'System Event' :
                    log.type === 'command' ? `Command: ${log.content}` :
        log.type === 'subagent' ? `Spawned Agent: ${log.agentName || 'Subagent'}` :
            `Loaded Skill: ${log.skillDetails?.name}`;

    return (
        <div
            onClick={onClick}
            className={`cursor-pointer mb-2 ml-12 p-2 rounded-lg border transition-all flex items-center justify-between group ${isSelected
                ? 'bg-indigo-500/20 border-indigo-500/50 ring-1 ring-indigo-500/20'
                : 'bg-slate-950 border-slate-900 hover:border-slate-800'
                }`}
        >
            <div className="flex items-center gap-2 overflow-hidden">
                {icons[log.type as keyof typeof icons] || <Box size={12} />}
                <span className={`text-[11px] font-mono truncate transition-colors ${isSelected ? 'text-indigo-300' : 'text-slate-400'}`}>
                    {label}
                </span>
            </div>
            <div className="flex items-center gap-2">
                {log.linkedSessionId && (
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            onOpenThread?.(log.linkedSessionId!);
                        }}
                        className="text-[10px] px-1.5 py-0.5 rounded border border-indigo-500/30 text-indigo-300 bg-indigo-500/10 hover:bg-indigo-500/20"
                    >
                        Open Thread
                    </button>
                )}
                {fileCount > 0 && (
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            onShowFiles?.();
                        }}
                        className="text-[10px] px-1.5 py-0.5 rounded border border-blue-500/30 text-blue-300 bg-blue-500/10 hover:bg-blue-500/20"
                    >
                        F:{fileCount}
                    </button>
                )}
                {artifactCount > 0 && (
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            onShowArtifacts?.();
                        }}
                        className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/30 text-amber-300 bg-amber-500/10 hover:bg-amber-500/20"
                    >
                        A:{artifactCount}
                    </button>
                )}
                <ChevronRight size={12} className={`text-slate-600 transition-transform ${isSelected ? 'rotate-90 text-indigo-400' : 'group-hover:translate-x-0.5'}`} />
            </div>
        </div>
    );
};

const DetailPane: React.FC<{
    log: SessionLog;
    formattedMessage?: TranscriptFormattedMessage;
    commandArtifacts?: SessionArtifact[];
    onOpenArtifacts?: () => void;
}> = ({ log, formattedMessage, commandArtifacts = [], onOpenArtifacts }) => {
    const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());

    const toggleSection = (id: string) => {
        const next = new Set(expandedSections);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        setExpandedSections(next);
    };

    const parsedMessage = formattedMessage || parseTranscriptMessage(log.content);
    const detailTitle = (() => {
        if (log.type === 'subagent') return 'Subagent Thread';
        if (log.type === 'tool') return 'Tool Execution';
        if (log.type === 'subagent_start') return 'Subagent Start';
        if (log.type === 'message' && parsedMessage.kind === 'claude-command') return 'Command Message';
        return 'Log Details';
    })();

    const renderStructuredMessage = () => {
        if (parsedMessage.kind === 'claude-command') {
            const commandLabel = parsedMessage.command?.name || parsedMessage.command?.message || 'Unknown Command';
            return (
                <div className="bg-slate-900/30 border border-emerald-500/20 rounded-xl p-5 space-y-4">
                    <div className="flex items-start justify-between gap-3">
                        <div>
                            <div className="text-[10px] text-emerald-300 uppercase tracking-widest font-bold mb-2">Command</div>
                            <p className="font-mono text-sm text-emerald-200 break-all">{commandLabel}</p>
                        </div>
                        <span className="text-[10px] px-2 py-1 rounded border border-emerald-500/30 text-emerald-300 bg-emerald-500/10">
                            Claude Code
                        </span>
                    </div>

                    {parsedMessage.command?.args !== undefined && (
                        <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
                            <div className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-2">Command Args</div>
                            <pre className="text-xs text-slate-300 whitespace-pre-wrap break-words font-mono max-h-56 overflow-y-auto">
                                {parsedMessage.command.args || '(no args)'}
                            </pre>
                        </div>
                    )}

                    {commandArtifacts.length > 0 && (
                        <button
                            onClick={onOpenArtifacts}
                            className="text-xs px-3 py-1.5 rounded-lg border border-amber-500/30 text-amber-300 bg-amber-500/10 hover:bg-amber-500/20"
                        >
                            Open Command Artifact ({commandArtifacts.length})
                        </button>
                    )}
                </div>
            );
        }

        if (parsedMessage.kind === 'claude-local-command-caveat') {
            return (
                <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-5">
                    <div className="text-[10px] text-amber-300 uppercase tracking-widest font-bold mb-3">Local Command Caveat</div>
                    <p className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">
                        {parsedMessage.text || 'Caveat metadata'}
                    </p>
                </div>
            );
        }

        if (parsedMessage.kind === 'claude-local-command-stdout') {
            return (
                <div className="bg-sky-500/5 border border-sky-500/20 rounded-xl p-5">
                    <div className="text-[10px] text-sky-300 uppercase tracking-widest font-bold mb-3">Local Command Output</div>
                    <pre className="text-xs font-mono text-slate-300 whitespace-pre-wrap break-words max-h-80 overflow-y-auto">
                        {parsedMessage.text && parsedMessage.text.trim() ? parsedMessage.text : '(empty stdout)'}
                    </pre>
                </div>
            );
        }

        if (parsedMessage.kind === 'tagged') {
            return (
                <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5 space-y-4">
                    <div className="flex flex-wrap gap-2">
                        {parsedMessage.tags.map(tag => (
                            <span
                                key={`${tag.tag}-${tag.start}`}
                                className="text-[10px] font-mono px-2 py-0.5 rounded border border-slate-700 bg-slate-900 text-slate-400"
                            >
                                {getReadableTagName(tag.tag)}
                            </span>
                        ))}
                    </div>
                    {parsedMessage.text && (
                        <p className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed break-words">{parsedMessage.text}</p>
                    )}
                </div>
            );
        }

        return (
            <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5">
                <p className="text-slate-300 leading-relaxed whitespace-pre-wrap text-sm">{log.content}</p>
            </div>
        );
    };

    const renderRawMessageSection = () => {
        if (parsedMessage.kind === 'plain') {
            return null;
        }
        const rawSectionId = `raw-${parsedMessage.kind}`;
        return (
            <div className="bg-slate-950/50 border border-slate-800 rounded-xl p-4">
                <button
                    onClick={() => toggleSection(rawSectionId)}
                    className="w-full flex justify-between items-center text-[10px] text-slate-500 uppercase font-bold tracking-wider hover:text-slate-300 transition-colors"
                >
                    <span>{expandedSections.has(rawSectionId) ? 'Hide Raw' : 'View Raw...'}</span>
                    {expandedSections.has(rawSectionId) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>
                {expandedSections.has(rawSectionId) && (
                    <pre className="mt-3 text-xs font-mono text-slate-300 bg-slate-900/70 p-3 rounded border border-slate-800 whitespace-pre-wrap break-words max-h-96 overflow-y-auto animate-in fade-in slide-in-from-top-1 duration-200">
                        {parsedMessage.rawText}
                    </pre>
                )}
            </div>
        );
    };

    return (
        <div className="flex flex-col h-full animate-in fade-in slide-in-from-right-2 duration-300">
            <div className="p-4 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-lg shadow-inner">
                        {log.type === 'tool'
                            ? <Terminal size={16} />
                            : log.type === 'subagent' || log.type === 'subagent_start'
                                ? <Zap size={16} />
                                : log.type === 'skill'
                                    ? <Cpu size={16} />
                                    : <MessageSquare size={16} />}
                    </div>
                    <div>
                        <h4 className="text-sm font-bold text-slate-100 uppercase tracking-tight">
                            {detailTitle}
                        </h4>
                        <p className="text-[10px] text-slate-500 font-mono">{log.timestamp}</p>
                    </div>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* TOOL DETAILS WITH INLINE EXPANSION */}
                {log.type === 'tool' && log.toolCall && (
                    <div className="space-y-4">
                        <div className="bg-slate-950 rounded-xl border border-slate-800 overflow-hidden">
                            <div className="px-4 py-3 bg-slate-900 border-b border-slate-800 flex justify-between items-center">
                                <span className="text-xs font-mono text-amber-500 flex items-center gap-2">
                                    <Terminal size={14} /> {log.toolCall.name}
                                </span>
                                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${log.toolCall.status === 'success' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'}`}>
                                    {log.toolCall.status.toUpperCase()}
                                </span>
                            </div>

                            {/* Arguments Section */}
                            <div className="p-4 border-b border-slate-800">
                                <button
                                    onClick={() => toggleSection('args')}
                                    className="w-full flex justify-between items-center text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-2 hover:text-slate-300 transition-colors"
                                >
                                    <span>Arguments</span>
                                    {expandedSections.has('args') ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                </button>
                                {expandedSections.has('args') && (
                                    <pre className="text-xs font-mono text-slate-300 bg-slate-900/50 p-3 rounded border border-slate-800 overflow-x-auto animate-in slide-in-from-top-1 duration-200">
                                        {log.toolCall.args}
                                    </pre>
                                )}
                            </div>

                            {/* Output Section */}
                            {log.toolCall.output && (
                                <div className="p-4 bg-slate-900/20">
                                    <button
                                        onClick={() => toggleSection('output')}
                                        className="w-full flex justify-between items-center text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-2 hover:text-slate-300 transition-colors"
                                    >
                                        <span>Output</span>
                                        {expandedSections.has('output') ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                    </button>
                                    {expandedSections.has('output') && (
                                        <pre className="text-xs font-mono text-slate-400 overflow-x-auto whitespace-pre-wrap animate-in slide-in-from-top-1 duration-200">
                                            {log.toolCall.output}
                                        </pre>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* SUBAGENT THREAD DETAILS */}
                {log.type === 'subagent' && log.subagentThread && (
                    <div className="space-y-4">
                        <div className="border-l-2 border-indigo-500/30 pl-4 space-y-4">
                            {log.subagentThread.map((sl, idx) => (
                                <div
                                    key={sl.id}
                                    onClick={() => toggleSection(`sub-${sl.id}`)}
                                    className="bg-slate-900/50 rounded-lg p-3 border border-slate-800 cursor-pointer hover:border-slate-700 transition-all"
                                >
                                    <div className="flex justify-between items-center mb-2">
                                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${sl.speaker === 'user' ? 'bg-slate-800 text-slate-400' : 'bg-indigo-500/10 text-indigo-400'}`}>
                                            {sl.speaker.toUpperCase()}
                                        </span>
                                        <div className="flex items-center gap-2">
                                            <span className="text-[9px] text-slate-600 font-mono">{sl.timestamp}</span>
                                            {expandedSections.has(`sub-${sl.id}`) ? <ChevronDown size={12} className="text-slate-500" /> : <ChevronRight size={12} className="text-slate-500" />}
                                        </div>
                                    </div>
                                    <p className={`text-xs text-slate-300 ${expandedSections.has(`sub-${sl.id}`) ? '' : 'line-clamp-2'}`}>{sl.content}</p>
                                    {expandedSections.has(`sub-${sl.id}`) && sl.toolCall && (
                                        <div className="mt-3 text-[10px] font-mono text-amber-500 bg-amber-500/5 p-2 rounded border border-amber-500/10 animate-in fade-in duration-200">
                                            <div className="mb-1 flex justify-between">
                                                <span>{'>'} {sl.toolCall.name}</span>
                                                <span className="opacity-50">{sl.toolCall.status}</span>
                                            </div>
                                            <div className="text-slate-500 truncate">{sl.toolCall.args}</div>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* FALLBACK FOR REGULAR/TYPED MESSAGES */}
                {log.type !== 'tool' && log.type !== 'subagent' && log.type !== 'skill' && (
                    <>
                        {renderStructuredMessage()}
                        {renderRawMessageSection()}
                        {log.linkedSessionId && (
                            <p className="text-[11px] text-indigo-300 font-mono">Linked Thread: {log.linkedSessionId}</p>
                        )}
                    </>
                )}

                {/* SKILLS */}
                {log.type === 'skill' && log.skillDetails && (
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                        <div className="flex items-center gap-2 text-blue-400 font-mono text-sm mb-3">
                            <Cpu size={16} /> {log.skillDetails.name}
                        </div>
                        <p className="text-slate-400 text-xs mb-4 leading-relaxed">{log.skillDetails.description}</p>
                        <div className="flex items-center justify-between text-[10px] border-t border-slate-800 pt-3">
                            <span className="text-slate-500">Version</span>
                            <span className="font-mono text-slate-300">{log.skillDetails.version}</span>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

// --- View Components ---

const TranscriptView: React.FC<{
    session: AgentSession;
    selectedLogId: string | null;
    setSelectedLogId: (id: string | null) => void;
    filterAgent?: string | null;
    threadSessions: AgentSession[];
    subagentNameBySessionId: Map<string, string>;
    onOpenThread: (sessionId: string) => void;
    onShowLinked: (tab: 'activity' | 'artifacts', sourceLogId: string) => void;
    primaryFeatureLink?: SessionFeatureLink | null;
    onOpenFeature?: (featureId: string) => void;
    onOpenForensics?: () => void;
}> = ({ session, selectedLogId, setSelectedLogId, filterAgent, threadSessions, subagentNameBySessionId, onOpenThread, onShowLinked, primaryFeatureLink, onOpenFeature, onOpenForensics }) => {

    const logs = filterAgent
        ? session.logs.filter(l => l.agentName === filterAgent || l.speaker === 'user' || l.speaker === 'system')
        : session.logs;

    const selectedLog = logs.find(l => l.id === selectedLogId);
    const threadLinks = threadSessions.filter(t => t.id !== session.id);

    const filesByLogId = useMemo(() => {
        const map = new Map<string, number>();
        (session.updatedFiles || []).forEach(file => {
            if (!file.sourceLogId) return;
            map.set(file.sourceLogId, (map.get(file.sourceLogId) || 0) + 1);
        });
        return map;
    }, [session.updatedFiles]);

    const formattedMessagesByLogId = useMemo(() => {
        const map = new Map<string, TranscriptFormattedMessage>();
        logs.forEach(log => {
            if (log.type === 'message') {
                map.set(log.id, parseTranscriptMessage(log.content));
            }
        });
        return map;
    }, [logs]);

    const artifactsByLogId = useMemo(() => {
        const map = new Map<string, SessionArtifact[]>();
        (session.linkedArtifacts || []).forEach(artifact => {
            if (!artifact.sourceLogId) return;
            const existing = map.get(artifact.sourceLogId);
            if (existing) {
                existing.push(artifact);
            } else {
                map.set(artifact.sourceLogId, [artifact]);
            }
        });
        return map;
    }, [session.linkedArtifacts]);

    const selectedCommandArtifacts = useMemo(() => {
        if (!selectedLog) {
            return [];
        }
        return (artifactsByLogId.get(selectedLog.id) || []).filter(artifact => artifact.type === 'command');
    }, [artifactsByLogId, selectedLog]);
    const commitHashes = useMemo(() => collectSessionCommitHashes(session), [session]);
    const displayedCommitHashes = commitHashes.slice(0, 6);
    const hiddenCommitCount = Math.max(0, commitHashes.length - displayedCommitHashes.length);
    const platformType = (session.platformType || '').trim() || 'Claude Code';
    const platformVersions = useMemo(() => {
        const values: string[] = [];
        (session.platformVersions || []).forEach(value => {
            const normalized = String(value || '').trim();
            if (normalized && !values.includes(normalized)) values.push(normalized);
        });
        const primary = (session.platformVersion || '').trim();
        if (primary && !values.includes(primary)) values.push(primary);
        return values;
    }, [session.platformVersion, session.platformVersions]);
    const latestPlatformVersion = platformVersions[platformVersions.length - 1] || '';
    const platformVersionTransitions = useMemo(() => (
        (session.platformVersionTransitions || [])
            .filter(event => event && event.fromVersion && event.toVersion)
    ), [session.platformVersionTransitions]);
    const sessionForensics = useMemo(() => asRecord(session.sessionForensics), [session.sessionForensics]);
    const forensicsThinking = useMemo(() => asRecord(sessionForensics.thinking), [sessionForensics]);
    const forensicsEntryContext = useMemo(() => asRecord(sessionForensics.entryContext), [sessionForensics]);
    const forensicsSidecars = useMemo(() => asRecord(sessionForensics.sidecars), [sessionForensics]);
    const thinkingLevel = takeString(forensicsThinking.level, session.thinkingLevel)?.toUpperCase() || 'Unknown';
    const permissionModes = useMemo(
        () => asStringArray(forensicsEntryContext.permissionModes),
        [forensicsEntryContext]
    );
    const requestIds = useMemo(
        () => asStringArray(forensicsEntryContext.requestIds),
        [forensicsEntryContext]
    );
    const queueOperations = useMemo(
        () => (Array.isArray(forensicsEntryContext.queueOperations) ? forensicsEntryContext.queueOperations : []),
        [forensicsEntryContext]
    );
    const apiErrors = useMemo(
        () => (Array.isArray(forensicsEntryContext.apiErrors) ? forensicsEntryContext.apiErrors : []),
        [forensicsEntryContext]
    );
    const todosSidecar = useMemo(() => asRecord(forensicsSidecars.todos), [forensicsSidecars]);
    const tasksSidecar = useMemo(() => asRecord(forensicsSidecars.tasks), [forensicsSidecars]);
    const teamsSidecar = useMemo(() => asRecord(forensicsSidecars.teams), [forensicsSidecars]);
    const todosCount = asNumber(todosSidecar.totalItems, 0);
    const tasksCount = Array.isArray(tasksSidecar.tasks) ? tasksSidecar.tasks.length : asNumber(tasksSidecar.taskFileCount, 0);
    const teamMessagesCount = asNumber(teamsSidecar.totalMessages, 0);
    const teamUnreadCount = asNumber(teamsSidecar.unreadMessages, 0);
    const hasDetailedForensics = Object.keys(sessionForensics).length > 0;

    return (
        <div className="flex-1 flex gap-4 min-h-0 min-w-full h-full">
            {/* Pane 1: Chat Transcript (Left) */}
            <div
                className={`flex flex-col bg-slate-900/50 border border-slate-800 rounded-2xl overflow-hidden transition-all duration-500 ease-out ${selectedLogId ? 'basis-[30%] min-w-[320px] max-w-[520px]' : 'flex-1 min-w-[420px]'
                    }`}
            >
                <div className="p-4 border-b border-slate-800 bg-slate-950/50 flex items-center justify-between">
                    <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
                        <MessageSquare size={14} className="text-indigo-400" /> {filterAgent ? `Transcript: ${filterAgent}` : 'Full Transcript'}
                    </h3>
                    <div className="text-[10px] text-slate-600 font-mono">{logs.length} Steps</div>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-2 custom-scrollbar">
                    {logs.map(log => (
                        <LogItemBlurb
                            key={log.id}
                            log={log}
                            formattedMessage={formattedMessagesByLogId.get(log.id)}
                            isSelected={selectedLogId === log.id}
                            onClick={() => setSelectedLogId(log.id === selectedLogId ? null : log.id)}
                            fileCount={filesByLogId.get(log.id) || 0}
                            artifactCount={(artifactsByLogId.get(log.id) || []).length}
                            onShowFiles={() => onShowLinked('activity', log.id)}
                            onShowArtifacts={() => onShowLinked('artifacts', log.id)}
                            onOpenThread={onOpenThread}
                        />
                    ))}
                    {logs.length === 0 && <div className="p-8 text-center text-slate-500 italic">No logs found for this view.</div>}
                </div>
            </div>

            {/* Pane 2: Expanded Details (Middle) - Dynamic visibility */}
            {selectedLogId && (
                <div className="flex-1 min-w-[420px] flex flex-col bg-slate-900 border border-indigo-500/20 rounded-2xl overflow-hidden shadow-2xl animate-in fade-in slide-in-from-right-4 duration-300">
                    {selectedLog && (
                        <DetailPane
                            log={selectedLog}
                            formattedMessage={formattedMessagesByLogId.get(selectedLog.id)}
                            commandArtifacts={selectedCommandArtifacts}
                            onOpenArtifacts={() => onShowLinked('artifacts', selectedLog.id)}
                        />
                    )}
                </div>
            )}

            {/* Pane 3: Metadata Details (Far Right) - Smaller fixed-ish width */}
            <div className="w-[260px] min-w-[220px] max-w-[300px] flex flex-col gap-5 overflow-y-auto pb-4 shrink-0">
                {/* Key Metadata */}
                {(primaryFeatureLink || session.sessionMetadata) && (
                    <div className="bg-slate-900 border border-emerald-500/30 rounded-2xl p-5 shadow-sm space-y-3">
                        <h3 className="text-xs font-bold text-emerald-300 uppercase tracking-widest">Key Metadata</h3>

                        {session.sessionMetadata && (
                            <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 space-y-2">
                                <div className="text-[10px] text-emerald-200/80 uppercase tracking-wide">Session Type</div>
                                <div className="text-sm font-semibold text-emerald-100">
                                    {session.sessionMetadata.sessionTypeLabel || 'Unclassified'}
                                </div>
                                <div className="space-y-1.5">
                                    {session.sessionMetadata.fields.map(field => (
                                        <div key={`${session.sessionMetadata?.mappingId}-${field.id}`} className="text-xs">
                                            <div className="text-[10px] text-emerald-200/70 uppercase tracking-wide">{field.label}</div>
                                            <div className="text-slate-200 font-mono text-[11px] break-words">{field.value}</div>
                                        </div>
                                    ))}
                                    {primaryFeatureLink && (
                                        <div className="text-xs">
                                            <div className="text-[10px] text-emerald-200/70 uppercase tracking-wide">Linked Feature</div>
                                            <button
                                                onClick={() => onOpenFeature?.(primaryFeatureLink.featureId)}
                                                className="text-indigo-300 hover:text-indigo-200 font-semibold truncate max-w-full text-left"
                                            >
                                                {primaryFeatureLink.featureName || primaryFeatureLink.featureId}
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {primaryFeatureLink && (
                            <button
                                onClick={() => onOpenFeature?.(primaryFeatureLink.featureId)}
                                className="w-full text-left rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 hover:bg-emerald-500/15 transition-colors"
                            >
                                <div className="text-[10px] text-emerald-200/80 uppercase tracking-wide">Primary Feature Link</div>
                                <div className="text-sm font-semibold text-emerald-100 truncate mt-1">
                                    {primaryFeatureLink.featureName || primaryFeatureLink.featureId}
                                </div>
                                <div className="mt-2 flex flex-wrap items-center gap-2">
                                    <span className="text-[10px] font-mono text-emerald-200 border border-emerald-500/30 px-1.5 py-0.5 rounded">
                                        {Math.round(primaryFeatureLink.confidence * 100)}% confidence
                                    </span>
                                    {primaryFeatureLink.linkStrategy && (
                                        <span className="text-[10px] text-emerald-100/80 border border-emerald-500/20 px-1.5 py-0.5 rounded">
                                            {formatSessionReason(primaryFeatureLink.linkStrategy)}
                                        </span>
                                    )}
                                </div>
                            </button>
                        )}
                    </div>
                )}

                {/* Performance Summary */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Forensics</h3>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-xs text-slate-400"><Clock size={14} /> Duration</div>
                            <span className="text-xs font-mono text-slate-200">{session.durationSeconds}s</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-xs text-slate-400"><Database size={14} /> Tokens</div>
                            <span className="text-xs font-mono text-slate-200">{(session.tokensIn + session.tokensOut).toLocaleString()}</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-xs text-slate-400"><Code size={14} /> Base Model</div>
                            <span
                                className="text-[10px] font-mono text-indigo-400 truncate max-w-[140px]"
                                title={session.model}
                            >
                                {formatModelDisplayName(session.model, session.modelDisplayName)}
                            </span>
                        </div>
                        <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2 text-xs text-slate-400"><Cpu size={14} /> Platform</div>
                            <span
                                className="text-[10px] font-mono text-amber-300 truncate max-w-[140px]"
                                title={`${platformType}${latestPlatformVersion ? ` ${latestPlatformVersion}` : ''}`}
                            >
                                {latestPlatformVersion ? `${platformType} ${latestPlatformVersion}` : platformType}
                            </span>
                        </div>
                        {platformVersions.length > 1 && (
                            <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-800/60">
                                {platformVersions.length} versions seen in this session
                            </div>
                        )}
                        {platformVersionTransitions.length > 0 && (
                            <div className="pt-2 border-t border-slate-800/60 space-y-1.5">
                                <div className="text-[9px] uppercase tracking-wider text-slate-500">Version Changes</div>
                                {platformVersionTransitions.map((transition, idx) => (
                                    <div key={`${transition.timestamp}-${idx}`} className="text-[10px] font-mono text-slate-300">
                                        <span className="text-slate-500">{formatTimeAgo(transition.timestamp)}:</span>{' '}
                                        {transition.fromVersion} {'->'} {transition.toVersion}
                                    </div>
                                ))}
                            </div>
                        )}
                        <div className="pt-2 border-t border-slate-800/60 space-y-2">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-slate-400"><Bot size={14} /> Thinking</div>
                                <span className="text-[10px] font-mono text-fuchsia-300">{thinkingLevel}</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-slate-400"><Terminal size={14} /> Request IDs</div>
                                <span className="text-[10px] font-mono text-slate-200">{requestIds.length}</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-slate-400"><Scroll size={14} /> Queue Ops</div>
                                <span className="text-[10px] font-mono text-slate-200">{queueOperations.length}</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-slate-400"><HardDrive size={14} /> Sidecars</div>
                                <span className="text-[10px] font-mono text-slate-200" title={`Todos ${todosCount} · Tasks ${tasksCount} · Team ${teamMessagesCount}`}>
                                    {todosCount}/{tasksCount}/{teamMessagesCount}
                                </span>
                            </div>
                            {teamUnreadCount > 0 && (
                                <div className="text-[10px] text-amber-300 font-mono">Team unread: {teamUnreadCount}</div>
                            )}
                            {permissionModes.length > 0 && (
                                <div className="pt-1">
                                    <div className="text-[9px] uppercase tracking-wider text-slate-500 mb-1">Permission Modes</div>
                                    <div className="flex flex-wrap gap-1">
                                        {permissionModes.slice(0, 3).map(mode => (
                                            <span key={mode} className="text-[9px] px-1.5 py-0.5 rounded border border-slate-700 text-slate-300 font-mono">
                                                {mode}
                                            </span>
                                        ))}
                                        {permissionModes.length > 3 && (
                                            <span className="text-[9px] px-1.5 py-0.5 rounded border border-slate-700 text-slate-500">
                                                +{permissionModes.length - 3}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            )}
                            {apiErrors.length > 0 && (
                                <div className="text-[10px] text-rose-300 font-mono">API errors captured: {apiErrors.length}</div>
                            )}
                            {hasDetailedForensics && onOpenForensics && (
                                <button
                                    onClick={onOpenForensics}
                                    className="w-full mt-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-1.5 rounded-md border border-indigo-500/30 bg-indigo-500/10 text-indigo-200 hover:bg-indigo-500/20 transition-colors"
                                >
                                    Open Full Forensics
                                </button>
                            )}
                        </div>
                    </div>
                </div>

                {/* Git Context */}
                {(commitHashes.length > 0 || (session.gitBranch && session.gitBranch.trim())) && (
                    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
                        <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Version Control</h3>
                        <div className="space-y-4">
                            {displayedCommitHashes.length > 0 && (
                                <div className="group">
                                    <div className="text-[9px] text-slate-600 uppercase font-bold mb-1 group-hover:text-slate-400 transition-colors">
                                        Commit{commitHashes.length === 1 ? '' : 's'}
                                    </div>
                                    <div className="flex flex-wrap items-center gap-1.5">
                                        {displayedCommitHashes.map(commit => (
                                            <span
                                                key={commit}
                                                title={commit}
                                                className="inline-flex items-center gap-1 text-[10px] font-mono text-indigo-300 bg-indigo-500/10 px-1.5 py-0.5 rounded border border-indigo-500/20"
                                            >
                                                <GitCommit size={10} /> {toShortCommitHash(commit)}
                                            </span>
                                        ))}
                                        {hiddenCommitCount > 0 && (
                                            <span className="text-[10px] font-mono text-slate-400">
                                                +{hiddenCommitCount} more
                                            </span>
                                        )}
                                    </div>
                                </div>
                            )}
                            {session.gitBranch && session.gitBranch.trim() && (
                                <div className="group">
                                    <div className="text-[9px] text-slate-600 uppercase font-bold mb-1">Branch</div>
                                    <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
                                        <GitBranch size={14} className="text-slate-500" /> {session.gitBranch}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Tool Breakdown */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 flex-1 shadow-sm">
                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Tool Efficiency</h3>
                    <div className="space-y-5">
                        {session.toolsUsed.map(tool => (
                            <div key={tool.name} className="space-y-1.5">
                                <div className="flex justify-between items-center text-[11px] font-mono">
                                    <span className="text-slate-400">{tool.name}</span>
                                    <span className="text-slate-300 font-bold">{tool.count}</span>
                                </div>
                                <div className="w-full bg-slate-950 h-1.5 rounded-full overflow-hidden border border-slate-800/50">
                                    <div
                                        className={`h-full transition-all duration-1000 ${tool.successRate > 0.9 ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.3)]' : 'bg-amber-500'}`}
                                        style={{ width: `${tool.successRate * 100}%` }}
                                    />
                                </div>
                                <div className="flex justify-end">
                                    <span className="text-[9px] text-slate-600 font-mono">{(tool.successRate * 100).toFixed(0)}% SR</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Linked Sub-Threads */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Linked Sub-Threads</h3>
                    <div className="space-y-2 max-h-56 overflow-y-auto">
                        {threadLinks.length === 0 && (
                            <div className="text-xs text-slate-500">No linked sub-threads found.</div>
                        )}
                        {threadLinks.map(thread => (
                            <button
                                key={thread.id}
                                onClick={() => onOpenThread(thread.id)}
                                className="w-full text-left p-2 rounded-lg border border-slate-800 bg-slate-950 hover:border-indigo-500/40 transition-colors"
                            >
                                <div className="text-[11px] font-mono text-indigo-300 truncate">{thread.id}</div>
                                <div className="text-[10px] text-slate-500 mt-1">
                                    {getThreadDisplayName(thread, subagentNameBySessionId)}
                                </div>
                            </button>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
};

const SessionFeaturesView: React.FC<{
    linkedFeatures: SessionFeatureLink[];
    onOpenFeature: (featureId: string) => void;
}> = ({ linkedFeatures, onOpenFeature }) => {
    const grouped = useMemo(() => {
        const primary = linkedFeatures.filter(feature => feature.isPrimaryLink);
        const related = linkedFeatures.filter(feature => !feature.isPrimaryLink);
        return { primary, related };
    }, [linkedFeatures]);

    const renderFeatureCard = (feature: SessionFeatureLink) => {
        const pct = feature.totalTasks > 0
            ? Math.round((feature.completedTasks / feature.totalTasks) * 100)
            : 0;
        return (
            <div key={feature.featureId} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                        <div className="text-sm font-semibold text-slate-100 truncate">
                            {feature.featureName || feature.featureId}
                        </div>
                        <button
                            onClick={() => onOpenFeature(feature.featureId)}
                            className="text-[11px] font-mono text-indigo-300 hover:text-indigo-200 transition-colors"
                        >
                            {feature.featureId}
                        </button>
                    </div>
                    <span className="text-[10px] px-1.5 py-0.5 rounded border border-indigo-500/30 bg-indigo-500/10 text-indigo-300">
                        {Math.round(feature.confidence * 100)}% confidence
                    </span>
                </div>

                <div className="mt-3 flex items-center gap-2 text-[10px]">
                    <span className={`px-1.5 py-0.5 rounded border ${feature.isPrimaryLink ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10' : 'border-slate-700 text-slate-400 bg-slate-800/60'}`}>
                        {feature.isPrimaryLink ? 'Primary' : 'Related'}
                    </span>
                    {feature.featureStatus && (
                        <span className="px-1.5 py-0.5 rounded border border-slate-700 text-slate-300 bg-slate-800/60 capitalize">
                            {feature.featureStatus}
                        </span>
                    )}
                    {feature.featureCategory && (
                        <span className="px-1.5 py-0.5 rounded border border-purple-500/30 text-purple-300 bg-purple-500/10 capitalize">
                            {feature.featureCategory}
                        </span>
                    )}
                    {feature.linkStrategy && (
                        <span className="px-1.5 py-0.5 rounded border border-slate-700 text-slate-400 bg-slate-800/60">
                            {formatSessionReason(feature.linkStrategy)}
                        </span>
                    )}
                </div>

                {feature.reasons.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5 text-[10px] text-slate-500">
                        {feature.reasons.slice(0, 5).map(reason => (
                            <span key={`${feature.featureId}-${reason}`} className="px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800/60">
                                {formatSessionReason(reason)}
                            </span>
                        ))}
                    </div>
                )}

                <div className="mt-3">
                    <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
                        <span>Feature Progress</span>
                        <span className="font-mono">{feature.completedTasks}/{feature.totalTasks}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-slate-800 overflow-hidden">
                        <div
                            className="h-full rounded-full bg-indigo-500"
                            style={{ width: `${pct}%` }}
                        />
                    </div>
                </div>
            </div>
        );
    };

    if (linkedFeatures.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
                <Box size={42} className="mb-3 opacity-30" />
                <p className="text-sm">No linked features found for this session.</p>
                <p className="text-xs mt-1 text-slate-600">No high-confidence feature evidence has been detected yet.</p>
            </div>
        );
    }

    return (
        <div className="h-full overflow-y-auto pr-1 space-y-5">
            <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
                <div className="flex items-center justify-between">
                    <div className="text-xs font-bold uppercase tracking-wider text-emerald-300">Primary Feature Links</div>
                    <div className="text-[11px] text-emerald-200/80">{grouped.primary.length}</div>
                </div>
                <p className="text-[11px] text-emerald-200/70 mt-1">Likely primary features this session directly worked on.</p>
            </div>

            {grouped.primary.length > 0 && grouped.primary.map(renderFeatureCard)}
            {grouped.primary.length === 0 && (
                <div className="text-xs text-slate-500 border border-dashed border-slate-800 rounded-lg p-4">
                    No primary links yet. Related feature matches are shown below.
                </div>
            )}

            {grouped.related.length > 0 && (
                <div className="space-y-3 pt-2">
                    <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Related Feature Links</div>
                    {grouped.related.map(renderFeatureCard)}
                </div>
            )}
        </div>
    );
};

const collectThreadDetailSessions = (
    session: AgentSession,
    threadSessions: AgentSession[],
    threadSessionDetails: Record<string, AgentSession>,
): AgentSession[] => {
    const byId = new Map<string, AgentSession>();
    byId.set(session.id, session);
    threadSessions.forEach(thread => {
        const detail = threadSessionDetails[thread.id] || (thread.id === session.id ? session : null);
        if (detail) byId.set(thread.id, detail);
    });
    return Array.from(byId.values());
};

const ActivityView: React.FC<{
    session: AgentSession;
    threadSessions: AgentSession[];
    threadSessionDetails: Record<string, AgentSession>;
    subagentNameBySessionId: Map<string, string>;
    onOpenDoc: (doc: PlanDocument) => void;
    onOpenThread: (sessionId: string) => void;
    highlightedSourceLogId?: string | null;
}> = ({ session, threadSessions, threadSessionDetails, subagentNameBySessionId, onOpenDoc, onOpenThread, highlightedSourceLogId }) => {
    const { documents, activeProject } = useData();
    const sessionsForActivity = useMemo(
        () => collectThreadDetailSessions(session, threadSessions, threadSessionDetails),
        [session, threadSessions, threadSessionDetails]
    );

    const resolveDocument = useCallback((path: string): PlanDocument | null => {
        const normalized = normalizePath(path);
        for (const doc of documents) {
            const docPath = normalizePath(doc.filePath);
            if (normalized === docPath || normalized.endsWith(`/${docPath}`) || docPath.endsWith(`/${normalized}`)) {
                return doc;
            }
        }
        return null;
    }, [documents]);

    const activityRows = useMemo(() => {
        const rows: SessionActivityItem[] = [];

        for (const thread of sessionsForActivity) {
            const threadName = getThreadDisplayName(thread, subagentNameBySessionId);
            const logsById = new Map<string, SessionLog>();
            thread.logs.forEach(log => logsById.set(log.id, log));
            const commitEvents = collectCommitEvents(thread);

            thread.logs.forEach(log => {
                const label = log.type === 'tool'
                    ? `Tool: ${log.toolCall?.name || 'tool'}`
                    : log.type === 'subagent_start'
                        ? 'Subagent Started'
                        : log.type === 'subagent'
                            ? `Subagent: ${log.agentName || 'agent'}`
                            : log.type === 'skill'
                                ? `Skill: ${log.skillDetails?.name || 'skill'}`
                                : log.type === 'thought'
                                    ? 'Thought'
                                    : log.type === 'system'
                                        ? 'System'
                                        : log.type === 'command'
                                            ? `Command: ${log.content}`
                                            : 'Message';
                rows.push({
                    id: `${thread.id}:log:${log.id}`,
                    kind: 'log',
                    timestamp: log.timestamp,
                    sourceLogId: log.id,
                    sessionId: thread.id,
                    threadName,
                    label,
                    detail: log.content,
                    linkedSessionId: log.linkedSessionId,
                });
            });

            (thread.updatedFiles || []).forEach((file: SessionFileUpdate, idx: number) => {
                const action = normalizeFileAction(file.action, file.sourceToolName);
                if (action === 'other') return;
                const filePath = normalizePath(file.filePath);
                if (!filePath) return;

                const doc = resolveDocument(filePath);
                const localPath = resolveLocalPath(filePath, activeProject?.path);
                const fileLogIndex = parseLogIndex(file.sourceLogId);
                const fileTs = toEpoch(file.timestamp);
                let commitHash = '';
                let nearestAfter: CommitEvent | null = null;
                let nearestBefore: CommitEvent | null = null;
                for (const event of commitEvents) {
                    const compareByIndex = fileLogIndex >= 0 && event.logIndex >= 0;
                    const isAfter = compareByIndex ? event.logIndex >= fileLogIndex : event.timestampMs >= fileTs;
                    const isBefore = compareByIndex ? event.logIndex <= fileLogIndex : event.timestampMs <= fileTs;
                    if (isAfter && !nearestAfter) nearestAfter = event;
                    if (isBefore) nearestBefore = event;
                }
                if (nearestAfter) commitHash = nearestAfter.hash;
                else if (nearestBefore) commitHash = nearestBefore.hash;
                else if (thread.gitCommitHash) commitHash = thread.gitCommitHash;

                rows.push({
                    id: `${thread.id}:file:${file.sourceLogId || idx}:${filePath}`,
                    kind: 'file',
                    timestamp: file.timestamp || '',
                    sourceLogId: file.sourceLogId,
                    sessionId: thread.id,
                    threadName,
                    label: `${formatAction(action)} ${filePath}`,
                    detail: file.fileType || 'Other',
                    action,
                    filePath,
                    fileType: file.fileType || 'Other',
                    localPath,
                    documentId: doc?.id,
                    githubUrl: commitHash ? toGitHubBlobUrl(activeProject?.repoUrl || '', commitHash, filePath, activeProject?.path) : null,
                    additions: file.additions || 0,
                    deletions: file.deletions || 0,
                });
            });

            (thread.linkedArtifacts || []).forEach((artifact, idx) => {
                const sourceLog = artifact.sourceLogId ? logsById.get(artifact.sourceLogId) : undefined;
                rows.push({
                    id: `${thread.id}:artifact:${artifact.id || idx}`,
                    kind: 'artifact',
                    timestamp: sourceLog?.timestamp || thread.startedAt,
                    sourceLogId: artifact.sourceLogId,
                    sessionId: thread.id,
                    threadName,
                    label: artifact.title || artifact.type || 'Artifact',
                    detail: artifact.source || artifact.type || '',
                    artifactType: artifact.type,
                    artifactUrl: artifact.url,
                });
            });
        }

        return rows.sort((a, b) => {
            const ta = toEpoch(a.timestamp);
            const tb = toEpoch(b.timestamp);
            if (ta !== tb) return tb - ta;
            return a.id.localeCompare(b.id);
        });
    }, [activeProject?.path, activeProject?.repoUrl, resolveDocument, sessionsForActivity, subagentNameBySessionId]);

    if (activityRows.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
                <Activity size={48} className="mb-4 opacity-20" />
                <p>No activity entries found for this thread family.</p>
            </div>
        );
    }

    const openRowFile = (row: SessionActivityItem) => {
        if (!row.filePath || !row.localPath) return;
        if (row.documentId) {
            const doc = documents.find(item => item.id === row.documentId);
            if (doc) {
                onOpenDoc(doc);
                return;
            }
        }
        window.location.href = `vscode://file/${encodeURI(row.localPath)}`;
    };

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden h-full flex flex-col">
            <div className="grid grid-cols-[170px_90px_1fr_130px_160px] gap-2 px-3 py-2 border-b border-slate-800 bg-slate-950/60 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                <div>Timestamp</div>
                <div>Type</div>
                <div>Entry</div>
                <div>Thread</div>
                <div>Links</div>
            </div>
            <div className="flex-1 overflow-y-auto">
                {activityRows.map(row => (
                    <div
                        key={row.id}
                        className={`grid grid-cols-[170px_90px_1fr_130px_160px] gap-2 px-3 py-2 border-b border-slate-800/70 text-xs hover:bg-slate-800/30 ${highlightedSourceLogId && row.sourceLogId === highlightedSourceLogId ? 'bg-indigo-500/10 border-indigo-500/30' : ''}`}
                    >
                        <div className="text-slate-500 text-[11px]">{row.timestamp ? new Date(row.timestamp).toLocaleString() : '—'}</div>
                        <div>
                            <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] ${row.kind === 'file' ? 'border-blue-500/30 bg-blue-500/10 text-blue-300' : row.kind === 'artifact' ? 'border-amber-500/30 bg-amber-500/10 text-amber-300' : 'border-slate-600 bg-slate-700/30 text-slate-300'}`}>
                                {formatAction(row.kind)}
                            </span>
                        </div>
                        <div className="min-w-0">
                            <div className="truncate text-slate-200">{row.label}</div>
                            {row.detail && <div className="truncate text-[11px] text-slate-500">{row.detail}</div>}
                            {row.kind === 'file' && (
                                <div className="text-[10px] font-mono mt-0.5">
                                    <span className="text-emerald-400">+{row.additions || 0}</span>
                                    <span className="mx-1 text-slate-600">/</span>
                                    <span className="text-rose-400">-{row.deletions || 0}</span>
                                </div>
                            )}
                        </div>
                        <div className="truncate text-slate-400">{row.threadName || row.sessionId}</div>
                        <div className="flex items-center gap-1 justify-end">
                            {row.kind === 'file' && row.localPath && (
                                <button
                                    onClick={() => openRowFile(row)}
                                    className="p-1 rounded text-slate-500 hover:text-indigo-300 hover:bg-indigo-500/10"
                                    title="Open file"
                                >
                                    <ExternalLink size={14} />
                                </button>
                            )}
                            {row.githubUrl && (
                                <a
                                    href={row.githubUrl}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="p-1 rounded text-slate-500 hover:text-indigo-300 hover:bg-indigo-500/10"
                                    title="Open file on GitHub"
                                >
                                    <GitCommit size={14} />
                                </a>
                            )}
                            {row.linkedSessionId && (
                                <button
                                    onClick={() => onOpenThread(row.linkedSessionId!)}
                                    className="text-[10px] px-1.5 py-0.5 rounded border border-indigo-500/30 bg-indigo-500/10 text-indigo-300"
                                    title="Open linked thread"
                                >
                                    Thread
                                </button>
                            )}
                            {row.artifactUrl && (
                                <a
                                    href={row.artifactUrl}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-300"
                                >
                                    Artifact
                                </a>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

const FilesView: React.FC<{
    session: AgentSession;
    threadSessions: AgentSession[];
    threadSessionDetails: Record<string, AgentSession>;
    subagentNameBySessionId: Map<string, string>;
    onOpenDoc: (doc: PlanDocument) => void;
    highlightedSourceLogId?: string | null;
}> = ({ session, threadSessions, threadSessionDetails, subagentNameBySessionId, onOpenDoc, highlightedSourceLogId }) => {
    const { documents, activeProject } = useData();
    const sessionsForFiles = useMemo(
        () => collectThreadDetailSessions(session, threadSessions, threadSessionDetails),
        [session, threadSessions, threadSessionDetails]
    );

    const resolveDocument = useCallback((path: string): PlanDocument | null => {
        const normalized = normalizePath(path);
        for (const doc of documents) {
            const docPath = normalizePath(doc.filePath);
            if (normalized === docPath || normalized.endsWith(`/${docPath}`) || docPath.endsWith(`/${normalized}`)) {
                return doc;
            }
        }
        return null;
    }, [documents]);

    const fileRows = useMemo(() => {
        type MutableFileAggregate = SessionFileAggregateRow & {
            actionsSet: Set<string>;
            sessionSet: Set<string>;
            agentSet: Set<string>;
            sourceLogSet: Set<string>;
            doc: PlanDocument | null;
        };

        const aggregates = new Map<string, MutableFileAggregate>();
        const ensureAggregate = (filePath: string): MutableFileAggregate => {
            const existing = aggregates.get(filePath);
            if (existing) return existing;
            const localPath = resolveLocalPath(filePath, activeProject?.path);
            const doc = resolveDocument(filePath);
            const created: MutableFileAggregate = {
                key: filePath,
                fileName: fileNameFromPath(filePath),
                filePath,
                actions: [],
                touchCount: 0,
                uniqueSessions: 0,
                uniqueAgents: 0,
                lastTouchedAt: '',
                netDiff: 0,
                additions: 0,
                deletions: 0,
                sourceLogIds: [],
                localPath,
                documentId: doc?.id,
                fileType: '',
                actionsSet: new Set<string>(),
                sessionSet: new Set<string>(),
                agentSet: new Set<string>(),
                sourceLogSet: new Set<string>(),
                doc,
            };
            aggregates.set(filePath, created);
            return created;
        };

        for (const thread of sessionsForFiles) {
            const threadName = getThreadDisplayName(thread, subagentNameBySessionId);
            (thread.updatedFiles || []).forEach(file => {
                const action = normalizeFileAction(file.action, file.sourceToolName);
                if (action === 'other') return;
                const filePath = normalizePath(file.filePath);
                if (!filePath) return;
                const row = ensureAggregate(filePath);
                row.touchCount += 1;
                row.actionsSet.add(action);
                row.sessionSet.add(thread.id);
                row.agentSet.add(file.agentName || (thread.id === session.id ? MAIN_SESSION_AGENT : threadName));
                if (file.sourceLogId) row.sourceLogSet.add(file.sourceLogId);
                const ts = file.timestamp || '';
                if (ts && (!row.lastTouchedAt || toEpoch(ts) >= toEpoch(row.lastTouchedAt))) {
                    row.lastTouchedAt = ts;
                }
                row.additions += file.additions || 0;
                row.deletions += file.deletions || 0;
                row.netDiff = row.additions - row.deletions;
                if (!row.fileType && file.fileType) row.fileType = file.fileType;
            });
        }

        const rows = Array.from(aggregates.values()).map(row => ({
            ...row,
            actions: Array.from(row.actionsSet).sort(),
            uniqueSessions: row.sessionSet.size,
            uniqueAgents: row.agentSet.size,
            sourceLogIds: Array.from(row.sourceLogSet),
        }));
        rows.sort((a, b) => {
            const ta = toEpoch(a.lastTouchedAt);
            const tb = toEpoch(b.lastTouchedAt);
            if (ta !== tb) return tb - ta;
            return a.filePath.localeCompare(b.filePath);
        });
        return rows;
    }, [activeProject?.path, resolveDocument, session.id, sessionsForFiles, subagentNameBySessionId]);

    if (fileRows.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
                <FileText size={48} className="mb-4 opacity-20" />
                <p>No tracked files found for this thread family.</p>
            </div>
        );
    }

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden h-full flex flex-col">
            <div className="grid grid-cols-[1.2fr_1.1fr_70px_80px_80px_150px_100px_90px] gap-2 px-3 py-2 border-b border-slate-800 bg-slate-950/60 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                <div>File</div>
                <div>Path</div>
                <div>Actions</div>
                <div>Touches</div>
                <div>Sessions</div>
                <div>Last Touched</div>
                <div>Net Diff</div>
                <div>Open</div>
            </div>
            <div className="flex-1 overflow-y-auto">
                {fileRows.map(row => (
                    <div
                        key={row.key}
                        className={`grid grid-cols-[1.2fr_1.1fr_70px_80px_80px_150px_100px_90px] gap-2 px-3 py-2 border-b border-slate-800/70 text-xs hover:bg-slate-800/30 ${highlightedSourceLogId && row.sourceLogIds.includes(highlightedSourceLogId) ? 'bg-indigo-500/10 border-indigo-500/30' : ''}`}
                    >
                        <div className="truncate text-slate-200 font-medium">{row.fileName}</div>
                        <div className="truncate font-mono text-[11px] text-slate-500">{row.filePath}</div>
                        <div className="flex flex-wrap gap-1">
                            {row.actions.map(action => (
                                <span key={`${row.key}:${action}`} className={`inline-flex rounded border px-1 py-0.5 text-[10px] ${action === 'read' ? 'bg-blue-500/10 border-blue-500/30 text-blue-300' : action === 'create' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : action === 'update' ? 'bg-amber-500/10 border-amber-500/30 text-amber-300' : action === 'delete' ? 'bg-rose-500/10 border-rose-500/30 text-rose-300' : 'bg-slate-700/30 border-slate-600 text-slate-300'}`}>
                                    {formatAction(action)}
                                </span>
                            ))}
                        </div>
                        <div className="text-slate-300">{row.touchCount}</div>
                        <div className="text-slate-300">{row.uniqueSessions}</div>
                        <div className="text-slate-500 text-[11px]">{row.lastTouchedAt ? new Date(row.lastTouchedAt).toLocaleString() : '—'}</div>
                        <div className="font-mono text-[11px]">
                            <span className={row.netDiff >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                                {row.netDiff >= 0 ? '+' : ''}{row.netDiff}
                            </span>
                        </div>
                        <div className="flex items-center justify-end gap-1">
                            <button
                                onClick={() => {
                                    if (row.documentId) {
                                        const doc = documents.find(item => item.id === row.documentId);
                                        if (doc) {
                                            onOpenDoc(doc);
                                            return;
                                        }
                                    }
                                    window.location.href = `vscode://file/${encodeURI(row.localPath)}`;
                                }}
                                className="p-1 rounded text-slate-500 hover:text-indigo-300 hover:bg-indigo-500/10"
                            >
                                <ExternalLink size={14} />
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

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

const ArtifactsView: React.FC<{
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
        []
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
        [groupedArtifacts]
    );
    const agentGroups = useMemo(
        () => groupedArtifacts.filter(group => {
            const type = (group.type || '').trim().toLowerCase();
            return type === 'agent' || type === 'task';
        }),
        [groupedArtifacts]
    );
    const toolGroups = useMemo(
        () => groupedArtifacts.filter(group => {
            const type = (group.type || '').trim().toLowerCase();
            if (type === 'skill' || type === 'agent' || type === 'task' || type === 'command') return false;
            return group.relatedToolLogs.length > 0 || group.sourceToolNames.length > 0;
        }),
        [groupedArtifacts]
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

// --- Analytics Sub-Components ---

const AnalyticsDetailsModal: React.FC<{
    title: string;
    data: any;
    onClose: () => void;
    onViewTranscript: (agentName?: string) => void;
}> = ({ title, data, onClose, onViewTranscript }) => {
    if (!data) return null;

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-200" onClick={onClose}>
            <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-lg shadow-2xl overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="p-5 border-b border-slate-800 flex justify-between items-center bg-slate-950">
                    <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                        <Activity size={18} className="text-indigo-500" />
                        {title}: {data.name}
                    </h3>
                    <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
                        <X size={20} />
                    </button>
                </div>
                <div className="p-6 space-y-6">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700/50">
                            <div className="text-xs text-slate-500 uppercase font-bold mb-1">Total Interactions</div>
                            <div className="text-2xl font-mono text-white">{data.value || 0}</div>
                        </div>
                        <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700/50">
                            <div className="text-xs text-slate-500 uppercase font-bold mb-1">Estimated Cost</div>
                            <div className="text-2xl font-mono text-emerald-400">${(data.cost || 0).toFixed(4)}</div>
                        </div>
                    </div>

                    <div className="space-y-2">
                        <div className="flex justify-between text-sm border-b border-slate-800 pb-2">
                            <span className="text-slate-400">Tokens Consumed</span>
                            <span className="font-mono text-slate-200">{(data.tokens || 0).toLocaleString()}</span>
                        </div>
                        <div className="flex justify-between text-sm border-b border-slate-800 pb-2">
                            <span className="text-slate-400">Tools Called</span>
                            <span className="font-mono text-slate-200">{data.toolCount || 0}</span>
                        </div>
                    </div>

                    <button
                        onClick={() => onViewTranscript(data.type === 'agent' ? data.name : undefined)}
                        className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
                    >
                        <MessageSquare size={16} /> Filter Transcript
                    </button>
                </div>
            </div>
        </div>
    );
};

const TokenTimeline: React.FC<{ session: AgentSession }> = ({ session }) => {
    const [timelineData, setTimelineData] = useState<Array<{
        index: number;
        time: string;
        tokens: number;
        stepTokens: number;
        agent?: string;
    }>>([]);

    useEffect(() => {
        let mounted = true;
        const loadSeries = async () => {
            try {
                const res = await analyticsService.getSeries({
                    metric: 'session_tokens',
                    period: 'point',
                    sessionId: session.id,
                    limit: 2000,
                });
                if (!mounted) return;
                const points = (res.items || []).map((point, index) => ({
                    index,
                    time: String(point.captured_at || ''),
                    tokens: Math.round(Number(point.value || 0)),
                    stepTokens: Math.round(Number(point.metadata?.stepTokens || 0)),
                    agent: String(point.metadata?.agent || ''),
                }));
                setTimelineData(points);
            } catch (err) {
                console.error('Failed to fetch token timeline:', err);
                let cumulative = 0;
                const fallback = (session.logs || []).map((log, index) => {
                    const step = Number(log.metadata?.totalTokens || 0);
                    cumulative += step;
                    return {
                        index,
                        time: log.timestamp,
                        tokens: cumulative,
                        stepTokens: step,
                        agent: log.agentName || '',
                    };
                }).filter(item => item.stepTokens > 0);
                setTimelineData(fallback);
            }
        };
        loadSeries();
        return () => {
            mounted = false;
        };
    }, [session.id, session.logs]);

    return (
        <div className="h-80 w-full relative">
            <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={timelineData} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                    <defs>
                        <linearGradient id="colorTokens" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis dataKey="time" stroke="#475569" tick={{ fontSize: 10 }} interval={Math.floor(timelineData.length / 5)} />
                    <YAxis stroke="#475569" tick={{ fontSize: 10 }} label={{ value: 'Tokens', angle: -90, position: 'insideLeft', fill: '#64748b' }} />
                    <Tooltip
                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                        itemStyle={{ color: '#e2e8f0' }}
                        labelStyle={{ color: '#94a3b8' }}
                    />

                    {/* Token Area */}
                    <Area type="monotone" dataKey="tokens" stroke="#3b82f6" fillOpacity={1} fill="url(#colorTokens)" name="Cumulative Tokens" />
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    );
};


const AnalyticsView: React.FC<{
    session: AgentSession;
    goToTranscript: (agentName?: string) => void;
}> = ({ session, goToTranscript }) => {
    const [modalData, setModalData] = useState<{ title: string; data: any } | null>(null);
    const [tokenViewMode, setTokenViewMode] = useState<'summary' | 'timeline'>('summary');

    const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6'];

    // --- Data Aggregation ---

    // 1. Tool Data
    const toolData = session.toolsUsed.map(t => ({
        name: t.name,
        value: t.count,
        type: 'tool',
        cost: session.totalCost * 0.1, // Mock portion
        tokens: Math.round(session.tokensIn * 0.1) // Mock portion
    }));

    // 2. Agent Data
    const agentStats = useMemo(() => {
        const stats: Record<string, { count: number, tokens: number, tools: number }> = {};
        session.logs.forEach(log => {
            if (log.speaker === 'agent') {
                const name = log.agentName || 'Main';
                if (!stats[name]) stats[name] = { count: 0, tokens: 0, tools: 0 };
                stats[name].count += 1;
                stats[name].tokens += log.content.length / 4; // Approx
                if (log.type === 'tool') stats[name].tools += 1;
            }
        });
        return Object.entries(stats).map(([name, stat]) => ({
            name,
            value: stat.count,
            tokens: Math.round(stat.tokens),
            toolCount: stat.tools,
            cost: (stat.tokens / 1000000) * 15, // Mock pricing
            type: 'agent'
        }));
    }, [session]);

    // 3. Model Data
    const modelData = useMemo(() => {
        // Mocking: assuming Agents use different models or the session model is primary
        // In a real app, logs would have `modelId`
        return [{
            name: session.model,
            value: session.logs.length,
            tokens: session.tokensIn + session.tokensOut,
            toolCount: session.toolsUsed.reduce((acc, t) => acc + t.count, 0),
            cost: session.totalCost,
            type: 'model'
        }];
    }, [session]);

    return (
        <div className="h-full overflow-y-auto pb-6 relative">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">

                {/* 1. AGENTS CHART */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <h3 className="text-sm font-bold text-slate-300 mb-6 flex items-center gap-2"><Users size={16} /> Active Agents</h3>
                    <div className="h-64 cursor-pointer">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={agentStats} onClick={(data: any) => data && data.activePayload && setModalData({ title: 'Agent Details', data: data.activePayload[0].payload })}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                                <XAxis dataKey="name" stroke="#475569" tick={{ fontSize: 12 }} />
                                <YAxis stroke="#475569" tick={{ fontSize: 12 }} />
                                <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                                <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} name="Interactions" />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* 2. TOOLS CHART */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <h3 className="text-sm font-bold text-slate-300 mb-6 flex items-center gap-2"><PieChartIcon size={16} /> Tool Usage</h3>
                    <div className="h-64 cursor-pointer">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={toolData}
                                    innerRadius={60}
                                    outerRadius={80}
                                    paddingAngle={5}
                                    dataKey="value"
                                    onClick={(data) => setModalData({ title: 'Tool Details', data: data })}
                                >
                                    {toolData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                    ))}
                                </Pie>
                                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', color: '#f1f5f9' }} itemStyle={{ color: '#e2e8f0' }} />
                                <Legend verticalAlign="bottom" height={36} wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* 3. MODELS CHART */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <h3 className="text-sm font-bold text-slate-300 mb-6 flex items-center gap-2"><Cpu size={16} /> Model Allocation</h3>
                    <div className="h-64 cursor-pointer">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart layout="vertical" data={modelData} onClick={(data: any) => data && data.activePayload && setModalData({ title: 'Model Details', data: data.activePayload[0].payload })}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                                <XAxis type="number" stroke="#475569" tick={{ fontSize: 12 }} />
                                <YAxis dataKey="name" type="category" stroke="#94a3b8" tick={{ fontSize: 10 }} width={100} />
                                <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                                <Bar dataKey="value" fill="#10b981" radius={[0, 4, 4, 0]} barSize={24} name="Steps Executed" />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* 4. TOKEN CONSUMPTION (Toggleable) */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <div className="flex justify-between items-center mb-6">
                        <h3 className="text-sm font-bold text-slate-300 flex items-center gap-2"><BarChart2 size={16} /> Token Consumption</h3>
                        <div className="flex bg-slate-950 rounded-lg p-0.5 border border-slate-800">
                            <button
                                onClick={() => setTokenViewMode('summary')}
                                className={`px-2 py-1 text-[10px] font-bold rounded ${tokenViewMode === 'summary' ? 'bg-indigo-600 text-white' : 'text-slate-500 hover:text-slate-300'}`}
                            >
                                Summary
                            </button>
                            <button
                                onClick={() => setTokenViewMode('timeline')}
                                className={`px-2 py-1 text-[10px] font-bold rounded ${tokenViewMode === 'timeline' ? 'bg-indigo-600 text-white' : 'text-slate-500 hover:text-slate-300'}`}
                            >
                                Timeline
                            </button>
                        </div>
                    </div>

                    <div className="h-64">
                        {tokenViewMode === 'summary' ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={[
                                    { name: 'Input', tokens: session.tokensIn, fill: '#3b82f6' },
                                    { name: 'Output', tokens: session.tokensOut, fill: '#10b981' }
                                ]} layout="vertical">
                                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                                    <XAxis type="number" stroke="#475569" tick={{ fontSize: 12 }} />
                                    <YAxis dataKey="name" type="category" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                                    <Tooltip cursor={{ fill: 'transparent' }} contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                                    <Bar dataKey="tokens" radius={[0, 4, 4, 0]} barSize={32} />
                                </BarChart>
                            </ResponsiveContainer>
                        ) : (
                            <TokenTimeline session={session} />
                        )}
                    </div>
                </div>

                {/* 5. MASTER TIMELINE VIEW (Full Width) */}
                <div className="md:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <h3 className="text-sm font-bold text-slate-300 mb-2 flex items-center gap-2"><Layers size={16} /> Session Master Timeline</h3>
                    <p className="text-xs text-slate-500 mb-6">Correlated view of token usage, tool executions, and file edits over the session lifecycle.</p>
                    <TokenTimeline session={session} />
                    <div className="mt-4 flex gap-4 justify-center">
                        <div className="flex items-center gap-2 text-xs text-slate-400">
                            <div className="w-3 h-3 bg-blue-500/50 border border-blue-500 rounded-sm"></div> Token Volume
                        </div>
                        <div className="flex items-center gap-2 text-xs text-slate-400">
                            <div className="w-2 h-2 rounded-full bg-amber-500"></div> Tool Execution
                        </div>
                    </div>
                </div>

            </div>

            {/* COST SUMMARY */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <h3 className="text-sm font-bold text-slate-300 mb-2">Cost Analysis</h3>
                <div className="flex items-center gap-8">
                    <div className="flex-1 bg-slate-950 rounded-lg p-4 border border-slate-800">
                        <div className="text-xs text-slate-500 mb-1">Total Cost</div>
                        <div className="text-3xl font-mono text-emerald-400 font-bold">${session.totalCost.toFixed(4)}</div>
                    </div>
                    <div className="flex-1 bg-slate-950 rounded-lg p-4 border border-slate-800">
                        <div className="text-xs text-slate-500 mb-1">Cost / Step</div>
                        <div className="text-3xl font-mono text-indigo-400 font-bold">${(session.totalCost / session.logs.length).toFixed(4)}</div>
                    </div>
                    <div className="flex-1 bg-slate-950 rounded-lg p-4 border border-slate-800">
                        <div className="text-xs text-slate-500 mb-1">Tokens / Step</div>
                        <div className="text-3xl font-mono text-blue-400 font-bold">{Math.round((session.tokensIn + session.tokensOut) / session.logs.length)}</div>
                    </div>
                </div>
            </div>

            {/* DETAIL MODAL */}
            {modalData && (
                <AnalyticsDetailsModal
                    title={modalData.title}
                    data={modalData.data}
                    onClose={() => setModalData(null)}
                    onViewTranscript={(agent) => {
                        goToTranscript(agent);
                        setModalData(null);
                    }}
                />
            )}
        </div>
    );
};

const AgentsView: React.FC<{
    session: AgentSession;
    onSelectAgent: (agentName: string) => void;
    threadSessions: AgentSession[];
    subagentNameBySessionId: Map<string, string>;
    onOpenThread: (sessionId: string) => void;
}> = ({ session, onSelectAgent, threadSessions, subagentNameBySessionId, onOpenThread }) => {
    const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

    const logAgents = Array.from(new Set(session.logs.filter(l => l.speaker === 'agent').map(l => l.agentName || MAIN_SESSION_AGENT)));
    const threadAgents = Array.from(new Set(threadSessions.map(t => getThreadDisplayName(t, subagentNameBySessionId))));
    const agents = Array.from(new Set([...logAgents, ...threadAgents]));

    const agentThreads = (agent: string) => threadSessions.filter(t => getThreadDisplayName(t, subagentNameBySessionId) === agent);

    return (
        <div className="space-y-4">
            {agents.map(agent => {
                const isOpen = expandedAgent === agent;
                const agentLogs = session.logs.filter(l => (
                    l.speaker === 'agent'
                    && (
                        l.agentName === agent
                        || (agent === MAIN_SESSION_AGENT && (!l.agentName || l.agentName === 'Main Agent'))
                    )
                ));
                const threads = agentThreads(agent);

                return (
                    <div key={agent} className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                        <button
                            onClick={() => setExpandedAgent(isOpen ? null : agent)}
                            className="w-full p-4 flex items-center justify-between hover:bg-slate-800/30 transition-colors"
                        >
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-sm font-bold text-indigo-400">
                                    {agent[0]}
                                </div>
                                <div className="text-left">
                                    <div className="font-bold text-slate-200">{agent}</div>
                                    <div className="text-xs text-slate-500 font-mono">{agentLogs.length} interactions · {threads.length} threads</div>
                                </div>
                            </div>
                            {isOpen ? <ChevronDown size={16} className="text-slate-500" /> : <ChevronRight size={16} className="text-slate-500" />}
                        </button>

                        {isOpen && (
                            <div className="p-4 border-t border-slate-800 space-y-3">
                                <button
                                    onClick={() => onSelectAgent(agent === MAIN_SESSION_AGENT ? '' : agent)}
                                    className="text-xs px-3 py-1.5 rounded-lg border border-indigo-500/30 text-indigo-300 bg-indigo-500/10 hover:bg-indigo-500/20"
                                >
                                    Open Sub-agent Transcript
                                </button>
                                <div className="space-y-2">
                                    {threads.length === 0 && (
                                        <div className="text-xs text-slate-500">No linked threads for this agent.</div>
                                    )}
                                    {threads.map(thread => (
                                        <button
                                            key={thread.id}
                                            onClick={() => onOpenThread(thread.id)}
                                            className="w-full text-left p-2 rounded-lg border border-slate-800 bg-slate-950 hover:border-indigo-500/40 transition-colors"
                                        >
                                            <div className="text-[11px] font-mono text-indigo-300 truncate">{thread.id}</div>
                                            <div className="text-[10px] text-slate-500 mt-1">{getThreadDisplayName(thread, subagentNameBySessionId)}</div>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
};

const ImpactView: React.FC<{ session: AgentSession }> = ({ session }) => {
    if (!session.impactHistory || session.impactHistory.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
                <Activity size={48} className="mb-4 opacity-20" />
                <p>No app impact metrics recorded for this session.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6 h-full overflow-y-auto pb-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <h3 className="text-sm font-bold text-slate-300 mb-6 flex items-center gap-2"><TrendingUp size={16} /> Codebase Impact Over Time</h3>
                <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={session.impactHistory}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis dataKey="timestamp" stroke="#475569" tick={{ fontSize: 12 }} />
                            <YAxis stroke="#475569" tick={{ fontSize: 12 }} />
                            <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                            <Legend />
                            <Line type="monotone" dataKey="locAdded" stroke="#10b981" strokeWidth={2} name="LOC Added" dot={false} />
                            <Line type="monotone" dataKey="locDeleted" stroke="#f43f5e" strokeWidth={2} name="LOC Removed" dot={false} />
                            <Line type="monotone" dataKey="fileCount" stroke="#3b82f6" strokeWidth={2} name="Files Touched" dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <h3 className="text-sm font-bold text-slate-300 mb-6 flex items-center gap-2"><ShieldAlert size={16} /> Test Stability</h3>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={session.impactHistory}>
                                <defs>
                                    <linearGradient id="colorPass" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                                    </linearGradient>
                                    <linearGradient id="colorFail" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#f43f5e" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                <XAxis dataKey="timestamp" stroke="#475569" tick={{ fontSize: 12 }} />
                                <YAxis stroke="#475569" tick={{ fontSize: 12 }} />
                                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                                <Area type="monotone" dataKey="testPassCount" stackId="1" stroke="#10b981" fill="url(#colorPass)" name="Tests Passed" />
                                <Area type="monotone" dataKey="testFailCount" stackId="1" stroke="#f43f5e" fill="url(#colorFail)" name="Tests Failed" />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 flex flex-col justify-center">
                    <h3 className="text-sm font-bold text-slate-300 mb-4">Final Session Impact</h3>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between p-3 bg-emerald-500/10 rounded-lg border border-emerald-500/20">
                            <div className="flex items-center gap-3">
                                <FileDiff className="text-emerald-500" size={20} />
                                <span className="text-sm text-slate-300">Net Code Growth</span>
                            </div>
                            <span className="font-mono font-bold text-emerald-400">+{session.impactHistory[session.impactHistory.length - 1].locAdded - session.impactHistory[session.impactHistory.length - 1].locDeleted} LOC</span>
                        </div>
                        <div className="flex items-center justify-between p-3 bg-blue-500/10 rounded-lg border border-blue-500/20">
                            <div className="flex items-center gap-3">
                                <Check className="text-blue-500" size={20} />
                                <span className="text-sm text-slate-300">Tests Passing</span>
                            </div>
                            <span className="font-mono font-bold text-blue-400">{session.impactHistory[session.impactHistory.length - 1].testPassCount}</span>
                        </div>
                        <div className="flex items-center justify-between p-3 bg-rose-500/10 rounded-lg border border-rose-500/20">
                            <div className="flex items-center gap-3">
                                <ShieldAlert className="text-rose-500" size={20} />
                                <span className="text-sm text-slate-300">New Regressions</span>
                            </div>
                            <span className="font-mono font-bold text-rose-400">{session.impactHistory[session.impactHistory.length - 1].testFailCount}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

const SessionForensicsView: React.FC<{ session: AgentSession }> = ({ session }) => {
    const forensics = useMemo(() => asRecord(session.sessionForensics), [session.sessionForensics]);
    const thinking = useMemo(() => asRecord(forensics.thinking), [forensics]);
    const entryContext = useMemo(() => asRecord(forensics.entryContext), [forensics]);
    const sidecars = useMemo(() => asRecord(forensics.sidecars), [forensics]);
    const todosSidecar = useMemo(() => asRecord(sidecars.todos), [sidecars]);
    const tasksSidecar = useMemo(() => asRecord(sidecars.tasks), [sidecars]);
    const teamsSidecar = useMemo(() => asRecord(sidecars.teams), [sidecars]);
    const sessionEnvSidecar = useMemo(() => asRecord(sidecars.sessionEnv), [sidecars]);

    const permissionModes = asStringArray(entryContext.permissionModes);
    const workingDirectories = asStringArray(entryContext.workingDirectories);
    const versions = asStringArray(entryContext.versions);
    const requestIds = asStringArray(entryContext.requestIds);
    const queueOperations = Array.isArray(entryContext.queueOperations) ? entryContext.queueOperations : [];
    const apiErrors = Array.isArray(entryContext.apiErrors) ? entryContext.apiErrors : [];
    const entryTypeCounts = asCountEntries(entryContext.entryTypeCounts, 12);
    const contentBlockTypeCounts = asCountEntries(entryContext.contentBlockTypeCounts, 12);
    const progressTypeCounts = asCountEntries(entryContext.progressTypeCounts, 12);

    if (Object.keys(forensics).length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
                <Database size={48} className="mb-4 opacity-20" />
                <p>No forensic payload available for this session.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6 h-full overflow-y-auto pb-6">
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
                    <h3 className="text-sm font-bold text-slate-300 flex items-center gap-2"><ShieldAlert size={16} /> Session Capture</h3>
                    <div className="space-y-2 text-xs">
                        <div className="flex justify-between gap-4"><span className="text-slate-500">Platform</span><span className="text-slate-200 font-mono">{String(forensics.platform || 'claude_code')}</span></div>
                        <div className="flex justify-between gap-4"><span className="text-slate-500">Schema Version</span><span className="text-slate-200 font-mono">{String(forensics.schemaVersion || 'n/a')}</span></div>
                        <div className="flex justify-between gap-4"><span className="text-slate-500">Raw Session ID</span><span className="text-slate-300 font-mono truncate max-w-[60%]" title={String(forensics.rawSessionId || '')}>{String(forensics.rawSessionId || '')}</span></div>
                        <div className="text-slate-500">Session File</div>
                        <div className="text-[11px] text-slate-300 font-mono break-all">{String(forensics.sessionFile || '')}</div>
                        <div className="text-slate-500">Claude Root</div>
                        <div className="text-[11px] text-slate-300 font-mono break-all">{String(forensics.claudeRoot || '')}</div>
                    </div>
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
                    <h3 className="text-sm font-bold text-slate-300 flex items-center gap-2"><Bot size={16} /> Thinking</h3>
                    <div className="space-y-2 text-xs">
                        <div className="flex justify-between gap-4"><span className="text-slate-500">Level</span><span className="text-fuchsia-300 font-mono uppercase">{String(thinking.level || session.thinkingLevel || 'unknown')}</span></div>
                        <div className="flex justify-between gap-4"><span className="text-slate-500">Source</span><span className="text-slate-300 font-mono truncate max-w-[60%]" title={String(thinking.source || '')}>{String(thinking.source || 'n/a')}</span></div>
                        <div className="flex justify-between gap-4"><span className="text-slate-500">Max Thinking Tokens</span><span className="text-slate-200 font-mono">{asNumber(thinking.maxThinkingTokens, 0).toLocaleString()}</span></div>
                        <div className="flex justify-between gap-4"><span className="text-slate-500">Disabled</span><span className={`font-mono ${thinking.disabled ? 'text-amber-300' : 'text-slate-300'}`}>{String(Boolean(thinking.disabled))}</span></div>
                        {thinking.explicitLevel && (
                            <div className="flex justify-between gap-4"><span className="text-slate-500">Explicit Level</span><span className="text-slate-300 font-mono uppercase">{String(thinking.explicitLevel)}</span></div>
                        )}
                    </div>
                </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                <h3 className="text-sm font-bold text-slate-300 flex items-center gap-2"><HardDrive size={16} /> Sidecars</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                        <div className="text-[10px] uppercase tracking-wider text-slate-500">Todos</div>
                        <div className="text-xs text-slate-200 mt-1 font-mono">{asNumber(todosSidecar.fileCount, 0)} files · {asNumber(todosSidecar.totalItems, 0)} items</div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                        <div className="text-[10px] uppercase tracking-wider text-slate-500">Tasks</div>
                        <div className="text-xs text-slate-200 mt-1 font-mono">{asNumber(tasksSidecar.taskFileCount, 0)} files · HWM {String(tasksSidecar.highWatermark || '0')}</div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                        <div className="text-[10px] uppercase tracking-wider text-slate-500">Teams</div>
                        <div className="text-xs text-slate-200 mt-1 font-mono">{asNumber(teamsSidecar.totalMessages, 0)} msgs · {asNumber(teamsSidecar.unreadMessages, 0)} unread</div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                        <div className="text-[10px] uppercase tracking-wider text-slate-500">Session Env</div>
                        <div className="text-xs text-slate-200 mt-1 font-mono">{asNumber(sessionEnvSidecar.fileCount, 0)} files</div>
                    </div>
                </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                <h3 className="text-sm font-bold text-slate-300 flex items-center gap-2"><Terminal size={16} /> Entry Context</h3>
                <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                    <div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Session Context</div>
                        <div className="space-y-1.5 text-xs">
                            <div className="flex justify-between"><span className="text-slate-500">Request IDs</span><span className="text-slate-200 font-mono">{requestIds.length}</span></div>
                            <div className="flex justify-between"><span className="text-slate-500">Queue Ops</span><span className="text-slate-200 font-mono">{queueOperations.length}</span></div>
                            <div className="flex justify-between"><span className="text-slate-500">API Errors</span><span className={`font-mono ${apiErrors.length > 0 ? 'text-rose-300' : 'text-slate-200'}`}>{apiErrors.length}</span></div>
                            <div className="flex justify-between"><span className="text-slate-500">Snapshots</span><span className="text-slate-200 font-mono">{asNumber(entryContext.snapshotCount, 0)}</span></div>
                        </div>
                    </div>
                    <div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Permission Modes</div>
                        <div className="flex flex-wrap gap-1">
                            {permissionModes.length === 0 && <span className="text-xs text-slate-500">None captured</span>}
                            {permissionModes.map(mode => (
                                <span key={mode} className="text-[10px] px-1.5 py-0.5 rounded border border-slate-700 text-slate-300 font-mono">{mode}</span>
                            ))}
                        </div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2 mt-4">Working Directories</div>
                        <div className="space-y-1 max-h-24 overflow-y-auto pr-1">
                            {workingDirectories.length === 0 && <div className="text-xs text-slate-500">None captured</div>}
                            {workingDirectories.map(dir => (
                                <div key={dir} className="text-[10px] text-slate-300 font-mono break-all">{dir}</div>
                            ))}
                        </div>
                    </div>
                    <div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Versions Seen</div>
                        <div className="flex flex-wrap gap-1 mb-4">
                            {versions.length === 0 && <span className="text-xs text-slate-500">None captured</span>}
                            {versions.map(version => (
                                <span key={version} className="text-[10px] px-1.5 py-0.5 rounded border border-slate-700 text-amber-300 font-mono">{version}</span>
                            ))}
                        </div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Top Entry Types</div>
                        <div className="space-y-1">
                            {entryTypeCounts.length === 0 && <div className="text-xs text-slate-500">No counts</div>}
                            {entryTypeCounts.map(item => (
                                <div key={item.key} className="flex justify-between text-[10px]">
                                    <span className="text-slate-400 font-mono">{item.key}</span>
                                    <span className="text-slate-200 font-mono">{item.count}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                    <h3 className="text-sm font-bold text-slate-300 mb-3">Queue Operations</h3>
                    <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                        {queueOperations.length === 0 && <div className="text-xs text-slate-500">No queue operations recorded.</div>}
                        {queueOperations.slice(0, 40).map((operation, idx) => {
                            const op = asRecord(operation);
                            return (
                                <div key={`${String(op.timestamp || idx)}-${idx}`} className="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
                                    <div className="text-[10px] text-slate-500 font-mono">{String(op.timestamp || '')}</div>
                                    <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 text-[11px]">
                                        <span className="text-indigo-300 font-mono">{String(op.operation || 'event')}</span>
                                        {op.taskId && <span className="text-slate-300 font-mono">Task {String(op.taskId)}</span>}
                                        {op.status && <span className="text-amber-300 font-mono">{String(op.status)}</span>}
                                    </div>
                                    {op.summary && <div className="text-[11px] text-slate-300 mt-1 break-words">{String(op.summary)}</div>}
                                </div>
                            );
                        })}
                    </div>
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                    <h3 className="text-sm font-bold text-slate-300 mb-3">Additional Event Mix</h3>
                    <div className="space-y-3 text-[11px]">
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Content Block Types</div>
                            <div className="space-y-1">
                                {contentBlockTypeCounts.length === 0 && <div className="text-xs text-slate-500">No counts</div>}
                                {contentBlockTypeCounts.map(item => (
                                    <div key={item.key} className="flex justify-between">
                                        <span className="text-slate-400 font-mono">{item.key}</span>
                                        <span className="text-slate-200 font-mono">{item.count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Progress Types</div>
                            <div className="space-y-1">
                                {progressTypeCounts.length === 0 && <div className="text-xs text-slate-500">No counts</div>}
                                {progressTypeCounts.map(item => (
                                    <div key={item.key} className="flex justify-between">
                                        <span className="text-slate-400 font-mono">{item.key}</span>
                                        <span className="text-slate-200 font-mono">{item.count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <h3 className="text-sm font-bold text-slate-300 mb-3">API Errors</h3>
                <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                    {apiErrors.length === 0 && <div className="text-xs text-slate-500">No API errors captured.</div>}
                    {apiErrors.slice(0, 30).map((error, idx) => {
                        const row = asRecord(error);
                        return (
                            <div key={`${String(row.timestamp || idx)}-${idx}`} className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-2">
                                <div className="text-[10px] text-rose-300/80 font-mono">{String(row.timestamp || '')}</div>
                                <div className="text-[11px] text-rose-100 mt-1 break-words">{String(row.message || '')}</div>
                            </div>
                        );
                    })}
                </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <h3 className="text-sm font-bold text-slate-300 mb-3">Raw Forensics Payload</h3>
                <pre className="text-[10px] leading-4 font-mono bg-slate-950 border border-slate-800 rounded-lg p-3 overflow-x-auto text-slate-300">
                    {JSON.stringify(forensics, null, 2)}
                </pre>
            </div>
        </div>
    );
};

// --- Main Container ---

interface SessionModelFacet {
    raw: string;
    modelDisplayName: string;
    modelProvider: string;
    modelFamily: string;
    modelVersion: string;
    count: number;
}

interface SessionPlatformFacet {
    platformType: string;
    platformVersion: string;
    count: number;
}

const MODEL_PROVIDER_ORDER = ['Claude', 'OpenAI', 'Gemini', 'Codex'];
const MODEL_FAMILY_ORDER = ['Opus', 'Sonnet', 'Haiku', 'Codex'];

const titleCaseToken = (value: string): string =>
    value
        .split(/\s+/)
        .filter(Boolean)
        .map(token => token.charAt(0).toUpperCase() + token.slice(1))
        .join(' ');

const inferProviderFromRawModel = (rawModel: string): string => {
    const raw = (rawModel || '').toLowerCase();
    if (!raw) return '';
    if (raw.includes('claude')) return 'Claude';
    if (raw.includes('gpt') || raw.includes('openai')) return 'OpenAI';
    if (raw.includes('gemini')) return 'Gemini';
    if (raw.includes('codex')) return 'Codex';
    const token = raw.split(/[-_\s]+/).filter(Boolean)[0] || '';
    return titleCaseToken(token);
};

const inferFamilyFromRawModel = (rawModel: string): string => {
    const raw = (rawModel || '').toLowerCase();
    if (!raw) return '';
    if (raw.includes('opus')) return 'Opus';
    if (raw.includes('sonnet')) return 'Sonnet';
    if (raw.includes('haiku')) return 'Haiku';
    if (raw.includes('codex')) return 'Codex';
    const parts = raw.split(/[-_\s]+/).filter(Boolean);
    return parts[1] ? titleCaseToken(parts[1]) : '';
};

const inferVersionFromRawModel = (rawModel: string, family: string): string => {
    const tokens = (rawModel || '').toLowerCase().split(/[-_\s]+/).filter(Boolean);
    const numericTokens = tokens.filter(token => /^\d+$/.test(token));
    let numeric = '';
    if (numericTokens.length >= 2) numeric = `${numericTokens[0]}.${numericTokens[1]}`;
    else if (numericTokens.length === 1) numeric = numericTokens[0];

    if (family && numeric) return `${family} ${numeric}`;
    if (family) return family;
    return numeric;
};

const normalizeModelFacet = (facet: SessionModelFacet): SessionModelFacet => {
    const raw = (facet.raw || '').trim();
    const provider = (facet.modelProvider || '').trim() || inferProviderFromRawModel(raw);
    const family = (facet.modelFamily || '').trim() || inferFamilyFromRawModel(raw);
    const version = (facet.modelVersion || '').trim() || inferVersionFromRawModel(raw, family);
    const displayName = (facet.modelDisplayName || '').trim() || formatModelDisplayName(raw, '');
    return {
        raw,
        modelDisplayName: displayName,
        modelProvider: provider,
        modelFamily: family,
        modelVersion: version,
        count: facet.count || 0,
    };
};

const stripFamilyPrefix = (version: string, family: string): string => {
    const normalizedVersion = (version || '').trim();
    const normalizedFamily = (family || '').trim();
    if (!normalizedVersion || !normalizedFamily) return normalizedVersion;
    const prefixPattern = new RegExp(`^${normalizedFamily}\\s+`, 'i');
    return normalizedVersion.replace(prefixPattern, '').trim() || normalizedVersion;
};

const compareByPreferredOrder = (left: string, right: string, preferred: string[]): number => {
    const leftIdx = preferred.findIndex(value => value.toLowerCase() === left.toLowerCase());
    const rightIdx = preferred.findIndex(value => value.toLowerCase() === right.toLowerCase());
    const leftRank = leftIdx === -1 ? Number.MAX_SAFE_INTEGER : leftIdx;
    const rightRank = rightIdx === -1 ? Number.MAX_SAFE_INTEGER : rightIdx;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return left.localeCompare(right);
};

const versionParts = (value: string): number[] => {
    const matches = (value || '').match(/\d+/g);
    if (!matches) return [];
    return matches.map(token => Number.parseInt(token, 10)).filter(num => Number.isFinite(num));
};

const compareVersionLabelsDesc = (left: string, right: string): number => {
    const leftParts = versionParts(left);
    const rightParts = versionParts(right);
    const maxLength = Math.max(leftParts.length, rightParts.length);
    for (let idx = 0; idx < maxLength; idx += 1) {
        const leftPart = leftParts[idx] ?? -1;
        const rightPart = rightParts[idx] ?? -1;
        if (leftPart !== rightPart) return rightPart - leftPart;
    }
    return right.localeCompare(left);
};

const buildSessionFilterPayload = (filters: Partial<SessionFilters>): SessionFilters => {
    const payload: SessionFilters = {
        include_subagents: filters.include_subagents ?? true,
    };

    const stringKeys: Array<keyof SessionFilters> = [
        'status',
        'model',
        'model_provider',
        'model_family',
        'model_version',
        'platform_type',
        'platform_version',
        'root_session_id',
        'start_date',
        'end_date',
        'created_start',
        'created_end',
        'completed_start',
        'completed_end',
        'updated_start',
        'updated_end',
    ];
    stringKeys.forEach(key => {
        const rawValue = filters[key];
        const value = typeof rawValue === 'string' ? rawValue.trim() : '';
        if (value) payload[key] = value as any;
    });

    if (typeof filters.min_duration === 'number' && Number.isFinite(filters.min_duration)) {
        payload.min_duration = filters.min_duration;
    }
    if (typeof filters.max_duration === 'number' && Number.isFinite(filters.max_duration)) {
        payload.max_duration = filters.max_duration;
    }

    return payload;
};

const areSessionFiltersEqual = (left: Partial<SessionFilters>, right: Partial<SessionFilters>): boolean =>
    JSON.stringify(buildSessionFilterPayload(left)) === JSON.stringify(buildSessionFilterPayload(right));

const SessionFilterBar: React.FC = () => {
    const { sessionFilters, setSessionFilters, sessions } = useData();
    const [localFilters, setLocalFilters] = useState<SessionFilters>(() => buildSessionFilterPayload(sessionFilters));
    const [modelFacets, setModelFacets] = useState<SessionModelFacet[]>([]);
    const [modelFacetsLoading, setModelFacetsLoading] = useState(false);
    const [platformFacets, setPlatformFacets] = useState<SessionPlatformFacet[]>([]);
    const [platformFacetsLoading, setPlatformFacetsLoading] = useState(false);
    const [collapsedSections, setCollapsedSections] = useState({
        general: true,
        models: true,
        dates: true,
    });

    useEffect(() => {
        setLocalFilters(prev => {
            const next = buildSessionFilterPayload(sessionFilters);
            return areSessionFiltersEqual(prev, next) ? prev : next;
        });
    }, [sessionFilters]);

    const handleChange = (key: keyof SessionFilters, value: any) => {
        setLocalFilters(prev => ({
            ...prev,
            [key]: typeof value === 'boolean' ? value : (value || undefined),
        }));
    };

    useEffect(() => {
        let cancelled = false;
        const loadModelFacets = async () => {
            try {
                setModelFacetsLoading(true);
                const params = new URLSearchParams({
                    include_subagents: localFilters.include_subagents === false ? 'false' : 'true',
                });
                const response = await fetch(`/api/sessions/facets/models?${params.toString()}`);
                if (!response.ok) {
                    throw new Error(`Failed to load session model facets (${response.status})`);
                }
                const payload = await response.json();
                if (cancelled) return;
                if (!Array.isArray(payload)) {
                    setModelFacets([]);
                    return;
                }
                setModelFacets(payload.map((item: any) => ({
                    raw: String(item?.raw || ''),
                    modelDisplayName: String(item?.modelDisplayName || ''),
                    modelProvider: String(item?.modelProvider || ''),
                    modelFamily: String(item?.modelFamily || ''),
                    modelVersion: String(item?.modelVersion || ''),
                    count: Number(item?.count || 0),
                })));
            } catch (error) {
                if (!cancelled) {
                    console.error('Failed to load session model facets', error);
                    setModelFacets([]);
                }
            } finally {
                if (!cancelled) setModelFacetsLoading(false);
            }
        };
        void loadModelFacets();
        return () => {
            cancelled = true;
        };
    }, [localFilters.include_subagents]);

    useEffect(() => {
        let cancelled = false;
        const loadPlatformFacets = async () => {
            try {
                setPlatformFacetsLoading(true);
                const params = new URLSearchParams({
                    include_subagents: localFilters.include_subagents === false ? 'false' : 'true',
                });
                const response = await fetch(`/api/sessions/facets/platforms?${params.toString()}`);
                if (!response.ok) {
                    throw new Error(`Failed to load session platform facets (${response.status})`);
                }
                const payload = await response.json();
                if (cancelled) return;
                if (!Array.isArray(payload)) {
                    setPlatformFacets([]);
                    return;
                }
                setPlatformFacets(payload.map((item: any) => ({
                    platformType: String(item?.platformType || 'Claude Code'),
                    platformVersion: String(item?.platformVersion || ''),
                    count: Number(item?.count || 0),
                })));
            } catch (error) {
                if (!cancelled) {
                    console.error('Failed to load session platform facets', error);
                    setPlatformFacets([]);
                }
            } finally {
                if (!cancelled) setPlatformFacetsLoading(false);
            }
        };
        void loadPlatformFacets();
        return () => {
            cancelled = true;
        };
    }, [localFilters.include_subagents]);

    const fallbackFacets = useMemo<SessionModelFacet[]>(() => {
        const byRawModel = new Map<string, SessionModelFacet>();
        sessions.forEach(session => {
            const raw = (session.model || '').trim();
            if (!raw) return;
            const existing = byRawModel.get(raw);
            if (existing) {
                existing.count += 1;
                return;
            }
            byRawModel.set(raw, {
                raw,
                modelDisplayName: session.modelDisplayName || '',
                modelProvider: session.modelProvider || '',
                modelFamily: session.modelFamily || '',
                modelVersion: session.modelVersion || '',
                count: 1,
            });
        });
        return Array.from(byRawModel.values());
    }, [sessions]);

    const normalizedModelFacets = useMemo(() => {
        const source = modelFacets.length > 0 ? modelFacets : fallbackFacets;
        const byRaw = new Map<string, SessionModelFacet>();
        source.forEach(item => {
            const normalized = normalizeModelFacet(item);
            if (!normalized.raw) return;
            const existing = byRaw.get(normalized.raw);
            if (existing) {
                existing.count += normalized.count || 0;
                return;
            }
            byRaw.set(normalized.raw, normalized);
        });
        return Array.from(byRaw.values());
    }, [fallbackFacets, modelFacets]);

    const fallbackPlatformFacets = useMemo<SessionPlatformFacet[]>(() => {
        const byFacet = new Map<string, SessionPlatformFacet>();
        sessions.forEach(session => {
            const platformType = (session.platformType || '').trim() || 'Claude Code';
            const versions: string[] = [];
            (session.platformVersions || []).forEach(value => {
                const normalized = String(value || '').trim();
                if (normalized && !versions.includes(normalized)) versions.push(normalized);
            });
            const primaryVersion = (session.platformVersion || '').trim();
            if (primaryVersion && !versions.includes(primaryVersion)) versions.unshift(primaryVersion);
            versions.forEach(version => {
                const key = `${platformType}::${version}`;
                const existing = byFacet.get(key);
                if (existing) {
                    existing.count += 1;
                    return;
                }
                byFacet.set(key, { platformType, platformVersion: version, count: 1 });
            });
        });
        return Array.from(byFacet.values());
    }, [sessions]);

    const normalizedPlatformFacets = useMemo<SessionPlatformFacet[]>(() => {
        const source = platformFacets.length > 0 ? platformFacets : fallbackPlatformFacets;
        const byFacet = new Map<string, SessionPlatformFacet>();
        source.forEach(facet => {
            const platformType = (facet.platformType || '').trim() || 'Claude Code';
            const platformVersion = (facet.platformVersion || '').trim();
            if (!platformVersion) return;
            const key = `${platformType}::${platformVersion}`;
            const existing = byFacet.get(key);
            if (existing) {
                existing.count += facet.count || 0;
                return;
            }
            byFacet.set(key, {
                platformType,
                platformVersion,
                count: facet.count || 0,
            });
        });
        return Array.from(byFacet.values());
    }, [fallbackPlatformFacets, platformFacets]);

    const platformTypeOptions = useMemo(() => {
        const types = Array.from(new Set(
            normalizedPlatformFacets
                .map(facet => facet.platformType)
                .filter(Boolean),
        ));
        return types.sort((left, right) => left.localeCompare(right));
    }, [normalizedPlatformFacets]);

    const platformVersionOptions = useMemo(() => {
        const selectedPlatformType = (localFilters.platform_type || '').trim();
        if (!selectedPlatformType) return [];
        const values = Array.from(new Set(
            normalizedPlatformFacets
                .filter(facet => facet.platformType === selectedPlatformType)
                .map(facet => facet.platformVersion)
                .filter(Boolean),
        ));
        return values.sort(compareVersionLabelsDesc);
    }, [localFilters.platform_type, normalizedPlatformFacets]);

    const providerOptions = useMemo(() => {
        const providers = Array.from(new Set(
            normalizedModelFacets
                .map(facet => facet.modelProvider)
                .filter(Boolean),
        ));
        return providers.sort((left, right) => compareByPreferredOrder(left, right, MODEL_PROVIDER_ORDER));
    }, [normalizedModelFacets]);

    const familyOptions = useMemo(() => {
        const selectedProvider = (localFilters.model_provider || '').trim();
        const families = Array.from(new Set(
            normalizedModelFacets
                .filter(facet => !selectedProvider || facet.modelProvider === selectedProvider)
                .map(facet => facet.modelFamily)
                .filter(Boolean),
        ));
        return families.sort((left, right) => compareByPreferredOrder(left, right, MODEL_FAMILY_ORDER));
    }, [localFilters.model_provider, normalizedModelFacets]);

    const versionOptions = useMemo(() => {
        const selectedFamily = (localFilters.model_family || '').trim();
        const selectedProvider = (localFilters.model_provider || '').trim();
        if (!selectedFamily) return [];

        const byValue = new Map<string, { value: string; label: string }>();
        normalizedModelFacets.forEach(facet => {
            if (selectedProvider && facet.modelProvider !== selectedProvider) return;
            if (facet.modelFamily !== selectedFamily) return;
            const version = (facet.modelVersion || '').trim();
            if (!version) return;
            if (!byValue.has(version)) {
                byValue.set(version, {
                    value: version,
                    label: stripFamilyPrefix(version, selectedFamily),
                });
            }
        });

        return Array.from(byValue.values()).sort((left, right) => compareVersionLabelsDesc(left.label, right.label));
    }, [localFilters.model_family, localFilters.model_provider, normalizedModelFacets]);

    const modelOptions = useMemo(() => {
        const selectedProvider = (localFilters.model_provider || '').trim();
        const selectedFamily = (localFilters.model_family || '').trim();
        const selectedVersion = (localFilters.model_version || '').trim();
        if (!selectedFamily || !selectedVersion) return [];

        const byRaw = new Map<string, { value: string; label: string }>();
        normalizedModelFacets.forEach(facet => {
            if (selectedProvider && facet.modelProvider !== selectedProvider) return;
            if (facet.modelFamily !== selectedFamily) return;
            if (facet.modelVersion !== selectedVersion) return;
            if (!facet.raw) return;
            if (!byRaw.has(facet.raw)) {
                byRaw.set(facet.raw, {
                    value: facet.raw,
                    label: facet.modelDisplayName || facet.modelVersion || facet.raw,
                });
            }
        });

        return Array.from(byRaw.values()).sort((left, right) => left.label.localeCompare(right.label));
    }, [localFilters.model_family, localFilters.model_provider, localFilters.model_version, normalizedModelFacets]);

    const handlePlatformTypeChange = (value: string) => {
        setLocalFilters(prev => ({
            ...prev,
            platform_type: value || undefined,
            platform_version: undefined,
        }));
    };

    const handlePlatformVersionChange = (value: string) => {
        setLocalFilters(prev => ({
            ...prev,
            platform_version: value || undefined,
        }));
    };

    const handleProviderChange = (value: string) => {
        setLocalFilters(prev => ({
            ...prev,
            model_provider: value || undefined,
            model_family: undefined,
            model_version: undefined,
            model: undefined,
        }));
    };

    const handleFamilyChange = (value: string) => {
        setLocalFilters(prev => ({
            ...prev,
            model_family: value || undefined,
            model_version: undefined,
            model: undefined,
        }));
    };

    const handleVersionChange = (value: string) => {
        setLocalFilters(prev => ({
            ...prev,
            model_version: value || undefined,
            model: undefined,
        }));
    };

    const toggleSection = (key: keyof typeof collapsedSections) => {
        setCollapsedSections(prev => ({
            ...prev,
            [key]: !prev[key],
        }));
    };

    const applyFilters = () => {
        setSessionFilters(buildSessionFilterPayload(localFilters));
    };

    const clearFilters = () => {
        const cleared: SessionFilters = { include_subagents: true };
        setLocalFilters(cleared);
        setSessionFilters(cleared);
    };

    const hasPendingChanges = !areSessionFiltersEqual(localFilters, sessionFilters);

    const hasActiveFilters = Boolean(
        localFilters.status
        || localFilters.model
        || localFilters.model_provider
        || localFilters.model_family
        || localFilters.model_version
        || localFilters.platform_type
        || localFilters.platform_version
        || localFilters.start_date
        || localFilters.end_date
        || localFilters.created_start
        || localFilters.created_end
        || localFilters.completed_start
        || localFilters.completed_end
        || localFilters.updated_start
        || localFilters.updated_end
        || localFilters.include_subagents === false
    );

    const renderDateRangeControl = (label: string, startKey: keyof SessionFilters, endKey: keyof SessionFilters) => (
        <div className="rounded-lg border border-slate-800 bg-slate-900/30 p-2 space-y-1.5">
            <p className="text-[10px] uppercase tracking-wider text-slate-400">{label}</p>
            <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                <span className="text-[10px] uppercase tracking-wider text-slate-500">From</span>
                <input
                    type="date"
                    value={String(localFilters[startKey] || '')}
                    onChange={e => handleChange(startKey, e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-300 focus:border-indigo-500 focus:outline-none"
                />
            </div>
            <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                <span className="text-[10px] uppercase tracking-wider text-slate-500">To</span>
                <input
                    type="date"
                    value={String(localFilters[endKey] || '')}
                    onChange={e => handleChange(endKey, e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-300 focus:border-indigo-500 focus:outline-none"
                />
            </div>
        </div>
    );

    return (
        <SidebarFiltersPortal>
            <SidebarFiltersSection title="Filter Sessions">
                <div className="space-y-2">
                    <button
                        onClick={() => toggleSection('general')}
                        className="w-full flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-slate-400 border border-slate-800 rounded-md px-2.5 py-2 hover:text-slate-200 hover:border-slate-700 transition-colors"
                    >
                        <span>General</span>
                        {collapsedSections.general ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                    </button>
                    {!collapsedSections.general && (
                        <div className="pl-1 space-y-2">
                            <div className="grid grid-cols-[74px_1fr] items-center gap-2">
                                <label className="text-[10px] text-slate-500 uppercase tracking-wider">Status</label>
                                <select
                                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-300 focus:border-indigo-500 focus:outline-none"
                                    value={localFilters.status || ''}
                                    onChange={e => handleChange('status', e.target.value)}
                                >
                                    <option value="">All</option>
                                    <option value="active">Active</option>
                                    <option value="completed">Completed</option>
                                    <option value="failed">Failed</option>
                                </select>
                            </div>

                            <div className="grid grid-cols-[74px_1fr] items-center gap-2">
                                <label className="text-[10px] text-slate-500 uppercase tracking-wider">Platform</label>
                                <select
                                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-300 focus:border-indigo-500 focus:outline-none"
                                    value={localFilters.platform_type || ''}
                                    onChange={e => handlePlatformTypeChange(e.target.value)}
                                >
                                    <option value="">All</option>
                                    {platformTypeOptions.map(platformType => (
                                        <option key={platformType} value={platformType}>{platformType}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="grid grid-cols-[74px_1fr] items-center gap-2">
                                <label className="text-[10px] text-slate-500 uppercase tracking-wider">CLI Ver</label>
                                <select
                                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-300 focus:border-indigo-500 focus:outline-none disabled:opacity-50"
                                    value={localFilters.platform_version || ''}
                                    onChange={e => handlePlatformVersionChange(e.target.value)}
                                    disabled={!localFilters.platform_type}
                                >
                                    <option value="">
                                        {localFilters.platform_type ? 'All' : 'Select platform first'}
                                    </option>
                                    {platformVersionOptions.map(version => (
                                        <option key={version} value={version}>{version}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="grid grid-cols-[74px_1fr] items-center gap-2">
                                <label className="text-[10px] text-slate-500 uppercase tracking-wider">Threads</label>
                                <label className="inline-flex items-center gap-2 text-[11px] text-slate-300">
                                    <input
                                        type="checkbox"
                                        checked={!!localFilters.include_subagents}
                                        onChange={e => handleChange('include_subagents', e.target.checked)}
                                        className="accent-indigo-500"
                                    />
                                    Include subagents
                                </label>
                            </div>
                        </div>
                    )}

                    <button
                        onClick={() => toggleSection('models')}
                        className="w-full flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-slate-400 border border-slate-800 rounded-md px-2.5 py-2 hover:text-slate-200 hover:border-slate-700 transition-colors"
                    >
                        <span>Model Fields</span>
                        {collapsedSections.models ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                    </button>
                    {!collapsedSections.models && (
                        <div className="pl-1 space-y-2">
                            <div className="grid grid-cols-[74px_1fr] items-center gap-2">
                                <label className="text-[10px] text-slate-500 uppercase tracking-wider">Provider</label>
                                <select
                                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-300 focus:border-indigo-500 focus:outline-none"
                                    value={localFilters.model_provider || ''}
                                    onChange={e => handleProviderChange(e.target.value)}
                                >
                                    <option value="">All</option>
                                    {providerOptions.map(provider => (
                                        <option key={provider} value={provider}>{provider}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="grid grid-cols-[74px_1fr] items-center gap-2">
                                <label className="text-[10px] text-slate-500 uppercase tracking-wider">Family</label>
                                <select
                                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-300 focus:border-indigo-500 focus:outline-none"
                                    value={localFilters.model_family || ''}
                                    onChange={e => handleFamilyChange(e.target.value)}
                                >
                                    <option value="">All</option>
                                    {familyOptions.map(family => (
                                        <option key={family} value={family}>{family}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="grid grid-cols-[74px_1fr] items-center gap-2">
                                <label className="text-[10px] text-slate-500 uppercase tracking-wider">Version</label>
                                <select
                                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-300 focus:border-indigo-500 focus:outline-none disabled:opacity-50"
                                    value={localFilters.model_version || ''}
                                    onChange={e => handleVersionChange(e.target.value)}
                                    disabled={!localFilters.model_family}
                                >
                                    <option value="">
                                        {localFilters.model_family ? 'All' : 'Select family first'}
                                    </option>
                                    {versionOptions.map(version => (
                                        <option key={version.value} value={version.value}>{version.label}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="grid grid-cols-[74px_1fr] items-center gap-2">
                                <label className="text-[10px] text-slate-500 uppercase tracking-wider">Model</label>
                                <select
                                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-300 focus:border-indigo-500 focus:outline-none disabled:opacity-50"
                                    value={localFilters.model || ''}
                                    onChange={e => handleChange('model', e.target.value)}
                                    disabled={!localFilters.model_version}
                                >
                                    <option value="">
                                        {localFilters.model_version ? 'All' : 'Select version first'}
                                    </option>
                                    {modelOptions.map(model => (
                                        <option key={model.value} value={model.value}>{model.label}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    )}

                    <button
                        onClick={() => toggleSection('dates')}
                        className="w-full flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-slate-400 border border-slate-800 rounded-md px-2.5 py-2 hover:text-slate-200 hover:border-slate-700 transition-colors"
                    >
                        <span>Date Ranges</span>
                        {collapsedSections.dates ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                    </button>
                    {!collapsedSections.dates && (
                        <div className="pl-1 space-y-2">
                            {renderDateRangeControl('Started', 'start_date', 'end_date')}
                            {renderDateRangeControl('Created', 'created_start', 'created_end')}
                            {renderDateRangeControl('Completed', 'completed_start', 'completed_end')}
                            {renderDateRangeControl('Updated', 'updated_start', 'updated_end')}
                        </div>
                    )}
                </div>

                <div className="mt-3 space-y-2">
                    <p className="text-[10px] text-slate-500 leading-snug break-words">
                        {modelFacetsLoading || platformFacetsLoading
                            ? 'Loading model/platform history…'
                            : `${normalizedModelFacets.length} model variants · ${normalizedPlatformFacets.length} platform versions`}
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                        <button
                            onClick={clearFilters}
                            className="w-full inline-flex items-center justify-center rounded-md border border-rose-500/30 bg-rose-500/15 px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-rose-200 hover:bg-rose-500/25 hover:border-rose-400/50 disabled:opacity-40 disabled:hover:bg-rose-500/15 disabled:hover:border-rose-500/30"
                            disabled={!hasActiveFilters}
                        >
                            Clear
                        </button>
                        <button
                            onClick={applyFilters}
                            className="w-full inline-flex items-center justify-center rounded-md border border-indigo-500/40 bg-indigo-500/25 px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-indigo-100 hover:bg-indigo-500/35 hover:border-indigo-400/60 disabled:opacity-40 disabled:hover:bg-indigo-500/25 disabled:hover:border-indigo-500/40"
                            disabled={!hasPendingChanges}
                        >
                            Apply
                        </button>
                    </div>
                </div>
            </SidebarFiltersSection>

            <SidebarFiltersSection title="Data Sync" icon={RefreshCw}>
                <button
                    onClick={async () => {
                        try {
                            const btn = document.getElementById('force-sync-btn');
                            if (btn) btn.classList.add('animate-spin');
                            await fetch('/api/cache/rescan', { method: 'POST' });
                            setTimeout(() => {
                                window.location.reload();
                            }, 2000);
                        } catch (e) {
                            console.error('Sync failed', e);
                        }
                    }}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-bold transition-all border border-slate-700 hover:border-slate-600"
                    title="Force full project re-scan"
                >
                    <RefreshCw size={14} id="force-sync-btn" />
                    <span>Force Sync</span>
                </button>
            </SidebarFiltersSection>
        </SidebarFiltersPortal>
    );
};

const SessionDetail: React.FC<{ session: AgentSession; onBack: () => void; onOpenSession: (sessionId: string) => void }> = ({ session, onBack, onOpenSession }) => {
    const { getSessionById } = useData();
    const navigate = useNavigate();
    const [selectedLogId, setSelectedLogId] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<'transcript' | 'activity' | 'forensics' | 'analytics' | 'agents' | 'impact' | 'files' | 'artifacts' | 'features'>('transcript');
    const [filterAgent, setFilterAgent] = useState<string | null>(null);
    const [viewingDoc, setViewingDoc] = useState<PlanDocument | null>(null);
    const [threadSessions, setThreadSessions] = useState<AgentSession[]>([]);
    const [threadSessionDetails, setThreadSessionDetails] = useState<Record<string, AgentSession>>({ [session.id]: session });
    const [linkedSourceLogId, setLinkedSourceLogId] = useState<string | null>(null);
    const [linkedFeatureLinks, setLinkedFeatureLinks] = useState<SessionFeatureLink[]>([]);

    useEffect(() => {
        let cancelled = false;
        const rootSessionId = session.rootSessionId || session.id;
        const load = async () => {
            try {
                const params = new URLSearchParams({
                    offset: '0',
                    limit: '500',
                    sort_by: 'started_at',
                    sort_order: 'desc',
                    include_subagents: 'true',
                    root_session_id: rootSessionId,
                });
                const res = await fetch(`/api/sessions?${params.toString()}`);
                if (!res.ok) return;
                const data = await res.json();
                if (!cancelled) {
                    setThreadSessions(data.items || []);
                }
            } catch (e) {
                console.error('Failed to load thread sessions', e);
            }
        };
        void load();
        return () => {
            cancelled = true;
        };
    }, [session.id, session.rootSessionId]);

    useEffect(() => {
        setThreadSessionDetails(prev => ({ ...prev, [session.id]: session }));
    }, [session]);

    useEffect(() => {
        let cancelled = false;
        const uniqueIds = Array.from(new Set([session.id, ...threadSessions.map(thread => thread.id)]));
        if (uniqueIds.length === 0) return;

        const loadThreadDetails = async () => {
            const detailEntries = await Promise.all(
                uniqueIds.map(async (threadId) => {
                    if (threadId === session.id) {
                        return [threadId, session] as const;
                    }
                    const detailed = await getSessionById(threadId);
                    return [threadId, detailed] as const;
                })
            );
            if (cancelled) return;
            setThreadSessionDetails(prev => {
                const next = { ...prev };
                detailEntries.forEach(([threadId, detailed]) => {
                    if (detailed) next[threadId] = detailed;
                });
                return next;
            });
        };

        void loadThreadDetails();
        return () => {
            cancelled = true;
        };
    }, [getSessionById, session, threadSessions]);

    useEffect(() => {
        let cancelled = false;
        const load = async () => {
            try {
                const res = await fetch(`/api/sessions/${encodeURIComponent(session.id)}/linked-features`);
                if (!res.ok) throw new Error(`Failed to load linked features (${res.status})`);
                const data = await res.json();
                if (!cancelled) {
                    setLinkedFeatureLinks(Array.isArray(data) ? data : []);
                }
            } catch {
                if (!cancelled) {
                    setLinkedFeatureLinks([]);
                }
            }
        };
        void load();
        return () => {
            cancelled = true;
        };
    }, [session.id]);

    const subagentNameBySessionId = useMemo(() => {
        const names = new Map<string, string>();

        for (const log of session.logs) {
            if (log.type !== 'tool' || log.toolCall?.name !== 'Task' || !log.linkedSessionId) {
                continue;
            }
            const taskSubagentName = extractTaskSubagentName(log.toolCall?.args);
            if (taskSubagentName) {
                names.set(log.linkedSessionId, taskSubagentName);
            }
        }

        for (const log of session.logs) {
            if (log.type !== 'subagent_start' || !log.linkedSessionId || names.has(log.linkedSessionId)) {
                continue;
            }
            const metadataName = takeString(log.metadata?.subagentName, log.metadata?.subagentType);
            if (metadataName) {
                names.set(log.linkedSessionId, metadataName);
            }
        }

        for (const thread of threadSessions) {
            if (!names.has(thread.id) && thread.agentId) {
                names.set(thread.id, `agent-${thread.agentId}`);
            }
        }

        return names;
    }, [session.logs, threadSessions]);

    const handleSelectAgent = (agent: string) => {
        setFilterAgent(agent || null); // Empty string resets filter
        setActiveTab('transcript');
    };

    const handleJumpToTranscript = (agentName?: string) => {
        if (agentName) setFilterAgent(agentName);
        else setFilterAgent(null);
        setActiveTab('transcript');
    }

    const handleShowLinked = (tab: 'activity' | 'artifacts', sourceLogId: string) => {
        setLinkedSourceLogId(sourceLogId);
        setActiveTab(tab);
    };

    const primaryFeatureLink = useMemo(
        () => linkedFeatureLinks.find(link => link.isPrimaryLink) || null,
        [linkedFeatureLinks]
    );
    const sessionDisplayTitle = useMemo(
        () => deriveSessionCardTitle(session.id, session.title, session.sessionMetadata || null),
        [session.id, session.title, session.sessionMetadata]
    );

    const handleOpenFeature = useCallback((featureId: string) => {
        if (!featureId) return;
        navigate(`/board?feature=${encodeURIComponent(featureId)}`);
    }, [navigate]);

    return (
        <div className="h-full flex flex-col animate-in fade-in slide-in-from-bottom-4 duration-500 relative">
            {/* Header */}
            <div className="flex justify-between items-center mb-4 px-2">
                <div className="flex items-center gap-4">
                    <button onClick={onBack} className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-all group">
                        <ArrowLeft size={18} className="group-hover:-translate-x-1 transition-transform" />
                    </button>
                    <div>
                        <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
                            {sessionDisplayTitle}
                        </h2>
                        <div className="text-xs text-slate-500 font-mono tracking-wider mt-0.5">{session.id}</div>
                        <div className="flex items-center gap-3 mt-0.5">
                            <span className="text-xs text-slate-500 flex items-center gap-1.5"><Calendar size={12} /> {new Date(session.startedAt).toLocaleString()}</span>
                            <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${session.status === 'active' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-slate-800 text-slate-500'}`}>
                                {session.status}
                            </span>
                        </div>
                    </div>
                </div>

                {/* Tabs */}
                <div className="flex items-center bg-slate-900 rounded-lg p-1 border border-slate-800 overflow-x-auto">
                    {[
                        { id: 'transcript', icon: MessageSquare, label: 'Transcript' },
                        { id: 'activity', icon: Activity, label: 'Activity' },
                        { id: 'forensics', icon: ShieldAlert, label: 'Forensics' },
                        { id: 'features', icon: Box, label: `Features (${linkedFeatureLinks.length})` },
                        { id: 'files', icon: FileText, label: 'Files' },
                        { id: 'artifacts', icon: LinkIcon, label: 'Artifacts' },
                        { id: 'impact', icon: TrendingUp, label: 'App Impact' },
                        { id: 'analytics', icon: BarChart2, label: 'Analytics' },
                        { id: 'agents', icon: Users, label: 'Agents' },
                    ].map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id as any)}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all whitespace-nowrap ${activeTab === tab.id
                                ? 'bg-indigo-600 text-white shadow'
                                : 'text-slate-400 hover:text-slate-200'
                                }`}
                        >
                            <tab.icon size={14} />
                            {tab.label}
                        </button>
                    ))}
                </div>

                <div className="flex items-center gap-6">
                    <div className="text-right">
                        <div className="text-[10px] text-slate-500 uppercase font-bold tracking-widest mb-1">Session Cost</div>
                        <div className="text-emerald-400 font-mono font-bold text-lg">${session.totalCost.toFixed(2)}</div>
                    </div>
                </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 min-h-0 min-w-full">
                {activeTab === 'transcript' && (
                    <TranscriptView
                        session={session}
                        selectedLogId={selectedLogId}
                        setSelectedLogId={setSelectedLogId}
                        filterAgent={filterAgent}
                        threadSessions={threadSessions}
                        subagentNameBySessionId={subagentNameBySessionId}
                        onOpenThread={onOpenSession}
                        onShowLinked={handleShowLinked}
                        primaryFeatureLink={primaryFeatureLink}
                        onOpenFeature={handleOpenFeature}
                        onOpenForensics={() => setActiveTab('forensics')}
                    />
                )}
                {activeTab === 'features' && (
                    <SessionFeaturesView
                        linkedFeatures={linkedFeatureLinks}
                        onOpenFeature={handleOpenFeature}
                    />
                )}
                {activeTab === 'forensics' && <SessionForensicsView session={session} />}
                {activeTab === 'activity' && (
                    <ActivityView
                        session={session}
                        threadSessions={threadSessions}
                        threadSessionDetails={threadSessionDetails}
                        subagentNameBySessionId={subagentNameBySessionId}
                        onOpenDoc={setViewingDoc}
                        onOpenThread={onOpenSession}
                        highlightedSourceLogId={linkedSourceLogId}
                    />
                )}
                {activeTab === 'files' && (
                    <FilesView
                        session={session}
                        threadSessions={threadSessions}
                        threadSessionDetails={threadSessionDetails}
                        subagentNameBySessionId={subagentNameBySessionId}
                        onOpenDoc={setViewingDoc}
                        highlightedSourceLogId={linkedSourceLogId}
                    />
                )}
                {activeTab === 'artifacts' && (
                    <ArtifactsView
                        session={session}
                        threadSessions={threadSessions}
                        subagentNameBySessionId={subagentNameBySessionId}
                        onOpenThread={onOpenSession}
                        highlightedSourceLogId={linkedSourceLogId}
                    />
                )}
                {activeTab === 'analytics' && <AnalyticsView session={session} goToTranscript={handleJumpToTranscript} />}
                {activeTab === 'agents' && (
                    <AgentsView
                        session={session}
                        onSelectAgent={handleSelectAgent}
                        threadSessions={threadSessions}
                        subagentNameBySessionId={subagentNameBySessionId}
                        onOpenThread={onOpenSession}
                    />
                )}
                {activeTab === 'impact' && <ImpactView session={session} />}
            </div>

            {viewingDoc && <DocumentModal doc={viewingDoc} onClose={() => setViewingDoc(null)} />}
        </div>
    );
};

export const SessionInspector: React.FC = () => {
    const { sessions, loadMoreSessions, hasMoreSessions, getSessionById, loading } = useData();
    const [searchParams, setSearchParams] = useSearchParams();
    const [selectedSession, setSelectedSession] = useState<AgentSession | null>(null);
    const [sessionBackStack, setSessionBackStack] = useState<AgentSession[]>([]);

    const openSession = useCallback(async (sessionId: string, fallback?: AgentSession, options?: { pushCurrent?: boolean }) => {
        if (options?.pushCurrent && selectedSession) {
            setSessionBackStack(prev => {
                if (prev.length > 0 && prev[prev.length - 1].id === selectedSession.id) {
                    return prev;
                }
                return [...prev, selectedSession];
            });
        }
        const full = await getSessionById(sessionId);
        if (full) {
            setSelectedSession(full);
            return;
        }
        if (fallback) {
            setSelectedSession(fallback);
        }
    }, [getSessionById, selectedSession]);

    const handleBackFromSession = useCallback(() => {
        setSessionBackStack(prev => {
            if (prev.length === 0) {
                setSelectedSession(null);
                return prev;
            }
            const parent = prev[prev.length - 1];
            setSelectedSession(parent);
            return prev.slice(0, -1);
        });
    }, []);

    // Deep-link: auto-select session from URL params
    useEffect(() => {
        const sessionParam = searchParams.get('session');
        if (sessionParam) {
            const exists = sessions.find(s => s.id === sessionParam);
            setSessionBackStack([]);
            void openSession(sessionParam, exists);
            setSearchParams({}, { replace: true });
        }
    }, [searchParams, sessions, setSearchParams, openSession]);

    const [sessionsViewMode, setSessionsViewMode] = useState<'threaded' | 'cards'>('threaded');
    const [expandedThreadSessionIds, setExpandedThreadSessionIds] = useState<Set<string>>(new Set());
    const liveNowMs = Date.now();

    const activeSessions = useMemo(
        () => sessions.filter(session => isSessionLiveInFlight(session, liveNowMs)),
        [sessions, liveNowMs]
    );
    const pastSessions = useMemo(
        () => sessions.filter(session => !isSessionLiveInFlight(session, liveNowMs)),
        [sessions, liveNowMs]
    );

    const sessionThreadRoots = useMemo(() => buildSessionThreadForest(sessions), [sessions]);
    const activeSessionThreadRoots = useMemo(
        () => sessionThreadRoots.filter(node => threadNodeHasLiveSession(node, liveNowMs)),
        [sessionThreadRoots, liveNowMs]
    );
    const pastSessionThreadRoots = useMemo(
        () => sessionThreadRoots.filter(node => !threadNodeHasLiveSession(node, liveNowMs)),
        [sessionThreadRoots, liveNowMs]
    );

    const openSessionFromList = useCallback((session: AgentSession) => {
        setSessionBackStack([]);
        void openSession(session.id, session);
    }, [openSession]);

    const toggleThreadChildren = useCallback((sessionId: string) => {
        setExpandedThreadSessionIds(prev => {
            const next = new Set(prev);
            if (next.has(sessionId)) next.delete(sessionId);
            else next.add(sessionId);
            return next;
        });
    }, []);

    const renderThreadNode = useCallback((node: SessionThreadNode, depth = 0): React.ReactNode => {
        const hasChildren = node.children.length > 0;
        const expanded = expandedThreadSessionIds.has(node.session.id);
        const displayStatus = isSessionLiveInFlight(node.session, liveNowMs) ? 'active' : 'completed';

        return (
            <div key={node.session.id} className="space-y-2">
                <SessionSummaryCard
                    session={node.session}
                    statusOverride={displayStatus}
                    threadToggle={hasChildren ? {
                        expanded,
                        childCount: countSessionThreadNodes(node.children),
                        onToggle: () => toggleThreadChildren(node.session.id),
                        label: 'Sub-Threads',
                    } : undefined}
                    onClick={() => openSessionFromList(node.session)}
                />

                {hasChildren && expanded && (
                    <div className={`mt-3 ${depth > 0 ? 'ml-2' : ''} pl-4 border-l border-slate-700/80 space-y-3`}>
                        {node.children.map(child => (
                            <div key={child.session.id} className="relative pl-3">
                                <div className="absolute left-0 top-5 w-3 border-t border-slate-700/80" />
                                {renderThreadNode(child, depth + 1)}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        );
    }, [expandedThreadSessionIds, liveNowMs, openSessionFromList, toggleThreadChildren]);

    if (selectedSession) {
        return (
            <SessionDetail
                session={selectedSession}
                onBack={handleBackFromSession}
                onOpenSession={(sessionId) => { void openSession(sessionId, undefined, { pushCurrent: true }); }}
            />
        );
    }

    return (
        <div className="h-full flex flex-col gap-8 animate-in fade-in duration-500 overflow-y-auto pb-8">
            <div>
                <h2 className="text-3xl font-bold text-slate-100 mb-2 font-mono tracking-tighter">Session Forensics</h2>
                <p className="text-slate-400 max-w-2xl mb-6">Examine agent behavior, tool call chains, and multi-agent orchestration logs with millisecond-precision timestamps.</p>
                <SessionFilterBar />
            </div>

            <div className="space-y-10">
                <div className="flex justify-end">
                    <div className="bg-slate-900 border border-slate-800 p-1 rounded-lg flex gap-1">
                        <button
                            onClick={() => setSessionsViewMode('threaded')}
                            className={`p-1.5 rounded-md transition-all flex items-center gap-1.5 text-[11px] ${sessionsViewMode === 'threaded' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
                            title="Nested thread tree view"
                        >
                            <Layers size={14} />
                            Threaded
                        </button>
                        <button
                            onClick={() => setSessionsViewMode('cards')}
                            className={`p-1.5 rounded-md transition-all flex items-center gap-1.5 text-[11px] ${sessionsViewMode === 'cards' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
                            title="Flat all-sessions card view"
                        >
                            <LayoutGrid size={14} />
                            All Session Cards
                        </button>
                    </div>
                </div>

                {/* Active Sessions Section */}
                <div className="space-y-4">
                    <h3 className="text-xs font-bold text-emerald-500 uppercase tracking-[0.2em] flex items-center gap-2">
                        <Activity size={16} /> Live In-Flight
                    </h3>
                    <p className="text-[11px] text-emerald-300/70 -mt-2">
                        Active sessions with updates in the last 10 minutes.
                    </p>
                    {sessionsViewMode === 'threaded' ? (
                        <div className="space-y-4">
                            {activeSessionThreadRoots.map(node => renderThreadNode(node))}
                            {activeSessionThreadRoots.length === 0 && (
                                <div className="col-span-full border border-dashed border-slate-800 rounded-2xl p-10 text-center text-slate-600 bg-slate-900/10">
                                    <Zap size={32} className="mx-auto mb-3 opacity-10" />
                                    <p className="text-sm">No live sessions detected on local system.</p>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                            {activeSessions.map(session => (
                                <SessionSummaryCard
                                    key={session.id}
                                    session={session}
                                    statusOverride="active"
                                    onClick={() => openSessionFromList(session)}
                                />
                            ))}
                            {activeSessions.length === 0 && (
                                <div className="col-span-full border border-dashed border-slate-800 rounded-2xl p-10 text-center text-slate-600 bg-slate-900/10">
                                    <Zap size={32} className="mx-auto mb-3 opacity-10" />
                                    <p className="text-sm">No live sessions detected on local system.</p>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Past Sessions Section */}
                <div className="space-y-4">
                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-[0.2em] flex items-center gap-2">
                        <Archive size={16} /> Historical Index
                    </h3>

                    {sessionsViewMode === 'threaded' ? (
                        <div className="space-y-4">
                            {pastSessionThreadRoots.map(node => renderThreadNode(node))}
                            {pastSessionThreadRoots.length === 0 && (
                                <div className="col-span-full border border-dashed border-slate-800 rounded-2xl p-10 text-center text-slate-600 bg-slate-900/10">
                                    <Zap size={32} className="mx-auto mb-3 opacity-10" />
                                    <p className="text-sm">No historical sessions found.</p>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                            {pastSessions.map(session => (
                                <SessionSummaryCard
                                    key={session.id}
                                    session={session}
                                    statusOverride="completed"
                                    onClick={() => openSessionFromList(session)}
                                />
                            ))}
                        </div>
                    )}

                    {hasMoreSessions && (
                        <div className="pt-4 flex justify-center">
                            <button
                                onClick={() => loadMoreSessions()}
                                disabled={loading}
                                className="px-6 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-full text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
                            >
                                {loading && <Activity size={14} className="animate-spin" />}
                                {loading ? 'Loading...' : 'Load More Sessions'}
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

const SessionSummaryCard: React.FC<{
    session: AgentSession;
    onClick: () => void;
    className?: string;
    statusOverride?: AgentSession['status'];
    threadToggle?: {
        expanded: boolean;
        childCount: number;
        onToggle: () => void;
        label?: string;
    };
}> = ({ session, onClick, className, statusOverride, threadToggle }) => {
    const displayTitle = deriveSessionCardTitle(session.id, session.title, session.sessionMetadata || null);
    const agentNames = Array.from(new Set(session.logs.filter(l => l.speaker === 'agent').map(l => l.agentName || 'Agent'))).slice(0, 3);
    const agentBadges = (session.agentsUsed && session.agentsUsed.length > 0)
        ? session.agentsUsed
        : Array.from(new Set(session.logs.filter(l => l.speaker === 'agent').map(l => l.agentName || 'Agent')));
    const models = (session.modelsUsed && session.modelsUsed.length > 0)
        ? session.modelsUsed.map(modelInfo => ({
            raw: modelInfo.raw,
            displayName: modelInfo.modelDisplayName,
            provider: modelInfo.modelProvider,
            family: modelInfo.modelFamily,
            version: modelInfo.modelVersion,
        }))
        : [{
            raw: session.model,
            displayName: session.modelDisplayName,
            provider: session.modelProvider,
            family: session.modelFamily,
            version: session.modelVersion,
        }];
    const detailSections: SessionCardDetailSection[] = [];
    const toolSummary = Array.isArray(session.toolSummary) ? session.toolSummary.filter(Boolean) : [];
    if (toolSummary.length > 0) {
        detailSections.push({
            id: `${session.id}-tools`,
            label: 'Tools',
            items: toolSummary,
        });
    }
    const displayStatus = statusOverride || session.status;
    return (
        <SessionCard
            sessionId={session.id}
            title={displayTitle}
            status={displayStatus}
            startedAt={session.startedAt}
            endedAt={session.endedAt}
            updatedAt={session.updatedAt}
            dates={session.dates}
            model={{
                raw: session.model,
                displayName: session.modelDisplayName,
                provider: session.modelProvider,
                family: session.modelFamily,
                version: session.modelVersion,
            }}
            models={models}
            agentBadges={agentBadges}
            skillBadges={session.skillsUsed || []}
            detailSections={detailSections}
            metadata={session.sessionMetadata || null}
            threadToggle={threadToggle}
            onClick={onClick}
            className={`group p-6 hover:border-indigo-500/50 hover:shadow-2xl hover:shadow-indigo-500/5 relative overflow-hidden ${className || ''}`}
            headerRight={(
                <div className="text-right">
                    <div className="text-emerald-400 font-mono font-bold text-sm">${session.totalCost.toFixed(2)}</div>
                </div>
            )}
            infoBadges={(
                <span className="text-[10px] text-slate-500 font-mono">
                    {session.logs.length} logs
                </span>
            )}
        >
            {displayStatus === 'active' && (
                <div className="absolute top-0 right-0 p-3">
                    <span className="flex h-3 w-3">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                    </span>
                </div>
            )}
            <div className="pt-3 border-t border-slate-800/60 flex items-center justify-between">
                <div className="flex -space-x-2">
                    {agentNames.map((agent, i) => (
                        <div key={i} className="w-7 h-7 rounded-full bg-slate-800 border-2 border-slate-900 flex items-center justify-center text-[10px] text-indigo-400 font-bold group-hover:border-slate-700 transition-colors" title={agent}>
                            {agent[0]}
                        </div>
                    ))}
                </div>
                <div className="flex gap-1.5">
                    {[...Array(5)].map((_, i) => (
                        <div key={i} className={`w-1.5 h-1.5 rounded-full ${i < (session.qualityRating || 0) ? 'bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.6)]' : 'bg-slate-800'}`} />
                    ))}
                </div>
            </div>
        </SessionCard>
    );
};
