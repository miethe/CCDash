/**
 * Session thread forest + live-slice merge behaviour.
 *
 * Covers the three presentation-layer defects diagnosed in
 * .claude/worknotes/sessions-live-and-subagent-threading/context.md:
 *
 *   RC2 — orphaned children were promoted to roots because parents were only
 *         resolved within the loaded pages. A session carrying a parent / fork /
 *         non-self root pointer must NEVER become a top-level root.
 *   RC3 — Live In-Flight was derived from page position, so live subagents and
 *         long-running orchestrators outside the loaded window were invisible.
 *
 * These are real behavioural tests (direct import of the pure helpers), not
 * source-text proofs: buildSessionThreadForest / mergeSessionsById have no DOM
 * dependency. The wiring proofs live in SessionInspectorFilterWiring.test.ts.
 */

import { describe, expect, it } from 'vitest';
import type { AgentSession } from '../../types';
import {
    buildSessionThreadForest,
    hasThreadParentLink,
    isSessionLiveInFlight,
    mergeSessionsById,
    threadNodeHasLiveSession,
    threadNodeOpenFallback,
    PLACEHOLDER_THREAD_TITLE,
    type SessionThreadNode,
} from '../SessionInspector';

const NOW = Date.parse('2026-08-12T16:00:00.000Z');
const minutesAgo = (minutes: number): string => new Date(NOW - minutes * 60_000).toISOString();

const session = (overrides: Partial<AgentSession> & { id: string }): AgentSession => ({
    taskId: '',
    status: 'completed',
    model: 'claude-sonnet-5',
    durationSeconds: 0,
    tokensIn: 0,
    tokensOut: 0,
    totalCost: 0,
    startedAt: minutesAgo(600),
    toolsUsed: [],
    logs: [],
    ...overrides,
});

const rootIdsOf = (nodes: SessionThreadNode[]): string[] => nodes.map(node => node.session.id);

const flatten = (nodes: SessionThreadNode[]): SessionThreadNode[] =>
    nodes.flatMap(node => [node, ...flatten(node.children)]);

const findNode = (nodes: SessionThreadNode[], id: string): SessionThreadNode | undefined =>
    flatten(nodes).find(node => node.session.id === id);

describe('buildSessionThreadForest — parent resolution', () => {
    it('keeps real multi-level nesting when every parent is loaded', () => {
        const forest = buildSessionThreadForest([
            session({ id: 'root-1', rootSessionId: 'root-1' }),
            session({ id: 'child-1', parentSessionId: 'root-1', rootSessionId: 'root-1', sessionType: 'subagent', threadKind: 'subagent' }),
            session({ id: 'grandchild-1', parentSessionId: 'child-1', rootSessionId: 'root-1', sessionType: 'subagent', threadKind: 'subagent' }),
        ]);

        expect(rootIdsOf(forest)).toEqual(['root-1']);
        expect(rootIdsOf(forest[0].children)).toEqual(['child-1']);
        expect(rootIdsOf(forest[0].children[0].children)).toEqual(['grandchild-1']);
    });

    it('attaches a fork under its forkParentSessionId when loaded', () => {
        const forest = buildSessionThreadForest([
            session({ id: 'root-1', rootSessionId: 'root-1' }),
            session({ id: 'mid-1', parentSessionId: 'root-1', rootSessionId: 'root-1', sessionType: 'subagent' }),
            session({ id: 'fork-1', forkParentSessionId: 'mid-1', rootSessionId: 'root-1', threadKind: 'fork' }),
        ]);

        expect(rootIdsOf(forest)).toEqual(['root-1']);
        expect(rootIdsOf(findNode(forest, 'mid-1')!.children)).toEqual(['fork-1']);
    });

    it('attaches an orphan under its family root when the direct parent is NOT loaded', () => {
        // The real shape: list is started_at desc, the subagent started 19h after
        // its root, and the intermediate parent page was never fetched.
        const forest = buildSessionThreadForest([
            session({ id: 'root-1', rootSessionId: 'root-1', startedAt: minutesAgo(1140) }),
            session({
                id: 'orphan-1',
                parentSessionId: 'never-loaded-parent',
                rootSessionId: 'root-1',
                sessionType: 'subagent',
                threadKind: 'subagent',
                startedAt: minutesAgo(4),
            }),
        ]);

        expect(rootIdsOf(forest)).toEqual(['root-1']);
        expect(rootIdsOf(forest[0].children)).toEqual(['orphan-1']);
    });

    it('synthesises a marked placeholder root when the family root is not loaded either', () => {
        const forest = buildSessionThreadForest([
            session({
                id: 'orphan-1',
                parentSessionId: 'never-loaded-parent',
                rootSessionId: 'never-loaded-root',
                sessionType: 'subagent',
                startedAt: minutesAgo(4),
            }),
        ]);

        expect(rootIdsOf(forest)).toEqual(['never-loaded-root']);
        expect(forest[0].placeholder).toBe(true);
        expect(forest[0].session.title).toBe(PLACEHOLDER_THREAD_TITLE);
        expect(rootIdsOf(forest[0].children)).toEqual(['orphan-1']);
        // Placeholder inherits its newest descendant's start time so it sorts in
        // the right era rather than falling to the bottom of the list.
        expect(Date.parse(forest[0].session.startedAt)).toBe(Date.parse(minutesAgo(4)));
    });

    it('never promotes a session with any parent/fork/root pointer to a top-level root', () => {
        const orphans: AgentSession[] = [
            session({ id: 'by-parent', parentSessionId: 'gone', startedAt: minutesAgo(3) }),
            session({ id: 'by-fork', forkParentSessionId: 'gone-fork', threadKind: 'fork', startedAt: minutesAgo(3) }),
            session({ id: 'by-subagent-parent', subagentParentId: 'gone-sub', sessionType: 'subagent', startedAt: minutesAgo(3) }),
            session({ id: 'by-root', rootSessionId: 'gone-root', startedAt: minutesAgo(3) }),
        ];
        const forest = buildSessionThreadForest(orphans);

        orphans.forEach(candidate => {
            expect(hasThreadParentLink(candidate)).toBe(true);
            expect(rootIdsOf(forest)).not.toContain(candidate.id);
            expect(findNode(forest, candidate.id)).toBeDefined();
        });
        // Every root here is a placeholder stand-in, never one of the children.
        expect(forest.every(node => node.placeholder)).toBe(true);
    });

    it('leaves a genuine root (self-referential rootSessionId, no parents) at top level', () => {
        const selfRoot = session({ id: 'root-1', rootSessionId: 'root-1' });
        expect(hasThreadParentLink(selfRoot)).toBe(false);
        expect(rootIdsOf(buildSessionThreadForest([selfRoot]))).toEqual(['root-1']);
    });

    it('is resilient to blank/missing lineage fields and duplicate rows', () => {
        const forest = buildSessionThreadForest([
            session({ id: 'root-1', rootSessionId: '' , parentSessionId: null, forkParentSessionId: null }),
            session({ id: 'root-1', rootSessionId: 'root-1' }),
            session({ id: 'child-1', parentSessionId: '   ', rootSessionId: 'root-1', sessionType: 'subagent' }),
        ]);

        expect(rootIdsOf(forest)).toEqual(['root-1']);
        expect(rootIdsOf(forest[0].children)).toEqual(['child-1']);
    });

    it('breaks lineage cycles instead of hanging', () => {
        const forest = buildSessionThreadForest([
            session({ id: 'a', parentSessionId: 'b', rootSessionId: 'a' }),
            session({ id: 'b', parentSessionId: 'a', rootSessionId: 'b' }),
        ]);

        expect(flatten(forest)).toHaveLength(2);
        expect(forest.length).toBeGreaterThan(0);
    });

    it('sorts roots and children newest-first', () => {
        const forest = buildSessionThreadForest([
            session({ id: 'root-old', rootSessionId: 'root-old', startedAt: minutesAgo(500) }),
            session({ id: 'root-new', rootSessionId: 'root-new', startedAt: minutesAgo(10) }),
            session({ id: 'child-old', parentSessionId: 'root-new', rootSessionId: 'root-new', startedAt: minutesAgo(9), sessionType: 'subagent' }),
            session({ id: 'child-new', parentSessionId: 'root-new', rootSessionId: 'root-new', startedAt: minutesAgo(2), sessionType: 'subagent' }),
        ]);

        expect(rootIdsOf(forest)).toEqual(['root-new', 'root-old']);
        expect(rootIdsOf(findNode(forest, 'root-new')!.children)).toEqual(['child-new', 'child-old']);
    });
});

describe('clicking a placeholder cannot produce a selected session', () => {
    // A placeholder's `session` is a synthetic stub (blank startedAt/model, logs: []).
    // If it were handed to openSession as the `fallback`, openSession's fallback
    // branch would setSelectedSession(stub) and render a complete-looking Session
    // Detail view built from nothing — instead of the correct error state. ~0.7% of
    // subagent parent refs dangle, and any transient fetch error takes the same path.
    const placeholderNode = (): SessionThreadNode => {
        const forest = buildSessionThreadForest([
            session({
                id: 'S-child',
                parentSessionId: 'S-gone-parent',
                rootSessionId: 'S-unloaded-root',
                sessionType: 'subagent',
            }),
        ]);
        expect(forest[0].placeholder).toBe(true);
        return forest[0];
    };

    it('supplies NO fallback row for a placeholder node', () => {
        expect(threadNodeOpenFallback(placeholderNode())).toBeUndefined();
    });

    it('still supplies the real row for a genuine node (normal open keeps working)', () => {
        const real = buildSessionThreadForest([session({ id: 'S-real', rootSessionId: 'S-real' })])[0];
        expect(real.placeholder).toBeUndefined();
        expect(threadNodeOpenFallback(real)).toBe(real.session);
    });

    it('drives openSession to the error branch, not the fallback branch, when the fetch returns null', () => {
        // Mirrors openSession's branch order: fetched → fallback → error.
        const openOutcome = (fetched: AgentSession | null, fallback: AgentSession | undefined) => {
            if (fetched) return { selected: fetched, error: null as string | null };
            if (fallback) return { selected: fallback, error: null as string | null };
            return { selected: null, error: 'Unable to load session' };
        };

        const node = placeholderNode();
        const outcome = openOutcome(null, threadNodeOpenFallback(node));
        expect(outcome.selected).toBeNull();
        expect(outcome.error).toContain('Unable to load session');

        // A placeholder whose real row IS fetchable must still open normally.
        const fetchedReal = session({ id: node.session.id, title: 'The real root', rootSessionId: node.session.id });
        expect(openOutcome(fetchedReal, threadNodeOpenFallback(node)).selected).toBe(fetchedReal);
    });

    it('never lets the placeholder stub reach a caller as a real session row', () => {
        const node = placeholderNode();
        // The stub is deliberately inert: no transcript, no start time, no model.
        expect(node.session.logs).toEqual([]);
        expect(node.session.model).toBe('');
        // ...which is exactly why it must not be a fallback.
        expect(threadNodeOpenFallback(node)).toBeUndefined();
    });
});

describe('mergeSessionsById — live slice merge', () => {
    it('dedupes by id and prefers the live (fresher) copy', () => {
        const paged = [session({ id: 's-1', updatedAt: minutesAgo(45), status: 'active' })];
        const live = [session({ id: 's-1', updatedAt: minutesAgo(1), status: 'active' })];

        const merged = mergeSessionsById(paged, live);

        expect(merged).toHaveLength(1);
        expect(merged[0].updatedAt).toBe(minutesAgo(1));
    });

    it('appends live-only rows and sorts the union newest-first', () => {
        const paged = [
            session({ id: 'p-new', startedAt: minutesAgo(20) }),
            session({ id: 'p-old', startedAt: minutesAgo(900) }),
        ];
        const live = [session({ id: 'l-newest', startedAt: minutesAgo(2) })];

        expect(mergeSessionsById(paged, live).map(s => s.id)).toEqual(['l-newest', 'p-new', 'p-old']);
    });

    it('returns the paged list untouched when the live slice is empty or absent', () => {
        const paged = [session({ id: 'p-1' })];
        expect(mergeSessionsById(paged, [])).toBe(paged);
        expect(mergeSessionsById(paged, undefined as unknown as AgentSession[])).toBe(paged);
    });
});

describe('Live In-Flight — live subagents outside the loaded page', () => {
    // Reproduces the SessionInspector pipeline: merge(paged, live) → forest →
    // roots filtered by threadNodeHasLiveSession.
    const liveInFlightRoots = (paged: AgentSession[], live: AgentSession[]): SessionThreadNode[] =>
        buildSessionThreadForest(mergeSessionsById(paged, live))
            .filter(node => threadNodeHasLiveSession(node, NOW));

    it('surfaces a live subagent that is absent from the paginated page, nested under its parent', () => {
        const pagedRoot = session({
            id: 'root-1',
            rootSessionId: 'root-1',
            status: 'active',
            startedAt: minutesAgo(1140),
            updatedAt: minutesAgo(600), // stale: would NOT qualify on its own
        });
        const liveSubagent = session({
            id: 'S-agent-live',
            parentSessionId: 'root-1',
            rootSessionId: 'root-1',
            sessionType: 'subagent',
            threadKind: 'subagent',
            status: 'active',
            startedAt: minutesAgo(6),
            updatedAt: minutesAgo(1),
        });

        // Without the live slice the subagent simply is not there.
        expect(liveInFlightRoots([pagedRoot], [])).toHaveLength(0);

        const roots = liveInFlightRoots([pagedRoot], [liveSubagent]);
        expect(rootIdsOf(roots)).toEqual(['root-1']);
        expect(rootIdsOf(roots[0].children)).toEqual(['S-agent-live']);
    });

    it('surfaces a live orchestrator that has aged off the loaded window', () => {
        const pagedOnly = [session({ id: 'p-1', rootSessionId: 'p-1', updatedAt: minutesAgo(300) })];
        const liveOrchestrator = session({
            id: 'S-724fa4e8',
            rootSessionId: 'S-724fa4e8',
            status: 'active',
            startedAt: minutesAgo(1160),
            updatedAt: minutesAgo(2),
        });

        expect(rootIdsOf(liveInFlightRoots(pagedOnly, [liveOrchestrator]))).toEqual(['S-724fa4e8']);
    });

    it('still withholds stale status=active zombies (10-minute freshness gate retained)', () => {
        const zombie = session({
            id: 'S-zombie',
            rootSessionId: 'S-zombie',
            status: 'active',
            startedAt: minutesAgo(5000),
            updatedAt: minutesAgo(4000),
        });

        expect(isSessionLiveInFlight(zombie, NOW)).toBe(false);
        expect(liveInFlightRoots([], [zombie])).toHaveLength(0);
    });

    it('treats a placeholder root as live when only its unloaded-family child is live', () => {
        const liveSubagent = session({
            id: 'S-agent-live',
            parentSessionId: 'unloaded-parent',
            rootSessionId: 'unloaded-root',
            sessionType: 'subagent',
            status: 'active',
            startedAt: minutesAgo(5),
            updatedAt: minutesAgo(1),
        });

        const roots = liveInFlightRoots([], [liveSubagent]);
        expect(roots).toHaveLength(1);
        expect(roots[0].placeholder).toBe(true);
        expect(rootIdsOf(roots[0].children)).toEqual(['S-agent-live']);
    });
});
