import { AgentSession, SessionLog, SessionFileUpdate, SessionTranscriptAppendPayload } from '../../types';

export const normalizePath = (path: string): string => path.replace(/\\/g, '/').replace(/^\.\/+/, '').trim();

export const fileNameFromPath = (path: string): string => {
    const normalized = normalizePath(path);
    const parts = normalized.split('/');
    return parts[parts.length - 1] || normalized;
};

export const resolveLocalPath = (filePath: string, projectRoot?: string | null): string => {
    const normalizedFilePath = normalizePath(filePath);
    if (normalizedFilePath.startsWith('/')) return normalizedFilePath;
    if (!projectRoot) return normalizedFilePath;
    return `${projectRoot.replace(/\/+$/, '')}/${normalizedFilePath}`;
};

export const toEpoch = (timestamp?: string): number => {
    if (!timestamp) return 0;
    const ms = Date.parse(timestamp);
    return Number.isFinite(ms) ? ms : 0;
};

export const formatUsd = (value: number | string | null | undefined, digits = 2): string => {
    const parsed = typeof value === 'number' ? value : Number(value ?? 0);
    if (!Number.isFinite(parsed)) return (0).toFixed(digits);
    return parsed.toFixed(digits);
};

export const parseLogIndex = (logId?: string): number => {
    if (!logId) return -1;
    const match = /^log-(\d+)$/.exec(logId.trim());
    return match ? Number.parseInt(match[1], 10) : -1;
};

export const normalizeFileAction = (action: string | undefined, sourceToolName?: string): 'read' | 'create' | 'update' | 'delete' | 'other' => {
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

export const formatAction = (action: string): string => {
    const normalized = (action || '').trim();
    if (!normalized) return 'Unknown';
    return normalized.charAt(0).toUpperCase() + normalized.slice(1);
};

export const collectCommitEvents = (session: AgentSession): Array<{ hash: string; logIndex: number; timestampMs: number; }> => {
    const events: Array<{ hash: string; logIndex: number; timestampMs: number; }> = [];
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

export const toGitHubBlobUrl = (repoUrl: string, commitHash: string, filePath: string, projectRoot?: string | null): string | null => {
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

export const collectThreadDetailSessions = (
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

export const asSessionTranscriptAppendPayload = (raw: unknown): SessionTranscriptAppendPayload | null => {
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

