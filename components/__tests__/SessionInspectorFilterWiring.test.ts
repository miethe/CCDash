/**
 * Session filter wiring: the panel's state must reach the fetch.
 *
 * RC1 in .claude/worknotes/sessions-live-and-subagent-threading/context.md:
 * `sessionFilters` was a hardcoded `{}` and `setSessionFilters` an explicit
 * no-op, and SessionInspector called useSessionsQuery WITHOUT a filters
 * argument — so `include_subagents` was never sent, the backend applied its
 * `False` default, and every subagent was excluded from /sessions.
 *
 * Two kinds of proof here:
 *   1. Wire-level (real): the filter objects the app actually uses produce the
 *      expected query string through createApiClient().getSessions.
 *   2. Source-level (structural): both useSessionsQuery call sites pass
 *      `filters`, the dead stub is gone, and the shared provider is mounted.
 *      Source proofs are the established pattern for SessionInspector in this
 *      repo (no jsdom / @testing-library available).
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

import { createApiClient, setApiProjectScope } from '../../services/apiClient';
import {
    DEFAULT_SESSION_FILTERS,
    normalizeSessionFilters,
    sessionFiltersEqual,
} from '../../contexts/DataContext';
import { LIVE_SESSION_FILTERS, LIVE_SESSIONS_LIMIT } from '../../services/queries/sessions';

const SESSION_INSPECTOR_SOURCE = fs.readFileSync(
    path.resolve(__dirname, '../SessionInspector.tsx'),
    'utf-8',
);
const DATA_CONTEXT_SOURCE = fs.readFileSync(
    path.resolve(__dirname, '../../contexts/DataContext.tsx'),
    'utf-8',
);

function stubFetch(body: unknown = { items: [], total: 0, offset: 0, limit: 50 }): void {
    vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
            new Response(JSON.stringify(body), {
                status: 200,
                headers: { 'content-type': 'application/json' },
            }),
        ),
    );
}

function calledUrl(): string {
    const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls;
    if (calls.length === 0) throw new Error('fetch was not called');
    return calls[0][0] as string;
}

afterEach(() => {
    setApiProjectScope(null);
    vi.unstubAllGlobals();
});

describe('session filters reach the fetch', () => {
    it('defaults to include_subagents=true and sends it on the wire', async () => {
        expect(DEFAULT_SESSION_FILTERS.include_subagents).toBe(true);

        stubFetch();
        await createApiClient().getSessions(DEFAULT_SESSION_FILTERS, { offset: 0, limit: 50 });

        expect(calledUrl()).toContain('include_subagents=true');
    });

    it('sends every panel field the operator set', async () => {
        stubFetch();
        await createApiClient().getSessions(
            normalizeSessionFilters({
                include_subagents: true,
                status: 'active',
                thread_kind: 'subagent',
                model: 'claude-opus-5',
                start_date: '2026-08-01',
                min_duration: 30,
            }),
            { offset: 0, limit: 50 },
        );

        const url = calledUrl();
        expect(url).toContain('status=active');
        expect(url).toContain('thread_kind=subagent');
        expect(url).toContain('model=claude-opus-5');
        expect(url).toContain('start_date=2026-08-01');
        expect(url).toContain('min_duration=30');
        expect(url).toContain('include_subagents=true');
    });

    it('live slice asks for active sessions INCLUDING subagents', async () => {
        stubFetch();
        await createApiClient().getSessions(LIVE_SESSION_FILTERS, {
            offset: 0,
            limit: LIVE_SESSIONS_LIMIT,
        });

        const url = calledUrl();
        expect(url).toContain('status=active');
        expect(url).toContain('include_subagents=true');
        expect(url).toContain(`limit=${LIVE_SESSIONS_LIMIT}`);
        // Bounded so the live slice cannot become a second unbounded list.
        expect(LIVE_SESSIONS_LIMIT).toBeLessThanOrEqual(200);
    });

    it('opting out of subagents omits the flag (backend default applies)', async () => {
        stubFetch();
        await createApiClient().getSessions({ include_subagents: false }, { offset: 0, limit: 50 });
        expect(calledUrl()).not.toContain('include_subagents');
    });
});

describe('normalizeSessionFilters / sessionFiltersEqual', () => {
    it('drops absent and blank values, keeps booleans and finite numbers', () => {
        expect(normalizeSessionFilters({
            status: '   ',
            model: ' claude-opus-5 ',
            include_subagents: false,
            min_duration: 12,
            max_duration: Number.NaN,
            thread_kind: undefined,
        })).toEqual({
            model: 'claude-opus-5',
            include_subagents: false,
            min_duration: 12,
        });
    });

    it('treats null/undefined input as an empty filter set', () => {
        expect(normalizeSessionFilters(null)).toEqual({});
        expect(normalizeSessionFilters(undefined)).toEqual({});
    });

    it('compares by content, not key order or identity', () => {
        expect(sessionFiltersEqual(
            { include_subagents: true, status: 'active' },
            { status: 'active', include_subagents: true },
        )).toBe(true);
        expect(sessionFiltersEqual({ include_subagents: true }, { include_subagents: false })).toBe(false);
        expect(sessionFiltersEqual({ include_subagents: true }, { include_subagents: true, model: 'x' })).toBe(false);
    });
});

describe('source-level wiring proofs', () => {
    it('DataContext no longer hardcodes an empty filter object or a no-op setter', () => {
        expect(DATA_CONTEXT_SOURCE).not.toContain('const sessionFilters: SessionFilters = {}');
        expect(DATA_CONTEXT_SOURCE).not.toContain('const setSessionFilters = useCallback((_filters: SessionFilters) => {}');
    });

    it('DataContext mounts the shared SessionFiltersProvider and useData() reads it', () => {
        expect(DATA_CONTEXT_SOURCE).toContain('<SessionFiltersProvider>');
        expect(DATA_CONTEXT_SOURCE).toContain('const { sessionFilters, setSessionFilters } = useSessionFilters();');
    });

    it('every SessionInspector useSessionsQuery call passes filters', () => {
        const callSites = SESSION_INSPECTOR_SOURCE.split('useSessionsQuery(').slice(1);
        expect(callSites.length).toBeGreaterThanOrEqual(2);
        callSites.forEach(tail => {
            // Argument object ends at the closing paren of the call.
            const args = tail.slice(0, tail.indexOf(')'));
            expect(args).toContain('filters:');
            expect(args).toContain('sessionFilters');
        });
    });

    it('SessionInspector mounts the dedicated live query and merges it deduped by id', () => {
        expect(SESSION_INSPECTOR_SOURCE).toContain('useLiveSessionsQuery({ projectId: activeProject?.id })');
        expect(SESSION_INSPECTOR_SOURCE).toContain('mergeSessionsById(pagedSessions, liveSessions)');
    });

    it('thread-node clicks route through openSessionFromThreadNode (placeholder-safe)', () => {
        // Both branches of renderThreadNode (placeholder row + SessionSummaryCard)
        // must use the node-aware path; openSessionFromList takes a raw AgentSession
        // and would pass a placeholder stub as openSession's fallback.
        const renderStart = SESSION_INSPECTOR_SOURCE.indexOf('const renderThreadNode = useCallback');
        expect(renderStart).toBeGreaterThan(-1);
        const renderEnd = SESSION_INSPECTOR_SOURCE.indexOf('if (selectedSession) {', renderStart);
        const body = SESSION_INSPECTOR_SOURCE.slice(renderStart, renderEnd);

        expect(body).not.toContain('openSessionFromList(node.session)');
        expect((body.match(/openSessionFromThreadNode\(node\)/g) ?? []).length).toBe(2);
        expect(SESSION_INSPECTOR_SOURCE).toContain('void openSession(node.session.id, threadNodeOpenFallback(node)');
    });

    it('a failed click (not just a deep link) can reach the error view', () => {
        // openSession only syncs the URL on success, so the error branch must fall
        // back to the tracked target id or the error state is never rendered.
        expect(SESSION_INSPECTOR_SOURCE).toContain('const failedSessionId = requestedSessionId || openTargetSessionId');
        expect(SESSION_INSPECTOR_SOURCE).toContain('if (!selectedSession && failedSessionId && sessionOpenError)');
        expect(SESSION_INSPECTOR_SOURCE).toContain('setOpenTargetSessionId(normalizedSessionId)');
    });

    it('the live auto-expand effect is keyed off the data-derived forest, not the per-render clock', () => {
        const effectIdx = SESSION_INSPECTOR_SOURCE.indexOf('const autoExpandedLiveThreadIdsRef');
        expect(effectIdx).toBeGreaterThan(-1);
        const body = SESSION_INSPECTOR_SOURCE.slice(effectIdx, effectIdx + 1600);
        expect(body).toContain('}, [sessionThreadRoots]);');
        expect(body).not.toContain('}, [activeSessionThreadRoots]);');
    });

    it('the 10-minute freshness gate is still applied to the merged list', () => {
        expect(SESSION_INSPECTOR_SOURCE).toContain('const LIVE_IN_FLIGHT_WINDOW_MS = 10 * 60 * 1000;');
        expect(SESSION_INSPECTOR_SOURCE).toContain('sessions.filter(session => isSessionLiveInFlight(session, liveNowMs))');
    });
});
