import { describe, expect, it } from 'vitest';
import type { AgentSession } from '../../types';
import { hasSessionDetail, mergeSessionDetail, shouldMountAppDataProviders } from '../DataContext';

const buildSession = (overrides: Partial<AgentSession> = {}): AgentSession => ({
    id: 'session-1',
    title: 'Session 1',
    taskId: '',
    status: 'active',
    model: 'gpt-5',
    modelDisplayName: 'GPT-5',
    modelProvider: 'OpenAI',
    modelFamily: 'gpt',
    modelVersion: '5',
    modelsUsed: [],
    platformType: 'Codex',
    platformVersion: '',
    platformVersions: [],
    platformVersionTransitions: [],
    agentsUsed: [],
    skillsUsed: [],
    toolSummary: [],
    sessionType: 'root',
    parentSessionId: null,
    rootSessionId: 'session-1',
    agentId: null,
    threadKind: 'root',
    conversationFamilyId: 'session-1',
    contextInheritance: 'full',
    forkParentSessionId: null,
    forkPointLogId: null,
    forkPointEntryUuid: null,
    forkPointParentEntryUuid: null,
    forkDepth: 0,
    forkCount: 0,
    durationSeconds: 0,
    tokensIn: 0,
    tokensOut: 0,
    totalCost: 0,
    startedAt: '',
    endedAt: '',
    createdAt: '',
    updatedAt: '',
    qualityRating: 0,
    frictionRating: 0,
    gitCommitHash: '',
    gitCommitHashes: [],
    gitAuthor: '',
    gitBranch: '',
    updatedFiles: [],
    linkedArtifacts: [],
    toolsUsed: [],
    impactHistory: [],
    logs: [],
    sessionMetadata: null,
    thinkingLevel: '',
    sessionForensics: {},
    dates: {
        startedAt: { value: '', confidence: 'low', source: 'session' },
        endedAt: { value: '', confidence: 'low', source: 'session' },
        createdAt: { value: '', confidence: 'low', source: 'session' },
        updatedAt: { value: '', confidence: 'low', source: 'session' },
        lastActivityAt: { value: '', confidence: 'low', source: 'session' },
    },
    timeline: [],
    ...overrides,
});

describe('DataContext session detail helpers', () => {
    it('recognizes when a cached session includes full detail', () => {
        expect(hasSessionDetail(buildSession())).toBe(false);
        expect(hasSessionDetail(buildSession({
            logs: [{
                id: 'log-1',
                timestamp: '',
                speaker: 'agent',
                type: 'message',
                content: 'Hello',
                metadata: {},
            }],
        }))).toBe(true);
    });

    it('replaces matching session detail without disturbing other entries', () => {
        const untouched = buildSession({ id: 'session-2', title: 'Session 2' });
        const existing = buildSession();
        const fetched = buildSession({
            title: 'Updated title',
            logs: [{
                id: 'log-1',
                timestamp: '',
                speaker: 'agent',
                type: 'message',
                content: 'Updated',
                metadata: {},
            }],
        });

        const merged = mergeSessionDetail([existing, untouched], fetched);

        expect(merged).toHaveLength(2);
        expect(merged[0]).toEqual(fetched);
        expect(merged[1]).toBe(untouched);
    });

    it('leaves the list unchanged when the fetched session is not present', () => {
        const existing = [buildSession()];
        const merged = mergeSessionDetail(existing, buildSession({ id: 'missing' }));

        expect(merged).toBe(existing);
    });
});

describe('DataContext auth provider gate', () => {
    it('defers app data providers while auth is loading or hosted unauthenticated', () => {
        expect(shouldMountAppDataProviders({
            loading: true,
            authenticated: false,
            metadata: { localMode: false, authMode: 'oidc' },
            session: null,
        })).toBe(false);

        expect(shouldMountAppDataProviders({
            loading: false,
            authenticated: false,
            metadata: { localMode: false, authMode: 'oidc' },
            session: {
                localMode: false,
                authMode: 'anonymous',
            },
        })).toBe(false);
    });

    it('mounts app data providers for local mode and hosted authenticated sessions', () => {
        expect(shouldMountAppDataProviders({
            loading: false,
            authenticated: true,
            metadata: { localMode: true, authMode: 'local' },
            session: {
                localMode: true,
                authMode: 'local',
            },
        })).toBe(true);

        expect(shouldMountAppDataProviders({
            loading: false,
            authenticated: true,
            metadata: { localMode: false, authMode: 'oidc' },
            session: {
                localMode: false,
                authMode: 'oidc',
            },
        })).toBe(true);
    });
});
