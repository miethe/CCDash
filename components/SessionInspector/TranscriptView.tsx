import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { AnimatePresence, motion } from 'framer-motion';
import { Activity, Archive, Bot, Box, Calendar, ChevronDown, ChevronRight, Clock, Code, Cpu, Database, Edit3, ExternalLink, GitBranch, GitCommit, HardDrive, Layers, Maximize2, MessageSquare, MoreHorizontal, PlayCircle, RefreshCw, Scroll, Search, ShieldAlert, Terminal, Users, X, Zap } from 'lucide-react';
import { AgentSession, Feature, LiveAgentActivity, LiveTranscriptState, ProjectTask, SessionArtifact, SessionLog, SessionTranscriptAppendPayload } from '../../types';
import { DocumentModal } from '../DocumentModal';
import { UnifiedContentViewer } from '../content/UnifiedContentViewer';
import { ProjectFileViewerModal } from '../content/ProjectFileViewerModal';
import { TranscriptFormattedMessage, TranscriptFormattingMappingRule, getReadableTagName, parseTranscriptMessage } from '../sessionTranscriptFormatting';
import { SessionTestStatusView } from '../TestVisualizer/SessionTestStatusView';
import { TranscriptMappedMessageCard, isMappedTranscriptMessageKind, mappedAccentColor, mappedTranscriptIcon } from '../TranscriptMappedMessageCard';
import { TypingIndicator, getMotionPreset, useAnimatedListDiff, useReducedMotionPreference, useSmartScrollAnchor } from '../animations';
import { Badge, ModelBadge, StableBadge } from '../ui/badge';
import { getFeatureStatusStyle } from '../featureStatus';
import { formatModelDisplayName } from '../../lib/modelIdentity';
import { getInlineContentViewerPayload, getTranscriptContentViewerPayload } from '../../lib/sessionContentViewer';
import { contextSummaryLabel, costSummaryLabel, formatContextMeasurementSource, resolveDisplayCost } from '../../lib/sessionSemantics';
import { buildSessionBlockInsights } from '../../lib/sessionBlockInsights';
import { isMemoryGuardEnabled } from '../../lib/featureFlags';
import { formatPercent, formatTokenCount, resolveTokenMetrics } from '../../lib/tokenMetrics';
import { getFeatureLinkedSessionPage, type LinkedFeatureSessionDTO } from '../../services/featureSurface';

const MAIN_SESSION_AGENT = 'Main Session';
const SHORT_COMMIT_LENGTH = 7;
const LIVE_IN_FLIGHT_WINDOW_MS = 10 * 60 * 1000;
const ACTIVE_SESSION_DETAIL_POLL_MS = 5_000;
type SessionInspectorTab = 'transcript' | 'activity' | 'forensics' | 'analytics' | 'agents' | 'impact' | 'files' | 'artifacts' | 'features' | 'test-status';

const isSessionInspectorTab = (value: string | null): value is SessionInspectorTab => (
    value === 'transcript'
    || value === 'activity'
    || value === 'forensics'
    || value === 'analytics'
    || value === 'agents'
    || value === 'impact'
    || value === 'files'
    || value === 'artifacts'
    || value === 'features'
    || value === 'test-status'
);

const getSessionIdFromQuery = (searchParams: URLSearchParams): string => {
    const direct = (searchParams.get('session') || '').trim();
    if (direct) return direct;
    return (searchParams.get('session_id') || '').trim();
};

const formatUsd = (value: number | string | null | undefined, digits = 2): string => {
    const parsed = typeof value === 'number' ? value : Number(value ?? 0);
    if (!Number.isFinite(parsed)) return (0).toFixed(digits);
    return parsed.toFixed(digits);
};

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

const formatTimeAgo = (timestamp?: string): string => {
    const epoch = toEpoch(timestamp);
    if (epoch <= 0) return 'Unknown';

    const diffMs = Date.now() - epoch;
    if (!Number.isFinite(diffMs) || diffMs < 0) return 'Just now';

    const minutes = Math.floor(diffMs / (60 * 1000));
    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;

    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;

    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d ago`;

    return new Date(epoch).toLocaleDateString();
};

const asSessionTranscriptAppendPayload = (raw: unknown): SessionTranscriptAppendPayload | null => {
    if (!raw || typeof raw !== 'object') return null;
    const candidate = raw as Record<string, unknown>;
    const payload = candidate.payload;
    if (!payload || typeof payload !== 'object') return null;
    const sessionId = String(candidate.sessionId || '').trim();
    const entryId = String(candidate.entryId || '').trim();
    const createdAt = String(candidate.createdAt || '').trim();
    const sequenceNo = Number(candidate.sequenceNo);
    if (!sessionId || !entryId || !createdAt || !Number.isFinite(sequenceNo)) {
        return null;
    }
    return {
        sessionId,
        entryId,
        sequenceNo,
        kind: String(candidate.kind || ''),
        createdAt,
        payload: payload as SessionTranscriptAppendPayload['payload'],
    };
};

const formatBlockWindow = (startAt: string, endAt: string): string => {
    const start = toEpoch(startAt);
    const end = toEpoch(endAt);
    if (start <= 0 || end <= 0) return 'Unknown window';
    const startLabel = new Date(start).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    const endLabel = new Date(end).toLocaleString([], { hour: 'numeric', minute: '2-digit' });
    return `${startLabel} - ${endLabel}`;
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

const getLiveAgentLabel = (
    session: AgentSession,
    subagentNameBySessionId: Map<string, string>,
): string => {
    const mappedName = subagentNameBySessionId.get(session.id);
    if (mappedName) return mappedName;
    const titled = (session.title || '').trim();
    if (titled && titled !== session.id) return titled;
    if (session.agentId) return `agent-${session.agentId}`;
    return 'Active Agent';
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

const TASK_ID_TEXT_PATTERN = /\b([A-Za-z]+(?:-[A-Za-z0-9]+)*-\d+(?:\.\d+)?)\b/;
const SUBAGENT_TOOL_NAMES = new Set(['task', 'agent']);
const TASK_MUTATION_TOOL_NAMES = new Set(['taskcreate', 'taskupdate']);

const toTextBlob = (value: unknown): string => {
    if (typeof value === 'string') {
        return value.trim();
    }
    if (value === null || value === undefined) {
        return '';
    }
    try {
        return JSON.stringify(value).trim();
    } catch {
        return String(value).trim();
    }
};

const parseJsonLikeValue = (value: unknown): unknown => {
    if (typeof value !== 'string') return value;
    const trimmed = value.trim();
    if (!trimmed) return '';
    const looksJson = (
        (trimmed.startsWith('{') && trimmed.endsWith('}'))
        || (trimmed.startsWith('[') && trimmed.endsWith(']'))
    );
    if (!looksJson) return value;
    try {
        return JSON.parse(trimmed);
    } catch {
        return value;
    }
};

const extractTaskIdFromText = (...values: unknown[]): string | null => {
    for (const value of values) {
        const text = toTextBlob(value);
        if (!text) continue;
        const match = TASK_ID_TEXT_PATTERN.exec(text);
        if (match && match[1]) return match[1];
    }
    return null;
};

interface TaskToolDetails {
    toolName: string;
    taskId: string | null;
    name: string | null;
    description: string | null;
    prompt: string | null;
    promptPreview: string | null;
    subagentType: string | null;
    mode: string | null;
    model: string | null;
    runInBackground: boolean | null;
    args: Record<string, unknown> | null;
}

interface TaskMutationToolDetails {
    toolName: string;
    taskId: string | null;
    subject: string | null;
    description: string | null;
    status: string | null;
    activeForm: string | null;
    taskType: string | null;
    blockedByAdded: string[];
    blockedByRemoved: string[];
    args: Record<string, unknown> | null;
    outputText: string | null;
    outputData: Record<string, unknown>;
}

interface TaskInvocationDisplayContext {
    subagentLabel: string | null;
    model: {
        raw: string;
        displayName?: string;
        provider?: string;
        family?: string;
        version?: string;
    } | null;
}

interface TestRunDetails {
    framework: string;
    command: string;
    description: string | null;
    timeoutMs: number | null;
    domains: string[];
    domain: string | null;
    targets: string[];
    flags: string[];
    status: string | null;
    durationSeconds: number | null;
    total: number | null;
    passRate: number | null;
    workers: number | null;
    collected: number | null;
    rootdir: string | null;
    pythonVersion: string | null;
    pytestVersion: string | null;
    counts: Record<string, number>;
}

interface ReadToolDetails {
    filePath: string | null;
    offset: number | null;
    limit: number | null;
    otherParams: Record<string, unknown>;
}

interface GrepToolMatch {
    lineNumber: number | null;
    content: string;
}

interface GrepToolFileMatch {
    filePath: string;
    matches: GrepToolMatch[];
}

interface GrepToolDetails {
    pattern: string | null;
    searchPath: string | null;
    outputMode: string | null;
    lineNumbersEnabled: boolean | null;
    otherParams: Record<string, unknown>;
    files: GrepToolFileMatch[];
}

const READ_TOOL_NAMES = new Set(['read', 'readfile']);
const GREP_TOOL_NAMES = new Set(['grep']);
const GREP_OUTPUT_LINE_PATTERN = /^(.*?):(\d+):(.*)$/;

const isSubagentToolCallName = (name?: string | null): boolean =>
    SUBAGENT_TOOL_NAMES.has(String(name || '').trim().toLowerCase());

const isTaskMutationToolCallName = (name?: string | null): boolean =>
    TASK_MUTATION_TOOL_NAMES.has(String(name || '').trim().toLowerCase());

const getTaskToolDetails = (log: SessionLog): TaskToolDetails | null => {
    if (log.type !== 'tool' || !isSubagentToolCallName(log.toolCall?.name)) {
        return null;
    }
    const args = parseToolArgs(log.toolCall?.args);
    const metadata = asRecord(log.metadata);
    const toolName = takeString(log.toolCall?.name) || 'Task';

    const name = takeString(metadata.taskName, args?.name);
    const description = takeString(metadata.taskDescription, args?.description);
    const promptText = takeString(metadata.taskPromptPreview, args?.prompt ? toTextBlob(args.prompt) : null);
    const taskId = takeString(metadata.taskId, extractTaskIdFromText(name, description, promptText));
    const subagentType = takeString(
        metadata.taskSubagentType,
        args?.subagent_type,
        args?.subagentType,
        args?.agent_name,
        args?.agentName,
    );
    const mode = takeString(metadata.taskMode, args?.mode);
    const model = takeString(metadata.taskModel, args?.model);
    const promptPreview = promptText && promptText.length > 320 ? `${promptText.slice(0, 320)}...` : promptText;
    const runInBackground = (() => {
        if (typeof metadata.taskRunInBackground === 'boolean') return metadata.taskRunInBackground;
        const raw = args?.run_in_background ?? args?.runInBackground;
        if (typeof raw === 'boolean') return raw;
        if (typeof raw === 'string') {
            const normalized = raw.trim().toLowerCase();
            if (normalized === 'true') return true;
            if (normalized === 'false') return false;
        }
        return null;
    })();

    return {
        toolName,
        taskId,
        name,
        description,
        prompt: promptText,
        promptPreview,
        subagentType,
        mode,
        model,
        runInBackground,
        args,
    };
};

const getTaskMutationToolDetails = (log: SessionLog): TaskMutationToolDetails | null => {
    if (log.type !== 'tool' || !isTaskMutationToolCallName(log.toolCall?.name)) {
        return null;
    }

    const args = parseToolArgs(log.toolCall?.args);
    const metadata = asRecord(log.metadata);
    const outputData = Object.entries(metadata).reduce<Record<string, unknown>>((acc, [key, value]) => {
        if (!key.startsWith('toolUseResult_')) return acc;
        acc[key.slice('toolUseResult_'.length)] = parseJsonLikeValue(value);
        return acc;
    }, {});
    const taskResult = asRecord(outputData.task);

    return {
        toolName: takeString(log.toolCall?.name) || 'TaskUpdate',
        taskId: takeString(
            args?.taskId,
            args?.task_id,
            taskResult.id,
            extractTaskIdFromText(log.toolCall?.output),
        ),
        subject: takeString(args?.subject, args?.title, taskResult.subject, taskResult.title),
        description: takeString(args?.description, args?.details, taskResult.description),
        status: takeString(args?.status, taskResult.status),
        activeForm: takeString(args?.activeForm, args?.active_form),
        taskType: takeString(args?.taskType, args?.task_type, taskResult.type),
        blockedByAdded: asStringArray(args?.addBlockedBy ?? args?.add_blocked_by),
        blockedByRemoved: asStringArray(args?.removeBlockedBy ?? args?.remove_blocked_by),
        args,
        outputText: takeString(log.toolCall?.output),
        outputData,
    };
};

const resolveTaskInvocationDisplayContext = (
    log: SessionLog,
    taskToolDetails: TaskToolDetails | null,
    threadSessionDetails: Record<string, AgentSession>,
    subagentNameBySessionId: Map<string, string>,
): TaskInvocationDisplayContext => {
    const linkedSession = log.linkedSessionId ? threadSessionDetails[log.linkedSessionId] || null : null;
    const subagentLabel = taskToolDetails?.subagentType
        || (log.linkedSessionId ? subagentNameBySessionId.get(log.linkedSessionId) || null : null)
        || null;
    const rawModel = taskToolDetails?.model || linkedSession?.model || '';

    return {
        subagentLabel,
        model: rawModel
            ? {
                raw: rawModel,
                displayName: linkedSession?.modelDisplayName,
                provider: linkedSession?.modelProvider,
                family: linkedSession?.modelFamily,
                version: linkedSession?.modelVersion,
            }
            : null,
    };
};

const inferTestFrameworkFromCommand = (command: string): string | null => {
    const lowered = String(command || '').toLowerCase();
    if (!lowered.trim()) return null;
    if (/\b(?:python(?:\d+(?:\.\d+)*)?\s+-m\s+)?pytest\b/.test(lowered)) return 'pytest';
    if (/\bvitest\b/.test(lowered)) return 'vitest';
    if (/\bjest\b/.test(lowered)) return 'jest';
    if (/\bgo\s+test\b/.test(lowered)) return 'go-test';
    if (/\bcargo\s+test\b/.test(lowered)) return 'cargo-test';
    if (/\bpnpm\s+test\b/.test(lowered)) return 'pnpm-test';
    if (/\bnpm\s+test\b/.test(lowered)) return 'npm-test';
    if (/\byarn\s+test\b/.test(lowered)) return 'yarn-test';
    return null;
};

const getTestRunDetails = (log: SessionLog): TestRunDetails | null => {
    if (log.type !== 'tool') {
        return null;
    }
    const metadata = asRecord(log.metadata);
    const toolCategory = String(metadata.toolCategory || '').trim().toLowerCase();
    const args = parseToolArgs(log.toolCall?.args);
    const testRun = asRecord(metadata.testRun);
    const result = asRecord(testRun.result);
    const countsRecord = asRecord(result.counts || metadata.testCounts);

    const command = takeString(
        metadata.bashCommand,
        testRun.command,
        testRun.commandSegment,
        metadata.command,
        args?.command,
        args?.cmd,
        args?.script,
    ) || '';
    const inferredFramework = inferTestFrameworkFromCommand(command);
    const framework = takeString(
        testRun.framework,
        metadata.testFramework,
        inferredFramework,
        toolCategory === 'test' ? 'test' : '',
    );
    if (!framework) {
        return null;
    }

    const domains = asStringArray(testRun.domains && Array.isArray(testRun.domains) ? testRun.domains : metadata.testDomains);
    const targets = asStringArray(testRun.targets && Array.isArray(testRun.targets) ? testRun.targets : metadata.testTargets);
    const flags = asStringArray(testRun.flags && Array.isArray(testRun.flags) ? testRun.flags : metadata.testFlags);
    const domain = takeString(testRun.primaryDomain, metadata.testDomain, domains[0]);
    const description = takeString(testRun.description, metadata.testDescription, args?.description);
    const timeoutMsRaw = asNumber(testRun.timeoutMs || metadata.testTimeoutMs || args?.timeout, 0);
    const durationSource = result.durationSeconds ?? metadata.testDurationSeconds;
    const durationSecondsRaw = asNumber(durationSource, -1);
    const passRateSource = result.passRate ?? metadata.testPassRate;
    const passRateRaw = asNumber(passRateSource, -1);
    let total = asNumber(result.total || metadata.testTotal, 0);
    const counts: Record<string, number> = {};
    ['passed', 'failed', 'error', 'skipped', 'xfailed', 'xpassed', 'deselected', 'rerun'].forEach(key => {
        const count = asNumber(countsRecord[key], 0);
        if (count > 0) {
            counts[key] = count;
        }
    });
    if (total <= 0) {
        total = Object.values(counts).reduce((sum, count) => sum + count, 0);
    }

    const status = takeString(
        result.status,
        metadata.testStatus,
        log.toolCall?.status === 'error' ? 'failed' : '',
    );

    return {
        framework,
        command,
        description,
        timeoutMs: timeoutMsRaw > 0 ? timeoutMsRaw : null,
        domains,
        domain,
        targets,
        flags,
        status,
        durationSeconds: durationSecondsRaw >= 0 ? durationSecondsRaw : null,
        total: total > 0 ? total : null,
        passRate: passRateRaw >= 0 ? passRateRaw : null,
        workers: asNumber(result.workers || metadata.testWorkers, 0) || null,
        collected: asNumber(result.collected || metadata.testCollected, 0) || null,
        rootdir: takeString(result.rootdir, metadata.testRootdir),
        pythonVersion: takeString(result.pythonVersion, metadata.testPythonVersion),
        pytestVersion: takeString(result.pytestVersion, metadata.testPytestVersion),
        counts,
    };
};

const toOptionalNumber = (value: unknown): number | null => {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim()) {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) return parsed;
    }
    return null;
};

const toOptionalBoolean = (value: unknown): boolean | null => {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value !== 0;
    if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        if (normalized === 'true' || normalized === '1' || normalized === 'yes') return true;
        if (normalized === 'false' || normalized === '0' || normalized === 'no') return false;
    }
    return null;
};

const collectOtherToolArgs = (
    args: Record<string, unknown> | null,
    excludedKeys: string[],
): Record<string, unknown> => {
    if (!args) return {};
    const excluded = new Set(excludedKeys.map(key => key.toLowerCase()));
    const other: Record<string, unknown> = {};
    Object.entries(args).forEach(([key, value]) => {
        if (!excluded.has(key.toLowerCase())) {
            other[key] = value;
        }
    });
    return other;
};

const parseGrepOutputByFile = (output: string | undefined): GrepToolFileMatch[] => {
    const grouped = new Map<string, GrepToolFileMatch>();
    const text = String(output || '').replace(/\r/g, '');
    if (!text.trim()) return [];

    text.split('\n').forEach(line => {
        const normalized = line.replace(/\s+$/, '');
        if (!normalized.trim()) return;
        const match = GREP_OUTPUT_LINE_PATTERN.exec(normalized);
        if (!match) return;
        const filePath = String(match[1] || '').trim();
        if (!filePath) return;
        const lineNumber = Number.parseInt(String(match[2] || ''), 10);
        const content = String(match[3] || '');
        const existing = grouped.get(filePath) || { filePath, matches: [] };
        existing.matches.push({
            lineNumber: Number.isFinite(lineNumber) ? lineNumber : null,
            content,
        });
        grouped.set(filePath, existing);
    });

    return Array.from(grouped.values());
};

const getReadToolDetails = (log: SessionLog): ReadToolDetails | null => {
    if (log.type !== 'tool') return null;
    const toolName = String(log.toolCall?.name || '').trim().toLowerCase();
    if (!READ_TOOL_NAMES.has(toolName)) return null;

    const args = parseToolArgs(log.toolCall?.args);
    const filePath = takeString(
        args?.file_path,
        args?.filePath,
        args?.path,
        args?.filename,
        args?.file,
    );
    const offset = toOptionalNumber(args?.offset);
    const limit = toOptionalNumber(args?.limit);
    const otherParams = collectOtherToolArgs(args, ['file_path', 'filePath', 'path', 'filename', 'file', 'offset', 'limit']);

    return {
        filePath,
        offset,
        limit,
        otherParams,
    };
};

const getGrepToolDetails = (log: SessionLog): GrepToolDetails | null => {
    if (log.type !== 'tool') return null;
    const toolName = String(log.toolCall?.name || '').trim().toLowerCase();
    if (!GREP_TOOL_NAMES.has(toolName)) return null;

    const args = parseToolArgs(log.toolCall?.args);
    const pattern = takeString(args?.pattern, args?.query, args?.regex);
    const searchPath = takeString(args?.path, args?.cwd, args?.directory, args?.root);
    const outputMode = takeString(args?.output_mode, args?.outputMode, args?.mode);
    const lineNumbersEnabled = toOptionalBoolean(args?.['-n'] ?? args?.n);
    const otherParams = collectOtherToolArgs(args, ['pattern', 'query', 'regex', 'path', 'cwd', 'directory', 'root', 'output_mode', 'outputMode', 'mode', '-n', 'n']);
    const files = parseGrepOutputByFile(log.toolCall?.output);

    return {
        pattern,
        searchPath,
        outputMode,
        lineNumbersEnabled,
        otherParams,
        files,
    };
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

const toSkillMentionToken = (raw: string): string | null => {
    const trimmed = String(raw || '').trim();
    if (!trimmed) return null;
    const token = trimmed
        .replace(/^[$/]+/, '')
        .split(/[\\/]/)
        .filter(Boolean)
        .pop()
        ?.replace(/[^A-Za-z0-9-]+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-+|-+$/g, '') || '';
    if (!token) return null;
    const normalized = /^[A-Za-z]/.test(token) ? token : `skill-${token}`;
    return `$${normalized}`;
};

const getTranscriptSourceText = (log: SessionLog): string => {
    if (log.type === 'command') {
        const args = String(log.metadata?.args || '').trim();
        return args ? `${log.content} ${args}`.trim() : String(log.content || '');
    }

    if (log.type === 'tool') {
        const metadata = asRecord(log.metadata);
        const toolArgs = parseToolArgs(log.toolCall?.args);
        const bashCommand = takeString(
            metadata.bashCommand,
            metadata.command,
            toolArgs?.command,
            toolArgs?.cmd,
            toolArgs?.script,
        );
        if (bashCommand) return bashCommand;

        const toolCategory = String(metadata.toolCategory || '').trim().toLowerCase();
        const toolName = String(log.toolCall?.name || '').trim().toLowerCase();
        const skillName = takeString(
            metadata.toolLabel,
            metadata.skill,
            toolArgs?.skill,
            toolArgs?.name,
        );
        if (toolCategory === 'skill' || toolName === 'skill') {
            const skillToken = skillName ? toSkillMentionToken(skillName) : null;
            if (skillToken) return skillToken;
        }

        return String(log.content || '');
    }

    if (log.type === 'skill') {
        const skillName = takeString(log.skillDetails?.name, asRecord(log.metadata).skill, log.content);
        const skillToken = skillName ? toSkillMentionToken(skillName) : null;
        if (skillToken) return skillToken;
    }

    if (log.type === 'system') {
        const metadata = asRecord(log.metadata);
        if (String(metadata.eventType || '').trim().toLowerCase() === 'hook_progress') {
            return takeString(
                metadata.hookPath,
                metadata.hookCommand,
                metadata.hookName,
                log.content,
            );
        }
    }

    return String(log.content || '');
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

const isForkStartSystemLog = (log: SessionLog): boolean => {
    if (log.type !== 'system') return false;
    const metadata = asRecord(log.metadata);
    const syntheticType = String(metadata.syntheticEventType || metadata.eventType || '').trim().toLowerCase();
    return syntheticType === 'fork_start';
};

const collectSessionSubagentTypes = (session: AgentSession): string[] => {
    const seen = new Set<string>();
    const values: string[] = [];
    const add = (candidate: unknown) => {
        const normalized = String(candidate || '').trim();
        if (!normalized) return;
        const lowered = normalized.toLowerCase();
        if (lowered === 'subagent' || lowered === 'agent') return;
        if (/^agent[-_]/i.test(normalized)) return;
        if (seen.has(lowered)) return;
        seen.add(lowered);
        values.push(normalized);
    };

    (session.logs || []).forEach(log => {
        if (log.type === 'tool') {
            const details = getTaskToolDetails(log);
            add(details?.subagentType);
        }
        if (log.type === 'subagent_start') {
            add(log.metadata?.subagentType);
            add(log.metadata?.subagentName);
            add(log.metadata?.taskSubagentType);
        }
    });

    (session.linkedArtifacts || []).forEach(artifact => {
        if ((artifact.type || '').trim().toLowerCase() !== 'agent') return;
        add(artifact.title);
    });

    if ((session.sessionType || '').trim().toLowerCase() === 'subagent') {
        const title = (session.title || '').trim();
        if (title && title !== session.id) {
            add(title);
        }
    }

    return values.sort((a, b) => a.localeCompare(b));
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

type ToolGroupCategory = 'hooks' | 'git' | 'tests' | 'other';

const HOOK_TOOL_CALL_PATTERNS = [
    /\bhook(s)?\b/,
    /\bpre-commit\b/,
    /\bpost-commit\b/,
    /\bpre-push\b/,
    /\bpost-merge\b/,
    /\bhusky\b/,
    /\blint-staged\b/,
];

const GIT_TOOL_CALL_PATTERNS = [
    /\bgit\b/,
    /\bcommit\b/,
    /\bcheckout\b/,
    /\bbranch\b/,
    /\brebase\b/,
    /\bmerge\b/,
    /\bcherry-pick\b/,
    /\bstash\b/,
    /\bdiff\b/,
    /\breset\b/,
    /\brestore\b/,
    /\bpush\b/,
    /\bpull\b/,
];

const TEST_TOOL_CALL_PATTERNS = [
    /\btest(s|ing)?\b/,
    /\bpytest\b/,
    /\bjest\b/,
    /\bvitest\b/,
    /\bmocha\b/,
    /\bcypress\b/,
    /\bplaywright\b/,
    /\bcoverage\b/,
    /\bspec\b/,
];

const TOOL_GROUP_SECTION_DEFS: Array<{ id: ToolGroupCategory; label: string; emptyLabel: string }> = [
    { id: 'hooks', label: 'Hooks', emptyLabel: 'No hook-related tool calls.' },
    { id: 'git', label: 'Git Calls', emptyLabel: 'No git-related tool calls.' },
    { id: 'tests', label: 'Tests', emptyLabel: 'No test-related tool calls.' },
    { id: 'other', label: 'Other Tool Calls', emptyLabel: 'No other tool calls.' },
];

const anyPatternMatches = (value: string, patterns: RegExp[]): boolean =>
    patterns.some(pattern => pattern.test(value));

const classifyToolGroup = (group: ArtifactGroup): ToolGroupCategory => {
    const toolSignals = [
        group.type,
        group.title,
        group.description,
        group.source,
        ...group.sourceToolNames,
        ...group.relatedToolLogs.map(log => log.toolCall?.name || ''),
        ...group.relatedToolLogs.map(log => log.content || ''),
    ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();

    if (anyPatternMatches(toolSignals, HOOK_TOOL_CALL_PATTERNS)) return 'hooks';
    if (anyPatternMatches(toolSignals, GIT_TOOL_CALL_PATTERNS)) return 'git';
    if (anyPatternMatches(toolSignals, TEST_TOOL_CALL_PATTERNS)) return 'tests';
    return 'other';
};

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
    if (normalized === 'manual_set') return 'manually set';
    if (normalized === 'task_frontmatter') return 'task linkage';
    if (normalized === 'session_evidence') return 'session evidence';
    if (normalized === 'command_args_path') return 'command path';
    if (normalized === 'file_write') return 'file write';
    if (normalized === 'shell_reference') return 'shell reference';
    if (normalized === 'search_reference') return 'search reference';
    if (normalized === 'file_read') return 'file read';
    return normalized.replace(/_/g, ' ');
};

const TASK_STATUS_PRIORITY: Record<string, number> = {
    done: 5,
    deferred: 4,
    review: 3,
    'in-progress': 2,
    backlog: 1,
    todo: 1,
};

const taskUpdatedAtEpoch = (task: ProjectTask): number => {
    const parsed = Date.parse(task.updatedAt || '');
    return Number.isNaN(parsed) ? 0 : parsed;
};

const taskStatusPriority = (task: ProjectTask): number =>
    TASK_STATUS_PRIORITY[String(task.status || '').toLowerCase()] || 0;

const taskSignalScore = (task: ProjectTask): number => {
    let score = 0;
    if ((task.sessionId || '').trim()) score += 2;
    if ((task.commitHash || '').trim()) score += 2;
    const sourcePath = normalizePath(task.sourceFile || '').toLowerCase();
    if (sourcePath.includes('/progress/')) score += 1;
    if (sourcePath.includes('/project_plans/')) score += 0.5;
    return score;
};

const pickFresherTask = (existing: ProjectTask, candidate: ProjectTask): ProjectTask => {
    const existingUpdated = taskUpdatedAtEpoch(existing);
    const candidateUpdated = taskUpdatedAtEpoch(candidate);
    if (candidateUpdated !== existingUpdated) return candidateUpdated > existingUpdated ? candidate : existing;

    const existingStatus = taskStatusPriority(existing);
    const candidateStatus = taskStatusPriority(candidate);
    if (candidateStatus !== existingStatus) return candidateStatus > existingStatus ? candidate : existing;

    const existingSignals = taskSignalScore(existing);
    const candidateSignals = taskSignalScore(candidate);
    if (candidateSignals !== existingSignals) return candidateSignals > existingSignals ? candidate : existing;

    return existing;
};

const getTaskIdentity = (task: ProjectTask): string => {
    const taskId = String(task.id || '').trim().toLowerCase();
    if (taskId) return taskId;
    return String(task.title || '').trim().toLowerCase();
};

const dedupePhaseTasks = (tasks: ProjectTask[]): ProjectTask[] => {
    const byIdentity = new Map<string, ProjectTask>();
    tasks.forEach(task => {
        const identity = getTaskIdentity(task);
        if (!identity) return;

        const existing = byIdentity.get(identity);
        if (!existing) {
            byIdentity.set(identity, task);
            return;
        }

        const preferred = pickFresherTask(existing, task);
        const other = preferred === existing ? task : existing;
        byIdentity.set(identity, {
            ...other,
            ...preferred,
            title: preferred.title || other.title,
            description: preferred.description || other.description,
            sourceFile: preferred.sourceFile || other.sourceFile,
            sessionId: preferred.sessionId || other.sessionId,
            commitHash: preferred.commitHash || other.commitHash,
            relatedFiles: (preferred.relatedFiles && preferred.relatedFiles.length > 0) ? preferred.relatedFiles : other.relatedFiles,
            updatedAt: preferred.updatedAt || other.updatedAt,
            status: preferred.status || other.status,
        });
    });
    return Array.from(byIdentity.values());
};

interface SessionThreadNode {
    session: AgentSession;
    children: SessionThreadNode[];
}

const threadNodeHasLiveSession = (node: SessionThreadNode, nowMs: number): boolean => {
    if (isSessionLiveInFlight(node.session, nowMs)) return true;
    return node.children.some(child => threadNodeHasLiveSession(child, nowMs));
};

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

const isSubthread = (session: AgentSession): boolean => {
    if (isForkThread(session)) return true;
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

const threadToggleLabelForChildren = (children: SessionThreadNode[]): string => {
    const hasFork = children.some(child => isForkThread(child.session));
    const hasSubagent = children.some(child => !isForkThread(child.session));
    if (hasFork && hasSubagent) return 'Forks & Sub-Threads';
    if (hasFork) return 'Forks';
    return 'Sub-Threads';
};

const buildSessionThreadForest = (sessions: AgentSession[]): SessionThreadNode[] => {
    const nodes = new Map<string, SessionThreadNode>();
    sessions.forEach(session => {
        nodes.set(session.id, { session, children: [] });
    });

    const attached = new Set<string>();
    sessions.forEach(session => {
        if (!isSubthread(session)) return;
        const candidateParents = isForkThread(session)
            ? [
                session.forkParentSessionId || '',
                session.parentSessionId || '',
                session.rootSessionId && session.rootSessionId !== session.id ? session.rootSessionId : '',
            ]
            : [
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
    threadSessionDetails: Record<string, AgentSession>;
    subagentNameBySessionId: Map<string, string>;
    onOpenThread?: (threadId: string) => void;
}> = ({ log, formattedMessage, isSelected, onClick, fileCount = 0, artifactCount = 0, onShowFiles, onShowArtifacts, threadSessionDetails, subagentNameBySessionId, onOpenThread }) => {
    const isAgent = log.speaker === 'agent';
    const isUser = log.speaker === 'user';
    const isSystem = log.speaker === 'system';
    const isForkStartEvent = isForkStartSystemLog(log);
    const taskToolDetails = getTaskToolDetails(log);
    const taskMutationDetails = getTaskMutationToolDetails(log);
    const taskDisplayContext = resolveTaskInvocationDisplayContext(log, taskToolDetails, threadSessionDetails, subagentNameBySessionId);

    const renderMessagePreview = () => {
        const parsed = formattedMessage || parseTranscriptMessage(log.content);

        if (isMappedTranscriptMessageKind(parsed.kind) && parsed.mapped) {
            const accent = mappedAccentColor(parsed.mapped.color, parsed.kind);
            const mappedLabel = parsed.mapped.transcriptLabel || parsed.mapped.label || 'Mapped Event';
            return (
                <div className="space-y-1.5">
                    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-semibold" style={{ color: accent }}>
                        {mappedTranscriptIcon(parsed.mapped.icon, parsed.kind, 11)}
                        <span>{mappedLabel}</span>
                    </div>
                    <p className="font-mono text-xs line-clamp-2 break-all text-panel-foreground">{parsed.summary}</p>
                    {parsed.command?.args && (
                        <p className="text-xs text-muted-foreground whitespace-pre-wrap line-clamp-2 break-words">{parsed.command.args}</p>
                    )}
                </div>
            );
        }

        if (parsed.kind === 'claude-command') {
            const commandLabel = parsed.command?.name || parsed.command?.message || 'Command';
            return (
                <div className="space-y-1">
                    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-emerald-300/90 font-semibold">
                        <Terminal size={11} /> Command Invocation
                    </div>
                    <p className="font-mono text-xs line-clamp-1 break-all">{commandLabel}</p>
                    {parsed.command?.args && (
                        <p className="text-xs text-muted-foreground whitespace-pre-wrap line-clamp-2 break-words">{parsed.command.args}</p>
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
                            <span key={`${log.id}-${tag.tag}-${tag.start}`} className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-panel-border bg-panel/80 text-muted-foreground">
                                {getReadableTagName(tag.tag)}
                            </span>
                        ))}
                        {parsed.tags.length > 3 && (
                            <span className="text-[10px] text-muted-foreground">+{parsed.tags.length - 3} more</span>
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

    if (log.type === 'message' || isForkStartEvent) {
        return (
            <div
                onClick={onClick}
                className={`group cursor-pointer flex gap-4 mb-4 px-2 py-1 rounded-xl transition-all ${isUser ? 'flex-row-reverse' : 'flex-row'} ${isSelected ? 'bg-indigo-500/10 ring-1 ring-focus/30' : 'hover:bg-surface-muted/40'
                    }`}
            >
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 border transition-colors ${isSelected
                    ? 'border-indigo-500 bg-indigo-500/20 text-indigo-400'
                    : isUser
                        ? 'bg-surface-muted border-panel-border text-muted-foreground'
                        : isForkStartEvent
                            ? 'bg-cyan-500/15 border-cyan-500/35 text-cyan-300'
                            : isSystem
                            ? 'bg-panel border-panel-border text-foreground'
                        : 'bg-indigo-500/10 border-indigo-500/20 text-indigo-400'
                    }`}>
                    {isUser
                        ? <span className="text-xs font-bold">U</span>
                        : isForkStartEvent
                            ? <GitBranch size={14} />
                            : isSystem
                                ? <span className="text-xs font-bold">S</span>
                                : <Bot size={16} />}
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
                            ? 'bg-surface-muted border-panel-border text-foreground'
                            : isForkStartEvent
                                ? 'bg-cyan-500/10 border-cyan-500/35 text-cyan-100'
                            : isSystem
                                ? 'bg-panel/70 border-panel-border text-foreground'
                            : 'bg-panel border-panel-border text-foreground'
                        }`}>
                        {renderMessagePreview()}
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                        {isForkStartEvent && log.linkedSessionId && (
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onOpenThread?.(log.linkedSessionId!);
                                }}
                                className="text-[10px] px-2 py-0.5 rounded border border-cyan-500/40 text-cyan-200 bg-cyan-500/10 hover:bg-cyan-500/20"
                            >
                                Open Fork
                            </button>
                        )}
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
        thought: <MessageSquare size={12} className="text-foreground" />,
        system: isForkStartEvent ? <GitBranch size={12} className="text-cyan-300" /> : <ShieldAlert size={12} className="text-muted-foreground" />,
        command: <Terminal size={12} className="text-emerald-400" />,
        subagent_start: <Zap size={12} className="text-purple-300" />,
    };

    const mappedNonMessageLabel = (
        formattedMessage
        && isMappedTranscriptMessageKind(formattedMessage.kind)
        && formattedMessage.mapped
    )
        ? `${formattedMessage.mapped.transcriptLabel}: ${formattedMessage.summary}`
        : null;

    const label = log.type === 'tool' ? (mappedNonMessageLabel || `Used Tool: ${log.toolCall?.name}`) :
        log.type === 'subagent_start' ? `Sub-thread Started` :
            log.type === 'thought' ? 'Agent Thought' :
                log.type === 'system' ? (isForkStartEvent ? 'Fork Started' : 'System Event') :
                    log.type === 'command'
                        ? (formattedMessage && isMappedTranscriptMessageKind(formattedMessage.kind) && formattedMessage.mapped
                            ? `${formattedMessage.mapped.transcriptLabel}: ${formattedMessage.summary}`
                            : `Command: ${log.content}`)
                        :
        log.type === 'subagent' ? `Spawned Agent: ${log.agentName || 'Subagent'}` :
            (mappedNonMessageLabel || `Loaded Skill: ${log.skillDetails?.name}`);
    const mappedNonMessageAccent = (
        formattedMessage
        && isMappedTranscriptMessageKind(formattedMessage.kind)
        && formattedMessage.mapped
    )
        ? mappedAccentColor(formattedMessage.mapped.color, formattedMessage.kind)
        : null;
    const testToolDetails = getTestRunDetails(log);

    return (
        <div
            onClick={onClick}
            className={`cursor-pointer mb-2 ml-12 p-2 rounded-lg border transition-all flex items-center justify-between group ${isSelected
                ? 'bg-indigo-500/20 border-indigo-500/50 ring-1 ring-focus/20'
                : 'bg-surface-overlay border-panel-border hover:border-panel-border'
                }`}
        >
            <div className="flex items-center gap-2 overflow-hidden">
                {icons[log.type as keyof typeof icons] || <Box size={12} />}
                {taskToolDetails ? (
                    <div className="min-w-0 space-y-0.5">
                        <div className={`text-[10px] uppercase tracking-wider font-semibold ${isSelected ? 'text-indigo-300' : 'text-amber-400'}`}>
                            {taskToolDetails.toolName} Invocation
                        </div>
                        <div className={`text-[11px] truncate ${isSelected ? 'text-indigo-100' : 'text-foreground'}`}>
                            {taskToolDetails.description || taskToolDetails.name || taskToolDetails.taskId || 'Subagent tool call'}
                        </div>
                        <div className="flex flex-wrap items-center gap-1 pt-0.5">
                            {taskToolDetails.taskId && (
                                <StableBadge value={taskToolDetails.taskId} namespace="task" mono />
                            )}
                            {taskDisplayContext.subagentLabel && (
                                <StableBadge value={taskDisplayContext.subagentLabel} namespace="subagent" />
                            )}
                            {taskDisplayContext.model && (
                                <ModelBadge
                                    raw={taskDisplayContext.model.raw}
                                    displayName={taskDisplayContext.model.displayName}
                                    provider={taskDisplayContext.model.provider}
                                    family={taskDisplayContext.model.family}
                                    version={taskDisplayContext.model.version}
                                />
                            )}
                            {typeof taskToolDetails.runInBackground === 'boolean' && (
                                <Badge className="border-panel-border bg-panel text-muted-foreground">
                                    {taskToolDetails.runInBackground ? 'background' : 'foreground'}
                                </Badge>
                            )}
                        </div>
                    </div>
                ) : taskMutationDetails ? (
                    <div className="min-w-0 space-y-0.5">
                        <div className={`text-[10px] uppercase tracking-wider font-semibold ${isSelected ? 'text-indigo-300' : 'text-sky-400'}`}>
                            {taskMutationDetails.toolName}
                        </div>
                        <div className={`text-[11px] truncate ${isSelected ? 'text-indigo-100' : 'text-foreground'}`}>
                            {taskMutationDetails.subject || taskMutationDetails.description || taskMutationDetails.outputText || 'Task mutation'}
                        </div>
                        <div className="flex flex-wrap items-center gap-1 pt-0.5">
                            {taskMutationDetails.taskId && (
                                <StableBadge value={taskMutationDetails.taskId} namespace="task" mono />
                            )}
                            {taskMutationDetails.status && (
                                <StableBadge value={taskMutationDetails.status} namespace="task-status" />
                            )}
                            {taskMutationDetails.blockedByAdded.length > 0 && (
                                <Badge className="border-amber-500/35 bg-amber-500/10 text-amber-200">
                                    +blockedBy {taskMutationDetails.blockedByAdded.length}
                                </Badge>
                            )}
                            {taskMutationDetails.blockedByRemoved.length > 0 && (
                                <Badge className="border-rose-500/35 bg-rose-500/10 text-rose-200">
                                    -blockedBy {taskMutationDetails.blockedByRemoved.length}
                                </Badge>
                            )}
                        </div>
                    </div>
                ) : testToolDetails ? (
                    <div className="min-w-0 space-y-0.5">
                        <div className={`text-[10px] uppercase tracking-wider font-semibold ${isSelected ? 'text-indigo-300' : 'text-emerald-400'}`}>
                            {testToolDetails.framework} Test Run
                        </div>
                        <div className={`text-[11px] truncate ${isSelected ? 'text-indigo-100' : 'text-foreground'}`}>
                            {testToolDetails.description || testToolDetails.domain || testToolDetails.command || 'Test execution'}
                        </div>
                        <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                            {testToolDetails.status && <span>{testToolDetails.status}</span>}
                            {typeof testToolDetails.total === 'number' && <span>{testToolDetails.total} tests</span>}
                            {typeof testToolDetails.durationSeconds === 'number' && <span>{testToolDetails.durationSeconds.toFixed(2)}s</span>}
                            {testToolDetails.domain && <span>{testToolDetails.domain}</span>}
                        </div>
                    </div>
                ) : (mappedNonMessageLabel && formattedMessage?.mapped && mappedNonMessageAccent) ? (
                    <div className="min-w-0 space-y-0.5">
                        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-semibold" style={{ color: mappedNonMessageAccent }}>
                            {mappedTranscriptIcon(formattedMessage.mapped.icon, formattedMessage.kind, 11)}
                            <span className="truncate">{formattedMessage.mapped.transcriptLabel || formattedMessage.mapped.label}</span>
                        </div>
                        <div className={`text-[11px] font-mono truncate ${isSelected ? 'text-indigo-100' : 'text-foreground'}`}>
                            {formattedMessage.summary}
                        </div>
                        {formattedMessage.mapped.args && (
                            <div className="text-[10px] text-muted-foreground font-mono truncate">
                                {formattedMessage.mapped.args}
                            </div>
                        )}
                    </div>
                ) : (
                    <span className={`text-[11px] font-mono truncate transition-colors ${isSelected ? 'text-indigo-300' : 'text-muted-foreground'}`}>
                        {label}
                    </span>
                )}
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
                <ChevronRight size={12} className={`text-muted-foreground transition-transform ${isSelected ? 'rotate-90 text-indigo-400' : 'group-hover:translate-x-0.5'}`} />
            </div>
        </div>
    );
};

const DetailPane: React.FC<{
    log: SessionLog;
    formattedMessage?: TranscriptFormattedMessage;
    commandArtifacts?: SessionArtifact[];
    threadSessionDetails: Record<string, AgentSession>;
    subagentNameBySessionId: Map<string, string>;
    onOpenArtifacts?: () => void;
}> = ({ log, formattedMessage, commandArtifacts = [], threadSessionDetails, subagentNameBySessionId, onOpenArtifacts }) => {
    const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());

    const toggleSection = (id: string) => {
        const next = new Set(expandedSections);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        setExpandedSections(next);
    };

    const parsedMessage = formattedMessage || parseTranscriptMessage(getTranscriptSourceText(log));
    const taskToolDetails = getTaskToolDetails(log);
    const taskMutationDetails = getTaskMutationToolDetails(log);
    const testToolDetails = getTestRunDetails(log);
    const readToolDetails = getReadToolDetails(log);
    const grepToolDetails = getGrepToolDetails(log);
    const inlineContentViewerPayload = getInlineContentViewerPayload(
        readToolDetails?.filePath,
        log.toolCall?.output,
    );
    const taskPromptViewerPayload = getTranscriptContentViewerPayload(
        `${log.id}-task-prompt`,
        taskToolDetails?.prompt || null,
    );
    const transcriptViewerPayload = getTranscriptContentViewerPayload(log.id, log.content);
    const taskDisplayContext = resolveTaskInvocationDisplayContext(log, taskToolDetails, threadSessionDetails, subagentNameBySessionId);
    const detailTitle = (() => {
        if (isMappedTranscriptMessageKind(parsedMessage.kind)) return 'Mapped Transcript Event';
        if (log.type === 'subagent') return 'Subagent Thread';
        if (log.type === 'tool' && taskToolDetails) return `${taskToolDetails.toolName} Invocation`;
        if (log.type === 'tool' && taskMutationDetails) return `${taskMutationDetails.toolName} Operation`;
        if (log.type === 'tool' && testToolDetails) return `${testToolDetails.framework} Test Run`;
        if (log.type === 'tool') return 'Tool Execution';
        if (log.type === 'subagent_start') return 'Subagent Start';
        if (log.type === 'message' && parsedMessage.kind === 'claude-command') return 'Command Message';
        return 'Log Details';
    })();

    const renderStructuredMessage = () => {
        if (isMappedTranscriptMessageKind(parsedMessage.kind) && parsedMessage.mapped) {
            return (
                <TranscriptMappedMessageCard
                    message={parsedMessage}
                    commandArtifactsCount={commandArtifacts.length}
                    onOpenArtifacts={onOpenArtifacts}
                />
            );
        }

        if (parsedMessage.kind === 'claude-command') {
            const commandLabel = parsedMessage.command?.name || parsedMessage.command?.message || 'Unknown Command';
            return (
                <div className="bg-panel/40 border border-emerald-500/20 rounded-xl p-5 space-y-4">
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
                        <div className="bg-surface-overlay/80 border border-panel-border rounded-lg p-3">
                            <div className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mb-2">Command Args</div>
                            <pre className="text-xs text-foreground whitespace-pre-wrap break-words font-mono max-h-56 overflow-y-auto">
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
                    <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
                        {parsedMessage.text || 'Caveat metadata'}
                    </p>
                </div>
            );
        }

        if (parsedMessage.kind === 'claude-local-command-stdout') {
            return (
                <div className="bg-sky-500/5 border border-sky-500/20 rounded-xl p-5">
                    <div className="text-[10px] text-sky-300 uppercase tracking-widest font-bold mb-3">Local Command Output</div>
                    <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words max-h-80 overflow-y-auto">
                        {parsedMessage.text && parsedMessage.text.trim() ? parsedMessage.text : '(empty stdout)'}
                    </pre>
                </div>
            );
        }

        if (parsedMessage.kind === 'tagged') {
            return (
                <div className="bg-panel/40 border border-panel-border rounded-xl p-5 space-y-4">
                    <div className="flex flex-wrap gap-2">
                        {parsedMessage.tags.map(tag => (
                            <span
                                key={`${tag.tag}-${tag.start}`}
                                className="text-[10px] font-mono px-2 py-0.5 rounded border border-panel-border bg-panel text-muted-foreground"
                            >
                                {getReadableTagName(tag.tag)}
                            </span>
                        ))}
                    </div>
                    {parsedMessage.text && (
                        <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed break-words">{parsedMessage.text}</p>
                    )}
                </div>
            );
        }

        return (
            <div className="bg-panel/40 border border-panel-border rounded-xl p-5">
                <p className="text-foreground leading-relaxed whitespace-pre-wrap text-sm">{log.content}</p>
            </div>
        );
    };

    const renderRawMessageSection = () => {
        if (parsedMessage.kind === 'plain') {
            return null;
        }
        const rawSectionId = `raw-${parsedMessage.kind}`;
        return (
            <div className="bg-surface-overlay/70 border border-panel-border rounded-xl p-4">
                <button
                    onClick={() => toggleSection(rawSectionId)}
                    className="w-full flex justify-between items-center text-[10px] text-muted-foreground uppercase font-bold tracking-wider hover:text-foreground transition-colors"
                >
                    <span>{expandedSections.has(rawSectionId) ? 'Hide Raw' : 'View Raw...'}</span>
                    {expandedSections.has(rawSectionId) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>
                {expandedSections.has(rawSectionId) && (
                    <pre className="mt-3 text-xs font-mono text-foreground bg-panel/75 p-3 rounded border border-panel-border whitespace-pre-wrap break-words max-h-96 overflow-y-auto animate-in fade-in slide-in-from-top-1 duration-200">
                        {parsedMessage.rawText}
                    </pre>
                )}
            </div>
        );
    };

    return (
        <div className="flex flex-col h-full animate-in fade-in slide-in-from-right-2 duration-300">
            <div className="p-4 border-b border-panel-border bg-panel/60 flex items-center justify-between">
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
                        <h4 className="text-sm font-bold text-panel-foreground uppercase tracking-tight">
                            {detailTitle}
                        </h4>
                        <p className="text-[10px] text-muted-foreground font-mono">{log.timestamp}</p>
                    </div>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* TOOL DETAILS WITH INLINE EXPANSION */}
                {log.type === 'tool' && log.toolCall && (
                    <div className="space-y-4">
                        {isMappedTranscriptMessageKind(parsedMessage.kind) && parsedMessage.mapped && (
                            <TranscriptMappedMessageCard
                                message={parsedMessage}
                                commandArtifactsCount={commandArtifacts.length}
                                onOpenArtifacts={onOpenArtifacts}
                            />
                        )}
                        <div className="bg-surface-overlay rounded-xl border border-panel-border overflow-hidden">
                            <div className="px-4 py-3 bg-panel border-b border-panel-border flex justify-between items-center">
                                <span className="text-xs font-mono text-amber-500 flex items-center gap-2">
                                    <Terminal size={14} /> {log.toolCall.name}
                                </span>
                                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${log.toolCall.status === 'success' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'}`}>
                                    {log.toolCall.status.toUpperCase()}
                                </span>
                            </div>

                            {taskToolDetails && (
                                <div className="p-4 border-b border-panel-border bg-amber-500/5">
                                    <div className="text-[10px] text-amber-300 uppercase tracking-widest font-bold mb-3">{taskToolDetails.toolName} Details</div>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                                        {taskToolDetails.taskId && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Task ID</div>
                                                <div className="font-mono text-amber-200">{taskToolDetails.taskId}</div>
                                            </div>
                                        )}
                                        {(taskToolDetails.description || taskToolDetails.name) && (
                                            <div className="sm:col-span-2">
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Description</div>
                                                <div className="text-panel-foreground">{taskToolDetails.description || taskToolDetails.name}</div>
                                            </div>
                                        )}
                                        {taskDisplayContext.subagentLabel && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Subagent</div>
                                                <StableBadge value={taskDisplayContext.subagentLabel} namespace="subagent" />
                                            </div>
                                        )}
                                        {taskDisplayContext.model && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Model</div>
                                                <ModelBadge
                                                    raw={taskDisplayContext.model.raw}
                                                    displayName={taskDisplayContext.model.displayName}
                                                    provider={taskDisplayContext.model.provider}
                                                    family={taskDisplayContext.model.family}
                                                    version={taskDisplayContext.model.version}
                                                />
                                            </div>
                                        )}
                                        {taskToolDetails.mode && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Mode</div>
                                                <div className="text-foreground">{taskToolDetails.mode}</div>
                                            </div>
                                        )}
                                        {typeof taskToolDetails.runInBackground === 'boolean' && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Run In Background</div>
                                                <div className="text-foreground">{taskToolDetails.runInBackground ? 'true' : 'false'}</div>
                                            </div>
                                        )}
                                        {taskToolDetails.promptPreview && (
                                            <div className="sm:col-span-2">
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Prompt (Preview)</div>
                                                <p className="text-foreground whitespace-pre-wrap break-words">{taskToolDetails.promptPreview}</p>
                                                {taskToolDetails.prompt && taskToolDetails.prompt !== taskToolDetails.promptPreview && (
                                                    <button
                                                        onClick={() => toggleSection('task-full-prompt')}
                                                        className="mt-2 text-[10px] px-2 py-1 rounded border border-amber-500/30 text-amber-300 bg-amber-500/10 hover:bg-amber-500/20"
                                                    >
                                                        {expandedSections.has('task-full-prompt') ? 'Hide Full Prompt' : 'View Full Prompt'}
                                                    </button>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                    {expandedSections.has('task-full-prompt') && taskToolDetails.prompt && (
                                        <div className="mt-3 max-h-96 animate-in slide-in-from-top-1 duration-200">
                                            {taskPromptViewerPayload ? (
                                                <UnifiedContentViewer
                                                    path={taskPromptViewerPayload.path}
                                                    content={taskPromptViewerPayload.content}
                                                    readOnly
                                                    className="h-full"
                                                    ariaLabel={`Task prompt: ${taskPromptViewerPayload.path}`}
                                                />
                                            ) : (
                                                <pre className="text-xs font-mono text-foreground bg-panel/70 p-3 rounded border border-panel-border whitespace-pre-wrap break-words max-h-96 overflow-y-auto">
                                                    {taskToolDetails.prompt}
                                                </pre>
                                            )}
                                        </div>
                                    )}
                                    {taskToolDetails.args && (
                                        <div className="mt-4 bg-panel/70 border border-panel-border rounded-lg p-3">
                                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-bold mb-2">Invocation Parameters</div>
                                            <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words max-h-72 overflow-y-auto">
                                                {JSON.stringify(taskToolDetails.args, null, 2)}
                                            </pre>
                                        </div>
                                    )}
                                </div>
                            )}

                            {taskMutationDetails && (
                                <div className="p-4 border-b border-panel-border bg-sky-500/5">
                                    <div className="text-[10px] text-sky-300 uppercase tracking-widest font-bold mb-3">{taskMutationDetails.toolName} Details</div>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                                        {taskMutationDetails.taskId && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Task ID</div>
                                                <StableBadge value={taskMutationDetails.taskId} namespace="task" mono />
                                            </div>
                                        )}
                                        {taskMutationDetails.status && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Status</div>
                                                <StableBadge value={taskMutationDetails.status} namespace="task-status" />
                                            </div>
                                        )}
                                        {taskMutationDetails.subject && (
                                            <div className="sm:col-span-2">
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Subject</div>
                                                <div className="text-panel-foreground">{taskMutationDetails.subject}</div>
                                            </div>
                                        )}
                                        {taskMutationDetails.description && (
                                            <div className="sm:col-span-2">
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Description</div>
                                                <div className="text-foreground whitespace-pre-wrap break-words">{taskMutationDetails.description}</div>
                                            </div>
                                        )}
                                        {taskMutationDetails.taskType && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Task Type</div>
                                                <div className="text-foreground">{taskMutationDetails.taskType}</div>
                                            </div>
                                        )}
                                        {taskMutationDetails.activeForm && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Active Form</div>
                                                <div className="text-foreground">{taskMutationDetails.activeForm}</div>
                                            </div>
                                        )}
                                        {taskMutationDetails.blockedByAdded.length > 0 && (
                                            <div className="sm:col-span-2">
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Blocked By Added</div>
                                                <div className="flex flex-wrap gap-1">
                                                    {taskMutationDetails.blockedByAdded.map(item => (
                                                        <StableBadge key={`blocked-by-add-${item}`} value={item} namespace="dependency" mono />
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        {taskMutationDetails.blockedByRemoved.length > 0 && (
                                            <div className="sm:col-span-2">
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Blocked By Removed</div>
                                                <div className="flex flex-wrap gap-1">
                                                    {taskMutationDetails.blockedByRemoved.map(item => (
                                                        <StableBadge key={`blocked-by-remove-${item}`} value={item} namespace="dependency" mono />
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                    {taskMutationDetails.args && (
                                        <div className="mt-4 bg-panel/70 border border-panel-border rounded-lg p-3">
                                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-bold mb-2">Arguments</div>
                                            <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words max-h-72 overflow-y-auto">
                                                {JSON.stringify(taskMutationDetails.args, null, 2)}
                                            </pre>
                                        </div>
                                    )}
                                    {(taskMutationDetails.outputText || Object.keys(taskMutationDetails.outputData).length > 0) && (
                                        <div className="mt-4 bg-panel/70 border border-panel-border rounded-lg p-3 space-y-3">
                                            {taskMutationDetails.outputText && (
                                                <div>
                                                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-bold mb-2">Output Text</div>
                                                    <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words max-h-56 overflow-y-auto">
                                                        {taskMutationDetails.outputText}
                                                    </pre>
                                                </div>
                                            )}
                                            {Object.keys(taskMutationDetails.outputData).length > 0 && (
                                                <div>
                                                    <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-bold mb-2">Output Data</div>
                                                    <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words max-h-72 overflow-y-auto">
                                                        {JSON.stringify(taskMutationDetails.outputData, null, 2)}
                                                    </pre>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}

                            {testToolDetails && (
                                <div className="p-4 border-b border-panel-border bg-emerald-500/5">
                                    <div className="text-[10px] text-emerald-300 uppercase tracking-widest font-bold mb-3">Test Run Details</div>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                                        <div>
                                            <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Framework</div>
                                            <div className="font-mono text-emerald-200">{testToolDetails.framework}</div>
                                        </div>
                                        {testToolDetails.status && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Status</div>
                                                <div className="text-panel-foreground">{testToolDetails.status}</div>
                                            </div>
                                        )}
                                        {(testToolDetails.domain || testToolDetails.domains.length > 0) && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Domain</div>
                                                <div className="text-foreground">
                                                    {testToolDetails.domain || testToolDetails.domains.join(', ')}
                                                </div>
                                            </div>
                                        )}
                                        {typeof testToolDetails.timeoutMs === 'number' && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Timeout</div>
                                                <div className="text-foreground">{testToolDetails.timeoutMs} ms</div>
                                            </div>
                                        )}
                                        {typeof testToolDetails.durationSeconds === 'number' && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Duration</div>
                                                <div className="text-foreground">{testToolDetails.durationSeconds.toFixed(2)} s</div>
                                            </div>
                                        )}
                                        {typeof testToolDetails.total === 'number' && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Total</div>
                                                <div className="text-foreground">{testToolDetails.total} tests</div>
                                            </div>
                                        )}
                                        {typeof testToolDetails.passRate === 'number' && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Pass Rate</div>
                                                <div className="text-foreground">{(testToolDetails.passRate * 100).toFixed(1)}%</div>
                                            </div>
                                        )}
                                        {typeof testToolDetails.collected === 'number' && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Collected</div>
                                                <div className="text-foreground">{testToolDetails.collected}</div>
                                            </div>
                                        )}
                                        {typeof testToolDetails.workers === 'number' && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Workers</div>
                                                <div className="text-foreground">{testToolDetails.workers}</div>
                                            </div>
                                        )}
                                        {testToolDetails.pytestVersion && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Pytest</div>
                                                <div className="text-foreground">{testToolDetails.pytestVersion}</div>
                                            </div>
                                        )}
                                        {testToolDetails.pythonVersion && (
                                            <div>
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Python</div>
                                                <div className="text-foreground">{testToolDetails.pythonVersion}</div>
                                            </div>
                                        )}
                                        {testToolDetails.rootdir && (
                                            <div className="sm:col-span-2">
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Rootdir</div>
                                                <div className="font-mono text-foreground break-all">{testToolDetails.rootdir}</div>
                                            </div>
                                        )}
                                        {testToolDetails.description && (
                                            <div className="sm:col-span-2">
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Description</div>
                                                <div className="text-panel-foreground">{testToolDetails.description}</div>
                                            </div>
                                        )}
                                        {Object.keys(testToolDetails.counts).length > 0 && (
                                            <div className="sm:col-span-2">
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Result Counts</div>
                                                <div className="flex flex-wrap gap-2">
                                                    {Object.entries(testToolDetails.counts).map(([key, value]) => (
                                                        <span key={key} className="text-[10px] px-2 py-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-200 font-mono">
                                                            {key}: {value}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        {testToolDetails.targets.length > 0 && (
                                            <div className="sm:col-span-2">
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Targets</div>
                                                <div className="text-foreground font-mono break-all whitespace-pre-wrap">
                                                    {testToolDetails.targets.slice(0, 12).join('\n')}
                                                </div>
                                            </div>
                                        )}
                                        {testToolDetails.flags.length > 0 && (
                                            <div className="sm:col-span-2">
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Flags</div>
                                                <div className="text-foreground font-mono break-all">{testToolDetails.flags.join(' ')}</div>
                                            </div>
                                        )}
                                        {testToolDetails.command && (
                                            <div className="sm:col-span-2">
                                                <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Command</div>
                                                <div className="text-foreground font-mono break-all">{testToolDetails.command}</div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}

                            {readToolDetails && (
                                <div className="p-4 border-b border-panel-border bg-sky-500/5">
                                    <div className="text-[10px] text-sky-300 uppercase tracking-widest font-bold mb-3">Read Details</div>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                                        <div className="sm:col-span-2">
                                            <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">File</div>
                                            <div className="font-mono text-sky-200 break-all">{readToolDetails.filePath || 'n/a'}</div>
                                        </div>
                                        <div>
                                            <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Offset</div>
                                            <div className="text-foreground font-mono">
                                                {typeof readToolDetails.offset === 'number' ? readToolDetails.offset : 'n/a'}
                                            </div>
                                        </div>
                                        <div>
                                            <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Limit</div>
                                            <div className="text-foreground font-mono">
                                                {typeof readToolDetails.limit === 'number' ? readToolDetails.limit : 'n/a'}
                                            </div>
                                        </div>
                                    </div>
                                    {Object.keys(readToolDetails.otherParams).length > 0 && (
                                        <div className="mt-4 bg-panel/70 border border-panel-border rounded-lg p-3">
                                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-bold mb-2">Other Parameters</div>
                                            <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words max-h-72 overflow-y-auto">
                                                {JSON.stringify(readToolDetails.otherParams, null, 2)}
                                            </pre>
                                        </div>
                                    )}
                                    {inlineContentViewerPayload && (
                                        <div className="mt-4">
                                            <div className="mb-2 text-[10px] text-muted-foreground uppercase tracking-wider font-bold">Shared Viewer Preview</div>
                                            <UnifiedContentViewer
                                                path={inlineContentViewerPayload.path}
                                                content={inlineContentViewerPayload.content}
                                                readOnly
                                                ariaLabel={`Transcript file content: ${inlineContentViewerPayload.path}`}
                                            />
                                        </div>
                                    )}
                                </div>
                            )}

                            {grepToolDetails && (
                                <div className="p-4 border-b border-panel-border bg-cyan-500/5">
                                    <div className="text-[10px] text-cyan-300 uppercase tracking-widest font-bold mb-3">Grep Details</div>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                                        <div className="sm:col-span-2">
                                            <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Pattern</div>
                                            <div className="font-mono text-cyan-200 break-all">{grepToolDetails.pattern || 'n/a'}</div>
                                        </div>
                                        <div className="sm:col-span-2">
                                            <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Path</div>
                                            <div className="font-mono text-foreground break-all">{grepToolDetails.searchPath || 'n/a'}</div>
                                        </div>
                                        <div>
                                            <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Output Mode</div>
                                            <div className="text-foreground font-mono">{grepToolDetails.outputMode || 'n/a'}</div>
                                        </div>
                                        <div>
                                            <div className="text-muted-foreground uppercase tracking-wider text-[10px] mb-1">Line Numbers</div>
                                            <div className="text-foreground font-mono">
                                                {grepToolDetails.lineNumbersEnabled === null
                                                    ? 'n/a'
                                                    : (grepToolDetails.lineNumbersEnabled ? 'enabled' : 'disabled')}
                                            </div>
                                        </div>
                                    </div>
                                    {Object.keys(grepToolDetails.otherParams).length > 0 && (
                                        <div className="mt-4 bg-panel/70 border border-panel-border rounded-lg p-3">
                                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-bold mb-2">Other Parameters</div>
                                            <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words max-h-72 overflow-y-auto">
                                                {JSON.stringify(grepToolDetails.otherParams, null, 2)}
                                            </pre>
                                        </div>
                                    )}
                                    <div className="mt-4 bg-panel/70 border border-panel-border rounded-lg p-3">
                                        <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-bold mb-2">Matches By File</div>
                                        {grepToolDetails.files.length === 0 ? (
                                            <div className="text-xs text-muted-foreground">No parseable grep matches were found in tool output.</div>
                                        ) : (
                                            <div className="space-y-2">
                                                {grepToolDetails.files.map((file, index) => {
                                                    const sectionId = `grep-file-${index}-${file.filePath}`;
                                                    const isExpanded = expandedSections.has(sectionId);
                                                    return (
                                                        <div key={sectionId} className="border border-panel-border rounded-md bg-surface-overlay/80 overflow-hidden">
                                                            <button
                                                                onClick={() => toggleSection(sectionId)}
                                                                className="w-full px-3 py-2 flex items-center justify-between gap-3 text-left hover:bg-panel/75 transition-colors"
                                                            >
                                                                <span className="font-mono text-xs text-cyan-200 break-all">{file.filePath}</span>
                                                                <div className="flex items-center gap-2 shrink-0">
                                                                    <span className="text-[10px] text-muted-foreground">{file.matches.length} match{file.matches.length === 1 ? '' : 'es'}</span>
                                                                    {isExpanded ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
                                                                </div>
                                                            </button>
                                                            {isExpanded && (
                                                                <pre className="border-t border-panel-border px-3 py-2 text-xs font-mono text-foreground whitespace-pre-wrap break-words max-h-72 overflow-y-auto animate-in slide-in-from-top-1 duration-200">
                                                                    {file.matches
                                                                        .map(match => `${typeof match.lineNumber === 'number' ? match.lineNumber : '?'}: ${match.content}`)
                                                                        .join('\n')}
                                                                </pre>
                                                            )}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}

                            {/* Arguments Section */}
                            <div className="p-4 border-b border-panel-border">
                                <button
                                    onClick={() => toggleSection('args')}
                                    className="w-full flex justify-between items-center text-[10px] text-muted-foreground uppercase font-bold tracking-wider mb-2 hover:text-foreground transition-colors"
                                >
                                    <span>Arguments</span>
                                    {expandedSections.has('args') ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                </button>
                                {expandedSections.has('args') && (
                                    <pre className="text-xs font-mono text-foreground bg-panel/60 p-3 rounded border border-panel-border overflow-x-auto animate-in slide-in-from-top-1 duration-200">
                                        {log.toolCall.args}
                                    </pre>
                                )}
                            </div>

                            {/* Output Section */}
                            {log.toolCall.output && !inlineContentViewerPayload && (
                                <div className="p-4 bg-panel/20">
                                    <button
                                        onClick={() => toggleSection('output')}
                                        className="w-full flex justify-between items-center text-[10px] text-muted-foreground uppercase font-bold tracking-wider mb-2 hover:text-foreground transition-colors"
                                    >
                                        <span>Output</span>
                                        {expandedSections.has('output') ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                    </button>
                                    {expandedSections.has('output') && (
                                        <pre className="text-xs font-mono text-muted-foreground overflow-x-auto whitespace-pre-wrap animate-in slide-in-from-top-1 duration-200">
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
                                    className="bg-panel/60 rounded-lg p-3 border border-panel-border cursor-pointer hover:border-panel-border transition-all"
                                >
                                    <div className="flex justify-between items-center mb-2">
                                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${sl.speaker === 'user' ? 'bg-surface-muted text-muted-foreground' : 'bg-indigo-500/10 text-indigo-400'}`}>
                                            {sl.speaker.toUpperCase()}
                                        </span>
                                        <div className="flex items-center gap-2">
                                            <span className="text-[9px] text-muted-foreground font-mono">{sl.timestamp}</span>
                                            {expandedSections.has(`sub-${sl.id}`) ? <ChevronDown size={12} className="text-muted-foreground" /> : <ChevronRight size={12} className="text-muted-foreground" />}
                                        </div>
                                    </div>
                                    <p className={`text-xs text-foreground ${expandedSections.has(`sub-${sl.id}`) ? '' : 'line-clamp-2'}`}>{sl.content}</p>
                                    {expandedSections.has(`sub-${sl.id}`) && sl.toolCall && (
                                        <div className="mt-3 text-[10px] font-mono text-amber-500 bg-amber-500/5 p-2 rounded border border-amber-500/10 animate-in fade-in duration-200">
                                            <div className="mb-1 flex justify-between">
                                                <span>{'>'} {sl.toolCall.name}</span>
                                                <span className="opacity-50">{sl.toolCall.status}</span>
                                            </div>
                                            <div className="text-muted-foreground truncate">{sl.toolCall.args}</div>
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
                        {transcriptViewerPayload ? (
                            <UnifiedContentViewer
                                path={transcriptViewerPayload.path}
                                content={transcriptViewerPayload.content}
                                readOnly
                                ariaLabel={`Transcript content: ${transcriptViewerPayload.path}`}
                            />
                        ) : (
                            <>
                                {renderStructuredMessage()}
                                {renderRawMessageSection()}
                            </>
                        )}
                        {log.linkedSessionId && (
                            <p className="text-[11px] text-indigo-300 font-mono">Linked Thread: {log.linkedSessionId}</p>
                        )}
                    </>
                )}

                {/* SKILLS */}
                {log.type === 'skill' && log.skillDetails && (
                    <div className="space-y-4">
                        {transcriptViewerPayload ? (
                            <UnifiedContentViewer
                                path={transcriptViewerPayload.path}
                                content={transcriptViewerPayload.content}
                                readOnly
                                ariaLabel={`Skill content: ${transcriptViewerPayload.path}`}
                            />
                        ) : (
                            <>
                                {isMappedTranscriptMessageKind(parsedMessage.kind) && parsedMessage.mapped && (
                                    <TranscriptMappedMessageCard
                                        message={parsedMessage}
                                        commandArtifactsCount={commandArtifacts.length}
                                        onOpenArtifacts={onOpenArtifacts}
                                    />
                                )}
                                <div className="bg-panel border border-panel-border rounded-xl p-5 shadow-lg">
                                    <div className="flex items-center gap-2 text-blue-400 font-mono text-sm mb-3">
                                        <Cpu size={16} /> {log.skillDetails.name}
                                    </div>
                                    <p className="text-muted-foreground text-xs mb-4 leading-relaxed">{log.skillDetails.description}</p>
                                    <div className="flex items-center justify-between text-[10px] border-t border-panel-border pt-3">
                                        <span className="text-muted-foreground">Version</span>
                                        <span className="font-mono text-foreground">{log.skillDetails.version}</span>
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

// --- Virtualized Transcript List ---

const TRANSCRIPT_ROW_GAP = 8; // px — matches space-y-2

export const VirtualizedTranscriptList: React.FC<{
    containerRef: React.RefObject<HTMLDivElement | null>;
    logs: SessionLog[];
    insertedIds: Set<string>;
    isLive: boolean;
    selectedLogId: string | null;
    setSelectedLogId: (id: string | null) => void;
    formattedMessagesByLogId: Map<string, TranscriptFormattedMessage>;
    filesByLogId: Map<string, number>;
    artifactsByLogId: Map<string, SessionArtifact[]>;
    threadSessionDetails: Record<string, AgentSession>;
    subagentNameBySessionId: Map<string, string>;
    onOpenThread: (sessionId: string) => void;
    onShowLinked: (tab: 'activity' | 'artifacts', sourceLogId: string) => void;
    messagePreset: ReturnType<typeof import('../animations').getMotionPreset>;
    transcriptTruncated?: { droppedCount: number; firstRetainedTimestamp?: string };
}> = ({
    containerRef,
    logs,
    insertedIds,
    isLive,
    selectedLogId,
    setSelectedLogId,
    formattedMessagesByLogId,
    filesByLogId,
    artifactsByLogId,
    threadSessionDetails,
    subagentNameBySessionId,
    onOpenThread,
    onShowLinked,
    messagePreset,
    transcriptTruncated,
}) => {
    const rowVirtualizer = useVirtualizer({
        count: logs.length,
        getScrollElement: () => containerRef.current,
        estimateSize: () => 68,
        overscan: 8,
        gap: TRANSCRIPT_ROW_GAP,
    });

    const virtualItems = rowVirtualizer.getVirtualItems();
    const totalSize = rowVirtualizer.getTotalSize();

    return (
        <div
            ref={containerRef}
            className="flex-1 overflow-y-auto custom-scrollbar"
            style={{ contain: 'strict' }}
        >
            {/* Truncation notice */}
            {isMemoryGuardEnabled() && transcriptTruncated && transcriptTruncated.droppedCount > 0 && (
                <div className="px-4 pt-4 pb-2">
                    <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300 font-mono">
                        Older {transcriptTruncated.droppedCount.toLocaleString()} messages hidden
                        {transcriptTruncated.firstRetainedTimestamp ? (
                            <span className="text-amber-400/70 ml-1">(showing from {new Date(transcriptTruncated.firstRetainedTimestamp).toLocaleTimeString()})</span>
                        ) : null}
                    </div>
                </div>
            )}

            {logs.length === 0 && (
                <div className="p-8 text-center text-muted-foreground italic">No logs found for this view.</div>
            )}

            {logs.length > 0 && (
                <div
                    style={{
                        height: totalSize + 32, // 16px top + 16px bottom padding
                        position: 'relative',
                        paddingTop: 16,
                    }}
                >
                    <AnimatePresence initial={false}>
                        {virtualItems.map(virtualRow => {
                            const log = logs[virtualRow.index];
                            const shouldAnimateIn = isLive && insertedIds.has(log.id);
                            return (
                                <motion.div
                                    key={log.id}
                                    data-index={virtualRow.index}
                                    ref={rowVirtualizer.measureElement}
                                    style={{
                                        position: 'absolute',
                                        top: 0,
                                        left: 0,
                                        width: '100%',
                                        transform: `translateY(${virtualRow.start + 16}px)`,
                                        paddingLeft: 16,
                                        paddingRight: 16,
                                    }}
                                    initial={shouldAnimateIn ? messagePreset.initial : false}
                                    animate={shouldAnimateIn ? messagePreset.animate : undefined}
                                    exit={messagePreset.exit}
                                    transition={messagePreset.transition}
                                >
                                    <LogItemBlurb
                                        log={log}
                                        formattedMessage={formattedMessagesByLogId.get(log.id)}
                                        isSelected={selectedLogId === log.id}
                                        onClick={() => setSelectedLogId(log.id === selectedLogId ? null : log.id)}
                                        fileCount={filesByLogId.get(log.id) || 0}
                                        artifactCount={(artifactsByLogId.get(log.id) || []).length}
                                        onShowFiles={() => onShowLinked('activity', log.id)}
                                        onShowArtifacts={() => onShowLinked('artifacts', log.id)}
                                        threadSessionDetails={threadSessionDetails}
                                        subagentNameBySessionId={subagentNameBySessionId}
                                        onOpenThread={onOpenThread}
                                    />
                                </motion.div>
                            );
                        })}
                    </AnimatePresence>
                </div>
            )}
        </div>
    );
};

// --- View Components ---

export const TranscriptView: React.FC<{
    session: AgentSession;
    selectedLogId: string | null;
    setSelectedLogId: (id: string | null) => void;
    filterAgent?: string | null;
    threadSessions: AgentSession[];
    threadSessionDetails: Record<string, AgentSession>;
    subagentNameBySessionId: Map<string, string>;
    onOpenThread: (sessionId: string) => void;
    onShowLinked: (tab: 'activity' | 'artifacts', sourceLogId: string) => void;
    primaryFeatureLink?: SessionFeatureLink | null;
    onOpenFeature?: (featureId: string) => void;
    onOpenForensics?: () => void;
}> = ({ session, selectedLogId, setSelectedLogId, filterAgent, threadSessions, threadSessionDetails, subagentNameBySessionId, onOpenThread, onShowLinked, primaryFeatureLink, onOpenFeature, onOpenForensics }) => {

    const logs = filterAgent
        ? session.logs.filter(l => l.agentName === filterAgent || l.speaker === 'user' || l.speaker === 'system')
        : session.logs;
    const [transcriptMappings, setTranscriptMappings] = useState<TranscriptFormattingMappingRule[]>([]);
    const prefersReducedMotion = useReducedMotionPreference();
    const messagePreset = getMotionPreset('messageFlyIn', prefersReducedMotion);
    const smartScroll = useSmartScrollAnchor<HTMLDivElement>({
        thresholdPx: 120,
        stickBehavior: prefersReducedMotion ? 'auto' : 'smooth',
    });

    useEffect(() => {
        let cancelled = false;
        const loadMappings = async () => {
            try {
                const res = await fetch('/api/session-mappings');
                if (!res.ok) return;
                const data = await res.json();
                if (!cancelled && Array.isArray(data)) {
                    setTranscriptMappings(data as TranscriptFormattingMappingRule[]);
                }
            } catch {
                if (!cancelled) {
                    setTranscriptMappings([]);
                }
            }
        };
        void loadMappings();
        return () => {
            cancelled = true;
        };
    }, []);

    const animatedLogs = useAnimatedListDiff(logs, {
        getId: log => log.id,
    });
    const selectedLog = animatedLogs.items.find(l => l.id === selectedLogId);
    const threadLinks = threadSessions.filter(t => t.id !== session.id);
    const forkLinks = useMemo(
        () => threadLinks.filter(thread => isForkThread(thread)),
        [threadLinks],
    );
    const linkedSubthreads = useMemo(
        () => threadLinks.filter(thread => !isForkThread(thread)),
        [threadLinks],
    );
    const directForkLinks = useMemo(
        () => forkLinks.filter(thread => String(thread.forkParentSessionId || '').trim() === session.id),
        [forkLinks, session.id],
    );
    const parentForkSessionId = String(session.forkParentSessionId || '').trim();
    const currentSessionIsFork = isForkThread(session);
    const parentForkLink = useMemo(
        () => (parentForkSessionId ? threadLinks.find(thread => thread.id === parentForkSessionId) || null : null),
        [parentForkSessionId, threadLinks],
    );
    const siblingForkLinks = useMemo(
        () => (
            currentSessionIsFork && parentForkSessionId
                ? forkLinks.filter(thread => (
                    thread.id !== session.id
                    && String(thread.forkParentSessionId || '').trim() === parentForkSessionId
                ))
                : []
        ),
        [currentSessionIsFork, forkLinks, parentForkSessionId, session.id],
    );
    const forkSummaryBySessionId = useMemo(() => {
        const map = new Map<string, {
            sessionId: string;
            label?: string;
            forkPointTimestamp?: string;
            forkPointPreview?: string;
            entryCount?: number;
            contextInheritance?: string;
        }>();
        (session.forks || []).forEach(summary => {
            const id = String(summary.sessionId || '').trim();
            if (id && !map.has(id)) {
                map.set(id, summary);
            }
        });
        return map;
    }, [session.forks]);
    const liveNowMs = Date.now();
    const activeLiveAgents = useMemo<LiveAgentActivity[]>(() => {
        return linkedSubthreads
            .filter(thread => isSessionLiveInFlight(thread, liveNowMs))
            .map(thread => ({
                agentName: getLiveAgentLabel(thread, subagentNameBySessionId),
                sessionId: thread.id,
                threadSessionId: thread.id,
                lastSeenAt: thread.updatedAt || thread.startedAt,
                status: 'active' as const,
            }))
            .sort((a, b) => toEpoch(b.lastSeenAt) - toEpoch(a.lastSeenAt));
    }, [linkedSubthreads, liveNowMs, subagentNameBySessionId]);
    const liveTranscriptState = useMemo<LiveTranscriptState>(() => ({
        isLive: session.status === 'active',
        pendingMessageCount: smartScroll.pendingInserts,
        autoStickToLatest: smartScroll.isNearBottom,
        activeAgents: activeLiveAgents,
    }), [activeLiveAgents, session.status, smartScroll.isNearBottom, smartScroll.pendingInserts]);
    const { clearPendingInserts, onItemsInserted, scrollToLatest } = smartScroll;

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
            const isHookSystemEvent = (
                log.type === 'system'
                && String(asRecord(log.metadata).eventType || '').trim().toLowerCase() === 'hook_progress'
            );
            if (log.type === 'message' || log.type === 'command' || log.type === 'tool' || log.type === 'skill' || isHookSystemEvent) {
                const sourceText = getTranscriptSourceText(log);
                map.set(log.id, parseTranscriptMessage(sourceText, {
                    mappings: transcriptMappings,
                    platformType: session.platformType,
                }));
            }
        });
        return map;
    }, [logs, session.platformType, transcriptMappings]);

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
    const forensicsResourceFootprint = useMemo(() => asRecord(sessionForensics.resourceFootprint), [sessionForensics]);
    const forensicsQueuePressure = useMemo(() => asRecord(sessionForensics.queuePressure), [sessionForensics]);
    const forensicsSubagentTopology = useMemo(() => asRecord(sessionForensics.subagentTopology), [sessionForensics]);
    const forensicsToolResultIntensity = useMemo(() => asRecord(sessionForensics.toolResultIntensity), [sessionForensics]);
    const forensicsPlatformTelemetry = useMemo(() => asRecord(sessionForensics.platformTelemetry), [sessionForensics]);
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
    const toolResultsSidecar = useMemo(() => asRecord(forensicsSidecars.toolResults), [forensicsSidecars]);
    const todosCount = asNumber(todosSidecar.totalItems, 0);
    const tasksCount = Array.isArray(tasksSidecar.tasks) ? tasksSidecar.tasks.length : asNumber(tasksSidecar.taskFileCount, 0);
    const teamMessagesCount = asNumber(teamsSidecar.totalMessages, 0);
    const teamUnreadCount = asNumber(teamsSidecar.unreadMessages, 0);
    const resourceObservationCount = asNumber(forensicsResourceFootprint.totalObservations, 0);
    const waitingForTaskCount = asNumber(forensicsQueuePressure.waitingForTaskCount, 0);
    const subagentStartCount = asNumber(forensicsSubagentTopology.subagentStartCount, 0);
    const toolResultFileCount = asNumber(
        toolResultsSidecar.fileCount,
        asNumber(forensicsToolResultIntensity.fileCount, 0),
    );
    const toolResultTotalBytes = asNumber(
        toolResultsSidecar.totalBytes,
        asNumber(forensicsToolResultIntensity.totalBytes, 0),
    );
    const telemetryProject = useMemo(() => asRecord(forensicsPlatformTelemetry.project), [forensicsPlatformTelemetry]);
    const telemetryMcpServerCount = asNumber(telemetryProject.mcpServerCount, 0);
    const hasDetailedForensics = Object.keys(sessionForensics).length > 0;

    useEffect(() => {
        if (!liveTranscriptState.isLive) {
            clearPendingInserts();
            return;
        }
        if (!animatedLogs.isHydrated || animatedLogs.insertedIds.size === 0) return;
        onItemsInserted(animatedLogs.insertedIds.size);
    }, [
        animatedLogs.insertedIds,
        animatedLogs.isHydrated,
        clearPendingInserts,
        liveTranscriptState.isLive,
        onItemsInserted,
    ]);

    useEffect(() => {
        clearPendingInserts();
        if (liveTranscriptState.isLive) {
            scrollToLatest('auto');
        }
    }, [clearPendingInserts, filterAgent, liveTranscriptState.isLive, scrollToLatest, session.id]);

    return (
        <div className="flex-1 flex gap-4 min-h-0 min-w-full h-full">
            {/* Pane 1: Chat Transcript (Left) */}
            <div
                className={`relative flex flex-col bg-panel/60 border border-panel-border rounded-2xl overflow-hidden transition-all duration-500 ease-out ${selectedLogId ? 'basis-[30%] min-w-[320px] max-w-[520px]' : 'flex-1 min-w-[420px]'
                    }`}
            >
                <div className="p-4 border-b border-panel-border bg-surface-overlay/70 flex items-center justify-between">
                    <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-2">
                        <MessageSquare size={14} className="text-indigo-400" /> {filterAgent ? `Transcript: ${filterAgent}` : 'Full Transcript'}
                    </h3>
                    <div className="text-[10px] text-muted-foreground font-mono">{animatedLogs.items.length} Steps</div>
                </div>
                <VirtualizedTranscriptList
                    containerRef={smartScroll.containerRef}
                    logs={animatedLogs.items}
                    insertedIds={animatedLogs.insertedIds}
                    isLive={liveTranscriptState.isLive}
                    selectedLogId={selectedLogId}
                    setSelectedLogId={setSelectedLogId}
                    formattedMessagesByLogId={formattedMessagesByLogId}
                    filesByLogId={filesByLogId}
                    artifactsByLogId={artifactsByLogId}
                    threadSessionDetails={threadSessionDetails}
                    subagentNameBySessionId={subagentNameBySessionId}
                    onOpenThread={onOpenThread}
                    onShowLinked={onShowLinked}
                    messagePreset={messagePreset}
                    transcriptTruncated={session.transcriptTruncated}
                />
                {liveTranscriptState.isLive && (
                    <div className="border-t border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <div className="flex flex-wrap items-center gap-2">
                                <span className="inline-flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-emerald-200">
                                    <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(74,222,128,0.6)]" />
                                    Live
                                </span>
                                <TypingIndicator label="Live transcript activity" />
                                <span className="text-[11px] text-emerald-100/80">
                                    {liveTranscriptState.autoStickToLatest ? 'Auto-following latest updates' : 'New updates are waiting below your scroll position'}
                                </span>
                            </div>
                            {!liveTranscriptState.autoStickToLatest && liveTranscriptState.pendingMessageCount > 0 && (
                                <button
                                    type="button"
                                    onClick={() => scrollToLatest()}
                                    className="inline-flex items-center gap-2 rounded-full border border-emerald-400/40 bg-emerald-400/10 px-3 py-1 text-[11px] font-semibold text-emerald-100 hover:bg-emerald-400/20 transition-colors"
                                >
                                    {liveTranscriptState.pendingMessageCount} new message{liveTranscriptState.pendingMessageCount === 1 ? '' : 's'}
                                </button>
                            )}
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                            {liveTranscriptState.activeAgents.length > 0 ? (
                                liveTranscriptState.activeAgents.slice(0, 6).map(agent => (
                                    <button
                                        key={agent.threadSessionId || agent.sessionId || agent.agentName}
                                        type="button"
                                        onClick={() => {
                                            if (agent.sessionId) onOpenThread(agent.sessionId);
                                        }}
                                        className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/25 bg-surface-overlay/70 px-2.5 py-1 text-[11px] text-emerald-100 hover:border-emerald-300/40 hover:bg-emerald-400/10 transition-colors"
                                    >
                                        <Activity size={11} />
                                        {agent.agentName}
                                    </button>
                                ))
                            ) : (
                                <span className="text-[11px] text-emerald-100/65">
                                    Monitoring the main thread for new transcript entries.
                                </span>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* Pane 2: Expanded Details (Middle) - Dynamic visibility */}
            <AnimatePresence initial={false}>
                {selectedLogId && (
                    <motion.div
                        layout
                        initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, x: 24 }}
                        animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, x: 0 }}
                        exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, x: 24 }}
                        transition={messagePreset.transition}
                        className="flex-1 min-w-[420px] flex flex-col bg-panel border border-indigo-500/20 rounded-2xl overflow-hidden shadow-2xl"
                    >
                        {selectedLog && (
                            <DetailPane
                                log={selectedLog}
                                formattedMessage={formattedMessagesByLogId.get(selectedLog.id)}
                                commandArtifacts={selectedCommandArtifacts}
                                threadSessionDetails={threadSessionDetails}
                                subagentNameBySessionId={subagentNameBySessionId}
                                onOpenArtifacts={() => onShowLinked('artifacts', selectedLog.id)}
                            />
                        )}
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Pane 3: Metadata Details (Far Right) - Smaller fixed-ish width */}
            <div className="w-[260px] min-w-[220px] max-w-[300px] flex flex-col gap-5 overflow-y-auto pb-4 shrink-0">
                {/* Key Metadata */}
                {(primaryFeatureLink || session.sessionMetadata) && (
                    <div className="bg-panel border border-emerald-500/30 rounded-2xl p-5 shadow-sm space-y-3">
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
                                            <div className="text-panel-foreground font-mono text-[11px] break-words">{field.value}</div>
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
                <div className="bg-panel border border-panel-border rounded-2xl p-5 shadow-sm">
                    <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-4">Forensics</h3>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-xs text-muted-foreground"><Clock size={14} /> Duration</div>
                            <span className="text-xs font-mono text-panel-foreground">{session.durationSeconds}s</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-xs text-muted-foreground"><Database size={14} /> Observed Workload</div>
                            <span className="text-xs font-mono text-panel-foreground">{formatTokenCount(resolveTokenMetrics(session).workloadTokens)}</span>
                        </div>
                        {session.currentContextTokens && session.contextWindowSize ? (
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground"><Layers size={14} /> Current Context</div>
                                <span className="text-xs font-mono text-cyan-300">{contextSummaryLabel(session)}</span>
                            </div>
                        ) : null}
                        {resolveTokenMetrics(session).cacheInputTokens > 0 && (
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground"><Zap size={14} /> Cache Input</div>
                                <span className="text-xs font-mono text-cyan-300">
                                    {formatTokenCount(resolveTokenMetrics(session).cacheInputTokens)} ({formatPercent(resolveTokenMetrics(session).cacheShare, 0)})
                                </span>
                            </div>
                        )}
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-xs text-muted-foreground"><Activity size={14} /> Cost Source</div>
                            <span className="text-[10px] text-foreground">{costSummaryLabel(session)}</span>
                        </div>
                        {session.currentContextTokens && (
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground"><RefreshCw size={14} /> Context Signal</div>
                                <span className="text-[10px] text-muted-foreground">{formatContextMeasurementSource(session.contextMeasurementSource)}</span>
                            </div>
                        )}
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-xs text-muted-foreground"><Code size={14} /> Base Model</div>
                            <ModelBadge
                                raw={session.model}
                                displayName={session.modelDisplayName}
                                provider={session.modelProvider}
                                family={session.modelFamily}
                                version={session.modelVersion}
                                className="max-w-[160px] truncate"
                            />
                        </div>
                        <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2 text-xs text-muted-foreground"><Cpu size={14} /> Platform</div>
                            <span
                                className="text-[10px] font-mono text-amber-300 truncate max-w-[140px]"
                                title={`${platformType}${latestPlatformVersion ? ` ${latestPlatformVersion}` : ''}`}
                            >
                                {latestPlatformVersion ? `${platformType} ${latestPlatformVersion}` : platformType}
                            </span>
                        </div>
                        {platformVersions.length > 1 && (
                            <div className="text-[10px] text-muted-foreground pt-1 border-t border-panel-border/70">
                                {platformVersions.length} versions seen in this session
                            </div>
                        )}
                        {platformVersionTransitions.length > 0 && (
                            <div className="pt-2 border-t border-panel-border/70 space-y-1.5">
                                <div className="text-[9px] uppercase tracking-wider text-muted-foreground">Version Changes</div>
                                {platformVersionTransitions.map((transition, idx) => (
                                    <div key={`${transition.timestamp}-${idx}`} className="text-[10px] font-mono text-foreground">
                                        <span className="text-muted-foreground">{formatTimeAgo(transition.timestamp)}:</span>{' '}
                                        {transition.fromVersion} {'->'} {transition.toVersion}
                                    </div>
                                ))}
                            </div>
                        )}
                        <div className="pt-2 border-t border-panel-border/70 space-y-2">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground"><Bot size={14} /> Thinking</div>
                                <span className="text-[10px] font-mono text-fuchsia-300">{thinkingLevel}</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground"><Terminal size={14} /> Request IDs</div>
                                <span className="text-[10px] font-mono text-panel-foreground">{requestIds.length}</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground"><Scroll size={14} /> Queue Ops</div>
                                <span className="text-[10px] font-mono text-panel-foreground">{queueOperations.length}</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground"><Activity size={14} /> Waiting Tasks</div>
                                <span className={`text-[10px] font-mono ${waitingForTaskCount > 0 ? 'text-amber-300' : 'text-panel-foreground'}`}>{waitingForTaskCount}</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground"><Database size={14} /> Resources</div>
                                <span className="text-[10px] font-mono text-panel-foreground">{resourceObservationCount}</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground"><Users size={14} /> Subagents</div>
                                <span className="text-[10px] font-mono text-panel-foreground">{subagentStartCount}</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground"><HardDrive size={14} /> Sidecars</div>
                                <span className="text-[10px] font-mono text-panel-foreground" title={`Todos ${todosCount} · Tasks ${tasksCount} · Team ${teamMessagesCount} · ToolResults ${toolResultFileCount}`}>
                                    {todosCount}/{tasksCount}/{teamMessagesCount}/{toolResultFileCount}
                                </span>
                            </div>
                            {(toolResultFileCount > 0 || toolResultTotalBytes > 0) && (
                                <div className="text-[10px] text-sky-300 font-mono">
                                    Tool results: {(toolResultTotalBytes / (1024 * 1024)).toFixed(2)} MB
                                </div>
                            )}
                            {telemetryMcpServerCount > 0 && (
                                <div className="text-[10px] text-emerald-300 font-mono">
                                    MCP servers configured: {telemetryMcpServerCount}
                                </div>
                            )}
                            {teamUnreadCount > 0 && (
                                <div className="text-[10px] text-amber-300 font-mono">Team unread: {teamUnreadCount}</div>
                            )}
                            {permissionModes.length > 0 && (
                                <div className="pt-1">
                                    <div className="text-[9px] uppercase tracking-wider text-muted-foreground mb-1">Permission Modes</div>
                                    <div className="flex flex-wrap gap-1">
                                        {permissionModes.slice(0, 3).map(mode => (
                                            <span key={mode} className="text-[9px] px-1.5 py-0.5 rounded border border-panel-border text-foreground font-mono">
                                                {mode}
                                            </span>
                                        ))}
                                        {permissionModes.length > 3 && (
                                            <span className="text-[9px] px-1.5 py-0.5 rounded border border-panel-border text-muted-foreground">
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
                    <div className="bg-panel border border-panel-border rounded-2xl p-5">
                        <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-4">Version Control</h3>
                        <div className="space-y-4">
                            {displayedCommitHashes.length > 0 && (
                                <div className="group">
                                    <div className="text-[9px] text-muted-foreground uppercase font-bold mb-1 group-hover:text-muted-foreground transition-colors">
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
                                            <span className="text-[10px] font-mono text-muted-foreground">
                                                +{hiddenCommitCount} more
                                            </span>
                                        )}
                                    </div>
                                </div>
                            )}
                            {session.gitBranch && session.gitBranch.trim() && (
                                <div className="group">
                                    <div className="text-[9px] text-muted-foreground uppercase font-bold mb-1">Branch</div>
                                    <div className="flex items-center gap-2 text-xs font-mono text-foreground">
                                        <GitBranch size={14} className="text-muted-foreground" /> {session.gitBranch}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Tool Breakdown */}
                <div className="bg-panel border border-panel-border rounded-2xl p-5 flex-1 shadow-sm">
                    <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-4">Tool Efficiency</h3>
                    <div className="space-y-5">
                        {session.toolsUsed.map(tool => (
                            <div key={tool.name} className="space-y-1.5">
                                <div className="flex justify-between items-center text-[11px] font-mono">
                                    <span className="text-muted-foreground">{tool.name}</span>
                                    <span className="text-foreground font-bold">{tool.count}</span>
                                </div>
                                <div className="w-full bg-surface-overlay h-1.5 rounded-full overflow-hidden border border-panel-border/60">
                                    <div
                                        className={`h-full transition-all duration-1000 ${tool.successRate > 0.9 ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.3)]' : 'bg-amber-500'}`}
                                        style={{ width: `${tool.successRate * 100}%` }}
                                    />
                                </div>
                                <div className="flex justify-end">
                                    <span className="text-[9px] text-muted-foreground font-mono">{(tool.successRate * 100).toFixed(0)}% SR</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Forks and Threads */}
                <div className="bg-panel border border-panel-border rounded-2xl p-5 shadow-sm space-y-4">
                    <div>
                        <h3 className="text-xs font-bold text-cyan-300 uppercase tracking-widest mb-3">Forks</h3>
                        <div className="space-y-2 max-h-56 overflow-y-auto">
                            {!parentForkLink && directForkLinks.length === 0 && siblingForkLinks.length === 0 && (session.forks || []).length === 0 && (
                                <div className="text-xs text-muted-foreground">No related forks found.</div>
                            )}
                            {parentForkLink && (
                                <button
                                    onClick={() => onOpenThread(parentForkLink.id)}
                                    className="w-full text-left p-2 rounded-lg border border-cyan-500/25 bg-cyan-500/5 hover:border-cyan-400/50 transition-colors"
                                >
                                    <div className="text-[10px] uppercase tracking-wider text-cyan-300/80">Parent</div>
                                    <div className="text-[11px] font-mono text-cyan-200 truncate">{parentForkLink.id}</div>
                                    <div className="text-[10px] text-cyan-100/80 mt-1">{getThreadDisplayName(parentForkLink, subagentNameBySessionId)}</div>
                                </button>
                            )}
                            {directForkLinks.map(thread => {
                                const summary = forkSummaryBySessionId.get(thread.id);
                                return (
                                    <button
                                        key={`fork-child-${thread.id}`}
                                        onClick={() => onOpenThread(thread.id)}
                                        className="w-full text-left p-2 rounded-lg border border-cyan-500/25 bg-cyan-500/5 hover:border-cyan-400/50 transition-colors"
                                    >
                                        <div className="text-[10px] uppercase tracking-wider text-cyan-300/80">Child Fork</div>
                                        <div className="text-[11px] font-mono text-cyan-200 truncate">{thread.id}</div>
                                        <div className="text-[10px] text-cyan-100/80 mt-1">{summary?.forkPointPreview || getThreadDisplayName(thread, subagentNameBySessionId)}</div>
                                    </button>
                                );
                            })}
                            {siblingForkLinks.map(thread => (
                                <button
                                    key={`fork-sibling-${thread.id}`}
                                    onClick={() => onOpenThread(thread.id)}
                                    className="w-full text-left p-2 rounded-lg border border-cyan-500/25 bg-cyan-500/5 hover:border-cyan-400/50 transition-colors"
                                >
                                    <div className="text-[10px] uppercase tracking-wider text-cyan-300/80">Sibling Fork</div>
                                    <div className="text-[11px] font-mono text-cyan-200 truncate">{thread.id}</div>
                                    <div className="text-[10px] text-cyan-100/80 mt-1">{getThreadDisplayName(thread, subagentNameBySessionId)}</div>
                                </button>
                            ))}
                            {(session.forks || []).map(summary => {
                                if (threadLinks.some(thread => thread.id === summary.sessionId)) {
                                    return null;
                                }
                                return (
                                    <button
                                        key={`fork-summary-${summary.sessionId}`}
                                        onClick={() => onOpenThread(summary.sessionId)}
                                        className="w-full text-left p-2 rounded-lg border border-cyan-500/25 bg-cyan-500/5 hover:border-cyan-400/50 transition-colors"
                                    >
                                        <div className="text-[10px] uppercase tracking-wider text-cyan-300/80">Fork</div>
                                        <div className="text-[11px] font-mono text-cyan-200 truncate">{summary.sessionId}</div>
                                        <div className="text-[10px] text-cyan-100/80 mt-1">{summary.forkPointPreview || summary.label || 'Fork branch'}</div>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    <div>
                        <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-3">Linked Sub-Threads</h3>
                        <div className="space-y-2 max-h-56 overflow-y-auto">
                            {linkedSubthreads.length === 0 && (
                                <div className="text-xs text-muted-foreground">No linked sub-threads found.</div>
                            )}
                            {linkedSubthreads.map(thread => (
                                <button
                                    key={thread.id}
                                    onClick={() => onOpenThread(thread.id)}
                                    className="w-full text-left p-2 rounded-lg border border-panel-border bg-surface-overlay hover:border-indigo-500/40 transition-colors"
                                >
                                    <div className="text-[11px] font-mono text-indigo-300 truncate">{thread.id}</div>
                                    <div className="text-[10px] text-muted-foreground mt-1">
                                        {getThreadDisplayName(thread, subagentNameBySessionId)}
                                    </div>
                                </button>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export const SessionFeaturesView: React.FC<{
    currentSessionId: string;
    linkedFeatures: SessionFeatureLink[];
    linkedFeatureDetailsById: Record<string, Feature>;
    availableFeatures: Feature[];
    taskArtifacts: Array<{
        taskId: string;
        normalizedTaskId: string;
    }>;
    loadingFeatureDetails: boolean;
    linkMutationInFlight: boolean;
    linkMutationError: string | null;
    onSetPrimaryFeature: (featureInput: string) => Promise<boolean>;
    onAddRelatedFeature: (featureInput: string) => Promise<boolean>;
    onRemoveLinkedFeature: (featureId: string) => Promise<void>;
    onOpenFeature: (featureId: string) => void;
    onOpenSession: (sessionId: string) => void;
}> = ({
    currentSessionId,
    linkedFeatures,
    linkedFeatureDetailsById,
    availableFeatures,
    taskArtifacts,
    loadingFeatureDetails,
    linkMutationInFlight,
    linkMutationError,
    onSetPrimaryFeature,
    onAddRelatedFeature,
    onRemoveLinkedFeature,
    onOpenFeature,
    onOpenSession,
}) => {
    const grouped = useMemo(() => {
        const primary = linkedFeatures.filter(feature => feature.isPrimaryLink);
        const related = linkedFeatures.filter(feature => !feature.isPrimaryLink);
        return { primary, related };
    }, [linkedFeatures]);
    const [expandedMainThreadsByFeatureId, setExpandedMainThreadsByFeatureId] = useState<Set<string>>(new Set());
    const [mainThreadSessionsByFeatureId, setMainThreadSessionsByFeatureId] = useState<Record<string, LinkedFeatureSessionDTO[]>>({});
    // P4-007: per-feature pagination cursors for the paginated session client
    const [mainThreadSessionsHasMoreByFeatureId, setMainThreadSessionsHasMoreByFeatureId] = useState<Record<string, boolean>>({});
    const [mainThreadSessionsNextOffsetByFeatureId, setMainThreadSessionsNextOffsetByFeatureId] = useState<Record<string, number>>({});
    const [mainThreadSessionsLoadingByFeatureId, setMainThreadSessionsLoadingByFeatureId] = useState<Record<string, boolean>>({});
    const [pendingFeatureInput, setPendingFeatureInput] = useState('');
    const featureInputListId = useMemo(
        () => `session-feature-options-${currentSessionId.replace(/[^a-zA-Z0-9_-]/g, '-')}`,
        [currentSessionId]
    );

    const handleSetPrimary = useCallback(() => {
        if (!pendingFeatureInput.trim()) return;
        void onSetPrimaryFeature(pendingFeatureInput).then(success => {
            if (success) setPendingFeatureInput('');
        });
    }, [onSetPrimaryFeature, pendingFeatureInput]);

    const handleAddRelated = useCallback(() => {
        if (!pendingFeatureInput.trim()) return;
        void onAddRelatedFeature(pendingFeatureInput).then(success => {
            if (success) setPendingFeatureInput('');
        });
    }, [onAddRelatedFeature, pendingFeatureInput]);

    // P4-007: replaced getLegacyFeatureLinkedSessions fan-out with paginated
    // getFeatureLinkedSessionPage. Each feature's sessions are fetched on-demand
    // when the user expands the "Related Main-Thread Sessions" accordion, not eagerly.
    const loadRelatedMainThreadSessions = useCallback(async (featureId: string, append = false) => {
        if (!featureId) return;
        if (!append && mainThreadSessionsByFeatureId[featureId]) return;
        if (mainThreadSessionsLoadingByFeatureId[featureId]) return;

        const nextOffset = append ? (mainThreadSessionsNextOffsetByFeatureId[featureId] ?? 0) : 0;
        setMainThreadSessionsLoadingByFeatureId(prev => ({ ...prev, [featureId]: true }));
        try {
            const page = await getFeatureLinkedSessionPage(featureId, { limit: 20, offset: nextOffset });
            const normalizedCurrentId = currentSessionId.trim();
            const mainThreads = (page.items || [])
                .filter(session => !session?.isSubthread)
                .filter(session => String(session?.sessionId || '').trim() !== normalizedCurrentId);

            setMainThreadSessionsByFeatureId(prev => ({
                ...prev,
                [featureId]: append ? [...(prev[featureId] || []), ...mainThreads] : mainThreads,
            }));
            setMainThreadSessionsHasMoreByFeatureId(prev => ({ ...prev, [featureId]: page.hasMore }));
            setMainThreadSessionsNextOffsetByFeatureId(prev => ({
                ...prev,
                [featureId]: nextOffset + mainThreads.length,
            }));
        } catch (error) {
            console.error(`Failed to load related main-thread sessions for feature ${featureId}:`, error);
            if (!append) setMainThreadSessionsByFeatureId(prev => ({ ...prev, [featureId]: [] }));
        } finally {
            setMainThreadSessionsLoadingByFeatureId(prev => ({ ...prev, [featureId]: false }));
        }
    }, [currentSessionId, mainThreadSessionsByFeatureId, mainThreadSessionsLoadingByFeatureId, mainThreadSessionsNextOffsetByFeatureId]);

    const toggleRelatedMainThreadSessions = useCallback((featureId: string) => {
        const isExpanded = expandedMainThreadsByFeatureId.has(featureId);
        if (!isExpanded && !mainThreadSessionsByFeatureId[featureId] && !mainThreadSessionsLoadingByFeatureId[featureId]) {
            void loadRelatedMainThreadSessions(featureId);
        }
        setExpandedMainThreadsByFeatureId(prev => {
            const next = new Set(prev);
            if (next.has(featureId)) next.delete(featureId);
            else next.add(featureId);
            return next;
        });
    }, [expandedMainThreadsByFeatureId, loadRelatedMainThreadSessions, mainThreadSessionsByFeatureId, mainThreadSessionsLoadingByFeatureId]);

    const taskHierarchy = useMemo(() => {
        if (taskArtifacts.length === 0) return [];
        const taskIdSet = new Set(taskArtifacts.map(task => task.normalizedTaskId));

        const mapped = linkedFeatures.map(featureLink => {
            const featureDetail = linkedFeatureDetailsById[featureLink.featureId];
            if (!featureDetail) return null;

            const phaseOrderByKey = new Map<string, number>();
            (featureDetail.phases || []).forEach((phase, index) => {
                const key = `${phase.id || ''}::${phase.phase || ''}`;
                phaseOrderByKey.set(key, index);
            });

            const bestTaskByIdentity = new Map<string, { task: ProjectTask; phase: Feature['phases'][number] }>();
            (featureDetail.phases || []).forEach(phase => {
                const phaseTasks = dedupePhaseTasks(phase.tasks || []);
                phaseTasks.forEach(task => {
                    const identity = getTaskIdentity(task);
                    if (!identity) return;

                    const existing = bestTaskByIdentity.get(identity);
                    if (!existing) {
                        bestTaskByIdentity.set(identity, { task, phase });
                        return;
                    }

                    const preferred = pickFresherTask(existing.task, task);
                    if (preferred === existing.task) return;
                    bestTaskByIdentity.set(identity, { task: preferred, phase });
                });
            });

            const phasesByKey = new Map<string, { phase: Feature['phases'][number]; tasks: ProjectTask[] }>();
            bestTaskByIdentity.forEach(({ task, phase }) => {
                const normalizedTaskId = String(task.id || '').trim().toLowerCase();
                if (!normalizedTaskId || !taskIdSet.has(normalizedTaskId)) return;

                const key = `${phase.id || ''}::${phase.phase || ''}`;
                const existing = phasesByKey.get(key);
                if (existing) {
                    existing.tasks.push(task);
                } else {
                    phasesByKey.set(key, { phase, tasks: [task] });
                }
            });

            const phases = Array.from(phasesByKey.values())
                .map(entry => ({
                    phase: entry.phase,
                    tasks: entry.tasks.sort((a, b) => String(a.id || '').localeCompare(String(b.id || ''))),
                }))
                .sort((a, b) => {
                    const aKey = `${a.phase.id || ''}::${a.phase.phase || ''}`;
                    const bKey = `${b.phase.id || ''}::${b.phase.phase || ''}`;
                    return (phaseOrderByKey.get(aKey) ?? Number.MAX_SAFE_INTEGER) - (phaseOrderByKey.get(bKey) ?? Number.MAX_SAFE_INTEGER);
                });

            if (phases.length === 0) return null;
            return { featureLink, phases };
        }).filter(Boolean) as Array<{
            featureLink: SessionFeatureLink;
            phases: Array<{ phase: Feature['phases'][number]; tasks: ProjectTask[] }>;
        }>;

        return mapped.sort((a, b) => {
            if (a.featureLink.isPrimaryLink !== b.featureLink.isPrimaryLink) {
                return a.featureLink.isPrimaryLink ? -1 : 1;
            }
            return b.featureLink.confidence - a.featureLink.confidence;
        });
    }, [linkedFeatureDetailsById, linkedFeatures, taskArtifacts]);

    const unresolvedTaskIds = useMemo(() => {
        const resolved = new Set<string>();
        taskHierarchy.forEach(entry => {
            entry.phases.forEach(phaseEntry => {
                phaseEntry.tasks.forEach(task => {
                    const taskId = String(task.id || '').trim().toLowerCase();
                    if (taskId) resolved.add(taskId);
                });
            });
        });
        return taskArtifacts
            .filter(task => !resolved.has(task.normalizedTaskId))
            .map(task => task.taskId)
            .sort((a, b) => a.localeCompare(b));
    }, [taskArtifacts, taskHierarchy]);

    const renderFeatureCard = (feature: SessionFeatureLink) => {
        const pct = feature.totalTasks > 0
            ? Math.round((feature.completedTasks / feature.totalTasks) * 100)
            : 0;
        const isExpanded = expandedMainThreadsByFeatureId.has(feature.featureId);
        const mainThreads = mainThreadSessionsByFeatureId[feature.featureId] || [];
        const isLoadingMainThreads = Boolean(mainThreadSessionsLoadingByFeatureId[feature.featureId]);
        // P4-007: pagination state for this feature's session page
        const hasMoreMainThreads = Boolean(mainThreadSessionsHasMoreByFeatureId[feature.featureId]);
        return (
            <div key={feature.featureId} className="group/feature-link bg-panel border border-panel-border rounded-xl p-4">
                <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                        <div className="text-sm font-semibold text-panel-foreground truncate">
                            {feature.featureName || feature.featureId}
                        </div>
                        <button
                            onClick={() => onOpenFeature(feature.featureId)}
                            className="text-[11px] font-mono text-indigo-300 hover:text-indigo-200 transition-colors"
                        >
                            {feature.featureId}
                        </button>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                        <span className="text-[10px] px-1.5 py-0.5 rounded border border-indigo-500/30 bg-indigo-500/10 text-indigo-300">
                            {Math.round(feature.confidence * 100)}% confidence
                        </span>
                        <button
                            type="button"
                            onClick={() => void onRemoveLinkedFeature(feature.featureId)}
                            disabled={linkMutationInFlight}
                            className="opacity-0 group-hover/feature-link:opacity-100 disabled:opacity-40 text-muted-foreground hover:text-rose-300 transition-colors p-1 rounded border border-panel-border hover:border-rose-500/50 bg-surface-overlay/80"
                            title="Remove linked feature"
                            aria-label={`Remove linked feature ${feature.featureName || feature.featureId}`}
                        >
                            <X size={12} />
                        </button>
                    </div>
                </div>

                <div className="mt-3 flex items-center gap-2 text-[10px]">
                    <span className={`px-1.5 py-0.5 rounded border ${feature.isPrimaryLink ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10' : 'border-panel-border text-muted-foreground bg-surface-muted/70'}`}>
                        {feature.isPrimaryLink ? 'Primary' : 'Related'}
                    </span>
                    {feature.featureStatus && (
                        <span className="px-1.5 py-0.5 rounded border border-panel-border text-foreground bg-surface-muted/70 capitalize">
                            {feature.featureStatus}
                        </span>
                    )}
                    {feature.featureCategory && (
                        <span className="px-1.5 py-0.5 rounded border border-purple-500/30 text-purple-300 bg-purple-500/10 capitalize">
                            {feature.featureCategory}
                        </span>
                    )}
                    {feature.linkStrategy && (
                        <span className="px-1.5 py-0.5 rounded border border-panel-border text-muted-foreground bg-surface-muted/70">
                            {formatSessionReason(feature.linkStrategy)}
                        </span>
                    )}
                </div>

                {feature.reasons.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
                        {feature.reasons.slice(0, 5).map(reason => (
                            <span key={`${feature.featureId}-${reason}`} className="px-1.5 py-0.5 rounded border border-panel-border bg-surface-muted/70">
                                {formatSessionReason(reason)}
                            </span>
                        ))}
                    </div>
                )}

                <div className="mt-3">
                    <div className="flex items-center justify-between text-[10px] text-muted-foreground mb-1">
                        <span>Feature Progress</span>
                        <span className="font-mono">{feature.completedTasks}/{feature.totalTasks}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-surface-muted overflow-hidden">
                        <div
                            className="h-full rounded-full bg-indigo-500"
                            style={{ width: `${pct}%` }}
                        />
                    </div>
                </div>

                <div className="mt-3 pt-3 border-t border-panel-border/90">
                    <button
                        onClick={() => toggleRelatedMainThreadSessions(feature.featureId)}
                        className="w-full inline-flex items-center justify-between rounded-lg border border-panel-border bg-surface-overlay/70 px-2.5 py-2 text-[11px] text-foreground hover:border-indigo-500/40 hover:text-indigo-200 transition-colors"
                    >
                        <span className="inline-flex items-center gap-1.5">
                            {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                            Related Main-Thread Sessions
                        </span>
                        <span className="font-mono text-[10px] text-muted-foreground">
                            {isLoadingMainThreads ? '...' : mainThreads.length}
                        </span>
                    </button>

                    {isExpanded && (
                        <div className="mt-2 space-y-1.5">
                            {isLoadingMainThreads && (
                                <div className="rounded-md border border-panel-border bg-surface-overlay/70 px-2.5 py-2 text-[11px] text-muted-foreground">
                                    Loading related main-thread sessions...
                                </div>
                            )}
                            {!isLoadingMainThreads && mainThreads.length === 0 && (
                                <div className="rounded-md border border-dashed border-panel-border bg-surface-overlay/70 px-2.5 py-2 text-[11px] text-muted-foreground">
                                    No other main-thread sessions are linked to this feature yet.
                                </div>
                            )}
                            {!isLoadingMainThreads && mainThreads.map(session => (
                                <button
                                    key={`${feature.featureId}-${session.sessionId}`}
                                    onClick={() => onOpenSession(session.sessionId)}
                                    className="w-full text-left rounded-md border border-panel-border bg-surface-overlay/70 px-2.5 py-2 hover:border-indigo-500/40 transition-colors"
                                >
                                    <div className="flex items-center justify-between gap-2">
                                        <div className="truncate text-[11px] text-indigo-300 font-mono">{session.sessionId}</div>
                                    </div>
                                    <div className="truncate text-[11px] text-foreground mt-0.5">
                                        {session.title || session.sessionId}
                                    </div>
                                    <div className="text-[10px] text-muted-foreground mt-1">
                                        {(session.workflowType || 'session')} · {session.startedAt ? new Date(session.startedAt).toLocaleString() : 'Unknown start'}
                                    </div>
                                </button>
                            ))}
                            {/* P4-007: load-more pagination control */}
                            {!isLoadingMainThreads && hasMoreMainThreads && (
                                <button
                                    type="button"
                                    onClick={() => void loadRelatedMainThreadSessions(feature.featureId, true)}
                                    className="w-full rounded-md border border-dashed border-indigo-500/30 bg-surface-overlay/50 px-2.5 py-2 text-[11px] text-indigo-300 hover:bg-indigo-500/10 transition-colors"
                                >
                                    Load more sessions
                                </button>
                            )}
                            {isLoadingMainThreads && mainThreads.length > 0 && (
                                <div className="text-[11px] text-muted-foreground text-center py-1">Loading more...</div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        );
    };

    return (
        <div className="h-full overflow-y-auto pr-1 space-y-5">
            <div className="bg-panel border border-panel-border rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                    <div>
                        <div className="text-xs font-bold uppercase tracking-wider text-indigo-300">Manage Feature Links</div>
                        <p className="text-[11px] text-muted-foreground mt-1">Set primary, add related, or remove links directly from this session.</p>
                    </div>
                    <div className="text-[10px] text-muted-foreground font-mono">{linkedFeatures.length} linked</div>
                </div>
                <div className="flex flex-col md:flex-row gap-2">
                    <input
                        type="text"
                        value={pendingFeatureInput}
                        onChange={event => setPendingFeatureInput(event.target.value)}
                        onKeyDown={event => {
                            if (event.key === 'Enter') {
                                event.preventDefault();
                                handleAddRelated();
                            }
                        }}
                        list={featureInputListId}
                        placeholder="Feature ID or exact feature name"
                        className="flex-1 text-xs rounded-lg border border-panel-border bg-surface-overlay/80 px-2.5 py-2 text-panel-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-focus/60"
                    />
                    <datalist id={featureInputListId}>
                        {availableFeatures.map(feature => (
                            <option key={feature.id} value={feature.id}>
                                {feature.name || feature.id}
                            </option>
                        ))}
                    </datalist>
                    <button
                        type="button"
                        onClick={handleSetPrimary}
                        disabled={linkMutationInFlight || !pendingFeatureInput.trim()}
                        className="text-xs font-semibold rounded-lg px-3 py-2 border border-emerald-500/40 text-emerald-200 bg-emerald-500/10 hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        Set Primary
                    </button>
                    <button
                        type="button"
                        onClick={handleAddRelated}
                        disabled={linkMutationInFlight || !pendingFeatureInput.trim()}
                        className="text-xs font-semibold rounded-lg px-3 py-2 border border-indigo-500/40 text-indigo-200 bg-indigo-500/10 hover:bg-indigo-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        Add Related
                    </button>
                </div>
                {linkMutationError && (
                    <div className="text-[11px] text-rose-300 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2.5 py-2">
                        {linkMutationError}
                    </div>
                )}
            </div>

            {linkedFeatures.length === 0 && taskArtifacts.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-muted-foreground py-10">
                    <Box size={42} className="mb-3 opacity-30" />
                    <p className="text-sm">No linked features found for this session.</p>
                    <p className="text-xs mt-1 text-muted-foreground">Use the controls above to set a primary feature or add related ones.</p>
                </div>
            ) : (
                <>
                    {linkedFeatures.length > 0 && (
                        <>
                            <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
                                <div className="flex items-center justify-between">
                                    <div className="text-xs font-bold uppercase tracking-wider text-emerald-300">Primary Feature Links</div>
                                    <div className="text-[11px] text-emerald-200/80">{grouped.primary.length}</div>
                                </div>
                                <p className="text-[11px] text-emerald-200/70 mt-1">Likely primary features this session directly worked on.</p>
                            </div>

                            {grouped.primary.length > 0 && grouped.primary.map(renderFeatureCard)}
                            {grouped.primary.length === 0 && (
                                <div className="text-xs text-muted-foreground border border-dashed border-panel-border rounded-lg p-4">
                                    No primary links yet. Related feature matches are shown below.
                                </div>
                            )}

                            {grouped.related.length > 0 && (
                                <div className="space-y-3 pt-2">
                                    <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Related Feature Links</div>
                                    {grouped.related.map(renderFeatureCard)}
                                </div>
                            )}
                        </>
                    )}

                    <div className="space-y-3 pt-2">
                        <div className="bg-indigo-500/5 border border-indigo-500/20 rounded-lg p-3">
                            <div className="flex items-center justify-between">
                                <div className="text-xs font-bold uppercase tracking-wider text-indigo-300">Task Links (Feature &gt; Phase &gt; Tasks)</div>
                                <div className="text-[11px] text-indigo-200/80">{taskArtifacts.length}</div>
                            </div>
                            <p className="text-[11px] text-indigo-200/70 mt-1">Task artifacts are mapped to their parent feature and phase using feature execution data.</p>
                        </div>

                        {taskArtifacts.length === 0 && (
                            <div className="text-xs text-muted-foreground border border-dashed border-panel-border rounded-lg p-4">
                                No task artifacts detected for this session.
                            </div>
                        )}

                        {taskArtifacts.length > 0 && loadingFeatureDetails && (
                            <div className="text-xs text-muted-foreground border border-panel-border rounded-lg p-4">
                                Loading feature phase/task details...
                            </div>
                        )}

                        {taskArtifacts.length > 0 && !loadingFeatureDetails && taskHierarchy.length === 0 && (
                            <div className="text-xs text-muted-foreground border border-dashed border-panel-border rounded-lg p-4">
                                Task artifacts were found, but none mapped to linked feature phases yet.
                            </div>
                        )}

                        {taskHierarchy.map(entry => (
                            <div key={`tasks-${entry.featureLink.featureId}`} className="bg-panel border border-panel-border rounded-xl p-4 space-y-3">
                                <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                        <div className="text-sm font-semibold text-panel-foreground truncate">
                                            {entry.featureLink.featureName || entry.featureLink.featureId}
                                        </div>
                                        <button
                                            onClick={() => onOpenFeature(entry.featureLink.featureId)}
                                            className="text-[11px] font-mono text-indigo-300 hover:text-indigo-200 transition-colors"
                                        >
                                            {entry.featureLink.featureId}
                                        </button>
                                    </div>
                                    <span className="text-[10px] px-1.5 py-0.5 rounded border border-indigo-500/30 bg-indigo-500/10 text-indigo-300">
                                        {entry.phases.reduce((sum, phaseEntry) => sum + phaseEntry.tasks.length, 0)} tasks
                                    </span>
                                </div>

                                <div className="space-y-2">
                                    {entry.phases.map(phaseEntry => (
                                        <div key={`${entry.featureLink.featureId}-${phaseEntry.phase.id || phaseEntry.phase.phase}`} className="rounded-lg border border-panel-border bg-surface-overlay/70 p-3">
                                            <div className="flex items-center justify-between gap-2">
                                                <div className="text-xs font-semibold text-panel-foreground">
                                                    Phase {phaseEntry.phase.phase}: {phaseEntry.phase.title || 'Untitled'}
                                                </div>
                                                <div className="text-[10px] text-muted-foreground font-mono">
                                                    {phaseEntry.phase.completedTasks}/{phaseEntry.phase.totalTasks}
                                                </div>
                                            </div>
                                            <div className="mt-2 space-y-1.5">
                                                {phaseEntry.tasks.map(task => {
                                                    const statusStyle = getFeatureStatusStyle(task.status || 'backlog');
                                                    return (
                                                        <div key={`${phaseEntry.phase.id || phaseEntry.phase.phase}-${task.id}`} className="flex items-center gap-2 text-xs rounded bg-panel/70 border border-panel-border px-2 py-1.5">
                                                            <span className="font-mono text-muted-foreground shrink-0">{task.id}</span>
                                                            <span className="text-foreground truncate">{task.title}</span>
                                                            <span className={`ml-auto text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${statusStyle.color}`}>
                                                                {statusStyle.label}
                                                            </span>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ))}

                        {unresolvedTaskIds.length > 0 && !loadingFeatureDetails && (
                            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
                                <div className="text-[11px] text-amber-300 font-semibold uppercase tracking-wider">Unmapped Task IDs</div>
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                    {unresolvedTaskIds.map(taskId => (
                                        <span key={`unmapped-${taskId}`} className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-amber-500/40 text-amber-200">
                                            {taskId}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
};
