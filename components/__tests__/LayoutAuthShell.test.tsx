import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  auth: {} as any,
  dataShouldThrow: false,
  useData: vi.fn(),
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
  useData: () => {
    state.useData();
    if (state.dataShouldThrow) {
      throw new Error('app data should not be read for this auth state');
    }
    return {
      notifications: [],
      error: null,
    };
  },
}));

vi.mock('../../contexts/AppRuntimeContext', () => ({
  useAppRuntime: () => ({
    runtimeUnreachable: false,
    retryRuntime: vi.fn(),
  }),
}));

vi.mock('../ProjectSelector', () => ({
  ProjectSelector: () => <div>Project selector</div>,
}));

import { Layout } from '../Layout';

const baseAuth = () => ({
  status: 'authenticated',
  loading: false,
  authenticated: true,
  unauthenticated: false,
  unauthorized: false,
  metadata: {
    provider: 'oidc',
    runtimeProfile: 'api',
    authMode: 'oidc',
    hosted: true,
    localMode: false,
  },
  session: {
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
  },
  principal: {
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
  },
  error: null,
  refreshSession: vi.fn(),
  signIn: vi.fn(),
  signOut: vi.fn(),
  hasPermission: vi.fn(() => true),
});

function renderLayout(path = '/dashboard') {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <Layout>
        <div>APP CONTENT</div>
      </Layout>
    </MemoryRouter>,
  );
}

describe('Layout auth shell', () => {
  beforeEach(() => {
    state.auth = baseAuth();
    state.dataShouldThrow = false;
    state.useData.mockClear();
  });

  it('passes local-mode sessions through to the app shell without sign-in friction', () => {
    state.auth = {
      ...baseAuth(),
      metadata: {
        provider: 'local',
        runtimeProfile: 'local',
        authMode: 'local',
        hosted: false,
        localMode: true,
      },
      session: {
        ...baseAuth().session,
        subject: 'local:local-operator',
        displayName: 'Local Operator',
        provider: 'local',
        authMode: 'local',
        localMode: true,
      },
      principal: {
        ...baseAuth().principal,
        subject: 'local:local-operator',
        displayName: 'Local Operator',
        provider: 'local',
        authMode: 'local',
        localMode: true,
      },
    };

    const html = renderLayout();

    expect(html).toContain('APP CONTENT');
    expect(html).toContain('Local runtime');
    expect(html).toContain('Local Operator');
    expect(html).not.toContain('Sign in');
    expect(state.useData).toHaveBeenCalledTimes(1);
  });

  it('renders hosted unauthenticated sign-in state without reading app data', () => {
    state.dataShouldThrow = true;
    state.auth = {
      ...baseAuth(),
      status: 'unauthenticated',
      authenticated: false,
      unauthenticated: true,
      session: {
        ...baseAuth().session,
        authenticated: false,
        subject: null,
        displayName: null,
        email: null,
      },
      principal: null,
    };

    const html = renderLayout('/analytics');

    expect(html).toContain('Hosted session');
    expect(html).toContain('Sign in to continue');
    expect(html).toContain('Sign in');
    expect(html).not.toContain('APP CONTENT');
    expect(state.useData).not.toHaveBeenCalled();
  });

  it('renders hosted sign-out affordance for authenticated sessions', () => {
    const html = renderLayout();

    expect(html).toContain('APP CONTENT');
    expect(html).toContain('Hosted session');
    expect(html).toContain('User One');
    expect(html).toContain('Sign out');
  });

  it('renders hosted membership context in the session shell', () => {
    state.auth = {
      ...baseAuth(),
      session: {
        ...baseAuth().session,
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
      principal: {
        ...baseAuth().principal,
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

    const html = renderLayout();

    expect(html).toContain('Enterprise enterprise-1 / Team team-1 / Workspace workspace-1 / Project project-1');
    expect(html).toContain('Roles: PM');
  });

  it('marks protected hosted nav items as permission-gated without blocking the shell', () => {
    state.auth = {
      ...baseAuth(),
      hasPermission: vi.fn(() => false),
    };

    const html = renderLayout('/dashboard');

    expect(html).toContain('APP CONTENT');
    expect(html).toContain('Execution');
    expect(html).toContain('aria-disabled="true"');
    expect(html).toContain('Permission hint only; backend authorization remains authoritative.');
  });

  it('renders shell-level messaging for unauthorized hosted sessions', () => {
    state.dataShouldThrow = true;
    state.auth = {
      ...baseAuth(),
      status: 'unauthorized',
      authenticated: false,
      unauthenticated: false,
      unauthorized: true,
      principal: null,
    };

    const html = renderLayout('/settings');

    expect(html).toContain('Access restricted');
    expect(html).toContain('Retry');
    expect(html).toContain('Sign out');
    expect(html).not.toContain('APP CONTENT');
    expect(state.useData).not.toHaveBeenCalled();
  });
});
