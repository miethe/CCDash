import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { AnimatePresence, motion } from 'framer-motion';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useData, type SessionFilters } from '../contexts/DataContext';
import { useModelColors } from '../contexts/ModelColorsContext';
import { AgentSession, SessionLog, LogType, SessionArtifact, PlanDocument, SessionActivityItem, SessionFileAggregateRow, SessionFileUpdate, Feature, ProjectTask, FeatureExecutionSessionLink, LiveAgentActivity, LiveTranscriptState, SessionTranscriptAppendPayload } from '../types';
import { Clock, Database, Terminal, Search, Edit3, GitCommit, GitBranch, ArrowLeft, Bot, Activity, Archive, PlayCircle, Cpu, Zap, Box, ChevronRight, MessageSquare, Code, ChevronDown, Calendar, BarChart2, PieChart as PieChartIcon, Users, TrendingUp, ShieldAlert, FileText, ExternalLink, Link as LinkIcon, HardDrive, Scroll, Maximize2, X, MoreHorizontal, Layers, RefreshCw, LayoutGrid, TestTube2 } from 'lucide-react';
import { Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, Legend, ComposedChart, Line } from 'recharts';
import { DocumentModal } from './DocumentModal';
import { UnifiedContentViewer } from './content/UnifiedContentViewer';
import { ProjectFileViewerModal } from './content/ProjectFileViewerModal';
import { TranscriptFormattedMessage, TranscriptFormattingMappingRule, parseTranscriptMessage, getReadableTagName } from './sessionTranscriptFormatting';
import { SessionCard, SessionCardDetailSection, deriveSessionCardTitle } from './SessionCard';
import { SessionArtifactsView } from './SessionArtifactsView';
import { SidebarFiltersPortal, SidebarFiltersSection } from './SidebarFilters';
import { getFeatureStatusStyle } from './featureStatus';
import { SessionTestStatusView } from './TestVisualizer/SessionTestStatusView';
import { TranscriptMappedMessageCard, isMappedTranscriptMessageKind, mappedAccentColor, mappedTranscriptIcon } from './TranscriptMappedMessageCard';
import { TypingIndicator, getMotionPreset, useAnimatedListDiff, useReducedMotionPreference, useSmartScrollAnchor } from './animations';
import { Badge, ModelBadge, StableBadge } from './ui/badge';
import { formatModelDisplayName } from '../lib/modelIdentity';
import { getInlineContentViewerPayload, getTranscriptContentViewerPayload } from '../lib/sessionContentViewer';
import { formatPercent, formatTokenCount, resolveTokenMetrics } from '../lib/tokenMetrics';
import { contextSummaryLabel, costSummaryLabel, formatContextMeasurementSource, resolveDisplayCost } from '../lib/sessionSemantics';
import { buildSessionBlockInsights } from '../lib/sessionBlockInsights';
import { mergeSessionTranscriptAppend } from '../lib/sessionTranscriptLive';
import { isSessionBlockInsightsEnabled, isUsageAttributionEnabled } from '../services/agenticIntelligence';
import { SessionIntelligencePanel } from './session-intelligence/SessionIntelligencePanel';
import {
    isSessionLiveUpdatesEnabled,
    isSessionTranscriptAppendEnabled,
    sessionTopic,
    sessionTranscriptTopic,
    sharedLiveConnectionManager,
    type LiveConnectionStatus,
} from '../services/live';
import { getLegacyFeatureDetail, getFeatureLinkedSessionPage, type LinkedFeatureSessionDTO } from '../services/featureSurface';
import { isMemoryGuardEnabled } from '../lib/featureFlags';
import { SessionFeaturesView, TranscriptView } from './SessionInspector/TranscriptView';

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
    onOpenFile: (filePath: string, localPath?: string | null) => void;
    onOpenThread: (sessionId: string) => void;
    highlightedSourceLogId?: string | null;
}> = ({ session, threadSessions, threadSessionDetails, subagentNameBySessionId, onOpenDoc, onOpenFile, onOpenThread, highlightedSourceLogId }) => {
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
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                <Activity size={48} className="mb-4 opacity-20" />
                <p>No activity entries found for this thread family.</p>
            </div>
        );
    }

    const openRowViewer = (row: SessionActivityItem) => {
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

    const openRowFile = (row: SessionActivityItem) => {
        if (!row.localPath) return;
        window.location.href = `vscode://file/${encodeURI(row.localPath)}`;
    };

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
                        <div className="text-muted-foreground text-[11px]">{row.timestamp ? new Date(row.timestamp).toLocaleString() : '—'}</div>
                        <div>
                            <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] ${row.kind === 'file' ? 'border-blue-500/30 bg-blue-500/10 text-blue-300' : row.kind === 'artifact' ? 'border-amber-500/30 bg-amber-500/10 text-amber-300' : 'border-hover bg-surface-muted/40 text-foreground'}`}>
                                {formatAction(row.kind)}
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

const FilesView: React.FC<{
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
                            {row.actions.map(action => (
                                <span key={`${row.key}:${action}`} className={`inline-flex rounded border px-1 py-0.5 text-[10px] ${action === 'read' ? 'bg-blue-500/10 border-blue-500/30 text-blue-300' : action === 'create' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : action === 'update' ? 'bg-amber-500/10 border-amber-500/30 text-amber-300' : action === 'delete' ? 'bg-rose-500/10 border-rose-500/30 text-rose-300' : 'bg-surface-muted/40 border-hover text-foreground'}`}>
                                    {formatAction(action)}
                                </span>
                            ))}
                        </div>
                        <div className="text-foreground">{row.touchCount}</div>
                        <div className="text-foreground">{row.uniqueSessions}</div>
                        <div className="text-muted-foreground text-[11px]">{row.lastTouchedAt ? new Date(row.lastTouchedAt).toLocaleString() : '—'}</div>
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

const ArtifactDetailsModal: React.FC<{
    group: ArtifactGroup;
    onClose: () => void;
    onOpenThread: (sessionId: string) => void;
    subagentNameBySessionId: Map<string, string>;
}> = ({ group, onClose, onOpenThread, subagentNameBySessionId }) => {
    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-surface-overlay/90 backdrop-blur-sm p-4 animate-in fade-in duration-200" onClick={onClose}>
            <div className="bg-panel border border-panel-border rounded-xl w-full max-w-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]" onClick={e => e.stopPropagation()}>
                <div className="p-5 border-b border-panel-border flex justify-between items-start bg-surface-overlay">
                    <div>
                        <h3 className="text-lg font-bold text-panel-foreground">{group.title}</h3>
                        <p className="text-xs text-muted-foreground mt-1">
                            {group.type} • {group.source} • {group.artifacts.length} merged artifacts
                        </p>
                    </div>
                    <button onClick={onClose} className="text-muted-foreground hover:text-panel-foreground transition-colors">
                        <X size={20} />
                    </button>
                </div>

                <div className="p-6 space-y-6 overflow-y-auto">
                    <div className="bg-surface-overlay/80 rounded-lg border border-panel-border p-4 text-sm text-foreground">
                        {group.description || 'No artifact description available.'}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">Source Log IDs</h4>
                            <div className="flex flex-wrap gap-2">
                                {group.sourceLogIds.length === 0 && <span className="text-xs text-muted-foreground">None</span>}
                                {group.sourceLogIds.map(sourceLogId => (
                                    <span key={sourceLogId} className="text-[10px] bg-surface-muted text-muted-foreground px-2 py-0.5 rounded border border-panel-border font-mono">
                                        {sourceLogId}
                                    </span>
                                ))}
                            </div>
                        </div>
                        <div>
                            <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">Source Tools</h4>
                            <div className="flex flex-wrap gap-2">
                                {group.sourceToolNames.length === 0 && <span className="text-xs text-muted-foreground">None</span>}
                                {group.sourceToolNames.map(sourceToolName => (
                                    <span key={sourceToolName} className="text-[10px] bg-surface-muted text-muted-foreground px-2 py-0.5 rounded border border-panel-border font-mono">
                                        {sourceToolName}
                                    </span>
                                ))}
                            </div>
                        </div>
                    </div>

                    <div>
                        <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">Related Tool Calls</h4>
                        <div className="space-y-2">
                            {group.relatedToolLogs.length === 0 && (
                                <div className="text-xs text-muted-foreground">No related tool calls found.</div>
                            )}
                            {group.relatedToolLogs.map(log => (
                                <div key={log.id} className="rounded-lg border border-panel-border bg-surface-overlay p-3">
                                    <div className="flex items-center justify-between gap-3">
                                        <div className="text-sm font-mono text-panel-foreground">{log.toolCall?.name || 'tool'}</div>
                                        <div className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-bold ${log.toolCall?.status === 'error' ? 'bg-rose-500/10 text-rose-400' : 'bg-emerald-500/10 text-emerald-400'}`}>
                                            {log.toolCall?.status || 'success'}
                                        </div>
                                    </div>
                                    <div className="text-[10px] text-muted-foreground mt-1">
                                        {log.id} • {log.timestamp}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div>
                        <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">Linked Sub-agent Threads</h4>
                        <div className="space-y-2">
                            {group.linkedThreads.length === 0 && (
                                <div className="text-xs text-muted-foreground">No linked sub-agent threads found.</div>
                            )}
                            {group.linkedThreads.map(thread => (
                                <div key={thread.id} className="rounded-lg border border-panel-border bg-surface-overlay p-3 flex items-center justify-between gap-3">
                                    <div>
                                        <div className="text-sm text-indigo-300 font-mono">{thread.id}</div>
                                        <div className="text-[10px] text-muted-foreground mt-1">{getThreadDisplayName(thread, subagentNameBySessionId)}</div>
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
                        <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">Merged Artifact IDs</h4>
                        <div className="flex flex-wrap gap-2">
                            {group.artifactIds.map(id => (
                                <span key={id} className="text-[10px] bg-surface-muted text-muted-foreground px-2 py-0.5 rounded border border-panel-border font-mono">
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
                    if (log.type !== 'tool' || !isSubagentToolCallName(log.toolCall?.name)) {
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
    const toolGroupSections = useMemo(() => {
        const groupedBySection: Record<ToolGroupCategory, ArtifactGroup[]> = {
            hooks: [],
            git: [],
            tests: [],
            other: [],
        };
        for (const group of toolGroups) {
            groupedBySection[classifyToolGroup(group)].push(group);
        }
        return TOOL_GROUP_SECTION_DEFS.map(section => ({
            ...section,
            groups: groupedBySection[section.id],
        }));
    }, [toolGroups]);

    const visibleGroups = useMemo(() => {
        if (activeSubTab === 'skills') return skillGroups;
        if (activeSubTab === 'agents') return agentGroups;
        return [];
    }, [activeSubTab, agentGroups, skillGroups]);

    const hasAnyData = commandEntries.length > 0 || skillGroups.length > 0 || agentGroups.length > 0 || toolGroups.length > 0;

    const renderArtifactCard = (group: ArtifactGroup) => (
        <button
            key={group.key}
            onClick={() => setSelectedGroup(group)}
            className={`text-left bg-panel border rounded-xl p-6 hover:border-indigo-500/50 transition-all group min-w-0 overflow-hidden ${highlightedSourceLogId && group.sourceLogIds.includes(highlightedSourceLogId) ? 'border-indigo-500/50 bg-indigo-500/5' : 'border-panel-border'}`}
        >
            <div className="flex justify-between items-start gap-3 mb-4 min-w-0">
                <div className={`p-2 rounded-lg ${group.type === 'memory' ? 'bg-purple-500/10 text-purple-400' :
                    group.type === 'request_log' ? 'bg-amber-500/10 text-amber-400' :
                        'bg-blue-500/10 text-blue-400'
                    }`}>
                    {group.type === 'memory' ? <HardDrive size={20} /> :
                        group.type === 'request_log' ? <Scroll size={20} /> :
                            <Database size={20} />}
                </div>
                <span
                    className="text-[10px] bg-surface-muted text-muted-foreground px-2 py-0.5 rounded uppercase font-bold tracking-wider max-w-[9rem] truncate"
                    title={group.source}
                >
                    {group.source}
                </span>
            </div>

            <h3 className="font-bold text-panel-foreground mb-2 group-hover:text-indigo-400 transition-colors truncate" title={group.title}>
                {group.title}
            </h3>
            <p className="text-sm text-muted-foreground mb-4 line-clamp-3 break-all" title={group.description || ''}>
                {group.description}
            </p>

            <div className="flex flex-wrap gap-2 mb-4">
                <span className="text-[10px] bg-surface-muted text-muted-foreground px-2 py-0.5 rounded border border-panel-border">
                    {group.artifacts.length} merged
                </span>
                <span className="text-[10px] bg-surface-muted text-muted-foreground px-2 py-0.5 rounded border border-panel-border">
                    {group.relatedToolLogs.length} tool calls
                </span>
                <span className="text-[10px] bg-surface-muted text-muted-foreground px-2 py-0.5 rounded border border-panel-border">
                    {group.linkedThreads.length} sub-threads
                </span>
            </div>

            <div className="pt-4 border-t border-panel-border flex justify-between items-center gap-2 min-w-0">
                <span className="text-xs font-mono text-muted-foreground truncate min-w-0 max-w-[65%]" title={group.artifactIds[0]}>
                    {group.artifactIds[0]}
                </span>
                <span className="text-xs flex items-center gap-1 text-indigo-400 group-hover:text-indigo-300 shrink-0">
                    View Details <ChevronRight size={12} />
                </span>
            </div>
        </button>
    );

    if (!hasAnyData) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                <LinkIcon size={48} className="mb-4 opacity-20" />
                <p>No linked artifacts found.</p>
            </div>
        );
    }

    return (
        <>
            <div className="mb-4 flex items-center gap-2 border border-panel-border rounded-lg bg-panel p-1 w-fit">
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
                            : 'text-muted-foreground hover:text-panel-foreground'
                            }`}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>

            {activeSubTab === 'commands' && (
                <div className="space-y-3">
                    {commandEntries.length === 0 && (
                        <div className="rounded-xl border border-panel-border bg-panel/50 p-4 text-sm text-muted-foreground">
                            No command activity found.
                        </div>
                    )}
                    {commandEntries.map(entry => (
                        <div
                            key={entry.logId}
                            className={`rounded-xl border p-4 ${highlightedSourceLogId && entry.logId === highlightedSourceLogId ? 'border-indigo-500/50 bg-indigo-500/5' : 'border-panel-border bg-panel/50'}`}
                        >
                            <div className="flex items-start justify-between gap-3">
                                <div>
                                    <div className="text-[10px] uppercase tracking-wider text-emerald-300/90 font-semibold mb-1 flex items-center gap-1.5">
                                        <Terminal size={11} /> Command
                                    </div>
                                    <p className="font-mono text-sm text-panel-foreground break-all">{entry.commandName}</p>
                                    {entry.args && (
                                        <p className="mt-2 text-xs text-muted-foreground whitespace-pre-wrap break-words">{entry.args}</p>
                                    )}
                                </div>
                                <div className="text-[10px] text-muted-foreground">{new Date(entry.timestamp).toLocaleString()}</div>
                            </div>

                            <div className="mt-3 flex flex-wrap gap-1.5">
                                {entry.phases.map(phase => (
                                    <span key={`${entry.logId}-phase-${phase}`} className="text-[10px] px-1.5 py-0.5 rounded border border-indigo-500/30 bg-indigo-500/10 text-indigo-300">
                                        Phase {phase}
                                    </span>
                                ))}
                                {entry.featureSlug && (
                                    <span className="text-[10px] px-1.5 py-0.5 rounded border border-panel-border bg-surface-muted/80 text-foreground">
                                        Feature {entry.featureSlug}
                                    </span>
                                )}
                                {entry.requestId && (
                                    <span className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-300 font-mono">
                                        {entry.requestId}
                                    </span>
                                )}
                                {entry.featurePath && (
                                    <span className="text-[10px] px-1.5 py-0.5 rounded border border-panel-border bg-surface-muted/80 text-muted-foreground font-mono">
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

            {activeSubTab === 'tools' && (
                <div className="space-y-6">
                    {toolGroupSections.map(section => (
                        <section key={section.id} className="space-y-3">
                            <div className="flex items-center justify-between border-b border-panel-border pb-2">
                                <h3 className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">{section.label}</h3>
                                <span className="text-[11px] text-muted-foreground">{section.groups.length}</span>
                            </div>
                            {section.groups.length === 0 ? (
                                <div className="rounded-xl border border-panel-border bg-panel/50 p-4 text-sm text-muted-foreground">
                                    {section.emptyLabel}
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                    {section.groups.map(renderArtifactCard)}
                                </div>
                            )}
                        </section>
                    ))}
                </div>
            )}

            {activeSubTab !== 'commands' && activeSubTab !== 'tools' && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {visibleGroups.length === 0 && (
                        <div className="rounded-xl border border-panel-border bg-panel/50 p-4 text-sm text-muted-foreground md:col-span-2 lg:col-span-3">
                            No {activeSubTab} artifacts found.
                        </div>
                    )}
                    {visibleGroups.map(renderArtifactCard)}
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
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-surface-overlay/90 backdrop-blur-sm p-4 animate-in fade-in duration-200" onClick={onClose}>
            <div className="bg-panel border border-panel-border rounded-xl w-full max-w-lg shadow-2xl overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="p-5 border-b border-panel-border flex justify-between items-center bg-surface-overlay">
                    <h3 className="text-lg font-bold text-panel-foreground flex items-center gap-2">
                        <Activity size={18} className="text-indigo-500" />
                        {title}: {data.name}
                    </h3>
                    <button onClick={onClose} className="text-muted-foreground hover:text-panel-foreground transition-colors">
                        <X size={20} />
                    </button>
                </div>
                <div className="p-6 space-y-6">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-surface-muted/60 p-3 rounded-lg border border-panel-border/60">
                            <div className="text-xs text-muted-foreground uppercase font-bold mb-1">Total Interactions</div>
                            <div className="text-2xl font-mono text-white">{data.value || 0}</div>
                        </div>
                        <div className="bg-surface-muted/60 p-3 rounded-lg border border-panel-border/60">
                            <div className="text-xs text-muted-foreground uppercase font-bold mb-1">Estimated Cost</div>
                            <div className="text-2xl font-mono text-emerald-400">${(data.cost || 0).toFixed(4)}</div>
                        </div>
                    </div>

                    <div className="space-y-2">
                        <div className="flex justify-between text-sm border-b border-panel-border pb-2">
                            <span className="text-muted-foreground">Tokens Consumed</span>
                            <span className="font-mono text-panel-foreground">{(data.tokens || 0).toLocaleString()}</span>
                        </div>
                        <div className="flex justify-between text-sm border-b border-panel-border pb-2">
                            <span className="text-muted-foreground">Tools Called</span>
                            <span className="font-mono text-panel-foreground">{data.toolCount || 0}</span>
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

const tokenDeltaForLog = (log: SessionLog): number => {
    const metadata = (log.metadata || {}) as Record<string, any>;
    const inputTokens = Number(metadata.inputTokens || 0);
    const outputTokens = Number(metadata.outputTokens || 0);
    const directDelta = Math.max(0, inputTokens + outputTokens);
    if (directDelta > 0) return directDelta;
    return Math.max(0, Number(metadata.totalTokens || 0));
};

const formatTimelineTick = (rawTime: string): string => {
    const timestampMs = toEpoch(rawTime);
    if (timestampMs > 0) {
        return new Date(timestampMs).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
        });
    }
    return rawTime ? rawTime.slice(11, 16) : '';
};

const formatTimelineLabel = (rawTime: string): string => {
    const timestampMs = toEpoch(rawTime);
    if (timestampMs > 0) {
        return new Date(timestampMs).toLocaleString();
    }
    return rawTime || 'Unknown';
};

const TokenTimeline: React.FC<{ sessions: AgentSession[] }> = ({ sessions }) => {
    const timelineData = useMemo(() => {
        type TimelineBucket = {
            time: string;
            timestampMs: number;
            tokenDelta: number;
            tokenCumulative: number;
            toolExecutions: number;
            failedTools: number;
            fileEdits: number;
            artifactLinks: number;
            testRuns: number;
        };

        const buckets = new Map<string, TimelineBucket>();
        const fallbackIndexByKey = new Map<string, number>();

        const getBucket = (timestamp: string, fallbackKey: string): TimelineBucket => {
            const cleanTime = String(timestamp || '').trim();
            const timestampMs = toEpoch(cleanTime);
            const key = timestampMs > 0
                ? `ms:${timestampMs}`
                : `raw:${cleanTime || fallbackKey}`;

            let row = buckets.get(key);
            if (!row) {
                row = {
                    time: cleanTime,
                    timestampMs,
                    tokenDelta: 0,
                    tokenCumulative: 0,
                    toolExecutions: 0,
                    failedTools: 0,
                    fileEdits: 0,
                    artifactLinks: 0,
                    testRuns: 0,
                };
                buckets.set(key, row);
                fallbackIndexByKey.set(key, fallbackIndexByKey.size);
            }
            return row;
        };

        sessions.forEach(scopeSession => {
            const logs = scopeSession.logs || [];
            const timestampByLogId = new Map(logs.map(log => [log.id, log.timestamp]));

            logs.forEach((log, logIndex) => {
                const bucket = getBucket(
                    log.timestamp || scopeSession.startedAt,
                    `${scopeSession.id}:log:${log.id || logIndex}`,
                );
                bucket.tokenDelta += tokenDeltaForLog(log);
                if (log.type === 'tool') {
                    bucket.toolExecutions += 1;
                    if (log.toolCall?.status === 'error' || log.toolCall?.isError) {
                        bucket.failedTools += 1;
                    }
                    if (getTestRunDetails(log)) {
                        bucket.testRuns += 1;
                    }
                }
            });

            (scopeSession.updatedFiles || []).forEach((file, fileIndex) => {
                const action = normalizeFileAction(file.action, file.sourceToolName);
                if (action === 'read' || action === 'other') return;
                const sourceTimestamp = file.sourceLogId ? String(timestampByLogId.get(file.sourceLogId) || '') : '';
                const bucket = getBucket(
                    file.timestamp || sourceTimestamp || scopeSession.startedAt,
                    `${scopeSession.id}:file:${file.sourceLogId || fileIndex}`,
                );
                bucket.fileEdits += 1;
            });

            (scopeSession.linkedArtifacts || []).forEach((artifact, artifactIndex) => {
                const sourceTimestamp = artifact.sourceLogId ? String(timestampByLogId.get(artifact.sourceLogId) || '') : '';
                const bucket = getBucket(
                    sourceTimestamp || scopeSession.startedAt,
                    `${scopeSession.id}:artifact:${artifact.id || artifactIndex}`,
                );
                bucket.artifactLinks += 1;
            });
        });

        let cumulative = 0;
        const ordered = Array.from(buckets.entries())
            .sort((a, b) => {
                const rowA = a[1];
                const rowB = b[1];
                if (rowA.timestampMs > 0 && rowB.timestampMs > 0) return rowA.timestampMs - rowB.timestampMs;
                if (rowA.timestampMs > 0) return -1;
                if (rowB.timestampMs > 0) return 1;
                return (fallbackIndexByKey.get(a[0]) || 0) - (fallbackIndexByKey.get(b[0]) || 0);
            })
            .map(([_, row], index) => {
                cumulative += row.tokenDelta;
                return {
                    index,
                    ...row,
                    tokenCumulative: cumulative,
                };
            });

        return ordered;
    }, [sessions]);

    const totals = useMemo(
        () => timelineData.reduce(
            (acc, row) => {
                acc.toolExecutions += row.toolExecutions;
                acc.failedTools += row.failedTools;
                acc.fileEdits += row.fileEdits;
                acc.artifactLinks += row.artifactLinks;
                acc.testRuns += row.testRuns;
                return acc;
            },
            { toolExecutions: 0, failedTools: 0, fileEdits: 0, artifactLinks: 0, testRuns: 0 }
        ),
        [timelineData]
    );

    return (
        <div className="space-y-4">
            <div className="h-80 w-full relative">
                <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={timelineData} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                        <defs>
                            <linearGradient id="colorTokens" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.35} />
                                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                        <XAxis
                            dataKey="index"
                            stroke="#475569"
                            tick={{ fontSize: 10 }}
                            interval={Math.max(0, Math.floor(timelineData.length / 7))}
                            tickFormatter={(value: number) => formatTimelineTick(String(timelineData[value]?.time || ''))}
                        />
                        <YAxis
                            yAxisId="tokens"
                            stroke="#475569"
                            tick={{ fontSize: 10 }}
                            label={{ value: 'Tokens', angle: -90, position: 'insideLeft', fill: '#64748b' }}
                        />
                        <YAxis
                            yAxisId="events"
                            orientation="right"
                            stroke="#64748b"
                            tick={{ fontSize: 10 }}
                            allowDecimals={false}
                            label={{ value: 'Events', angle: 90, position: 'insideRight', fill: '#64748b' }}
                        />
                        <Tooltip
                            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                            itemStyle={{ color: '#e2e8f0' }}
                            labelStyle={{ color: '#94a3b8' }}
                            labelFormatter={(value: number) => formatTimelineLabel(String(timelineData[value]?.time || ''))}
                        />
                        <Legend wrapperStyle={{ fontSize: '11px' }} />
                        <Area
                            yAxisId="tokens"
                            type="monotone"
                            dataKey="tokenCumulative"
                            stroke="#3b82f6"
                            fillOpacity={1}
                            fill="url(#colorTokens)"
                            name="Cumulative Tokens"
                        />
                        <Bar yAxisId="events" dataKey="toolExecutions" barSize={8} fill="#f59e0b" name="Tool Executions" />
                        <Bar yAxisId="events" dataKey="fileEdits" barSize={8} fill="#22c55e" name="File Edits" />
                        <Line yAxisId="events" type="monotone" dataKey="artifactLinks" stroke="#a855f7" dot={false} strokeWidth={2} name="Artifact Links" />
                        <Line yAxisId="events" type="monotone" dataKey="testRuns" stroke="#06b6d4" dot={false} strokeWidth={2} name="Test Runs" />
                    </ComposedChart>
                </ResponsiveContainer>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                <div className="rounded-lg border border-panel-border bg-surface-overlay/90 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Tool Executions</div>
                    <div className="text-sm font-mono text-amber-300">{totals.toolExecutions.toLocaleString()}</div>
                </div>
                <div className="rounded-lg border border-panel-border bg-surface-overlay/90 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Failed Tools</div>
                    <div className="text-sm font-mono text-rose-300">{totals.failedTools.toLocaleString()}</div>
                </div>
                <div className="rounded-lg border border-panel-border bg-surface-overlay/90 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">File Edits</div>
                    <div className="text-sm font-mono text-emerald-300">{totals.fileEdits.toLocaleString()}</div>
                </div>
                <div className="rounded-lg border border-panel-border bg-surface-overlay/90 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Artifact Links</div>
                    <div className="text-sm font-mono text-violet-300">{totals.artifactLinks.toLocaleString()}</div>
                </div>
                <div className="rounded-lg border border-panel-border bg-surface-overlay/90 px-3 py-2">
                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Test Runs</div>
                    <div className="text-sm font-mono text-cyan-300">{totals.testRuns.toLocaleString()}</div>
                </div>
            </div>
        </div>
    );
};

const AnalyticsView: React.FC<{
    session: AgentSession;
    threadSessions: AgentSession[];
    threadSessionDetails: Record<string, AgentSession>;
    goToTranscript: (agentName?: string) => void;
    usageAttributionEnabled: boolean;
    sessionBlockInsightsEnabled: boolean;
    runtimeStatus: ReturnType<typeof useData>['runtimeStatus'];
    onOpenSession: (sessionId: string) => void;
}> = ({
    session,
    threadSessions,
    threadSessionDetails,
    goToTranscript,
    usageAttributionEnabled,
    sessionBlockInsightsEnabled,
    runtimeStatus,
    onOpenSession,
}) => {
    const { getColorForModel } = useModelColors();
    const [modalData, setModalData] = useState<{ title: string; data: any } | null>(null);
    const [tokenViewMode, setTokenViewMode] = useState<'summary' | 'timeline'>('summary');
    const [scopeMode, setScopeMode] = useState<'thread_family' | 'main'>('thread_family');
    const [blockDurationHours, setBlockDurationHours] = useState<1 | 3 | 5 | 8>(5);

    const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6'];
    const blockDurationOptions: Array<1 | 3 | 5 | 8> = [1, 3, 5, 8];

    const sessionsInScope = useMemo(
        () => (
            scopeMode === 'main'
                ? [session]
                : collectThreadDetailSessions(session, threadSessions, threadSessionDetails)
        ),
        [scopeMode, session, threadSessions, threadSessionDetails]
    );

    const sessionHasLinkedSubthreads = useCallback(
        (sessionId: string) => sessionsInScope.some(candidate => (
            candidate.id !== sessionId
            && (
                candidate.parentSessionId === sessionId
                || candidate.rootSessionId === sessionId
            )
        )),
        [sessionsInScope]
    );

    const scopeTotals = useMemo(
        () => sessionsInScope.reduce(
            (acc, scopeSession) => {
                const resolvedTokens = resolveTokenMetrics(scopeSession, {
                    hasLinkedSubthreads: sessionHasLinkedSubthreads(scopeSession.id),
                });
                acc.tokensIn += resolvedTokens.tokenInput;
                acc.tokensOut += resolvedTokens.tokenOutput;
                acc.modelIOTokens += resolvedTokens.modelIOTokens;
                acc.cacheInputTokens += resolvedTokens.cacheInputTokens;
                acc.workloadTokens += resolvedTokens.workloadTokens;
                acc.toolFallbackTokens += resolvedTokens.usedToolFallback ? resolvedTokens.workloadTokens : 0;
                acc.toolFallbackCount += resolvedTokens.usedToolFallback ? 1 : 0;
                acc.totalCost += resolveDisplayCost(scopeSession);
                acc.logCount += (scopeSession.logs || []).length;
                return acc;
            },
            {
                tokensIn: 0,
                tokensOut: 0,
                modelIOTokens: 0,
                cacheInputTokens: 0,
                workloadTokens: 0,
                toolFallbackTokens: 0,
                toolFallbackCount: 0,
                totalCost: 0,
                logCount: 0,
            }
        ),
        [sessionHasLinkedSubthreads, sessionsInScope]
    );
    const attributionRows = useMemo(
        () => (session.usageAttributionSummary?.rows || []).slice(0, 8),
        [session.usageAttributionSummary]
    );
    const attributionCalibration = session.usageAttributionCalibration || null;
    const blockInsights = useMemo(
        () => buildSessionBlockInsights(session, { blockDurationHours }),
        [blockDurationHours, session]
    );
    const latestBlock = blockInsights.activeBlock || blockInsights.latestBlock;

    const toolData = useMemo(() => {
        const byTool = new Map<string, { name: string; value: number; tokens: number; type: 'tool'; toolCount: number }>();
        sessionsInScope.forEach(scopeSession => {
            (scopeSession.logs || []).forEach(log => {
                if (log.type !== 'tool') return;
                const toolName = String(log.toolCall?.name || 'tool').trim() || 'tool';
                const current = byTool.get(toolName) || { name: toolName, value: 0, tokens: 0, type: 'tool', toolCount: 0 };
                current.value += 1;
                current.toolCount += 1;
                current.tokens += tokenDeltaForLog(log);
                byTool.set(toolName, current);
            });
        });
        const totalTokens = Math.max(1, scopeTotals.workloadTokens);
        return Array.from(byTool.values())
            .sort((a, b) => b.value - a.value)
            .slice(0, 10)
            .map(row => ({
                ...row,
                cost: scopeTotals.totalCost * (row.tokens / totalTokens),
            }));
    }, [scopeTotals, sessionsInScope]);

    const agentStats = useMemo(() => {
        const stats: Record<string, { count: number, tokens: number, tools: number }> = {};
        sessionsInScope.forEach(scopeSession => {
            (scopeSession.logs || []).forEach(log => {
                if (log.speaker !== 'agent') return;
                const name = String(log.agentName || (scopeSession.id === session.id ? MAIN_SESSION_AGENT : scopeSession.title || scopeSession.id)).trim() || MAIN_SESSION_AGENT;
                if (!stats[name]) stats[name] = { count: 0, tokens: 0, tools: 0 };
                stats[name].count += 1;
                stats[name].tokens += tokenDeltaForLog(log);
                if (log.type === 'tool') stats[name].tools += 1;
            });
        });
        return Object.entries(stats).map(([name, stat]) => ({
            name,
            value: stat.count,
            tokens: Math.round(stat.tokens),
            toolCount: stat.tools,
            cost: scopeTotals.workloadTokens > 0
                ? (scopeTotals.totalCost * stat.tokens) / scopeTotals.workloadTokens
                : 0,
            type: 'agent'
        }));
    }, [scopeTotals, session.id, sessionsInScope]);

    const modelData = useMemo(() => {
        const byModel = new Map<string, { name: string; value: number; tokens: number; toolCount: number; cost: number; type: 'model' }>();
        sessionsInScope.forEach(scopeSession => {
            const modelName = String(scopeSession.model || 'unknown').trim() || 'unknown';
            const current = byModel.get(modelName) || { name: modelName, value: 0, tokens: 0, toolCount: 0, cost: 0, type: 'model' };
            const sessionTokens = resolveTokenMetrics(scopeSession, {
                hasLinkedSubthreads: sessionHasLinkedSubthreads(scopeSession.id),
            }).workloadTokens;
            current.value += (scopeSession.logs || []).length;
            current.tokens += sessionTokens;
            current.toolCount += (scopeSession.logs || []).filter(log => log.type === 'tool').length;
            current.cost += Number(scopeSession.totalCost || 0);
            byModel.set(modelName, current);
        });
        return Array.from(byModel.values()).sort((a, b) => b.value - a.value);
    }, [sessionHasLinkedSubthreads, sessionsInScope]);

    return (
        <div className="h-full overflow-y-auto pb-6 relative">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-panel-border bg-panel/80 px-4 py-3">
                <div>
                    <div className="text-xs uppercase tracking-wide text-muted-foreground">Correlation Scope</div>
                    <div className="text-sm text-panel-foreground">
                        {scopeMode === 'thread_family'
                            ? `Main thread + ${Math.max(0, sessionsInScope.length - 1)} linked sub-thread${sessionsInScope.length === 2 ? '' : 's'}`
                            : 'Main thread only'}
                    </div>
                </div>
                <div className="flex bg-surface-overlay rounded-lg p-0.5 border border-panel-border">
                    <button
                        onClick={() => setScopeMode('thread_family')}
                        className={`px-3 py-1.5 text-[11px] font-bold rounded ${scopeMode === 'thread_family' ? 'bg-indigo-600 text-white' : 'text-muted-foreground hover:text-foreground'}`}
                    >
                        Main + Linked
                    </button>
                    <button
                        onClick={() => setScopeMode('main')}
                        className={`px-3 py-1.5 text-[11px] font-bold rounded ${scopeMode === 'main' ? 'bg-indigo-600 text-white' : 'text-muted-foreground hover:text-foreground'}`}
                    >
                        Main Only
                    </button>
                </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                <div className="md:col-span-2">
                    <SessionIntelligencePanel
                        title="Session Intelligence Surface"
                        description="Inspect transcript hits and derived evidence without leaving the active session workflow."
                        sessionId={session.id}
                        rootSessionId={session.rootSessionId || session.id}
                        featureId={session.intelligenceSummary?.featureId || undefined}
                        runtimeStatus={runtimeStatus}
                        onOpenSession={onOpenSession}
                        onJumpToTranscript={() => goToTranscript()}
                    />
                </div>

                {/* 1. AGENTS CHART */}
                <div className="bg-panel border border-panel-border rounded-xl p-6">
                    <h3 className="text-sm font-bold text-foreground mb-6 flex items-center gap-2"><Users size={16} /> Active Agents</h3>
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
                <div className="bg-panel border border-panel-border rounded-xl p-6">
                    <h3 className="text-sm font-bold text-foreground mb-6 flex items-center gap-2"><PieChartIcon size={16} /> Tool Usage</h3>
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
                <div className="bg-panel border border-panel-border rounded-xl p-6">
                    <h3 className="text-sm font-bold text-foreground mb-6 flex items-center gap-2"><Cpu size={16} /> Model Allocation</h3>
                    <div className="h-64 cursor-pointer">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart layout="vertical" data={modelData} onClick={(data: any) => data && data.activePayload && setModalData({ title: 'Model Details', data: data.activePayload[0].payload })}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                                <XAxis type="number" stroke="#475569" tick={{ fontSize: 12 }} />
                                <YAxis dataKey="name" type="category" stroke="#94a3b8" tick={{ fontSize: 10 }} width={100} />
                                <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                                <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={24} name="Steps Executed">
                                    {modelData.map((entry, index) => (
                                        <Cell key={`model-bar-${entry.name}-${index}`} fill={getColorForModel({ model: entry.name })} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* 4. TOKEN CONSUMPTION (Toggleable) */}
                <div className="bg-panel border border-panel-border rounded-xl p-6">
                    <div className="flex justify-between items-center mb-6">
                        <h3 className="text-sm font-bold text-foreground flex items-center gap-2"><BarChart2 size={16} /> Token Consumption</h3>
                        <div className="flex bg-surface-overlay rounded-lg p-0.5 border border-panel-border">
                            <button
                                onClick={() => setTokenViewMode('summary')}
                                className={`px-2 py-1 text-[10px] font-bold rounded ${tokenViewMode === 'summary' ? 'bg-indigo-600 text-white' : 'text-muted-foreground hover:text-foreground'}`}
                            >
                                Summary
                            </button>
                            <button
                                onClick={() => setTokenViewMode('timeline')}
                                className={`px-2 py-1 text-[10px] font-bold rounded ${tokenViewMode === 'timeline' ? 'bg-indigo-600 text-white' : 'text-muted-foreground hover:text-foreground'}`}
                            >
                                Timeline
                            </button>
                        </div>
                    </div>

                    <div className="h-64">
                        {tokenViewMode === 'summary' ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={[
                                    { name: 'Model IO', tokens: scopeTotals.modelIOTokens, fill: '#3b82f6' },
                                    { name: 'Cache Input', tokens: scopeTotals.cacheInputTokens, fill: '#06b6d4' },
                                    ...(scopeTotals.toolFallbackTokens > 0
                                        ? [{ name: 'Tool Fallback', tokens: scopeTotals.toolFallbackTokens, fill: '#f59e0b' }]
                                        : [])
                                ]} layout="vertical">
                                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                                    <XAxis type="number" stroke="#475569" tick={{ fontSize: 12 }} />
                                    <YAxis dataKey="name" type="category" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                                    <Tooltip cursor={{ fill: 'transparent' }} contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                                    <Bar dataKey="tokens" radius={[0, 4, 4, 0]} barSize={32} />
                                </BarChart>
                            </ResponsiveContainer>
                        ) : (
                            <TokenTimeline sessions={sessionsInScope} />
                        )}
                    </div>
                </div>

                {/* 5. MASTER TIMELINE VIEW (Full Width) */}
                <div className="md:col-span-2 bg-panel border border-panel-border rounded-xl p-6">
                    <h3 className="text-sm font-bold text-foreground mb-2 flex items-center gap-2"><Layers size={16} /> Session Master Timeline</h3>
                    <p className="text-xs text-muted-foreground mb-6">Correlated lifecycle view across tokens, tool executions, file edits, artifacts, and test runs.</p>
                    <TokenTimeline sessions={sessionsInScope} />
                </div>

            </div>

            {/* COST SUMMARY */}
            {sessionBlockInsightsEnabled && (
                <div className="bg-panel border border-panel-border rounded-xl p-6 mb-6">
                    <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                        <div>
                            <h3 className="text-sm font-bold text-foreground">Session Block Insights</h3>
                            <p className="mt-1 text-xs text-muted-foreground">
                                Rolling workload and spend blocks for the main session only. These views are additive and never rewrite canonical workload or display-cost totals.
                            </p>
                        </div>
                        <div className="flex bg-surface-overlay rounded-lg p-0.5 border border-panel-border">
                            {blockDurationOptions.map(option => (
                                <button
                                    key={`session-block-duration-${option}`}
                                    onClick={() => setBlockDurationHours(option)}
                                    className={`px-2.5 py-1 text-[10px] font-bold rounded ${blockDurationHours === option ? 'bg-indigo-600 text-white' : 'text-muted-foreground hover:text-foreground'}`}
                                >
                                    {option}h
                                </button>
                            ))}
                        </div>
                    </div>

                    {blockInsights.dataSource === 'none' ? (
                        <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                            CCDash could not derive per-block workload events for this session yet. Refresh the session detail after sync if usage metadata becomes available.
                        </div>
                    ) : !blockInsights.isLongSession ? (
                        <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-4 py-3 text-sm text-foreground">
                            Session runtime is {blockInsights.sessionDurationHours.toFixed(1)}h, which is shorter than the current {blockDurationHours}h block window.
                        </div>
                    ) : latestBlock ? (
                        <>
                            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
                                <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-3">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Latest Block</div>
                                    <div className="mt-2 text-lg font-mono text-panel-foreground">{latestBlock.label}</div>
                                    <div className="mt-1 text-xs text-muted-foreground">{formatBlockWindow(latestBlock.startAt, latestBlock.actualEndAt)}</div>
                                </div>
                                <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-3">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Block Workload</div>
                                    <div className="mt-2 text-lg font-mono text-panel-foreground">{formatTokenCount(latestBlock.workloadTokens)}</div>
                                    <div className="mt-1 text-xs text-muted-foreground">{latestBlock.status} • {Math.round(latestBlock.progressPct)}% window</div>
                                </div>
                                <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-3">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Burn Rate</div>
                                    <div className="mt-2 text-lg font-mono text-panel-foreground">{formatTokenCount(latestBlock.tokenBurnRatePerHour)}/h</div>
                                    <div className="mt-1 text-xs text-muted-foreground">${formatUsd(latestBlock.costBurnRatePerHour, 4)}/h</div>
                                </div>
                                <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-3">
                                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Projected End</div>
                                    <div className="mt-2 text-lg font-mono text-panel-foreground">{formatTokenCount(latestBlock.projectedWorkloadTokens)}</div>
                                    <div className="mt-1 text-xs text-muted-foreground">${formatUsd(latestBlock.projectedCostUsd, 4)} projected block cost</div>
                                </div>
                            </div>

                            <div className="h-72 mb-4">
                                <ResponsiveContainer width="100%" height="100%">
                                    <ComposedChart data={blockInsights.blocks}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                                        <XAxis dataKey="label" stroke="#475569" tick={{ fontSize: 12 }} />
                                        <YAxis yAxisId="left" stroke="#475569" tick={{ fontSize: 12 }} />
                                        <YAxis
                                            yAxisId="right"
                                            orientation="right"
                                            stroke="#64748b"
                                            tick={{ fontSize: 12 }}
                                            tickFormatter={(value: number) => `$${Number(value || 0).toFixed(2)}`}
                                        />
                                        <Tooltip
                                            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                                            formatter={(value: number, name: string) => {
                                                if (name.toLowerCase().includes('cost')) return [`$${Number(value || 0).toFixed(4)}`, name];
                                                return [formatTokenCount(value), name];
                                            }}
                                            labelFormatter={(_, payload) => {
                                                const row = payload?.[0]?.payload;
                                                return row ? `${row.label} • ${formatBlockWindow(row.startAt, row.actualEndAt)}` : '';
                                            }}
                                        />
                                        <Bar yAxisId="left" dataKey="workloadTokens" name="Observed workload" fill="#3b82f6" radius={[6, 6, 0, 0]} />
                                        <Line yAxisId="left" type="monotone" dataKey="projectedWorkloadTokens" name="Projected block total" stroke="#f59e0b" strokeDasharray="4 4" strokeWidth={2} dot={false} />
                                        <Line yAxisId="right" type="monotone" dataKey="costUsd" name="Display cost" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
                                    </ComposedChart>
                                </ResponsiveContainer>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                {blockInsights.blocks.slice(-3).map(block => (
                                    <div key={`session-block-summary-${block.index}`} className="rounded-lg border border-panel-border bg-surface-overlay/70 px-3 py-3">
                                        <div className="flex items-center justify-between gap-2">
                                            <span className="text-sm font-semibold text-panel-foreground">{block.label}</span>
                                            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{block.status}</span>
                                        </div>
                                        <div className="mt-1 text-xs text-muted-foreground">{formatBlockWindow(block.startAt, block.actualEndAt)}</div>
                                        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
                                            <div className="rounded-md border border-panel-border bg-panel/80 px-2 py-2">
                                                <div className="text-muted-foreground">Model IO</div>
                                                <div className="mt-1 font-mono text-panel-foreground">{formatTokenCount(block.modelInputTokens + block.modelOutputTokens)}</div>
                                            </div>
                                            <div className="rounded-md border border-panel-border bg-panel/80 px-2 py-2">
                                                <div className="text-muted-foreground">Cache Input</div>
                                                <div className="mt-1 font-mono text-panel-foreground">{formatTokenCount(block.cacheCreationInputTokens + block.cacheReadInputTokens)}</div>
                                            </div>
                                            <div className="rounded-md border border-panel-border bg-panel/80 px-2 py-2">
                                                <div className="text-muted-foreground">Cost</div>
                                                <div className="mt-1 font-mono text-panel-foreground">${formatUsd(block.costUsd, 4)}</div>
                                            </div>
                                            <div className="rounded-md border border-panel-border bg-panel/80 px-2 py-2">
                                                <div className="text-muted-foreground">Token Rate</div>
                                                <div className="mt-1 font-mono text-panel-foreground">{formatTokenCount(block.tokenBurnRatePerHour)}/h</div>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </>
                    ) : null}
                </div>
            )}

            {usageAttributionEnabled && session.usageAttributionSummary ? (
            <div className="bg-panel border border-panel-border rounded-xl p-6 mb-6">
                <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                    <div>
                        <h3 className="text-sm font-bold text-foreground">Usage Attribution</h3>
                        <p className="mt-1 text-xs text-muted-foreground">Event-level ownership for this session only. Exclusive totals reconcile; supporting totals are participatory.</p>
                    </div>
                    <div className="flex gap-3 text-xs">
                        <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-2 text-foreground">
                            Coverage <span className="ml-1 font-mono text-panel-foreground">{formatPercent(Number(attributionCalibration?.primaryCoverage || 0), 0)}</span>
                        </div>
                        <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-2 text-foreground">
                            Model IO gap <span className="ml-1 font-mono text-panel-foreground">{formatTokenCount(Math.abs(Number(attributionCalibration?.modelIOGap || 0)))}</span>
                        </div>
                    </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-3">
                        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Exclusive Model IO</div>
                        <div className="mt-2 text-xl font-mono text-panel-foreground">{formatTokenCount(Number(attributionCalibration?.exclusiveModelIOTokens || 0))}</div>
                    </div>
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-3">
                        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Exclusive Cache</div>
                        <div className="mt-2 text-xl font-mono text-panel-foreground">{formatTokenCount(Number(attributionCalibration?.exclusiveCacheInputTokens || 0))}</div>
                    </div>
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-3">
                        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Avg Confidence</div>
                        <div className="mt-2 text-xl font-mono text-panel-foreground">{Number(attributionCalibration?.averageConfidence || 0).toFixed(2)}</div>
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-muted-foreground border-b border-panel-border">
                                <th className="text-left py-2 pr-3">Entity</th>
                                <th className="text-right py-2 pr-3">Exclusive</th>
                                <th className="text-right py-2 pr-3">Supporting</th>
                                <th className="text-right py-2 pr-3">Cost</th>
                                <th className="text-right py-2">Confidence</th>
                            </tr>
                        </thead>
                        <tbody>
                            {attributionRows.map((row, idx) => (
                                <tr key={`${row.entityType}-${row.entityId}-${idx}`} className="border-b border-panel-border text-foreground">
                                    <td className="py-2 pr-3">
                                        <div className="text-panel-foreground">{row.entityLabel || row.entityId}</div>
                                        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{row.entityType}</div>
                                    </td>
                                    <td className="py-2 pr-3 text-right font-mono">{formatTokenCount(Number(row.exclusiveTokens || 0))}</td>
                                    <td className="py-2 pr-3 text-right font-mono">{formatTokenCount(Number(row.supportingTokens || 0))}</td>
                                    <td className="py-2 pr-3 text-right font-mono">${Number(row.exclusiveCostUsdModelIO || 0).toFixed(2)}</td>
                                    <td className="py-2 text-right font-mono">{Number(row.averageConfidence || 0).toFixed(2)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
            ) : (
                <div className="bg-panel border border-amber-500/25 rounded-xl p-6 mb-6 text-sm text-amber-100">
                    {usageAttributionEnabled
                        ? 'Usage attribution is currently unavailable for this session. Check the backend rollout gate or refresh after re-enabling attribution APIs.'
                        : 'Usage attribution is disabled for this project. Re-enable it in Project Settings to restore event-level attribution summaries for this session.'}
                </div>
            )}

            <div className="bg-panel border border-panel-border rounded-xl p-6">
                <h3 className="text-sm font-bold text-foreground mb-2">Cost Analysis</h3>
                <div className="flex items-center gap-8">
                    <div className="flex-1 bg-surface-overlay rounded-lg p-4 border border-panel-border">
                        <div className="text-xs text-muted-foreground mb-1">Total Cost</div>
                        <div className="text-3xl font-mono text-emerald-400 font-bold">${formatUsd(scopeTotals.totalCost, 4)}</div>
                    </div>
                    <div className="flex-1 bg-surface-overlay rounded-lg p-4 border border-panel-border">
                        <div className="text-xs text-muted-foreground mb-1">Cost / Step</div>
                        <div className="text-3xl font-mono text-indigo-400 font-bold">${formatUsd(scopeTotals.totalCost / Math.max(scopeTotals.logCount, 1), 4)}</div>
                    </div>
                    <div className="flex-1 bg-surface-overlay rounded-lg p-4 border border-panel-border">
                        <div className="text-xs text-muted-foreground mb-1">Workload / Step</div>
                        <div className="text-3xl font-mono text-blue-400 font-bold">{Math.round(scopeTotals.workloadTokens / Math.max(scopeTotals.logCount, 1))}</div>
                    </div>
                </div>
                <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3 text-[11px]">
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-2 text-foreground">
                        <span className="text-muted-foreground">Observed workload</span>
                        <div className="mt-1 font-mono">{formatTokenCount(scopeTotals.workloadTokens)}</div>
                    </div>
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-2 text-foreground">
                        <span className="text-muted-foreground">Cache share</span>
                        <div className="mt-1 font-mono">{formatPercent(scopeTotals.workloadTokens > 0 ? scopeTotals.cacheInputTokens / scopeTotals.workloadTokens : 0, 0)}</div>
                    </div>
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/80 px-3 py-2 text-foreground">
                        <span className="text-muted-foreground">Fallback sessions</span>
                        <div className="mt-1 font-mono">{scopeTotals.toolFallbackCount}</div>
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
                    <div key={agent} className="bg-panel border border-panel-border rounded-xl overflow-hidden">
                        <button
                            onClick={() => setExpandedAgent(isOpen ? null : agent)}
                            className="w-full p-4 flex items-center justify-between hover:bg-surface-muted/40 transition-colors"
                        >
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-full bg-surface-muted border border-panel-border flex items-center justify-center text-sm font-bold text-indigo-400">
                                    {agent[0]}
                                </div>
                                <div className="text-left">
                                    <div className="font-bold text-panel-foreground">{agent}</div>
                                    <div className="text-xs text-muted-foreground font-mono">{agentLogs.length} interactions · {threads.length} threads</div>
                                </div>
                            </div>
                            {isOpen ? <ChevronDown size={16} className="text-muted-foreground" /> : <ChevronRight size={16} className="text-muted-foreground" />}
                        </button>

                        {isOpen && (
                            <div className="p-4 border-t border-panel-border space-y-3">
                                <button
                                    onClick={() => onSelectAgent(agent === MAIN_SESSION_AGENT ? '' : agent)}
                                    className="text-xs px-3 py-1.5 rounded-lg border border-indigo-500/30 text-indigo-300 bg-indigo-500/10 hover:bg-indigo-500/20"
                                >
                                    Open Sub-agent Transcript
                                </button>
                                <div className="space-y-2">
                                    {threads.length === 0 && (
                                        <div className="text-xs text-muted-foreground">No linked threads for this agent.</div>
                                    )}
                                    {threads.map(thread => (
                                        <button
                                            key={thread.id}
                                            onClick={() => onOpenThread(thread.id)}
                                            className="w-full text-left p-2 rounded-lg border border-panel-border bg-surface-overlay hover:border-indigo-500/40 transition-colors"
                                        >
                                            <div className="text-[11px] font-mono text-indigo-300 truncate">{thread.id}</div>
                                            <div className="text-[10px] text-muted-foreground mt-1">{getThreadDisplayName(thread, subagentNameBySessionId)}</div>
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

type ImpactSignal = 'positive' | 'risk' | 'neutral';
type ImpactCategory = 'code' | 'tests' | 'artifacts' | 'workflow' | 'system';

interface ImpactEventRow {
    id: string;
    timestamp: string;
    timestampMs: number;
    category: ImpactCategory;
    signal: ImpactSignal;
    summary: string;
    detail?: string;
}

interface ImpactInsight {
    id: string;
    title: string;
    description: string;
    signal: ImpactSignal;
}

const signalBadge = (signal: ImpactSignal): string => (
    signal === 'positive'
        ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
        : signal === 'risk'
            ? 'border-rose-500/40 bg-rose-500/10 text-rose-300'
            : 'border-panel-border bg-surface-muted/90 text-foreground'
);

const categoryBadge = (category: ImpactCategory): string => (
    category === 'code'
        ? 'border-blue-500/30 bg-blue-500/10 text-blue-300'
        : category === 'tests'
            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
            : category === 'artifacts'
                ? 'border-indigo-500/30 bg-indigo-500/10 text-indigo-300'
                : category === 'workflow'
                    ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                    : 'border-panel-border bg-surface-muted/90 text-foreground'
);

const formatImpactEventTime = (timestamp: string, timestampMs: number): string => {
    if (timestampMs > 0) return new Date(timestampMs).toLocaleString();
    return timestamp || 'unknown';
};

const ImpactView: React.FC<{ session: AgentSession; linkedFeatureLinks: SessionFeatureLink[] }> = ({ session, linkedFeatureLinks }) => {
    const [eventFilter, setEventFilter] = useState<'all' | ImpactCategory>('all');

    const impactModel = useMemo(() => {
        const logs = session.logs || [];
        const forensics = asRecord(session.sessionForensics);
        const entryContext = asRecord(forensics.entryContext);
        const queuePressure = asRecord(forensics.queuePressure);
        const subagentTopology = asRecord(forensics.subagentTopology);
        const testExecution = asRecord(forensics.testExecution);
        const apiErrors = Array.isArray(entryContext.apiErrors) ? entryContext.apiErrors : [];

        const actionCounts: Record<'read' | 'create' | 'update' | 'delete' | 'other', number> = {
            read: 0,
            create: 0,
            update: 0,
            delete: 0,
            other: 0,
        };

        let additions = 0;
        let deletions = 0;
        const fileUpdates = session.updatedFiles || [];
        const uniqueTouchedFiles = new Set<string>();
        const uniqueWrittenFiles = new Set<string>();
        const events: ImpactEventRow[] = [];

        const pushEvent = (event: ImpactEventRow) => {
            if (!event.summary.trim()) return;
            events.push(event);
        };

        fileUpdates.forEach((file, index) => {
            const action = normalizeFileAction(file.action, file.sourceToolName);
            actionCounts[action] += 1;
            const filePath = normalizePath(file.filePath || '');
            if (filePath) uniqueTouchedFiles.add(filePath);
            if (action !== 'read' && action !== 'other' && filePath) uniqueWrittenFiles.add(filePath);
            additions += Math.max(0, Number(file.additions || 0));
            deletions += Math.max(0, Number(file.deletions || 0));

            const timestamp = String(file.timestamp || '');
            const timestampMs = toEpoch(timestamp);
            const fileName = fileNameFromPath(filePath || `file-${index}`);
            pushEvent({
                id: `file-${index}-${file.sourceLogId || fileName}`,
                timestamp,
                timestampMs,
                category: 'code',
                signal: action === 'delete' ? 'neutral' : 'positive',
                summary: `${formatAction(action)} ${fileName}`,
                detail: `+${Math.max(0, Number(file.additions || 0))} / -${Math.max(0, Number(file.deletions || 0))}`,
            });
        });

        const parsedTestRuns = logs
            .map(log => {
                const details = getTestRunDetails(log);
                if (!details) return null;
                return { log, details };
            })
            .filter(Boolean) as Array<{ log: SessionLog; details: TestRunDetails }>;

        let derivedTotalTests = 0;
        let derivedPassedTests = 0;
        let derivedFailingRuns = 0;

        parsedTestRuns.forEach(({ log, details }, index) => {
            const failedCount = asNumber(details.counts.failed, 0) + asNumber(details.counts.error, 0);
            const status = String(details.status || '').toLowerCase();
            const isFail = status.includes('fail') || status.includes('error') || failedCount > 0;
            if (isFail) derivedFailingRuns += 1;
            const total = asNumber(details.total, 0);
            const passed = asNumber(details.counts.passed, 0);
            derivedTotalTests += total;
            derivedPassedTests += passed;

            pushEvent({
                id: `test-${log.id}-${index}`,
                timestamp: log.timestamp,
                timestampMs: toEpoch(log.timestamp),
                category: 'tests',
                signal: isFail ? 'risk' : 'positive',
                summary: `${details.framework} run ${isFail ? 'failed' : 'passed'}`,
                detail: total > 0 ? `${total} tests · ${failedCount} failing` : (details.description || details.command || '').slice(0, 120),
            });
        });

        const resultCounts = asRecord(testExecution.resultCounts);
        const statusCounts = asRecord(testExecution.statusCounts);
        const totalTests = asNumber(testExecution.totalTests, derivedTotalTests);
        const passedTests = asNumber(resultCounts.passed, derivedPassedTests);
        const failedTests = asNumber(resultCounts.failed, 0) + asNumber(resultCounts.error, 0);
        const runCount = asNumber(testExecution.runCount, parsedTestRuns.length);
        const forensicsPassRate = Number(testExecution.passRate);
        const passRate = Number.isFinite(forensicsPassRate)
            ? forensicsPassRate
            : (totalTests > 0 ? passedTests / totalTests : 0);
        const failingRuns = asNumber(statusCounts.failed, 0) + asNumber(statusCounts.error, 0) || derivedFailingRuns;

        const artifacts = session.linkedArtifacts || [];
        const artifactTypes = new Map<string, number>();
        const logTimestampById = new Map(logs.map(log => [log.id, log.timestamp]));
        artifacts.forEach((artifact, index) => {
            const normalizedType = String(artifact.type || 'other').trim().toLowerCase() || 'other';
            artifactTypes.set(normalizedType, (artifactTypes.get(normalizedType) || 0) + 1);
            const sourceTimestamp = artifact.sourceLogId ? String(logTimestampById.get(artifact.sourceLogId) || '') : '';
            pushEvent({
                id: `artifact-${artifact.id || index}`,
                timestamp: sourceTimestamp || session.startedAt,
                timestampMs: toEpoch(sourceTimestamp || session.startedAt),
                category: 'artifacts',
                signal: normalizedType === 'request_log' ? 'neutral' : 'positive',
                summary: `Artifact: ${artifact.title || artifact.id}`,
                detail: `${normalizedType} · ${artifact.source || 'unknown source'}`,
            });
        });

        (session.impactHistory || []).forEach((point, index) => {
            const row = asRecord(point);
            const timestamp = String(row.timestamp || '');
            const type = String(row.type || 'info').toLowerCase();
            const label = String(row.label || '').trim();
            const locAdded = asNumber(row.locAdded, 0);
            const locDeleted = asNumber(row.locDeleted, 0);
            const testsPass = asNumber(row.testPassCount, 0);
            const testsFail = asNumber(row.testFailCount, 0);
            const fileCount = asNumber(row.fileCount, 0);
            const summary = label || (
                (locAdded || locDeleted || testsPass || testsFail || fileCount)
                    ? `Impact snapshot (+${locAdded}/-${locDeleted}, files ${fileCount}, tests ${testsPass}/${testsFail})`
                    : ''
            );
            if (!summary) return;

            pushEvent({
                id: `impact-history-${index}`,
                timestamp,
                timestampMs: toEpoch(timestamp),
                category: 'system',
                signal: type === 'error' ? 'risk' : (type === 'success' ? 'positive' : 'neutral'),
                summary,
            });
        });

        const toolErrorCount = logs.filter(log => (
            log.type === 'tool'
            && (log.toolCall?.status === 'error' || log.toolCall?.isError)
        )).length;
        const queueOperationCount = asNumber(queuePressure.queueOperationCount, Array.isArray(entryContext.queueOperations) ? entryContext.queueOperations.length : 0);
        const waitingForTaskCount = asNumber(queuePressure.waitingForTaskCount, 0);
        const subagentStartCount = asNumber(subagentTopology.subagentStartCount, 0);

        if (waitingForTaskCount > 0) {
            pushEvent({
                id: 'queue-pressure',
                timestamp: session.endedAt || session.updatedAt || session.startedAt,
                timestampMs: toEpoch(session.endedAt || session.updatedAt || session.startedAt),
                category: 'workflow',
                signal: 'risk',
                summary: `Queue pressure detected (${waitingForTaskCount} waiting tasks)`,
                detail: queueOperationCount > 0 ? `${queueOperationCount} queue operations` : undefined,
            });
        }
        if (apiErrors.length > 0) {
            pushEvent({
                id: 'api-errors',
                timestamp: session.endedAt || session.updatedAt || session.startedAt,
                timestampMs: toEpoch(session.endedAt || session.updatedAt || session.startedAt),
                category: 'workflow',
                signal: 'risk',
                summary: `API errors captured (${apiErrors.length})`,
                detail: 'Review Session Forensics for raw error payloads.',
            });
        }

        const insights: ImpactInsight[] = [];
        if (uniqueWrittenFiles.size > 0 && failingRuns > 0) {
            insights.push({
                id: 'code-vs-failing-tests',
                title: 'Regression pressure after code changes',
                description: `${uniqueWrittenFiles.size} written files correlated with ${failingRuns} failing test run(s).`,
                signal: 'risk',
            });
        }
        if (uniqueWrittenFiles.size > 0 && runCount > 0 && passRate >= 0.9 && failingRuns === 0) {
            insights.push({
                id: 'healthy-delivery',
                title: 'Code change validated by tests',
                description: `${uniqueWrittenFiles.size} written files with ${(passRate * 100).toFixed(1)}% pass rate across ${runCount} run(s).`,
                signal: 'positive',
            });
        }
        if (artifacts.length > 0 && linkedFeatureLinks.length > 0) {
            insights.push({
                id: 'traceable-delivery',
                title: 'Execution traceability is strong',
                description: `${artifacts.length} linked artifact(s) tied to ${linkedFeatureLinks.length} linked feature(s).`,
                signal: 'positive',
            });
        }
        if (waitingForTaskCount > 0 || toolErrorCount > 0 || apiErrors.length > 0) {
            insights.push({
                id: 'workflow-friction',
                title: 'Execution friction detected',
                description: `${waitingForTaskCount} waiting tasks, ${toolErrorCount} tool errors, ${apiErrors.length} API errors.`,
                signal: 'risk',
            });
        }
        if (insights.length === 0) {
            insights.push({
                id: 'steady-session',
                title: 'Session impact appears stable',
                description: 'No high-signal risks were derived from current session capture.',
                signal: 'neutral',
            });
        }

        const coverage = [
            {
                id: 'files',
                label: 'File change capture',
                detail: fileUpdates.length > 0 ? `${fileUpdates.length} updates captured` : 'No file updates captured',
                signal: fileUpdates.length > 0 ? 'positive' : 'neutral' as ImpactSignal,
            },
            {
                id: 'tests',
                label: 'Test execution capture',
                detail: runCount > 0 ? `${runCount} test runs captured` : 'No test runs captured',
                signal: runCount > 0 ? 'positive' : 'risk' as ImpactSignal,
            },
            {
                id: 'artifacts',
                label: 'Artifact linkage',
                detail: artifacts.length > 0 ? `${artifacts.length} linked artifacts` : 'No linked artifacts captured',
                signal: artifacts.length > 0 ? 'positive' : 'neutral' as ImpactSignal,
            },
            {
                id: 'workflow',
                label: 'Workflow telemetry',
                detail: queueOperationCount > 0 || subagentStartCount > 0
                    ? `${queueOperationCount} queue ops · ${subagentStartCount} subagent starts`
                    : 'Minimal workflow telemetry in this session',
                signal: queueOperationCount > 0 || subagentStartCount > 0 ? 'positive' : 'neutral' as ImpactSignal,
            },
            {
                id: 'impact-events',
                label: 'Impact event stream',
                detail: events.length > 0 ? `${events.length} impact events derived` : 'No impact events derived',
                signal: events.length > 0 ? 'positive' : 'risk' as ImpactSignal,
            },
        ];

        const sortedEvents = events.sort((a, b) => b.timestampMs - a.timestampMs);
        const topArtifactTypes = Array.from(artifactTypes.entries())
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5);

        return {
            additions,
            deletions,
            netLoc: additions - deletions,
            filesTouched: uniqueTouchedFiles.size,
            filesWritten: uniqueWrittenFiles.size,
            actionCounts,
            runCount,
            totalTests,
            passRate,
            failedTests,
            failingRuns,
            artifactsCount: artifacts.length,
            topArtifactTypes,
            linkedFeatureCount: linkedFeatureLinks.length,
            toolErrorCount,
            queueOperationCount,
            waitingForTaskCount,
            apiErrorCount: apiErrors.length,
            insights,
            coverage,
            events: sortedEvents,
        };
    }, [linkedFeatureLinks, session]);

    const filteredEvents = useMemo(
        () => impactModel.events
            .filter(event => eventFilter === 'all' || event.category === eventFilter)
            .slice(0, 120),
        [eventFilter, impactModel.events]
    );

    return (
        <div className="space-y-6 h-full overflow-y-auto pb-6">
            <div className="rounded-xl border border-panel-border bg-panel/75 p-5">
                <h3 className="text-sm font-bold text-panel-foreground flex items-center gap-2"><TrendingUp size={16} /> App Impact</h3>
                <p className="text-xs text-muted-foreground mt-2">
                    Outcome layer for this session: code changes, validation movement, delivery artifacts, and workflow friction.
                </p>
                <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/70 p-3">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Diff From Analytics</div>
                        <p className="text-xs text-foreground mt-1">
                            Analytics explains resource consumption and execution behavior (tokens, tools, costs).
                        </p>
                    </div>
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/70 p-3">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">This Tab Adds</div>
                        <p className="text-xs text-foreground mt-1">
                            Correlations and conclusions about delivery outcomes, regressions, and execution risk.
                        </p>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                <div className="rounded-xl border border-panel-border bg-panel/75 p-4">
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Code Footprint</div>
                    <div className="text-2xl font-mono text-panel-foreground mt-1">{impactModel.filesWritten}</div>
                    <div className="text-xs text-muted-foreground mt-1">files written ({impactModel.filesTouched} touched)</div>
                    <div className={`text-xs font-mono mt-2 ${impactModel.netLoc >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                        {impactModel.netLoc >= 0 ? '+' : ''}{impactModel.netLoc} net lines
                    </div>
                </div>
                <div className="rounded-xl border border-panel-border bg-panel/75 p-4">
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Validation</div>
                    <div className="text-2xl font-mono text-panel-foreground mt-1">{impactModel.runCount}</div>
                    <div className="text-xs text-muted-foreground mt-1">test run(s)</div>
                    <div className={`text-xs font-mono mt-2 ${impactModel.failingRuns > 0 ? 'text-rose-300' : 'text-emerald-300'}`}>
                        {(impactModel.passRate * 100).toFixed(1)}% pass · {impactModel.failedTests} failed tests
                    </div>
                </div>
                <div className="rounded-xl border border-panel-border bg-panel/75 p-4">
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Delivery Traceability</div>
                    <div className="text-2xl font-mono text-panel-foreground mt-1">{impactModel.artifactsCount}</div>
                    <div className="text-xs text-muted-foreground mt-1">linked artifacts</div>
                    <div className="text-xs font-mono text-indigo-300 mt-2">{impactModel.linkedFeatureCount} linked features</div>
                </div>
                <div className="rounded-xl border border-panel-border bg-panel/75 p-4">
                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Risk Signals</div>
                    <div className="text-2xl font-mono text-panel-foreground mt-1">
                        {impactModel.toolErrorCount + impactModel.apiErrorCount + impactModel.waitingForTaskCount}
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">aggregate risk points</div>
                    <div className="text-xs font-mono text-amber-300 mt-2">
                        Tool errors {impactModel.toolErrorCount} · API errors {impactModel.apiErrorCount}
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <div className="xl:col-span-2 rounded-xl border border-panel-border bg-panel/75 p-5">
                    <h4 className="text-sm font-semibold text-panel-foreground mb-3 flex items-center gap-2"><LayoutGrid size={14} /> Impact Correlations</h4>
                    <div className="space-y-2">
                        {impactModel.insights.map(insight => (
                            <div key={insight.id} className="rounded-lg border border-panel-border bg-surface-overlay/70 p-3">
                                <div className="flex items-center justify-between gap-2">
                                    <div className="text-sm text-panel-foreground">{insight.title}</div>
                                    <span className={`text-[10px] px-1.5 py-0.5 rounded border uppercase tracking-wide ${signalBadge(insight.signal)}`}>
                                        {insight.signal}
                                    </span>
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">{insight.description}</p>
                            </div>
                        ))}
                    </div>
                </div>
                <div className="rounded-xl border border-panel-border bg-panel/75 p-5">
                    <h4 className="text-sm font-semibold text-panel-foreground mb-3 flex items-center gap-2"><RefreshCw size={14} /> Pipeline Coverage</h4>
                    <div className="space-y-2">
                        {impactModel.coverage.map(item => (
                            <div key={item.id} className="rounded-lg border border-panel-border bg-surface-overlay/70 p-2.5">
                                <div className="flex items-center justify-between gap-2">
                                    <span className="text-xs text-panel-foreground">{item.label}</span>
                                    <span className={`text-[10px] px-1.5 py-0.5 rounded border uppercase tracking-wide ${signalBadge(item.signal)}`}>
                                        {item.signal}
                                    </span>
                                </div>
                                <p className="text-[11px] text-muted-foreground mt-1">{item.detail}</p>
                            </div>
                        ))}
                    </div>
                    {impactModel.topArtifactTypes.length > 0 && (
                        <div className="mt-4 pt-3 border-t border-panel-border">
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Top Artifact Types</div>
                            <div className="space-y-1">
                                {impactModel.topArtifactTypes.map(([type, count]) => (
                                    <div key={type} className="flex justify-between text-[11px]">
                                        <span className="text-muted-foreground font-mono">{type}</span>
                                        <span className="text-panel-foreground font-mono">{count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>

            <div className="rounded-xl border border-panel-border bg-panel/75 p-5">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                    <h4 className="text-sm font-semibold text-panel-foreground flex items-center gap-2"><Layers size={14} /> Impact Event Stream</h4>
                    <div className="flex items-center gap-1 border border-panel-border rounded-lg bg-surface-overlay p-1">
                        {([
                            { id: 'all', label: 'All' },
                            { id: 'code', label: 'Code' },
                            { id: 'tests', label: 'Tests' },
                            { id: 'artifacts', label: 'Artifacts' },
                            { id: 'workflow', label: 'Workflow' },
                            { id: 'system', label: 'System' },
                        ] as Array<{ id: 'all' | ImpactCategory; label: string }>).map(filter => (
                            <button
                                key={filter.id}
                                onClick={() => setEventFilter(filter.id)}
                                className={`px-2 py-1 text-[10px] rounded-md transition-colors ${eventFilter === filter.id ? 'bg-indigo-600 text-white' : 'text-muted-foreground hover:text-panel-foreground'}`}
                            >
                                {filter.label}
                            </button>
                        ))}
                    </div>
                </div>

                <div className="mt-3 space-y-2 max-h-[28rem] overflow-y-auto pr-1">
                    {filteredEvents.length === 0 && (
                        <div className="rounded-lg border border-panel-border bg-surface-overlay/70 p-4 text-sm text-muted-foreground">
                            No events match this filter.
                        </div>
                    )}
                    {filteredEvents.map(event => (
                        <div key={event.id} className="rounded-lg border border-panel-border bg-surface-overlay/70 p-3">
                            <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded border uppercase tracking-wide ${categoryBadge(event.category)}`}>
                                            {event.category}
                                        </span>
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded border uppercase tracking-wide ${signalBadge(event.signal)}`}>
                                            {event.signal}
                                        </span>
                                    </div>
                                    <div className="text-sm text-panel-foreground mt-1 break-words">{event.summary}</div>
                                    {event.detail && <div className="text-xs text-muted-foreground mt-1 break-words">{event.detail}</div>}
                                </div>
                                <div className="text-[10px] text-muted-foreground whitespace-nowrap">{formatImpactEventTime(event.timestamp, event.timestampMs)}</div>
                            </div>
                        </div>
                    ))}
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
    const queuePressure = useMemo(() => asRecord(forensics.queuePressure), [forensics]);
    const resourceFootprint = useMemo(() => asRecord(forensics.resourceFootprint), [forensics]);
    const subagentTopology = useMemo(() => asRecord(forensics.subagentTopology), [forensics]);
    const toolResultIntensity = useMemo(() => asRecord(forensics.toolResultIntensity), [forensics]);
    const platformTelemetry = useMemo(() => asRecord(forensics.platformTelemetry), [forensics]);
    const codexPayloadSignals = useMemo(() => asRecord(forensics.codexPayloadSignals), [forensics]);
    const todosSidecar = useMemo(() => asRecord(sidecars.todos), [sidecars]);
    const tasksSidecar = useMemo(() => asRecord(sidecars.tasks), [sidecars]);
    const teamsSidecar = useMemo(() => asRecord(sidecars.teams), [sidecars]);
    const sessionEnvSidecar = useMemo(() => asRecord(sidecars.sessionEnv), [sidecars]);
    const toolResultsSidecar = useMemo(() => asRecord(sidecars.toolResults), [sidecars]);

    const permissionModes = asStringArray(entryContext.permissionModes);
    const workingDirectories = asStringArray(entryContext.workingDirectories);
    const versions = asStringArray(entryContext.versions);
    const requestIds = asStringArray(entryContext.requestIds);
    const queueOperations = Array.isArray(entryContext.queueOperations) ? entryContext.queueOperations : [];
    const apiErrors = Array.isArray(entryContext.apiErrors) ? entryContext.apiErrors : [];
    const entryTypeCounts = asCountEntries(entryContext.entryTypeCounts, 12);
    const contentBlockTypeCounts = asCountEntries(entryContext.contentBlockTypeCounts, 12);
    const progressTypeCounts = asCountEntries(entryContext.progressTypeCounts, 12);
    const queueOperationCounts = asCountEntries(queuePressure.operationCounts, 12);
    const queueStatusCounts = asCountEntries(queuePressure.statusCounts, 12);
    const queueTaskTypeCounts = asCountEntries(queuePressure.taskTypeCounts, 12);
    const resourceCategoryCounts = asCountEntries(resourceFootprint.categories, 12);
    const resourceScopeCounts = asCountEntries(resourceFootprint.scopes, 12);
    const resourceTopTargets = Array.isArray(resourceFootprint.topTargets) ? resourceFootprint.topTargets : [];
    const subagentLinkedSessionIds = asStringArray(subagentTopology.linkedSessionIds);
    const subagentTypes = useMemo(() => collectSessionSubagentTypes(session), [session]);
    const telemetryProject = asRecord(platformTelemetry.project);
    const telemetryMcpServerNames = asStringArray(telemetryProject.mcpServerNames);
    const codexPayloadTypeCounts = asCountEntries(codexPayloadSignals.payloadTypeCounts, 12);
    const codexToolNameCounts = asCountEntries(codexPayloadSignals.toolNameCounts, 12);
    const testExecution = useMemo(() => asRecord(forensics.testExecution), [forensics]);
    const testFrameworkCounts = asCountEntries(testExecution.frameworkCounts, 12);
    const testDomainCounts = asCountEntries(testExecution.domainCounts, 12);
    const testStatusCounts = asCountEntries(testExecution.statusCounts, 12);
    const testResultCounts = asCountEntries(testExecution.resultCounts, 12);
    const testRuns = Array.isArray(testExecution.runs) ? testExecution.runs : [];

    if (Object.keys(forensics).length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                <Database size={48} className="mb-4 opacity-20" />
                <p>No forensic payload available for this session.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6 h-full overflow-y-auto pb-6">
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="bg-panel border border-panel-border rounded-xl p-5 space-y-3">
                    <h3 className="text-sm font-bold text-foreground flex items-center gap-2"><ShieldAlert size={16} /> Session Capture</h3>
                    <div className="space-y-2 text-xs">
                        <div className="flex justify-between gap-4"><span className="text-muted-foreground">Schema Version</span><span className="text-panel-foreground font-mono">{String(forensics.schemaVersion || 'n/a')}</span></div>
                        <div className="flex justify-between gap-4"><span className="text-muted-foreground">Raw Session ID</span><span className="text-foreground font-mono truncate max-w-[60%]" title={String(forensics.rawSessionId || '')}>{String(forensics.rawSessionId || '')}</span></div>
                        <div className="text-muted-foreground">Session File</div>
                        <div className="text-[11px] text-foreground font-mono break-all">{String(forensics.sessionFile || '')}</div>
                        <div className="text-muted-foreground">Claude Root</div>
                        <div className="text-[11px] text-foreground font-mono break-all">{String(forensics.claudeRoot || '')}</div>
                    </div>
                </div>

                <div className="bg-panel border border-panel-border rounded-xl p-5 space-y-3">
                    <h3 className="text-sm font-bold text-foreground flex items-center gap-2"><Bot size={16} /> Thinking</h3>
                    <div className="space-y-2 text-xs">
                        <div className="flex justify-between gap-4"><span className="text-muted-foreground">Level</span><span className="text-fuchsia-300 font-mono uppercase">{String(thinking.level || session.thinkingLevel || 'unknown')}</span></div>
                        <div className="flex justify-between gap-4"><span className="text-muted-foreground">Source</span><span className="text-foreground font-mono truncate max-w-[60%]" title={String(thinking.source || '')}>{String(thinking.source || 'n/a')}</span></div>
                        <div className="flex justify-between gap-4"><span className="text-muted-foreground">Max Thinking Tokens</span><span className="text-panel-foreground font-mono">{asNumber(thinking.maxThinkingTokens, 0).toLocaleString()}</span></div>
                        <div className="flex justify-between gap-4"><span className="text-muted-foreground">Disabled</span><span className={`font-mono ${thinking.disabled ? 'text-amber-300' : 'text-foreground'}`}>{String(Boolean(thinking.disabled))}</span></div>
                        {thinking.explicitLevel && (
                            <div className="flex justify-between gap-4"><span className="text-muted-foreground">Explicit Level</span><span className="text-foreground font-mono uppercase">{String(thinking.explicitLevel)}</span></div>
                        )}
                    </div>
                </div>
            </div>

            <div className="bg-panel border border-panel-border rounded-xl p-5 space-y-4">
                <h3 className="text-sm font-bold text-foreground flex items-center gap-2"><HardDrive size={16} /> Sidecars</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/70 p-3">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Todos</div>
                        <div className="text-xs text-panel-foreground mt-1 font-mono">{asNumber(todosSidecar.fileCount, 0)} files · {asNumber(todosSidecar.totalItems, 0)} items</div>
                    </div>
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/70 p-3">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Tasks</div>
                        <div className="text-xs text-panel-foreground mt-1 font-mono">{asNumber(tasksSidecar.taskFileCount, 0)} files · HWM {String(tasksSidecar.highWatermark || '0')}</div>
                    </div>
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/70 p-3">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Teams</div>
                        <div className="text-xs text-panel-foreground mt-1 font-mono">{asNumber(teamsSidecar.totalMessages, 0)} msgs · {asNumber(teamsSidecar.unreadMessages, 0)} unread</div>
                    </div>
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/70 p-3">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Session Env</div>
                        <div className="text-xs text-panel-foreground mt-1 font-mono">{asNumber(sessionEnvSidecar.fileCount, 0)} files</div>
                    </div>
                    <div className="rounded-lg border border-panel-border bg-surface-overlay/70 p-3">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Tool Results</div>
                        <div className="text-xs text-panel-foreground mt-1 font-mono">
                            {asNumber(toolResultsSidecar.fileCount, 0)} files · {(asNumber(toolResultsSidecar.totalBytes, 0) / (1024 * 1024)).toFixed(2)} MB
                        </div>
                    </div>
                </div>
            </div>

            <div className="bg-panel border border-panel-border rounded-xl p-5 space-y-4">
                <h3 className="text-sm font-bold text-foreground flex items-center gap-2"><Terminal size={16} /> Entry Context</h3>
                <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                    <div>
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Session Context</div>
                        <div className="space-y-1.5 text-xs">
                            <div className="flex justify-between"><span className="text-muted-foreground">Request IDs</span><span className="text-panel-foreground font-mono">{requestIds.length}</span></div>
                            <div className="flex justify-between"><span className="text-muted-foreground">Queue Ops</span><span className="text-panel-foreground font-mono">{queueOperations.length}</span></div>
                            <div className="flex justify-between"><span className="text-muted-foreground">API Errors</span><span className={`font-mono ${apiErrors.length > 0 ? 'text-rose-300' : 'text-panel-foreground'}`}>{apiErrors.length}</span></div>
                            <div className="flex justify-between"><span className="text-muted-foreground">Snapshots</span><span className="text-panel-foreground font-mono">{asNumber(entryContext.snapshotCount, 0)}</span></div>
                        </div>
                    </div>
                    <div>
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Permission Modes</div>
                        <div className="flex flex-wrap gap-1">
                            {permissionModes.length === 0 && <span className="text-xs text-muted-foreground">None captured</span>}
                            {permissionModes.map(mode => (
                                <span key={mode} className="text-[10px] px-1.5 py-0.5 rounded border border-panel-border text-foreground font-mono">{mode}</span>
                            ))}
                        </div>
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2 mt-4">Working Directories</div>
                        <div className="space-y-1 max-h-24 overflow-y-auto pr-1">
                            {workingDirectories.length === 0 && <div className="text-xs text-muted-foreground">None captured</div>}
                            {workingDirectories.map(dir => (
                                <div key={dir} className="text-[10px] text-foreground font-mono break-all">{dir}</div>
                            ))}
                        </div>
                    </div>
                    <div>
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Versions Seen</div>
                        <div className="flex flex-wrap gap-1 mb-4">
                            {versions.length === 0 && <span className="text-xs text-muted-foreground">None captured</span>}
                            {versions.map(version => (
                                <span key={version} className="text-[10px] px-1.5 py-0.5 rounded border border-panel-border text-amber-300 font-mono">{version}</span>
                            ))}
                        </div>
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Top Entry Types</div>
                        <div className="space-y-1">
                            {entryTypeCounts.length === 0 && <div className="text-xs text-muted-foreground">No counts</div>}
                            {entryTypeCounts.map(item => (
                                <div key={item.key} className="flex justify-between text-[10px]">
                                    <span className="text-muted-foreground font-mono">{item.key}</span>
                                    <span className="text-panel-foreground font-mono">{item.count}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            <div className="bg-panel border border-panel-border rounded-xl p-5 space-y-4">
                <h3 className="text-sm font-bold text-foreground flex items-center gap-2"><TestTube2 size={16} /> Test Execution</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Runs</div>
                        <div className="text-panel-foreground font-mono mt-1">{asNumber(testExecution.runCount, 0)}</div>
                    </div>
                    <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Total Tests</div>
                        <div className="text-panel-foreground font-mono mt-1">{asNumber(testExecution.totalTests, 0)}</div>
                    </div>
                    <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Pass Rate</div>
                        <div className="text-panel-foreground font-mono mt-1">{(asNumber(testExecution.passRate, 0) * 100).toFixed(1)}%</div>
                    </div>
                    <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Duration</div>
                        <div className="text-panel-foreground font-mono mt-1">{asNumber(testExecution.totalDurationSeconds, 0).toFixed(2)}s</div>
                    </div>
                </div>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                    <div className="space-y-2">
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Frameworks</div>
                            <div className="space-y-1">
                                {testFrameworkCounts.length === 0 && <div className="text-xs text-muted-foreground">No test runs parsed</div>}
                                {testFrameworkCounts.map(item => (
                                    <div key={item.key} className="flex justify-between text-[10px]">
                                        <span className="text-muted-foreground font-mono">{item.key}</span>
                                        <span className="text-panel-foreground font-mono">{item.count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Statuses</div>
                            <div className="space-y-1">
                                {testStatusCounts.length === 0 && <div className="text-xs text-muted-foreground">No status signals</div>}
                                {testStatusCounts.map(item => (
                                    <div key={item.key} className="flex justify-between text-[10px]">
                                        <span className="text-muted-foreground font-mono">{item.key}</span>
                                        <span className="text-panel-foreground font-mono">{item.count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                    <div className="space-y-2">
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Domains</div>
                            <div className="space-y-1">
                                {testDomainCounts.length === 0 && <div className="text-xs text-muted-foreground">No domain inference</div>}
                                {testDomainCounts.map(item => (
                                    <div key={item.key} className="flex justify-between text-[10px]">
                                        <span className="text-muted-foreground font-mono">{item.key}</span>
                                        <span className="text-panel-foreground font-mono">{item.count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Result Counts</div>
                            <div className="space-y-1">
                                {testResultCounts.length === 0 && <div className="text-xs text-muted-foreground">No result counts</div>}
                                {testResultCounts.map(item => (
                                    <div key={item.key} className="flex justify-between text-[10px]">
                                        <span className="text-muted-foreground font-mono">{item.key}</span>
                                        <span className="text-panel-foreground font-mono">{item.count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
                {testRuns.length > 0 && (
                    <div>
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Recent Runs</div>
                        <div className="max-h-32 overflow-y-auto pr-1 space-y-1">
                            {testRuns.slice(0, 20).map((row, idx) => {
                                const run = asRecord(row);
                                return (
                                    <div key={`${idx}-${String(run.framework || '')}-${String(run.status || '')}`} className="rounded border border-panel-border bg-surface-overlay/70 p-2 text-[10px]">
                                        <div className="text-foreground font-mono">{String(run.framework || 'test')} · {String(run.status || 'unknown')}</div>
                                        <div className="text-muted-foreground mt-0.5">
                                            {String(run.domain || 'n/a')} · {asNumber(run.total, 0)} tests · {asNumber(run.durationSeconds, 0).toFixed(2)}s
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="bg-panel border border-panel-border rounded-xl p-5">
                    <h3 className="text-sm font-bold text-foreground mb-3">Queue Operations</h3>
                    <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                        {queueOperations.length === 0 && <div className="text-xs text-muted-foreground">No queue operations recorded.</div>}
                        {queueOperations.slice(0, 40).map((operation, idx) => {
                            const op = asRecord(operation);
                            return (
                                <div key={`${String(op.timestamp || idx)}-${idx}`} className="rounded-lg border border-panel-border bg-surface-overlay/70 p-2">
                                    <div className="text-[10px] text-muted-foreground font-mono">{String(op.timestamp || '')}</div>
                                    <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 text-[11px]">
                                        <span className="text-indigo-300 font-mono">{String(op.operation || 'event')}</span>
                                        {op.taskId && <span className="text-foreground font-mono">Task {String(op.taskId)}</span>}
                                        {op.status && <span className="text-amber-300 font-mono">{String(op.status)}</span>}
                                    </div>
                                    {op.summary && <div className="text-[11px] text-foreground mt-1 break-words">{String(op.summary)}</div>}
                                </div>
                            );
                        })}
                    </div>
                </div>

                <div className="bg-panel border border-panel-border rounded-xl p-5">
                    <h3 className="text-sm font-bold text-foreground mb-3">Additional Event Mix</h3>
                    <div className="space-y-3 text-[11px]">
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Content Block Types</div>
                            <div className="space-y-1">
                                {contentBlockTypeCounts.length === 0 && <div className="text-xs text-muted-foreground">No counts</div>}
                                {contentBlockTypeCounts.map(item => (
                                    <div key={item.key} className="flex justify-between">
                                        <span className="text-muted-foreground font-mono">{item.key}</span>
                                        <span className="text-panel-foreground font-mono">{item.count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Progress Types</div>
                            <div className="space-y-1">
                                {progressTypeCounts.length === 0 && <div className="text-xs text-muted-foreground">No counts</div>}
                                {progressTypeCounts.map(item => (
                                    <div key={item.key} className="flex justify-between">
                                        <span className="text-muted-foreground font-mono">{item.key}</span>
                                        <span className="text-panel-foreground font-mono">{item.count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="bg-panel border border-panel-border rounded-xl p-5">
                    <h3 className="text-sm font-bold text-foreground mb-3">Queue Pressure</h3>
                    <div className="space-y-3 text-[11px]">
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                            <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Operations</div>
                                <div className="text-panel-foreground font-mono mt-1">{asNumber(queuePressure.queueOperationCount, 0)}</div>
                            </div>
                            <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Waiting Tasks</div>
                                <div className={`font-mono mt-1 ${asNumber(queuePressure.waitingForTaskCount, 0) > 0 ? 'text-amber-300' : 'text-panel-foreground'}`}>
                                    {asNumber(queuePressure.waitingForTaskCount, 0)}
                                </div>
                            </div>
                            <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Distinct Tasks</div>
                                <div className="text-panel-foreground font-mono mt-1">{asNumber(queuePressure.distinctTaskCount, 0)}</div>
                            </div>
                        </div>
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Operation Mix</div>
                            <div className="space-y-1">
                                {queueOperationCounts.length === 0 && <div className="text-xs text-muted-foreground">No queue pressure counts</div>}
                                {queueOperationCounts.map(item => (
                                    <div key={`op-${item.key}`} className="flex justify-between">
                                        <span className="text-muted-foreground font-mono">{item.key}</span>
                                        <span className="text-panel-foreground font-mono">{item.count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div>
                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Status Mix</div>
                                <div className="space-y-1">
                                    {queueStatusCounts.length === 0 && <div className="text-xs text-muted-foreground">No status counts</div>}
                                    {queueStatusCounts.map(item => (
                                        <div key={`status-${item.key}`} className="flex justify-between">
                                            <span className="text-muted-foreground font-mono">{item.key}</span>
                                            <span className="text-panel-foreground font-mono">{item.count}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                            <div>
                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Task Type Mix</div>
                                <div className="space-y-1">
                                    {queueTaskTypeCounts.length === 0 && <div className="text-xs text-muted-foreground">No task type counts</div>}
                                    {queueTaskTypeCounts.map(item => (
                                        <div key={`task-type-${item.key}`} className="flex justify-between">
                                            <span className="text-muted-foreground font-mono">{item.key}</span>
                                            <span className="text-panel-foreground font-mono">{item.count}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="bg-panel border border-panel-border rounded-xl p-5">
                    <h3 className="text-sm font-bold text-foreground mb-3">Resource Footprint</h3>
                    <div className="space-y-3 text-[11px]">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div>
                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Categories</div>
                                <div className="space-y-1">
                                    {resourceCategoryCounts.length === 0 && <div className="text-xs text-muted-foreground">No resource categories</div>}
                                    {resourceCategoryCounts.map(item => (
                                        <div key={`resource-category-${item.key}`} className="flex justify-between">
                                            <span className="text-muted-foreground font-mono">{item.key}</span>
                                            <span className="text-panel-foreground font-mono">{item.count}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                            <div>
                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Scopes</div>
                                <div className="space-y-1">
                                    {resourceScopeCounts.length === 0 && <div className="text-xs text-muted-foreground">No scope counts</div>}
                                    {resourceScopeCounts.map(item => (
                                        <div key={`resource-scope-${item.key}`} className="flex justify-between">
                                            <span className="text-muted-foreground font-mono">{item.key}</span>
                                            <span className="text-panel-foreground font-mono">{item.count}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Top Targets</div>
                            <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
                                {resourceTopTargets.length === 0 && <div className="text-xs text-muted-foreground">No targets captured</div>}
                                {resourceTopTargets.slice(0, 20).map((row, idx) => {
                                    const item = asRecord(row);
                                    return (
                                        <div key={`target-${idx}`} className="flex justify-between gap-2">
                                            <span className="text-muted-foreground font-mono break-all">{String(item.target || '')}</span>
                                            <span className="text-panel-foreground font-mono shrink-0">{asNumber(item.count, 0)}</span>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="bg-panel border border-panel-border rounded-xl p-5 space-y-3">
                    <h3 className="text-sm font-bold text-foreground mb-1">Subagent Topology</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                        <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Task Calls</div>
                            <div className="text-panel-foreground font-mono mt-1">{asNumber(subagentTopology.taskToolCallCount, 0)}</div>
                        </div>
                        <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Linked Calls</div>
                            <div className="text-panel-foreground font-mono mt-1">{asNumber(subagentTopology.linkedTaskToolCallCount, 0)}</div>
                        </div>
                        <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Orphan Calls</div>
                            <div className={`font-mono mt-1 ${asNumber(subagentTopology.orphanTaskToolCallCount, 0) > 0 ? 'text-amber-300' : 'text-panel-foreground'}`}>
                                {asNumber(subagentTopology.orphanTaskToolCallCount, 0)}
                            </div>
                        </div>
                        <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Subagent Starts</div>
                            <div className="text-panel-foreground font-mono mt-1">{asNumber(subagentTopology.subagentStartCount, 0)}</div>
                        </div>
                        <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Subagent Files</div>
                            <div className="text-panel-foreground font-mono mt-1">{asNumber(subagentTopology.subagentTranscriptFileCount, 0)}</div>
                        </div>
                        <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Is Subagent</div>
                            <div className="text-panel-foreground font-mono mt-1">{String(Boolean(subagentTopology.isSubagentSession))}</div>
                        </div>
                        <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Agent Types</div>
                            <div className="text-panel-foreground font-mono mt-1">{subagentTypes.length}</div>
                        </div>
                    </div>
                    <div>
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Agent Types</div>
                        <div className="max-h-24 overflow-y-auto pr-1 space-y-1">
                            {subagentTypes.length === 0 && <div className="text-xs text-muted-foreground">No agent type metadata captured</div>}
                            {subagentTypes.slice(0, 20).map(typeName => (
                                <div key={typeName} className="text-[10px] text-foreground font-mono break-all">{typeName}</div>
                            ))}
                        </div>
                    </div>
                    <div>
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Linked Session IDs</div>
                        <div className="max-h-24 overflow-y-auto pr-1 space-y-1">
                            {subagentLinkedSessionIds.length === 0 && <div className="text-xs text-muted-foreground">No linked subagent sessions</div>}
                            {subagentLinkedSessionIds.slice(0, 40).map(linkedId => (
                                <div key={linkedId} className="text-[10px] text-foreground font-mono break-all">{linkedId}</div>
                            ))}
                        </div>
                    </div>
                </div>

                <div className="bg-panel border border-panel-border rounded-xl p-5 space-y-3">
                    <h3 className="text-sm font-bold text-foreground mb-1">Tool Result Intensity</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                        <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Files</div>
                            <div className="text-panel-foreground font-mono mt-1">{asNumber(toolResultIntensity.fileCount, asNumber(toolResultsSidecar.fileCount, 0))}</div>
                        </div>
                        <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Total Bytes</div>
                            <div className="text-panel-foreground font-mono mt-1">{asNumber(toolResultIntensity.totalBytes, asNumber(toolResultsSidecar.totalBytes, 0)).toLocaleString()}</div>
                        </div>
                        <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Avg File Bytes</div>
                            <div className="text-panel-foreground font-mono mt-1">{asNumber(toolResultIntensity.avgFileBytes, asNumber(toolResultsSidecar.avgFileBytes, 0)).toLocaleString()}</div>
                        </div>
                        <div className="rounded border border-panel-border bg-surface-overlay/70 p-2">
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Large Files</div>
                            <div className="text-panel-foreground font-mono mt-1">{asNumber(toolResultIntensity.largeFileCount, asNumber(toolResultsSidecar.largeFileCount, 0))}</div>
                        </div>
                    </div>
                    <div>
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Largest Files</div>
                        <div className="space-y-1 max-h-32 overflow-y-auto pr-1">
                            {(Array.isArray(toolResultIntensity.largestFiles) ? toolResultIntensity.largestFiles : []).length === 0 && (
                                <div className="text-xs text-muted-foreground">No tool result files captured</div>
                            )}
                            {(Array.isArray(toolResultIntensity.largestFiles) ? toolResultIntensity.largestFiles : []).slice(0, 20).map((row, idx) => {
                                const item = asRecord(row);
                                return (
                                    <div key={`tool-file-${idx}`} className="flex justify-between gap-2">
                                        <span className="text-muted-foreground font-mono break-all">{String(item.name || item.path || '')}</span>
                                        <span className="text-panel-foreground font-mono shrink-0">{asNumber(item.bytes, 0).toLocaleString()}</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            </div>

            <div className="bg-panel border border-panel-border rounded-xl p-5 space-y-4">
                <h3 className="text-sm font-bold text-foreground flex items-center gap-2"><Cpu size={16} /> Platform Telemetry</h3>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 text-xs">
                    <div className="space-y-1.5">
                        <div className="flex justify-between"><span className="text-muted-foreground">Config Source</span><span className="text-foreground font-mono truncate max-w-[65%]" title={String(platformTelemetry.source || '')}>{String(platformTelemetry.source || 'n/a')}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Projects</span><span className="text-panel-foreground font-mono">{asNumber(platformTelemetry.projectCount, 0)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Startups</span><span className="text-panel-foreground font-mono">{asNumber(platformTelemetry.numStartups, 0)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Prompt Queue Uses</span><span className="text-panel-foreground font-mono">{asNumber(platformTelemetry.promptQueueUseCount, 0)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Tool Usage Keys</span><span className="text-panel-foreground font-mono">{asNumber(platformTelemetry.toolUsageCount, 0)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Skill Usage Keys</span><span className="text-panel-foreground font-mono">{asNumber(platformTelemetry.skillUsageCount, 0)}</span></div>
                    </div>
                    <div className="space-y-1.5">
                        <div className="flex justify-between"><span className="text-muted-foreground">Matched Project</span><span className="text-foreground font-mono truncate max-w-[65%]" title={String(telemetryProject.path || '')}>{String(telemetryProject.path || 'n/a')}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">MCP Servers</span><span className="text-panel-foreground font-mono">{asNumber(telemetryProject.mcpServerCount, 0)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Disabled MCP</span><span className="text-panel-foreground font-mono">{asNumber(telemetryProject.disabledMcpServerCount, 0)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Enabled MCPJSON</span><span className="text-panel-foreground font-mono">{asNumber(telemetryProject.enabledMcpjsonServerCount, 0)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Web Search Requests</span><span className="text-panel-foreground font-mono">{asNumber(telemetryProject.lastTotalWebSearchRequests, 0)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Project Onboarding</span><span className="text-panel-foreground font-mono">{String(Boolean(telemetryProject.hasCompletedProjectOnboarding))}</span></div>
                    </div>
                </div>
                {telemetryMcpServerNames.length > 0 && (
                    <div>
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">MCP Server Names</div>
                        <div className="flex flex-wrap gap-1">
                            {telemetryMcpServerNames.slice(0, 20).map(name => (
                                <span key={name} className="text-[10px] px-1.5 py-0.5 rounded border border-panel-border text-emerald-300 font-mono">{name}</span>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {(codexPayloadTypeCounts.length > 0 || codexToolNameCounts.length > 0) && (
                <div className="bg-panel border border-panel-border rounded-xl p-5">
                    <h3 className="text-sm font-bold text-foreground mb-3">Codex Payload Signals</h3>
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 text-[11px]">
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Payload Types</div>
                            <div className="space-y-1">
                                {codexPayloadTypeCounts.map(item => (
                                    <div key={`codex-payload-${item.key}`} className="flex justify-between">
                                        <span className="text-muted-foreground font-mono">{item.key}</span>
                                        <span className="text-panel-foreground font-mono">{item.count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Tool Names</div>
                            <div className="space-y-1">
                                {codexToolNameCounts.map(item => (
                                    <div key={`codex-tool-${item.key}`} className="flex justify-between">
                                        <span className="text-muted-foreground font-mono">{item.key}</span>
                                        <span className="text-panel-foreground font-mono">{item.count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            <div className="bg-panel border border-panel-border rounded-xl p-5">
                <h3 className="text-sm font-bold text-foreground mb-3">API Errors</h3>
                <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                    {apiErrors.length === 0 && <div className="text-xs text-muted-foreground">No API errors captured.</div>}
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

            <div className="bg-panel border border-panel-border rounded-xl p-5">
                <h3 className="text-sm font-bold text-foreground mb-3">Raw Forensics Payload</h3>
                <pre className="text-[10px] leading-4 font-mono bg-surface-overlay border border-panel-border rounded-lg p-3 overflow-x-auto text-foreground">
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

type StringSessionFilterKey =
    'status'
    | 'thread_kind'
    | 'conversation_family_id'
    | 'model'
    | 'model_provider'
    | 'model_family'
    | 'model_version'
    | 'platform_type'
    | 'platform_version'
    | 'root_session_id'
    | 'start_date'
    | 'end_date'
    | 'created_start'
    | 'created_end'
    | 'completed_start'
    | 'completed_end'
    | 'updated_start'
    | 'updated_end';

const buildSessionFilterPayload = (filters: Partial<SessionFilters>): SessionFilters => {
    const payload: SessionFilters = {
        include_subagents: filters.include_subagents ?? true,
    };

    const stringKeys: StringSessionFilterKey[] = [
        'status',
        'thread_kind',
        'conversation_family_id',
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
        if (value) payload[key] = value;
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
        || localFilters.thread_kind
        || localFilters.conversation_family_id
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
        <div className="rounded-lg border border-panel-border bg-panel/40 p-2 space-y-1.5">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
            <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground">From</span>
                <input
                    type="date"
                    value={String(localFilters[startKey] || '')}
                    onChange={e => handleChange(startKey, e.target.value)}
                    className="w-full bg-surface-overlay border border-panel-border rounded-md px-2 py-1.5 text-[11px] text-foreground focus:border-focus focus:outline-none"
                />
            </div>
            <div className="grid grid-cols-[34px_1fr] items-center gap-1">
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground">To</span>
                <input
                    type="date"
                    value={String(localFilters[endKey] || '')}
                    onChange={e => handleChange(endKey, e.target.value)}
                    className="w-full bg-surface-overlay border border-panel-border rounded-md px-2 py-1.5 text-[11px] text-foreground focus:border-focus focus:outline-none"
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
                        className="w-full flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted-foreground border border-panel-border rounded-md px-2.5 py-2 hover:text-panel-foreground hover:border-panel-border transition-colors"
                    >
                        <span>General</span>
                        {collapsedSections.general ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                    </button>
                    {!collapsedSections.general && (
                        <div className="pl-1 space-y-2">
                            <div className="grid grid-cols-[74px_1fr] items-center gap-2">
                                <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Status</label>
                                <select
                                    className="w-full bg-surface-overlay border border-panel-border rounded-md px-2 py-1.5 text-[11px] text-foreground focus:border-focus focus:outline-none"
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
                                <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Thread</label>
                                <select
                                    className="w-full bg-surface-overlay border border-panel-border rounded-md px-2 py-1.5 text-[11px] text-foreground focus:border-focus focus:outline-none"
                                    value={localFilters.thread_kind || ''}
                                    onChange={e => handleChange('thread_kind', e.target.value)}
                                >
                                    <option value="">All</option>
                                    <option value="root">Root</option>
                                    <option value="fork">Fork</option>
                                    <option value="subagent">Subagent</option>
                                </select>
                            </div>

                            <div className="grid grid-cols-[74px_1fr] items-center gap-2">
                                <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Family</label>
                                <input
                                    type="text"
                                    value={localFilters.conversation_family_id || ''}
                                    onChange={e => handleChange('conversation_family_id', e.target.value)}
                                    placeholder="conversation family id"
                                    className="w-full bg-surface-overlay border border-panel-border rounded-md px-2 py-1.5 text-[11px] text-foreground placeholder:text-muted-foreground focus:border-focus focus:outline-none"
                                />
                            </div>

                            <div className="grid grid-cols-[74px_1fr] items-center gap-2">
                                <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Platform</label>
                                <select
                                    className="w-full bg-surface-overlay border border-panel-border rounded-md px-2 py-1.5 text-[11px] text-foreground focus:border-focus focus:outline-none"
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
                                <label className="text-[10px] text-muted-foreground uppercase tracking-wider">CLI Ver</label>
                                <select
                                    className="w-full bg-surface-overlay border border-panel-border rounded-md px-2 py-1.5 text-[11px] text-foreground focus:border-focus focus:outline-none disabled:opacity-50"
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
                                <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Threads</label>
                                <label className="inline-flex items-center gap-2 text-[11px] text-foreground">
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
                        className="w-full flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted-foreground border border-panel-border rounded-md px-2.5 py-2 hover:text-panel-foreground hover:border-panel-border transition-colors"
                    >
                        <span>Model Fields</span>
                        {collapsedSections.models ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                    </button>
                    {!collapsedSections.models && (
                        <div className="pl-1 space-y-2">
                            <div className="grid grid-cols-[74px_1fr] items-center gap-2">
                                <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Provider</label>
                                <select
                                    className="w-full bg-surface-overlay border border-panel-border rounded-md px-2 py-1.5 text-[11px] text-foreground focus:border-focus focus:outline-none"
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
                                <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Family</label>
                                <select
                                    className="w-full bg-surface-overlay border border-panel-border rounded-md px-2 py-1.5 text-[11px] text-foreground focus:border-focus focus:outline-none"
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
                                <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Version</label>
                                <select
                                    className="w-full bg-surface-overlay border border-panel-border rounded-md px-2 py-1.5 text-[11px] text-foreground focus:border-focus focus:outline-none disabled:opacity-50"
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
                                <label className="text-[10px] text-muted-foreground uppercase tracking-wider">Model</label>
                                <select
                                    className="w-full bg-surface-overlay border border-panel-border rounded-md px-2 py-1.5 text-[11px] text-foreground focus:border-focus focus:outline-none disabled:opacity-50"
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
                        className="w-full flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted-foreground border border-panel-border rounded-md px-2.5 py-2 hover:text-panel-foreground hover:border-panel-border transition-colors"
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
                    <p className="text-[10px] text-muted-foreground leading-snug break-words">
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
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-surface-muted hover:bg-hover text-foreground rounded-lg text-xs font-bold transition-all border border-panel-border hover:border-hover"
                    title="Force full project re-scan"
                >
                    <RefreshCw size={14} id="force-sync-btn" />
                    <span>Force Sync</span>
                </button>
            </SidebarFiltersSection>
        </SidebarFiltersPortal>
    );
};

const SessionDetail: React.FC<{
    session: AgentSession;
    onBack: () => void;
    onOpenSession: (sessionId: string) => void;
    initialTab: SessionInspectorTab;
    onTabChange: (tab: SessionInspectorTab) => void;
}> = ({ session, onBack, onOpenSession, initialTab, onTabChange }) => {
    const { activeProject, getSessionById, features, runtimeStatus } = useData();
    const navigate = useNavigate();
    const [selectedLogId, setSelectedLogId] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<SessionInspectorTab>(initialTab);
    const [filterAgent, setFilterAgent] = useState<string | null>(null);
    const [viewingDoc, setViewingDoc] = useState<PlanDocument | null>(null);
    const [viewingFile, setViewingFile] = useState<{ filePath: string; localPath?: string | null } | null>(null);
    const [threadSessions, setThreadSessions] = useState<AgentSession[]>([]);
    const [threadSessionDetails, setThreadSessionDetails] = useState<Record<string, AgentSession>>({ [session.id]: session });
    const [linkedSourceLogId, setLinkedSourceLogId] = useState<string | null>(null);
    const [linkedFeatureLinks, setLinkedFeatureLinks] = useState<SessionFeatureLink[]>([]);
    const [linkedFeatureDetailsById, setLinkedFeatureDetailsById] = useState<Record<string, Feature>>({});
    const [linkedFeatureDetailsLoading, setLinkedFeatureDetailsLoading] = useState(false);
    const [featureLinkMutationInFlight, setFeatureLinkMutationInFlight] = useState(false);
    const [featureLinkMutationError, setFeatureLinkMutationError] = useState<string | null>(null);
    const [sessionContextPrimaryInput, setSessionContextPrimaryInput] = useState('');
    const [sessionContextEditingPrimary, setSessionContextEditingPrimary] = useState(false);

    useEffect(() => {
        setActiveTab(initialTab);
    }, [initialTab]);

    const setActiveTabWithSync = useCallback((tab: SessionInspectorTab) => {
        setActiveTab(tab);
        onTabChange(tab);
    }, [onTabChange]);

    useEffect(() => {
        let cancelled = false;
        const conversationFamilyId = (session.conversationFamilyId || '').trim();
        const fallbackRootSessionId = session.rootSessionId || session.id;
        const load = async () => {
            try {
                const params = new URLSearchParams({
                    offset: '0',
                    limit: '500',
                    sort_by: 'started_at',
                    sort_order: 'desc',
                    include_subagents: 'true',
                });
                if (conversationFamilyId) {
                    params.set('conversation_family_id', conversationFamilyId);
                } else {
                    params.set('root_session_id', fallbackRootSessionId);
                }
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
        let intervalId: number | null = null;
        if (session.status === 'active') {
            intervalId = window.setInterval(() => {
                void load();
            }, ACTIVE_SESSION_DETAIL_POLL_MS);
        }
        return () => {
            cancelled = true;
            if (intervalId !== null) {
                window.clearInterval(intervalId);
            }
        };
    }, [session.conversationFamilyId, session.id, session.rootSessionId, session.status]);

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

    // P4-007: gate per-feature getLegacyFeatureDetail calls behind activeTab === 'features'.
    // Previously this fired eagerly on every mount (one HTTP call per linked feature).
    // Now it only fires when the features tab is open — demand-driven, not eager.
    //
    // TODO(P5-001): Replace getLegacyFeatureDetail fan-out entirely by extending
    // FeatureCardDTO to include phase/task summaries (or a dedicated
    // /api/v1/features/{id}/phases endpoint). Once available, drop this effect and
    // derive taskHierarchy from FeatureCardDTO data fetched by useFeatureSurface.
    useEffect(() => {
        if (activeTab !== 'features') return;
        let cancelled = false;
        const featureIds = Array.from(new Set(linkedFeatureLinks.map(link => link.featureId).filter(Boolean)));

        if (featureIds.length === 0) {
            setLinkedFeatureDetailsById({});
            setLinkedFeatureDetailsLoading(false);
            return () => {
                cancelled = true;
            };
        }

        const load = async () => {
            setLinkedFeatureDetailsLoading(true);
            try {
                const entries = await Promise.all(
                    featureIds.map(async featureId => {
                        try {
                            const data = await getLegacyFeatureDetail<Feature>(featureId);
                            return [featureId, data] as const;
                        } catch {
                            return null;
                        }
                    })
                );
                if (cancelled) return;

                const next: Record<string, Feature> = {};
                entries.forEach(entry => {
                    if (!entry) return;
                    const [featureId, featureDetail] = entry;
                    next[featureId] = featureDetail;
                });
                setLinkedFeatureDetailsById(next);
            } finally {
                if (!cancelled) {
                    setLinkedFeatureDetailsLoading(false);
                }
            }
        };

        void load();
        return () => {
            cancelled = true;
        };
    }, [activeTab, linkedFeatureLinks]);

    const availableFeatures = useMemo(
        () => [...features].sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id)),
        [features]
    );

    const resolveFeatureIdFromInput = useCallback((rawInput: string): string => {
        const value = rawInput.trim();
        if (!value) return '';

        const normalized = value.toLowerCase();
        const byId = availableFeatures.find(feature => String(feature.id || '').trim().toLowerCase() === normalized);
        if (byId) return byId.id;

        const byName = availableFeatures.filter(
            feature => String(feature.name || '').trim().toLowerCase() === normalized
        );
        if (byName.length === 1) return byName[0].id;

        return value;
    }, [availableFeatures]);

    const upsertSessionFeatureLink = useCallback(async (featureInput: string, linkRole: 'primary' | 'related'): Promise<boolean> => {
        const featureId = resolveFeatureIdFromInput(featureInput);
        if (!featureId) {
            setFeatureLinkMutationError('Select a feature ID or exact feature name first.');
            return false;
        }

        setFeatureLinkMutationInFlight(true);
        setFeatureLinkMutationError(null);
        try {
            const res = await fetch(`/api/sessions/${encodeURIComponent(session.id)}/linked-features`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    featureId,
                    linkRole,
                }),
            });
            const payload = await res.json().catch(() => null);
            if (!res.ok) {
                const detail = typeof payload?.detail === 'string' ? payload.detail : `Failed to update feature link (${res.status})`;
                throw new Error(detail);
            }
            setLinkedFeatureLinks(Array.isArray(payload) ? payload as SessionFeatureLink[] : []);
            return true;
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to update feature link';
            setFeatureLinkMutationError(message);
            return false;
        } finally {
            setFeatureLinkMutationInFlight(false);
        }
    }, [resolveFeatureIdFromInput, session.id]);

    const removeSessionFeatureLink = useCallback(async (featureId: string): Promise<void> => {
        const normalizedFeatureId = String(featureId || '').trim();
        if (!normalizedFeatureId) return;

        setFeatureLinkMutationInFlight(true);
        setFeatureLinkMutationError(null);
        try {
            const res = await fetch(
                `/api/sessions/${encodeURIComponent(session.id)}/linked-features/${encodeURIComponent(normalizedFeatureId)}`,
                { method: 'DELETE' }
            );
            const payload = await res.json().catch(() => null);
            if (!res.ok) {
                const detail = typeof payload?.detail === 'string' ? payload.detail : `Failed to remove feature link (${res.status})`;
                throw new Error(detail);
            }
            setLinkedFeatureLinks(Array.isArray(payload) ? payload as SessionFeatureLink[] : []);
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to remove feature link';
            setFeatureLinkMutationError(message);
        } finally {
            setFeatureLinkMutationInFlight(false);
        }
    }, [session.id]);

    useEffect(() => {
        setFeatureLinkMutationError(null);
        setSessionContextPrimaryInput('');
        setSessionContextEditingPrimary(false);
    }, [session.id]);

    const subagentNameBySessionId = useMemo(() => {
        const names = new Map<string, string>();

        for (const log of session.logs) {
            if (log.type !== 'tool' || !isSubagentToolCallName(log.toolCall?.name) || !log.linkedSessionId) {
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
            if (names.has(thread.id)) {
                continue;
            }
            const titled = (thread.title || '').trim();
            if (titled && titled !== thread.id) {
                names.set(thread.id, titled);
                continue;
            }
            if (thread.agentId) {
                names.set(thread.id, `agent-${thread.agentId}`);
            }
        }

        return names;
    }, [session.logs, threadSessions]);

    const handleSelectAgent = (agent: string) => {
        setFilterAgent(agent || null); // Empty string resets filter
        setActiveTabWithSync('transcript');
    };

    const handleJumpToTranscript = (agentName?: string) => {
        if (agentName) setFilterAgent(agentName);
        else setFilterAgent(null);
        setActiveTabWithSync('transcript');
    }

    const handleShowLinked = (tab: 'activity' | 'artifacts', sourceLogId: string) => {
        setLinkedSourceLogId(sourceLogId);
        setActiveTabWithSync(tab);
    };

    const primaryFeatureLink = useMemo(
        () => linkedFeatureLinks.find(link => link.isPrimaryLink) || null,
        [linkedFeatureLinks]
    );
    const relatedFeatureLinks = useMemo(
        () => linkedFeatureLinks.filter(link => !link.isPrimaryLink),
        [linkedFeatureLinks]
    );
    const relatedFeatureTooltipRows = useMemo(
        () => relatedFeatureLinks.map(link => ({
            featureId: link.featureId,
            featureName: linkedFeatureDetailsById[link.featureId]?.name || link.featureName || link.featureId,
            confidence: link.confidence,
        })),
        [linkedFeatureDetailsById, relatedFeatureLinks]
    );
    const sessionContextFeatureInputListId = useMemo(
        () => `session-context-feature-options-${session.id.replace(/[^a-zA-Z0-9_-]/g, '-')}`,
        [session.id]
    );

    const handleSetPrimaryFromSessionContext = useCallback(() => {
        if (!sessionContextPrimaryInput.trim()) return;
        void upsertSessionFeatureLink(sessionContextPrimaryInput, 'primary').then(success => {
            if (success) {
                setSessionContextPrimaryInput('');
                setSessionContextEditingPrimary(false);
            }
        });
    }, [sessionContextPrimaryInput, upsertSessionFeatureLink]);

    const taskArtifacts = useMemo(() => {
        const byNormalizedTaskId = new Map<string, string>();

        const addTaskId = (candidate: string | null | undefined) => {
            const value = String(candidate || '').trim();
            if (!value) return;
            const normalized = value.toLowerCase();
            if (!byNormalizedTaskId.has(normalized)) {
                byNormalizedTaskId.set(normalized, value);
            }
        };

        (session.linkedArtifacts || []).forEach(artifact => {
            if ((artifact.type || '').trim().toLowerCase() !== 'task') return;
            const taskId = extractTaskIdFromText(
                artifact.title,
                artifact.description,
                artifact.preview,
                artifact.url,
            );
            addTaskId(taskId);
        });

        session.logs.forEach(log => {
            const taskDetails = getTaskToolDetails(log);
            addTaskId(taskDetails?.taskId);
        });

        return Array.from(byNormalizedTaskId.entries())
            .sort((a, b) => a[1].localeCompare(b[1]))
            .map(([normalizedTaskId, taskId]) => ({ normalizedTaskId, taskId }));
    }, [session.linkedArtifacts, session.logs]);
    const sessionDisplayTitle = useMemo(
        () => deriveSessionCardTitle(session.id, session.title, session.sessionMetadata || null),
        [session.id, session.title, session.sessionMetadata]
    );
    const sessionForensics = useMemo(() => asRecord(session.sessionForensics), [session.sessionForensics]);
    const forkSummary = useMemo(() => asRecord(sessionForensics.forkSummary), [sessionForensics]);
    const threadKind = normalizedThreadKind(session);
    const isForkSession = isForkThread(session);
    const parentForkSessionId = (session.forkParentSessionId || '').trim();
    const parentForkSession = parentForkSessionId
        ? threadSessions.find(thread => thread.id === parentForkSessionId)
        : null;
    const forkPointPreview = String(
        forkSummary.forkPointPreview
        || session.sessionForensics?.forkPointPreview
        || '',
    ).trim();
    const forkPointTimestamp = String(forkSummary.forkPointTimestamp || '').trim();
    const siblingForkCount = useMemo(
        () => (
            isForkSession && parentForkSessionId
                ? threadSessions.filter(thread => (
                    thread.id !== session.id
                    && isForkThread(thread)
                    && String(thread.forkParentSessionId || '').trim() === parentForkSessionId
                )).length
                : 0
        ),
        [isForkSession, parentForkSessionId, session.id, threadSessions],
    );
    const threadKindBadge = (
        threadKind === 'fork'
            ? { label: 'fork', style: 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/35' }
            : threadKind === 'subagent'
                ? { label: 'subagent', style: 'bg-fuchsia-500/15 text-fuchsia-300 border border-fuchsia-500/30' }
                : { label: 'root', style: 'bg-surface-muted text-foreground border border-panel-border' }
    );
    const primaryFeatureDetail = useMemo(
        () => (primaryFeatureLink ? (linkedFeatureDetailsById[primaryFeatureLink.featureId] || null) : null),
        [linkedFeatureDetailsById, primaryFeatureLink]
    );
    const primaryFeatureStatus = (primaryFeatureDetail?.status || primaryFeatureLink?.featureStatus || '').trim();
    const primaryFeatureStatusStyle = getFeatureStatusStyle(primaryFeatureStatus || 'backlog');
    const platformValue = String(sessionForensics.platform || session.platformType || 'claude_code').trim() || 'claude_code';
    const platformVersion = String(session.platformVersion || '').trim();
    const platformDisplay = platformVersion ? `${platformValue} ${platformVersion}` : platformValue;
    const sessionDetailTabs: Array<{ id: SessionInspectorTab; icon: React.ComponentType<{ size?: number }>; label: string }> = [
        { id: 'transcript', icon: MessageSquare, label: 'Transcript' },
        { id: 'forensics', icon: ShieldAlert, label: 'Forensics' },
        { id: 'features', icon: Box, label: `Features (${linkedFeatureLinks.length})` },
        { id: 'test-status', icon: TestTube2, label: 'Test Status' },
        { id: 'analytics', icon: BarChart2, label: 'Analytics' },
        { id: 'artifacts', icon: LinkIcon, label: 'Artifacts' },
        { id: 'impact', icon: TrendingUp, label: 'App Impact' },
        { id: 'agents', icon: Users, label: 'Agents' },
        { id: 'files', icon: FileText, label: 'Files' },
        { id: 'activity', icon: Activity, label: 'Activity' },
    ];

    const handleOpenFeature = useCallback((featureId: string) => {
        if (!featureId) return;
        navigate(`/board?feature=${encodeURIComponent(featureId)}`);
    }, [navigate]);

    return (
        <div className="h-full flex flex-col animate-in fade-in slide-in-from-bottom-4 duration-500 relative">
            {/* Header */}
            <div className="mb-4 px-2 space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="flex items-start gap-4 min-w-0 flex-1">
                        <button onClick={onBack} className="p-2 rounded-lg hover:bg-surface-muted text-muted-foreground hover:text-panel-foreground transition-all group">
                            <ArrowLeft size={18} className="group-hover:-translate-x-1 transition-transform" />
                        </button>
                        <div className="min-w-0">
                            <h2 className="text-xl font-bold text-panel-foreground flex items-center gap-2 min-w-0">
                                {sessionDisplayTitle}
                            </h2>
                            <div className="text-xs text-muted-foreground font-mono tracking-wider mt-0.5 truncate">{session.id}</div>
                            <div className="flex flex-wrap items-center gap-3 mt-0.5">
                                <span className="text-xs text-muted-foreground flex items-center gap-1.5"><Calendar size={12} /> {new Date(session.startedAt).toLocaleString()}</span>
                                <ModelBadge
                                    raw={session.model}
                                    displayName={session.modelDisplayName}
                                    provider={session.modelProvider}
                                    family={session.modelFamily}
                                    version={session.modelVersion}
                                />
                                <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${session.status === 'active' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-surface-muted text-muted-foreground'}`}>
                                    {session.status}
                                </span>
                                <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${threadKindBadge.style}`}>
                                    {threadKindBadge.label}
                                </span>
                            </div>
                        </div>
                    </div>

                    <div className="rounded-xl border border-panel-border bg-panel/75 p-3 min-w-[18rem] max-w-[28rem] shrink-0 space-y-2">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Session Context</div>
                        <div className="flex flex-col gap-2">
                            <div className="flex items-start gap-2">
                                {primaryFeatureLink ? (
                                    <button
                                        onClick={() => handleOpenFeature(primaryFeatureLink.featureId)}
                                        className="flex-1 inline-flex items-center gap-2 rounded-lg border border-indigo-500/35 bg-indigo-500/10 px-2.5 py-1.5 text-left hover:bg-indigo-500/20 transition-colors min-w-0"
                                    >
                                        <span className="text-[10px] uppercase tracking-wide text-indigo-200/90 whitespace-nowrap">Linked Feature</span>
                                        <span className="text-xs text-indigo-100 font-medium truncate max-w-[16rem]">
                                            {primaryFeatureDetail?.name || primaryFeatureLink.featureName || primaryFeatureLink.featureId}
                                        </span>
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded border whitespace-nowrap ${primaryFeatureStatusStyle.badge}`}>
                                            {primaryFeatureStatusStyle.label}
                                        </span>
                                        <span className="text-[10px] text-indigo-200/80 font-mono whitespace-nowrap">
                                            {Math.round(primaryFeatureLink.confidence * 100)}%
                                        </span>
                                        <ExternalLink size={11} className="text-indigo-200/80 shrink-0" />
                                    </button>
                                ) : (
                                    !linkedFeatureDetailsLoading && (
                                        <span className="flex-1 text-[11px] text-muted-foreground px-2 py-1 rounded-lg border border-panel-border bg-panel/70">
                                            No linked feature
                                        </span>
                                    )
                                )}
                                <button
                                    type="button"
                                    onClick={() => {
                                        setFeatureLinkMutationError(null);
                                        setSessionContextEditingPrimary(prev => {
                                            const next = !prev;
                                            if (next) {
                                                setSessionContextPrimaryInput(primaryFeatureLink?.featureId || '');
                                            }
                                            return next;
                                        });
                                    }}
                                    className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1.5 text-[11px] transition-colors ${sessionContextEditingPrimary
                                        ? 'border-indigo-400/50 bg-indigo-500/15 text-indigo-100'
                                        : 'border-panel-border bg-panel/75 text-foreground hover:border-indigo-500/40 hover:text-indigo-200'
                                        }`}
                                    title={sessionContextEditingPrimary ? 'Hide primary feature editor' : 'Edit primary feature'}
                                    aria-label={sessionContextEditingPrimary ? 'Hide primary feature editor' : 'Edit primary feature'}
                                >
                                    <Edit3 size={12} />
                                    <span>{sessionContextEditingPrimary ? 'Close' : 'Edit'}</span>
                                </button>
                            </div>
                            {linkedFeatureDetailsLoading && (
                                <span className="text-[11px] text-muted-foreground px-2 py-1 rounded-lg border border-panel-border bg-panel/70">
                                    Resolving linked feature...
                                </span>
                            )}
                            {primaryFeatureLink && relatedFeatureLinks.length > 0 && (
                                <div className="relative group/related-feature-badge w-fit">
                                    <span className="text-[11px] text-muted-foreground px-2 py-1 rounded-lg border border-panel-border bg-panel/70 w-fit">
                                        +{relatedFeatureLinks.length} related
                                    </span>
                                    <div className="pointer-events-none absolute left-0 top-[calc(100%+8px)] z-20 min-w-[220px] max-w-[320px] rounded-lg border border-panel-border bg-surface-overlay/95 px-3 py-2 opacity-0 translate-y-1 shadow-2xl transition-all duration-150 group-hover/related-feature-badge:opacity-100 group-hover/related-feature-badge:translate-y-0">
                                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Related Features</div>
                                        <div className="space-y-1.5">
                                            {relatedFeatureTooltipRows.slice(0, 8).map(row => (
                                                <div key={`session-context-related-${row.featureId}`} className="flex items-center justify-between gap-3">
                                                    <span className="text-[11px] text-panel-foreground truncate">{row.featureName}</span>
                                                    <span className="text-[10px] text-muted-foreground font-mono shrink-0">{Math.round(row.confidence * 100)}%</span>
                                                </div>
                                            ))}
                                            {relatedFeatureTooltipRows.length > 8 && (
                                                <div className="text-[10px] text-muted-foreground">+{relatedFeatureTooltipRows.length - 8} more</div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}
                            {sessionContextEditingPrimary && (
                                <div className="rounded-lg border border-panel-border bg-surface-overlay/70 px-2.5 py-2 space-y-2">
                                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Set Primary Feature</div>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="text"
                                            value={sessionContextPrimaryInput}
                                            onChange={event => setSessionContextPrimaryInput(event.target.value)}
                                            onKeyDown={event => {
                                                if (event.key === 'Enter') {
                                                    event.preventDefault();
                                                    handleSetPrimaryFromSessionContext();
                                                }
                                            }}
                                            list={sessionContextFeatureInputListId}
                                            placeholder="Feature ID or exact feature name"
                                            className="flex-1 text-xs rounded-md border border-panel-border bg-panel/80 px-2 py-1.5 text-panel-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-focus/50"
                                        />
                                        <datalist id={sessionContextFeatureInputListId}>
                                            {availableFeatures.map(feature => (
                                                <option key={`session-context-option-${feature.id}`} value={feature.id}>
                                                    {feature.name || feature.id}
                                                </option>
                                            ))}
                                        </datalist>
                                        <button
                                            type="button"
                                            onClick={handleSetPrimaryFromSessionContext}
                                            disabled={featureLinkMutationInFlight || !sessionContextPrimaryInput.trim()}
                                            className="text-[11px] font-semibold rounded-md px-2.5 py-1.5 border border-emerald-500/40 text-emerald-200 bg-emerald-500/10 hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                        >
                                            Set
                                        </button>
                                    </div>
                                    {featureLinkMutationError && (
                                        <div className="text-[11px] text-rose-300">
                                            {featureLinkMutationError}
                                        </div>
                                    )}
                                </div>
                            )}
                            <div className="flex items-center justify-between gap-3 rounded-lg border border-panel-border bg-surface-overlay/70 px-2.5 py-1.5">
                                <span className="text-[11px] text-muted-foreground inline-flex items-center gap-1.5">
                                    <Cpu size={12} />
                                    Platform
                                </span>
                                <span className="text-[11px] text-panel-foreground font-mono truncate" title={platformDisplay}>
                                    {platformDisplay}
                                </span>
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center gap-6 shrink-0">
                        <div className="text-right">
                            <div className="text-[10px] text-muted-foreground uppercase font-bold tracking-widest mb-1">Session Cost</div>
                            <div className="text-emerald-400 font-mono font-bold text-lg">${formatUsd(resolveDisplayCost(session), 2)}</div>
                            <div className="text-[10px] text-muted-foreground mt-1">{costSummaryLabel(session)}</div>
                        </div>
                    </div>
                </div>

                {isForkSession && (
                    <div className="rounded-xl border border-cyan-500/30 bg-cyan-500/8 px-3 py-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="text-[11px] text-cyan-100 flex items-center gap-1.5">
                                <GitBranch size={12} className="text-cyan-300" />
                                <span className="uppercase tracking-wider font-semibold">Fork Origin</span>
                                <span className="text-cyan-200/80">
                                    Inherits {String(session.contextInheritance || 'full').trim() || 'full'} parent context
                                </span>
                            </div>
                            {parentForkSessionId && (
                                <button
                                    type="button"
                                    onClick={() => onOpenSession(parentForkSessionId)}
                                    className="text-[10px] font-semibold rounded-md border border-cyan-400/35 bg-cyan-500/10 text-cyan-100 px-2 py-1 hover:bg-cyan-500/20 transition-colors"
                                >
                                    Open Parent
                                </button>
                            )}
                        </div>
                        <div className="mt-1.5 text-[11px] text-cyan-200/90 font-mono break-all">
                            parent: {(parentForkSession?.title || parentForkSessionId || 'unknown').trim()}
                        </div>
                        {(forkPointPreview || forkPointTimestamp || siblingForkCount > 0) && (
                            <div className="mt-1.5 text-[11px] text-cyan-100/80">
                                {forkPointPreview && <span className="mr-3">"{forkPointPreview}"</span>}
                                {forkPointTimestamp && (
                                    <span className="mr-3">at {new Date(forkPointTimestamp).toLocaleString()}</span>
                                )}
                                {siblingForkCount > 0 && <span>{siblingForkCount} sibling fork{siblingForkCount === 1 ? '' : 's'}</span>}
                            </div>
                        )}
                    </div>
                )}

                {/* Tabs */}
                <div className="w-full flex items-center bg-panel rounded-lg p-1 border border-panel-border overflow-x-auto">
                    {sessionDetailTabs.map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTabWithSync(tab.id)}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all whitespace-nowrap ${activeTab === tab.id
                                ? 'bg-indigo-600 text-white shadow'
                                : 'text-muted-foreground hover:text-panel-foreground'
                                }`}
                        >
                            <tab.icon size={14} />
                            {tab.label}
                        </button>
                    ))}
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
                        threadSessionDetails={threadSessionDetails}
                        subagentNameBySessionId={subagentNameBySessionId}
                        onOpenThread={onOpenSession}
                        onShowLinked={handleShowLinked}
                        primaryFeatureLink={primaryFeatureLink}
                        onOpenFeature={handleOpenFeature}
                        onOpenForensics={() => setActiveTabWithSync('forensics')}
                    />
                )}
                {activeTab === 'features' && (
                    <SessionFeaturesView
                        currentSessionId={session.id}
                        linkedFeatures={linkedFeatureLinks}
                        linkedFeatureDetailsById={linkedFeatureDetailsById}
                        availableFeatures={availableFeatures}
                        taskArtifacts={taskArtifacts}
                        loadingFeatureDetails={linkedFeatureDetailsLoading}
                        linkMutationInFlight={featureLinkMutationInFlight}
                        linkMutationError={featureLinkMutationError}
                        onSetPrimaryFeature={featureInput => upsertSessionFeatureLink(featureInput, 'primary')}
                        onAddRelatedFeature={featureInput => upsertSessionFeatureLink(featureInput, 'related')}
                        onRemoveLinkedFeature={removeSessionFeatureLink}
                        onOpenFeature={handleOpenFeature}
                        onOpenSession={onOpenSession}
                    />
                )}
                {activeTab === 'test-status' && (
                    activeProject?.id ? (
                        <SessionTestStatusView
                            projectId={activeProject.id}
                            sessionId={session.id}
                            sessionStatus={session.status}
                            sessionFileUpdates={session.updatedFiles || []}
                            sessionLogs={session.logs || []}
                            onNavigateToTestingPage={() => navigate(`/tests?sessionId=${encodeURIComponent(session.id)}`)}
                        />
                    ) : (
                        <div className="rounded-lg border border-panel-border bg-panel/50 p-4 text-sm text-muted-foreground">
                            Select an active project to view session test status.
                        </div>
                    )
                )}
                {activeTab === 'forensics' && <SessionForensicsView session={session} />}
                {activeTab === 'activity' && (
                    <ActivityView
                        session={session}
                        threadSessions={threadSessions}
                        threadSessionDetails={threadSessionDetails}
                        subagentNameBySessionId={subagentNameBySessionId}
                        onOpenDoc={setViewingDoc}
                        onOpenFile={(filePath, localPath) => setViewingFile({ filePath, localPath })}
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
                        onOpenFile={(filePath, localPath) => setViewingFile({ filePath, localPath })}
                        highlightedSourceLogId={linkedSourceLogId}
                    />
                )}
                {activeTab === 'artifacts' && (
                    <SessionArtifactsView
                        session={session}
                        threadSessions={threadSessions}
                        subagentNameBySessionId={subagentNameBySessionId}
                        onOpenThread={onOpenSession}
                        highlightedSourceLogId={linkedSourceLogId}
                    />
                )}
                {activeTab === 'analytics' && (
                    <AnalyticsView
                        session={session}
                        threadSessions={threadSessions}
                        threadSessionDetails={threadSessionDetails}
                        goToTranscript={handleJumpToTranscript}
                        usageAttributionEnabled={isUsageAttributionEnabled(activeProject)}
                        sessionBlockInsightsEnabled={isSessionBlockInsightsEnabled(activeProject)}
                        runtimeStatus={runtimeStatus}
                        onOpenSession={onOpenSession}
                    />
                )}
                {activeTab === 'agents' && (
                    <AgentsView
                        session={session}
                        onSelectAgent={handleSelectAgent}
                        threadSessions={threadSessions}
                        subagentNameBySessionId={subagentNameBySessionId}
                        onOpenThread={onOpenSession}
                    />
                )}
                {activeTab === 'impact' && <ImpactView session={session} linkedFeatureLinks={linkedFeatureLinks} />}
            </div>

            {viewingDoc && <DocumentModal doc={viewingDoc} onClose={() => setViewingDoc(null)} />}
            {viewingFile && (
                <ProjectFileViewerModal
                    filePath={viewingFile.filePath}
                    localPath={viewingFile.localPath}
                    onClose={() => setViewingFile(null)}
                />
            )}
        </div>
    );
};

export const SessionInspector: React.FC = () => {
    const { sessions, loadMoreSessions, hasMoreSessions, getSessionById, loading } = useData();
    const [searchParams, setSearchParams] = useSearchParams();
    const [selectedSession, setSelectedSession] = useState<AgentSession | null>(null);
    const [sessionBackStack, setSessionBackStack] = useState<AgentSession[]>([]);
    const [activeSessionTab, setActiveSessionTab] = useState<SessionInspectorTab>('transcript');
    const [sessionOpenLoading, setSessionOpenLoading] = useState(false);
    const [sessionOpenError, setSessionOpenError] = useState<string | null>(null);
    const [selectedSessionLiveStatus, setSelectedSessionLiveStatus] = useState<LiveConnectionStatus>('idle');
    const openSessionRequestRef = useRef(0);
    const sessionLiveEnabled = isSessionLiveUpdatesEnabled();
    const selectedSessionId = selectedSession?.id ?? null;
    const selectedSessionStatus = selectedSession?.status ?? null;

    const updateSessionSearchParams = useCallback((
        sessionId: string | null,
        tab: SessionInspectorTab = 'transcript',
        options?: { replace?: boolean }
    ) => {
        const nextParams = new URLSearchParams(searchParams);
        nextParams.delete('session_id');
        if (sessionId && sessionId.trim()) {
            nextParams.set('session', sessionId.trim());
            nextParams.set('tab', tab);
        } else {
            nextParams.delete('session');
            nextParams.delete('tab');
        }
        if (nextParams.toString() === searchParams.toString()) return;
        setSearchParams(nextParams, { replace: options?.replace ?? false });
    }, [searchParams, setSearchParams]);

    const openSession = useCallback(async (
        sessionId: string,
        fallback?: AgentSession,
        options?: {
            pushCurrent?: boolean;
            syncUrl?: boolean;
            replaceUrl?: boolean;
            tab?: SessionInspectorTab;
        }
    ) => {
        const normalizedSessionId = sessionId.trim();
        if (!normalizedSessionId) return;

        const nextTab = options?.tab || activeSessionTab;
        if (options?.pushCurrent && selectedSession) {
            setSessionBackStack(prev => {
                if (prev.length > 0 && prev[prev.length - 1].id === selectedSession.id) {
                    return prev;
                }
                return [...prev, selectedSession];
            });
        }

        setSessionOpenError(null);
        setSessionOpenLoading(true);
        const requestId = openSessionRequestRef.current + 1;
        openSessionRequestRef.current = requestId;

        const full = await getSessionById(normalizedSessionId);
        if (openSessionRequestRef.current !== requestId) {
            return;
        }

        if (full) {
            setSelectedSession(full);
            setActiveSessionTab(nextTab);
            setSessionOpenLoading(false);
            if (options?.syncUrl !== false) {
                updateSessionSearchParams(normalizedSessionId, nextTab, { replace: options?.replaceUrl });
            }
            return;
        }

        if (fallback) {
            setSelectedSession(fallback);
            setActiveSessionTab(nextTab);
            setSessionOpenLoading(false);
            if (options?.syncUrl !== false) {
                updateSessionSearchParams(normalizedSessionId, nextTab, { replace: options?.replaceUrl });
            }
            return;
        }

        setSelectedSession(null);
        setSessionOpenLoading(false);
        setSessionOpenError(`Unable to load session ${normalizedSessionId}.`);
    }, [activeSessionTab, getSessionById, selectedSession, updateSessionSearchParams]);

    const refreshSelectedSessionDetail = useCallback(async (sessionId: string) => {
        const refreshed = await getSessionById(sessionId, { force: true });
        if (!refreshed) return;
        setSelectedSession(current => {
            if (!current || current.id !== refreshed.id) return current;
            if (
                current.status === refreshed.status
                && current.updatedAt === refreshed.updatedAt
                && current.logs.length === refreshed.logs.length
            ) {
                return current;
            }
            return refreshed;
        });
    }, [getSessionById]);

    useEffect(() => {
        if (!sessionLiveEnabled || !selectedSessionId || selectedSessionStatus !== 'active') {
            setSelectedSessionLiveStatus(prev => (prev === 'idle' ? prev : 'idle'));
            return undefined;
        }

        const sessionId = selectedSessionId;
        const transcriptAppendEnabled = isSessionTranscriptAppendEnabled();
        const unsubscribers: Array<() => void> = [];

        unsubscribers.push(sharedLiveConnectionManager.subscribe({
            topic: sessionTopic(sessionId),
            pauseWhenHidden: true,
            onStatusChange: status => {
                setSelectedSessionLiveStatus(status);
            },
            onEvent: event => {
                if (event.kind !== 'invalidate' || event.payload.resource !== 'session') return;
                if (!transcriptAppendEnabled) {
                    void refreshSelectedSessionDetail(sessionId).catch(() => {
                        // Polling fallback handles transient errors.
                    });
                    return;
                }

                let shouldRefetch = false;
                setSelectedSession(current => {
                    if (!current || current.id !== sessionId) return current;
                    const logCount = typeof event.payload.logCount === 'number' && Number.isFinite(event.payload.logCount)
                        ? event.payload.logCount
                        : current.logs.length;
                    const rawStatus = typeof event.payload.status === 'string' ? event.payload.status.trim() : '';
                    const nextStatus: AgentSession['status'] = rawStatus === 'active' || rawStatus === 'completed'
                        ? rawStatus
                        : current.status;
                    const nextUpdatedAt = typeof event.payload.updatedAt === 'string' && event.payload.updatedAt.trim()
                        ? event.payload.updatedAt
                        : current.updatedAt;
                    shouldRefetch = nextStatus !== current.status || logCount < current.logs.length;
                    if (shouldRefetch) return current;
                    if (nextStatus === current.status && nextUpdatedAt === current.updatedAt) return current;
                    return {
                        ...current,
                        status: nextStatus,
                        updatedAt: nextUpdatedAt,
                    };
                });
                if (shouldRefetch) {
                    void refreshSelectedSessionDetail(sessionId).catch(() => {
                        // Polling fallback handles transient errors.
                    });
                }
            },
            onSnapshotRequired: () => {
                void refreshSelectedSessionDetail(sessionId).catch(() => {
                    // Polling fallback handles transient errors.
                });
            },
        }));

        if (transcriptAppendEnabled) {
            unsubscribers.push(sharedLiveConnectionManager.subscribe({
                topic: sessionTranscriptTopic(sessionId),
                pauseWhenHidden: true,
                onStatusChange: status => {
                    setSelectedSessionLiveStatus(status);
                },
                onEvent: event => {
                    if (event.kind !== 'append') return;
                    const payload = asSessionTranscriptAppendPayload(event.payload);
                    if (!payload || payload.sessionId !== sessionId) {
                        void refreshSelectedSessionDetail(sessionId).catch(() => {
                            // Polling fallback handles transient errors.
                        });
                        return;
                    }
                    let shouldRefetch = false;
                    setSelectedSession(current => {
                        if (!current || current.id !== sessionId) return current;
                        if (event.topic !== sessionTranscriptTopic(sessionId)) {
                            shouldRefetch = true;
                            return current;
                        }
                        const decision = mergeSessionTranscriptAppend(current.logs, payload);
                        if (decision.action === 'refetch') {
                            shouldRefetch = true;
                            return current;
                        }
                        if (decision.action === 'skip') {
                            return current;
                        }
                        return {
                            ...current,
                            logs: decision.nextLogs,
                            updatedAt: payload.createdAt || current.updatedAt,
                        };
                    });
                    if (shouldRefetch) {
                        void refreshSelectedSessionDetail(sessionId).catch(() => {
                            // Polling fallback handles transient errors.
                        });
                    }
                },
                onSnapshotRequired: () => {
                    void refreshSelectedSessionDetail(sessionId).catch(() => {
                        // Polling fallback handles transient errors.
                    });
                },
            }));
        }

        return () => {
            unsubscribers.forEach(unsubscribe => unsubscribe());
        };
    }, [refreshSelectedSessionDetail, selectedSessionId, selectedSessionStatus, sessionLiveEnabled]);

    useEffect(() => {
        if (!selectedSession || selectedSession.status !== 'active') {
            return undefined;
        }
        if (sessionLiveEnabled && !['backoff', 'closed'].includes(selectedSessionLiveStatus)) {
            return undefined;
        }

        let cancelled = false;
        const pollSessionDetail = async () => {
            const refreshed = await getSessionById(selectedSession.id, { force: true });
            if (!refreshed || cancelled) return;
            setSelectedSession(current => {
                if (!current || current.id !== refreshed.id) return current;
                if (
                    current.status === refreshed.status
                    && current.updatedAt === refreshed.updatedAt
                    && current.logs.length === refreshed.logs.length
                ) {
                    return current;
                }
                return refreshed;
            });
        };

        void pollSessionDetail();
        const interval = window.setInterval(() => {
            void pollSessionDetail();
        }, ACTIVE_SESSION_DETAIL_POLL_MS);

        return () => {
            cancelled = true;
            window.clearInterval(interval);
        };
    }, [getSessionById, selectedSession, selectedSessionLiveStatus, sessionLiveEnabled]);

    const handleBackFromSession = useCallback(() => {
        if (sessionBackStack.length === 0) {
            setSelectedSession(null);
            setSessionBackStack([]);
            setSessionOpenError(null);
            setSessionOpenLoading(false);
            updateSessionSearchParams(null, 'transcript');
            return;
        }

        const parent = sessionBackStack[sessionBackStack.length - 1];
        setSessionBackStack(prev => prev.slice(0, -1));
        setSelectedSession(parent);
        setSessionOpenError(null);
        setSessionOpenLoading(false);
        updateSessionSearchParams(parent.id, activeSessionTab);
    }, [activeSessionTab, sessionBackStack, updateSessionSearchParams]);

    // Deep-link sync: open session from URL and preserve shareable query params.
    useEffect(() => {
        const requestedSessionId = getSessionIdFromQuery(searchParams);
        const tabParam = searchParams.get('tab');
        const requestedTab = isSessionInspectorTab(tabParam) ? tabParam : 'transcript';

        if (!requestedSessionId) {
            setSessionOpenLoading(false);
            if (selectedSession) {
                setSelectedSession(null);
                setSessionBackStack([]);
            }
            return;
        }

        if (!searchParams.get('session') && searchParams.get('session_id')) {
            updateSessionSearchParams(requestedSessionId, requestedTab, { replace: true });
            return;
        }

        if (selectedSession?.id === requestedSessionId) {
            if (activeSessionTab !== requestedTab) {
                setActiveSessionTab(requestedTab);
            }
            return;
        }

        const existing = sessions.find(session => session.id === requestedSessionId);
        setSessionBackStack([]);
        void openSession(requestedSessionId, existing, {
            syncUrl: false,
            tab: requestedTab,
        });
    }, [activeSessionTab, openSession, searchParams, selectedSession, sessions, updateSessionSearchParams]);

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
        setActiveSessionTab('transcript');
        void openSession(session.id, session, {
            syncUrl: true,
            tab: 'transcript',
        });
    }, [openSession]);

    const handleSessionTabChange = useCallback((tab: SessionInspectorTab) => {
        setActiveSessionTab(tab);
        if (!selectedSession) return;
        updateSessionSearchParams(selectedSession.id, tab, { replace: true });
    }, [selectedSession, updateSessionSearchParams]);

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
                        label: threadToggleLabelForChildren(node.children),
                    } : undefined}
                    onClick={() => openSessionFromList(node.session)}
                />

                {hasChildren && expanded && (
                    <div className={`mt-3 ${depth > 0 ? 'ml-2' : ''} pl-4 border-l border-panel-border/90 space-y-3`}>
                        {node.children.map(child => (
                            <div key={child.session.id} className="relative pl-3">
                                <div className="absolute left-0 top-5 w-3 border-t border-panel-border/90" />
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
                onOpenSession={(sessionId) => {
                    void openSession(sessionId, undefined, {
                        pushCurrent: true,
                        syncUrl: true,
                        tab: activeSessionTab,
                    });
                }}
                initialTab={activeSessionTab}
                onTabChange={handleSessionTabChange}
            />
        );
    }

    const requestedSessionId = getSessionIdFromQuery(searchParams);
    if (!selectedSession && requestedSessionId && sessionOpenLoading) {
        return (
            <div className="h-full flex flex-col items-center justify-center gap-3 text-muted-foreground">
                <Activity size={24} className="animate-spin text-indigo-400" />
                <div className="text-sm">Loading session <span className="font-mono text-foreground">{requestedSessionId}</span>...</div>
            </div>
        );
    }

    if (!selectedSession && requestedSessionId && sessionOpenError) {
        return (
            <div className="h-full flex flex-col items-center justify-center gap-4 text-center px-6">
                <div className="text-sm text-rose-300">{sessionOpenError}</div>
                <button
                    onClick={() => {
                        const tabParam = searchParams.get('tab');
                        const requestedTab = isSessionInspectorTab(tabParam) ? tabParam : 'transcript';
                        const fallback = sessions.find(session => session.id === requestedSessionId);
                        void openSession(requestedSessionId, fallback, {
                            syncUrl: false,
                            tab: requestedTab,
                        });
                    }}
                    className="px-3 py-1.5 rounded-md border border-panel-border bg-panel text-xs text-foreground hover:border-indigo-500/40 hover:text-indigo-200 transition-colors"
                >
                    Retry
                </button>
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col gap-8 animate-in fade-in duration-500 overflow-y-auto pb-8">
            <div>
                <h2 className="text-3xl font-bold text-panel-foreground mb-2 font-mono tracking-tighter">Session Forensics</h2>
                <p className="text-muted-foreground max-w-2xl mb-6">Examine agent behavior, tool call chains, and multi-agent orchestration logs with millisecond-precision timestamps.</p>
                <SessionFilterBar />
            </div>

            <div className="space-y-10">
                <div className="flex justify-end">
                    <div className="bg-panel border border-panel-border p-1 rounded-lg flex gap-1">
                        <button
                            onClick={() => setSessionsViewMode('threaded')}
                            className={`p-1.5 rounded-md transition-all flex items-center gap-1.5 text-[11px] ${sessionsViewMode === 'threaded' ? 'bg-indigo-600 text-white shadow' : 'text-muted-foreground hover:text-panel-foreground'}`}
                            title="Nested thread tree view"
                        >
                            <Layers size={14} />
                            Threaded
                        </button>
                        <button
                            onClick={() => setSessionsViewMode('cards')}
                            className={`p-1.5 rounded-md transition-all flex items-center gap-1.5 text-[11px] ${sessionsViewMode === 'cards' ? 'bg-indigo-600 text-white shadow' : 'text-muted-foreground hover:text-panel-foreground'}`}
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
                                <div className="col-span-full border border-dashed border-panel-border rounded-2xl p-10 text-center text-muted-foreground bg-panel/10">
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
                                <div className="col-span-full border border-dashed border-panel-border rounded-2xl p-10 text-center text-muted-foreground bg-panel/10">
                                    <Zap size={32} className="mx-auto mb-3 opacity-10" />
                                    <p className="text-sm">No live sessions detected on local system.</p>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Past Sessions Section */}
                <div className="space-y-4">
                    <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-[0.2em] flex items-center gap-2">
                        <Archive size={16} /> Historical Index
                    </h3>

                    {sessionsViewMode === 'threaded' ? (
                        <div className="space-y-4">
                            {pastSessionThreadRoots.map(node => renderThreadNode(node))}
                            {pastSessionThreadRoots.length === 0 && (
                                <div className="col-span-full border border-dashed border-panel-border rounded-2xl p-10 text-center text-muted-foreground bg-panel/10">
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
                                className="px-6 py-2 bg-surface-muted hover:bg-hover text-foreground rounded-full text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
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
