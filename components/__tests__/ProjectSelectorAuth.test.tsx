import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  auth: {} as any,
  data: {} as any,
}));

vi.mock('../../contexts/AuthSessionContext', () => ({
  useAuthSession: () => state.auth,
  summarizeAuthMembershipContext: (session: any) => {
    const memberships = session?.memberships ?? [];
    return {
      enterpriseIds: Array.from(new Set(memberships.map((m: any) => m.enterpriseId || (m.scopeType === 'enterprise' ? m.scopeId : '')).filter(Boolean))).sort(),
      teamIds: Array.from(new Set(memberships.map((m: any) => m.teamId || (m.scopeType === 'team' ? m.scopeId : '')).filter(Boolean))).sort(),
      workspaceIds: Array.from(new Set(memberships.map((m: any) => m.workspaceId || (m.scopeType === 'workspace' ? m.scopeId : '')).filter(Boolean))).sort(),
      projectIds: Array.from(new Set(memberships.map((m: any) => (m.scopeType === 'project' ? m.scopeId : '')).filter(Boolean))).sort(),
      roles: Array.from(new Set(memberships.map((m: any) => m.role).filter(Boolean))).sort(),
    };
  },
}));

vi.mock('../../contexts/DataContext', () => ({
  useData: () => state.data,
}));

import { ProjectSelector } from '../ProjectSelector';

const projects = [
  { id: 'project-1', name: 'Project One', path: '/tmp/project-one' },
  { id: 'project-2', name: 'Project Two', path: '/tmp/project-two' },
];

const baseSession = {
  authenticated: true,
  subject: 'oidc:user-1',
  displayName: 'User One',
  email: 'user@example.test',
  groups: [],
  scopes: [],
  memberships: [],
  provider: 'oidc',
  authMode: 'oidc',
  localMode: false,
};

describe('ProjectSelector permission-aware workspace UX', () => {
  beforeEach(() => {
    state.data = {
      projects,
      activeProject: projects[0],
      switchProject: vi.fn(),
    };
    state.auth = {
      metadata: { localMode: false },
      session: baseSession,
      hasPermission: vi.fn(() => true),
    };
  });

  it('keeps local mode project creation visible and low friction', () => {
    state.auth = {
      ...state.auth,
      metadata: { localMode: true },
      session: {
        ...baseSession,
        provider: 'local',
        authMode: 'local',
        localMode: true,
      },
      hasPermission: vi.fn(() => true),
    };

    const html = renderToStaticMarkup(<ProjectSelector initialOpen />);

    expect(html).toContain('Local workspace controls');
    expect(html).toContain('Add New Project');
    expect(html).not.toContain('Add Project Requires Permission');
  });

  it('disables the add-project trigger for hosted sessions without project creation permission', () => {
    state.auth = {
      ...state.auth,
      hasPermission: vi.fn(() => false),
    };

    const html = renderToStaticMarkup(<ProjectSelector initialOpen />);

    expect(html).toContain('Add Project Requires Permission');
    expect(html).toContain('disabled=""');
    expect(html).toContain('Permission hint only; backend authorization remains authoritative.');
  });

  it('renders enterprise, team, workspace, and active project role context', () => {
    state.auth = {
      ...state.auth,
      session: {
        ...baseSession,
        memberships: [
          {
            workspaceId: 'workspace-1',
            role: 'PM',
            scopeType: 'project',
            scopeId: 'project-1',
            enterpriseId: 'enterprise-1',
            teamId: 'team-1',
          },
        ],
      },
    };

    const html = renderToStaticMarkup(<ProjectSelector initialOpen />);

    expect(html).toContain('Ent enterprise-1 / Team team-1 / Workspace workspace-1 / Role PM');
  });
});
