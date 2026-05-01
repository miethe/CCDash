import React, { useMemo } from 'react';
import { Activity, ExternalLink, FileText, GitCommit, Maximize2 } from 'lucide-react';
import { useData } from '../../contexts/DataContext';
import { AgentSession, PlanDocument, SessionActivityItem, SessionFileAggregateRow, SessionFileUpdate } from '../../types';
import { SessionCard, SessionCardDetailSection, deriveSessionCardTitle } from '../SessionCard';
import { resolveDisplayCost } from '../../lib/sessionSemantics';
import {
    collectCommitEvents,
    collectThreadDetailSessions,
    fileNameFromPath,
    formatAction,
    formatUsd,
    normalizeFileAction,
    normalizePath,
    parseLogIndex,
    resolveLocalPath,
    toEpoch,
    toGitHubBlobUrl,
} from './sessionInspectorShared';

const MAIN_SESSION_AGENT = 'Main Session';

const formatTimestampLabel = (timestamp?: string): string => (timestamp ? new Date(timestamp).toLocaleString() : '—');

const normalizedThreadKind = (session: AgentSession): string => {
    const explicit = String(session.threadKind || '').trim().toLowerCase();
    if (explicit) return explicit;
    const sessionType = String(session.sessionType || '').trim().toLowerCase();
    if (sessionType === 'fork') return 'fork';
    if (sessionType === 'subagent') return 'subagent';
    return 'root';
};

const isForkThread = (session: AgentSession): boolean => {
    if (session.forkParentSessionId) return true;
    return normalizedThreadKind(session) === 'fork';
};

const getThreadDisplayName = (thread: AgentSession, subagentNameBySessionId: Map<string, string>): string => {
    if (isForkThread(thread)) {
        const titledFork = (thread.title || '').trim();
        if (titledFork && titledFork !== thread.id) return titledFork;
        return `fork-${thread.id.slice(-6)}`;
    }
    const titled = (thread.title || '').trim();
    return (
        subagentNameBySessionId.get(thread.id) ||
        (titled && titled !== thread.id ? titled : '') ||
        (thread.agentId ? `agent-${thread.agentId}` : '') ||
        thread.sessionType ||
        'thread'
    );
};

const getRowKindLabel = (kind: SessionActivityItem['kind']): string => formatAction(kind);

type ActivityRow = SessionActivityItem & {
    timestampLabel: string;
    kindLabel: string;
};

type FileRow = SessionFileAggregateRow & {
    actionLabels: string[];
    lastTouchedLabel: string;
    doc: PlanDocument | null;
    sourceLogSet: Set<string>;
    sessionSet: Set<string>;
    agentSet: Set<string>;
    actionsSet: Set<string>;
};

const collectActivityRows = (
    session: AgentSession,
    sessionsForActivity: AgentSession[],
    documents: PlanDocument[],
    activeProjectPath: string | undefined,
    activeProjectRepoUrl: string | undefined,
    subagentNameBySessionId: Map<string, string>,
): ActivityRow[] => {
    const rows: ActivityRow[] = [];

    const resolveDocument = (path: string): PlanDocument | null => {
        const normalized = normalizePath(path);
        for (const doc of documents) {
            const docPath = normalizePath(doc.filePath);
            if (normalized === docPath || normalized.endsWith(`/${docPath}`) || docPath.endsWith(`/${normalized}`)) {
                return doc;
            }
        }
        return null;
    };

    for (const thread of sessionsForActivity) {
        const threadName = getThreadDisplayName(thread, subagentNameBySessionId);
        const logsById = new Map<string, AgentSession['logs'][number]>();
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
                timestampLabel: formatTimestampLabel(log.timestamp),
                kindLabel: getRowKindLabel('log'),
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
            const localPath = resolveLocalPath(filePath, activeProjectPath);
            const fileLogIndex = parseLogIndex(file.sourceLogId);
            const fileTs = toEpoch(file.timestamp);
            let commitHash = '';
            let nearestAfter: { hash: string; logIndex: number; timestampMs: number } | null = null;
            let nearestBefore: { hash: string; logIndex: number; timestampMs: number } | null = null;
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
                timestampLabel: formatTimestampLabel(file.timestamp || ''),
                kindLabel: getRowKindLabel('file'),
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
                githubUrl: commitHash ? toGitHubBlobUrl(activeProjectRepoUrl || '', commitHash, filePath, activeProjectPath) : null,
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
                timestampLabel: formatTimestampLabel(sourceLog?.timestamp || thread.startedAt),
                kindLabel: getRowKindLabel('artifact'),
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
};

const collectFileRows = (
    session: AgentSession,
    sessionsForFiles: AgentSession[],
    documents: PlanDocument[],
    activeProjectPath: string | undefined,
    subagentNameBySessionId: Map<string, string>,
): FileRow[] => {
    const resolveDocument = (path: string): PlanDocument | null => {
        const normalized = normalizePath(path);
        for (const doc of documents) {
            const docPath = normalizePath(doc.filePath);
            if (normalized === docPath || normalized.endsWith(`/${docPath}`) || docPath.endsWith(`/${normalized}`)) {
                return doc;
            }
        }
        return null;
    };

    const aggregates = new Map<string, FileRow>();
    const ensureAggregate = (filePath: string): FileRow => {
        const existing = aggregates.get(filePath);
        if (existing) return existing;
        const localPath = resolveLocalPath(filePath, activeProjectPath);
        const doc = resolveDocument(filePath);
        const created: FileRow = {
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
            actionLabels: [],
            lastTouchedLabel: '—',
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
        actionLabels: Array.from(row.actionsSet).sort().map(action => formatAction(action)),
        uniqueSessions: row.sessionSet.size,
        uniqueAgents: row.agentSet.size,
        sourceLogIds: Array.from(row.sourceLogSet),
        lastTouchedLabel: row.lastTouchedAt ? formatTimestampLabel(row.lastTouchedAt) : '—',
    }));
    rows.sort((a, b) => {
        const ta = toEpoch(a.lastTouchedAt);
        const tb = toEpoch(b.lastTouchedAt);
        if (ta !== tb) return tb - ta;
        return a.filePath.localeCompare(b.filePath);
    });
    return rows;
};

export const ActivityView: React.FC<{
    session: AgentSession;
    threadSessions: AgentSession[];
    threadSessionDetails: Record<string, AgentSession>;
    subagentNameBySessionId: Map<string, string>;
    onOpenDoc: (doc: PlanDocument) => void;
    onOpenFile: (filePath: string, localPath?: string | null) => void;
    onOpenThread: (sessionId: string) => void;
    highlightedSourceLogId?: string | null;
}> = ({ session, threadSessions, threadSessionDetails, subagentNameBySessionId, onOpenDoc, onOpenFile, onOpenThread, highlightedSourceLogId }) => {
    const { documents, activeProject } = useData();
    const sessionsForActivity = useMemo(
        () => collectThreadDetailSessions(session, threadSessions, threadSessionDetails),
        [session, threadSessions, threadSessionDetails]
    );

    const activityRows = useMemo(
        () => collectActivityRows(
            session,
            sessionsForActivity,
            documents,
            activeProject?.path,
            activeProject?.repoUrl,
            subagentNameBySessionId,
            highlightedSourceLogId,
        ),
        [activeProject?.path, activeProject?.repoUrl, documents, highlightedSourceLogId, session, sessionsForActivity, subagentNameBySessionId]
    );

    const openRowViewer = (row: ActivityRow) => {
        if (!row.filePath) return;
        if (row.documentId) {
            const doc = documents.find(item => item.id === row.documentId);
            if (doc) {
                onOpenDoc(doc);
                return;
            }
        }
        onOpenFile(row.filePath, row.localPath);
    };

    const openRowFile = (row: ActivityRow) => {
        if (!row.localPath) return;
        window.location.href = `vscode://file/${encodeURI(row.localPath)}`;
    };

    if (activityRows.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                <Activity size={48} className="mb-4 opacity-20" />
                <p>No activity entries found for this thread family.</p>
            </div>
        );
    }

    return (
        <div className="bg-panel border border-panel-border rounded-xl overflow-hidden h-full flex flex-col">
            <div className="grid grid-cols-[170px_90px_1fr_130px_160px] gap-2 px-3 py-2 border-b border-panel-border bg-surface-overlay/70 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
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
                        className={`grid grid-cols-[170px_90px_1fr_130px_160px] gap-2 px-3 py-2 border-b border-panel-border/80 text-xs hover:bg-surface-muted/40 ${highlightedSourceLogId && row.sourceLogId === highlightedSourceLogId ? 'bg-indigo-500/10 border-indigo-500/30' : ''}`}
                    >
                        <div className="text-muted-foreground text-[11px]">{row.timestampLabel}</div>
                        <div>
                            <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] ${row.kind === 'file' ? 'border-blue-500/30 bg-blue-500/10 text-blue-300' : row.kind === 'artifact' ? 'border-amber-500/30 bg-amber-500/10 text-amber-300' : 'border-hover bg-surface-muted/40 text-foreground'}`}>
                                {row.kindLabel}
                            </span>
                        </div>
                        <div className="min-w-0">
                            <div className="truncate text-panel-foreground">{row.label}</div>
                            {row.detail && <div className="truncate text-[11px] text-muted-foreground">{row.detail}</div>}
                            {row.kind === 'file' && (
                                <div className="text-[10px] font-mono mt-0.5">
                                    <span className="text-emerald-400">+{row.additions || 0}</span>
                                    <span className="mx-1 text-muted-foreground">/</span>
                                    <span className="text-rose-400">-{row.deletions || 0}</span>
                                </div>
                            )}
                        </div>
                        <div className="truncate text-muted-foreground">{row.threadName || row.sessionId}</div>
                        <div className="flex items-center gap-1 justify-end">
                            {row.kind === 'file' && row.filePath && (
                                <button
                                    onClick={() => openRowViewer(row)}
                                    className="p-1 rounded text-muted-foreground hover:text-indigo-300 hover:bg-indigo-500/10"
                                    title="Open in shared viewer"
                                >
                                    <Maximize2 size={14} />
                                </button>
                            )}
                            {row.kind === 'file' && row.localPath && (
                                <button
                                    onClick={() => openRowFile(row)}
                                    className="p-1 rounded text-muted-foreground hover:text-indigo-300 hover:bg-indigo-500/10"
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
                                    className="p-1 rounded text-muted-foreground hover:text-indigo-300 hover:bg-indigo-500/10"
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

export const FilesView: React.FC<{
    session: AgentSession;
    threadSessions: AgentSession[];
    threadSessionDetails: Record<string, AgentSession>;
    subagentNameBySessionId: Map<string, string>;
    onOpenDoc: (doc: PlanDocument) => void;
    onOpenFile: (filePath: string, localPath?: string | null) => void;
    highlightedSourceLogId?: string | null;
}> = ({ session, threadSessions, threadSessionDetails, subagentNameBySessionId, onOpenDoc, onOpenFile, highlightedSourceLogId }) => {
    const { documents, activeProject } = useData();
    const sessionsForFiles = useMemo(
        () => collectThreadDetailSessions(session, threadSessions, threadSessionDetails),
        [session, threadSessions, threadSessionDetails]
    );

    const fileRows = useMemo(
        () => collectFileRows(session, sessionsForFiles, documents, activeProject?.path, subagentNameBySessionId),
        [activeProject?.path, documents, session, sessionsForFiles, subagentNameBySessionId]
    );

    if (fileRows.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                <FileText size={48} className="mb-4 opacity-20" />
                <p>No tracked files found for this thread family.</p>
            </div>
        );
    }

    return (
        <div className="bg-panel border border-panel-border rounded-xl overflow-hidden h-full flex flex-col">
            <div className="grid grid-cols-[1.2fr_1.1fr_70px_80px_80px_150px_100px_110px] gap-2 px-3 py-2 border-b border-panel-border bg-surface-overlay/70 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                <div>File</div>
                <div>Path</div>
                <div>Actions</div>
                <div>Touches</div>
                <div>Sessions</div>
                <div>Last Touched</div>
                <div>Net Diff</div>
                <div>Links</div>
            </div>
            <div className="flex-1 overflow-y-auto">
                {fileRows.map(row => (
                    <div
                        key={row.key}
                        className={`grid grid-cols-[1.2fr_1.1fr_70px_80px_80px_150px_100px_110px] gap-2 px-3 py-2 border-b border-panel-border/80 text-xs hover:bg-surface-muted/40 ${highlightedSourceLogId && row.sourceLogIds.includes(highlightedSourceLogId) ? 'bg-indigo-500/10 border-indigo-500/30' : ''}`}
                    >
                        <div className="truncate text-panel-foreground font-medium">{row.fileName}</div>
                        <div className="truncate font-mono text-[11px] text-muted-foreground">{row.filePath}</div>
                        <div className="flex flex-wrap gap-1">
                            {row.actionLabels.map((label, index) => (
                                <span key={`${row.key}:${row.actions[index]}`} className={`inline-flex rounded border px-1 py-0.5 text-[10px] ${row.actions[index] === 'read' ? 'bg-blue-500/10 border-blue-500/30 text-blue-300' : row.actions[index] === 'create' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : row.actions[index] === 'update' ? 'bg-amber-500/10 border-amber-500/30 text-amber-300' : row.actions[index] === 'delete' ? 'bg-rose-500/10 border-rose-500/30 text-rose-300' : 'bg-surface-muted/40 border-hover text-foreground'}`}>
                                    {label}
                                </span>
                            ))}
                        </div>
                        <div className="text-foreground">{row.touchCount}</div>
                        <div className="text-foreground">{row.uniqueSessions}</div>
                        <div className="text-muted-foreground text-[11px]">{row.lastTouchedLabel}</div>
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
                                    onOpenFile(row.filePath, row.localPath);
                                }}
                                className="p-1 rounded text-muted-foreground hover:text-indigo-300 hover:bg-indigo-500/10"
                                title="Open in shared viewer"
                            >
                                <Maximize2 size={14} />
                            </button>
                            {row.localPath && (
                                <button
                                    onClick={() => {
                                        window.location.href = `vscode://file/${encodeURI(row.localPath)}`;
                                    }}
                                    className="p-1 rounded text-muted-foreground hover:text-indigo-300 hover:bg-indigo-500/10"
                                    title="Open locally"
                                >
                                    <ExternalLink size={14} />
                                </button>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export const SessionSummaryCard: React.FC<{
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
    const displayTitle = useMemo(
        () => deriveSessionCardTitle(session.id, session.title, session.sessionMetadata || null),
        [session.id, session.sessionMetadata, session.title]
    );
    const agentNames = useMemo(
        () => Array.from(new Set(session.logs.filter(l => l.speaker === 'agent').map(l => l.agentName || 'Agent'))).slice(0, 3),
        [session.logs]
    );
    const agentBadges = useMemo(
        () => (session.agentsUsed && session.agentsUsed.length > 0)
            ? session.agentsUsed
            : Array.from(new Set(session.logs.filter(l => l.speaker === 'agent').map(l => l.agentName || 'Agent'))),
        [session.agentsUsed, session.logs]
    );
    const models = useMemo(
        () => (session.modelsUsed && session.modelsUsed.length > 0)
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
            }],
        [session.model, session.modelDisplayName, session.modelFamily, session.modelProvider, session.modelVersion, session.modelsUsed]
    );
    const detailSections = useMemo<SessionCardDetailSection[]>(() => {
        const sections: SessionCardDetailSection[] = [];
        const toolSummary = Array.isArray(session.toolSummary) ? session.toolSummary.filter(Boolean) : [];
        if (toolSummary.length > 0) {
            sections.push({
                id: `${session.id}-tools`,
                label: 'Tools',
                items: toolSummary,
            });
        }
        return sections;
    }, [session.id, session.toolSummary]);
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
                    <div className="text-emerald-400 font-mono font-bold text-sm">${formatUsd(resolveDisplayCost(session), 2)}</div>
                </div>
            )}
            infoBadges={(
                <div className="flex items-center gap-2">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold uppercase tracking-wider ${
                        isForkThread(session)
                            ? 'text-cyan-300 border-cyan-500/35 bg-cyan-500/10'
                            : normalizedThreadKind(session) === 'subagent'
                                ? 'text-fuchsia-300 border-fuchsia-500/35 bg-fuchsia-500/10'
                                : 'text-muted-foreground border-panel-border bg-panel'
                    }`}>
                        {normalizedThreadKind(session)}
                    </span>
                    <span className="text-[10px] text-muted-foreground font-mono">
                        {session.logs.length} logs
                    </span>
                    {session.currentContextTokens && session.contextWindowSize ? (
                        <span className="text-[10px] px-1.5 py-0.5 rounded border border-cyan-500/30 text-cyan-200 bg-cyan-500/10">
                            Context {Number(session.contextUtilizationPct || 0).toFixed(1)}%
                        </span>
                    ) : null}
                </div>
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
            <div className="pt-3 border-t border-panel-border/70 flex items-center justify-between">
                <div className="flex -space-x-2">
                    {agentNames.map((agent, i) => (
                        <div key={i} className="w-7 h-7 rounded-full bg-surface-muted border-2 border-panel-border flex items-center justify-center text-[10px] text-indigo-400 font-bold group-hover:border-panel-border transition-colors" title={agent}>
                            {agent[0]}
                        </div>
                    ))}
                </div>
                <div className="flex gap-1.5">
                    {[...Array(5)].map((_, i) => (
                        <div key={i} className={`w-1.5 h-1.5 rounded-full ${i < (session.qualityRating || 0) ? 'bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.6)]' : 'bg-surface-muted'}`} />
                    ))}
                </div>
            </div>
        </SessionCard>
    );
};
