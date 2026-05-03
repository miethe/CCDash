import { describe, expect, it } from 'vitest';

import type { AuthSessionResponse } from '../../types';
import { deriveAuthSessionStatus, evaluateAuthPermission } from '../AuthSessionContext';
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
});
