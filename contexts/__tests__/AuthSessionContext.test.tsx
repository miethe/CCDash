import { describe, expect, it } from 'vitest';

import type { AuthSessionResponse } from '../../types';
import {
  deriveAuthSessionStatus,
  evaluateAuthPermission,
  isLocalAuthSession,
  summarizeAuthMembershipContext,
} from '../AuthSessionContext';
import { ApiError } from '../../services/apiClient';

const authenticatedSession: AuthSessionResponse = {
  authenticated: true,
  subject: 'oidc:user-123',
  displayName: 'User One',
  email: 'user@example.test',
  groups: ['engineering', 'admin'],
  scopes: ['project:read', 'feature:update'],
  memberships: [
    {
      workspaceId: 'workspace-1',
      role: 'owner',
      scopeType: 'workspace',
      enterpriseId: 'enterprise-1',
    },
    {
      workspaceId: 'workspace-1',
      role: 'reviewer',
      scopeType: 'project',
      scopeId: 'project-1',
      bindingId: 'binding-1',
    },
  ],
  provider: 'oidc',
  authMode: 'oidc',
  localMode: false,
};

describe('AuthSessionContext helpers', () => {
  it('derives status from session payloads and auth-classified errors', () => {
    expect(deriveAuthSessionStatus(authenticatedSession)).toBe('authenticated');
    expect(deriveAuthSessionStatus({ ...authenticatedSession, authenticated: false })).toBe('unauthenticated');
    expect(deriveAuthSessionStatus(null, new ApiError({
      status: 401,
      statusText: 'Unauthorized',
      url: '/api/projects',
      detail: { code: 'principal_unauthenticated' },
    }))).toBe('unauthenticated');
    expect(deriveAuthSessionStatus(null, new ApiError({
      status: 403,
      statusText: 'Forbidden',
      url: '/api/projects',
      detail: { code: 'permission_not_granted' },
    }))).toBe('unauthorized');
  });

  it('checks scopes, groups, roles, and membership selectors without granting backend authority', () => {
    expect(evaluateAuthPermission(authenticatedSession, 'project:read')).toBe(true);
    expect(evaluateAuthPermission(authenticatedSession, 'engineering')).toBe(true);
    expect(evaluateAuthPermission(authenticatedSession, 'owner')).toBe(true);
    expect(evaluateAuthPermission(authenticatedSession, { groups: ['admin'] })).toBe(true);
    expect(evaluateAuthPermission(authenticatedSession, {
      memberships: [{ scopeType: 'project', scopeId: 'project-1', role: 'reviewer' }],
    })).toBe(true);
    expect(evaluateAuthPermission(authenticatedSession, {
      scopes: ['project:read', 'feature:update'],
      groups: ['admin'],
      requireAll: true,
    })).toBe(true);
    expect(evaluateAuthPermission(authenticatedSession, {
      scopes: ['project:read', 'admin.settings:update'],
      requireAll: true,
    })).toBe(false);
    expect(evaluateAuthPermission({ ...authenticatedSession, authenticated: false }, 'project:read')).toBe(false);
  });

  it('keeps local mode permissive for UI affordances only', () => {
    const localSession: AuthSessionResponse = {
      ...authenticatedSession,
      authenticated: false,
      groups: [],
      scopes: [],
      memberships: [],
      provider: 'local',
      authMode: 'local',
      localMode: true,
    };

    expect(isLocalAuthSession(localSession)).toBe(true);
    expect(evaluateAuthPermission(localSession, 'admin.settings:update')).toBe(true);
    expect(evaluateAuthPermission(localSession, { scopes: ['execution.run:create'] })).toBe(true);
  });

  it('summarizes enterprise, team, workspace, project, and role context from memberships', () => {
    const context = summarizeAuthMembershipContext({
      ...authenticatedSession,
      memberships: [
        ...authenticatedSession.memberships,
        {
          workspaceId: 'workspace-2',
          role: 'viewer',
          scopeType: 'team',
          scopeId: 'team-1',
          enterpriseId: 'enterprise-1',
          teamId: 'team-1',
        },
      ],
    });

    expect(context.enterpriseIds).toEqual(['enterprise-1']);
    expect(context.teamIds).toEqual(['team-1']);
    expect(context.workspaceIds).toEqual(['workspace-1', 'workspace-2']);
    expect(context.projectIds).toEqual(['project-1']);
    expect(context.roles).toEqual(['owner', 'reviewer', 'viewer']);
  });
});
