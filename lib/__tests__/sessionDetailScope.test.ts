import { describe, expect, it } from 'vitest';
import { sameSessionScope, sessionDetailPollKey, scopedSessionFallback } from '../sessionDetailScope';
import type { AgentSession } from '../../types';
import { readFileSync } from 'node:fs';

const row = (projectId: string) => ({ id: 'duplicate', projectId, status: 'active', logs: [] } as unknown as AgentSession);

describe('active session polling preserves explicit project scope', () => {
    it('separates duplicate IDs and rejects an old project polling response', () => {
        const activeProjectRow = row('active-project');
        const selectedRow = row('linked-project');
        expect(sessionDetailPollKey(selectedRow.id, selectedRow.projectId!)).not.toEqual(sessionDetailPollKey(activeProjectRow.id, activeProjectRow.projectId!));
        expect(sameSessionScope(selectedRow, activeProjectRow)).toBe(false);
        expect(sameSessionScope(selectedRow, row('linked-project'))).toBe(true);
        expect(scopedSessionFallback([activeProjectRow], 'duplicate', 'linked-project')).toBeUndefined();
        expect(scopedSessionFallback([activeProjectRow, selectedRow], 'duplicate', 'linked-project')).toBe(selectedRow);
    });
    it('wires explicit scope into polling, merge-back and optimistic fallback', () => {
        const source = readFileSync(new URL('../../components/SessionInspector.tsx', import.meta.url), 'utf8');
        expect(source).toContain('queryKey: sessionDetailPollKey(selectedSessionId, selectedSessionProjectId)');
        expect(source).toContain('getSessionById(selectedSessionId!, { force: true, projectId: selectedSessionProjectId || undefined })');
        expect(source).toContain('sameSessionScope(current, polledSessionDetail)');
        expect(source).toContain('scopedSessionFallback(sessions, requestedSessionId, requestedProjectId)');
    });
});
