import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type {
  AuthLoginStartResponse,
  AuthProviderMetadataResponse,
  AuthSessionMembership,
  AuthSessionResponse,
  AuthSessionStatus,
} from '../types';
import { isApiError } from '../services/apiClient';
import { useDataClient } from './DataClientContext';

export interface AuthPermissionRequest {
  scopes?: string[];
  groups?: string[];
  roles?: string[];
  memberships?: Array<Partial<Pick<AuthSessionMembership, 'workspaceId' | 'role' | 'scopeType' | 'scopeId' | 'enterpriseId' | 'teamId'>>>;
  requireAll?: boolean;
}

export interface AuthSessionMembershipContext {
  enterpriseIds: string[];
  teamIds: string[];
  workspaceIds: string[];
  projectIds: string[];
  roles: string[];
}

export interface AuthSignInOptions {
  redirectTo?: string;
  redirect?: boolean;
}

interface AuthSessionContextValue {
  status: AuthSessionStatus;
  loading: boolean;
  authenticated: boolean;
  unauthenticated: boolean;
  unauthorized: boolean;
  metadata: AuthProviderMetadataResponse | null;
  session: AuthSessionResponse | null;
  principal: AuthSessionResponse | null;
  error: unknown;
  refreshSession: () => Promise<void>;
  signIn: (options?: AuthSignInOptions) => Promise<AuthLoginStartResponse>;
  signOut: () => Promise<void>;
  /**
   * Client-side affordance only. Backend authorization remains authoritative.
   */
  hasPermission: (request: string | AuthPermissionRequest) => boolean;
}

const AuthSessionContext = createContext<AuthSessionContextValue | null>(null);

const EMPTY_SESSION: AuthSessionResponse | null = null;

export function deriveAuthSessionStatus(session: AuthSessionResponse | null, error?: unknown): AuthSessionStatus {
  if (isApiError(error)) {
    if (error.authClassification === 'unauthenticated') return 'unauthenticated';
    if (error.authClassification === 'unauthorized') return 'unauthorized';
  }
  if (session?.authenticated) return 'authenticated';
  return 'unauthenticated';
}

export function isLocalAuthSession(session: AuthSessionResponse | null): boolean {
  return Boolean(session?.localMode || session?.authMode === 'local' || session?.provider === 'local');
}

export function summarizeAuthMembershipContext(session: AuthSessionResponse | null): AuthSessionMembershipContext {
  const memberships = session?.memberships ?? [];
  const enterpriseIds = new Set<string>();
  const teamIds = new Set<string>();
  const workspaceIds = new Set<string>();
  const projectIds = new Set<string>();
  const roles = new Set<string>();

  memberships.forEach(membership => {
    if (membership.enterpriseId) enterpriseIds.add(membership.enterpriseId);
    if (membership.teamId) teamIds.add(membership.teamId);
    if (membership.workspaceId) workspaceIds.add(membership.workspaceId);
    if (membership.role) roles.add(membership.role);
    if (membership.scopeType === 'enterprise' && membership.scopeId) enterpriseIds.add(membership.scopeId);
    if (membership.scopeType === 'team' && membership.scopeId) teamIds.add(membership.scopeId);
    if (membership.scopeType === 'workspace' && membership.scopeId) workspaceIds.add(membership.scopeId);
    if (membership.scopeType === 'project' && membership.scopeId) projectIds.add(membership.scopeId);
  });

  return {
    enterpriseIds: Array.from(enterpriseIds).sort(),
    teamIds: Array.from(teamIds).sort(),
    workspaceIds: Array.from(workspaceIds).sort(),
    projectIds: Array.from(projectIds).sort(),
    roles: Array.from(roles).sort(),
  };
}

export function evaluateAuthPermission(
  session: AuthSessionResponse | null,
  request: string | AuthPermissionRequest,
): boolean {
  if (isLocalAuthSession(session)) {
    return true;
  }

  if (!session?.authenticated) {
    return false;
  }

  const scopes = new Set(session.scopes ?? []);
  const groups = new Set(session.groups ?? []);
  const memberships = session.memberships ?? [];
  const roles = new Set(memberships.map(membership => membership.role).filter(Boolean));

  if (typeof request === 'string') {
    return scopes.has(request) || groups.has(request) || roles.has(request);
  }

  const requireAll = request.requireAll ?? false;
  const checks: boolean[] = [];
  const matchCollection = (actual: Set<string>, requested?: string[]): boolean | null => {
    const values = (requested ?? []).filter(Boolean);
    if (values.length === 0) return null;
    return requireAll ? values.every(value => actual.has(value)) : values.some(value => actual.has(value));
  };

  const scopeMatch = matchCollection(scopes, request.scopes);
  if (scopeMatch !== null) checks.push(scopeMatch);

  const groupMatch = matchCollection(groups, request.groups);
  if (groupMatch !== null) checks.push(groupMatch);

  const roleMatch = matchCollection(roles, request.roles);
  if (roleMatch !== null) checks.push(roleMatch);

  const membershipRequests = request.memberships ?? [];
  if (membershipRequests.length > 0) {
    const matchesMembership = (expected: AuthPermissionRequest['memberships'][number]): boolean => (
      memberships.some(actual => (
        Object.entries(expected).every(([key, value]) => {
          if (value === undefined || value === null || value === '') return true;
          return actual[key as keyof AuthSessionMembership] === value;
        })
      ))
    );
    checks.push(
      requireAll
        ? membershipRequests.every(matchesMembership)
        : membershipRequests.some(matchesMembership),
    );
  }

  if (checks.length === 0) {
    return false;
  }
  return requireAll ? checks.every(Boolean) : checks.some(Boolean);
}

export const AuthSessionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const client = useDataClient();
  const [status, setStatus] = useState<AuthSessionStatus>('loading');
  const [metadata, setMetadata] = useState<AuthProviderMetadataResponse | null>(null);
  const [session, setSession] = useState<AuthSessionResponse | null>(EMPTY_SESSION);
  const [error, setError] = useState<unknown>(null);

  const refreshSession = useCallback(async () => {
    setStatus('loading');
    setError(null);
    try {
      const [nextMetadata, nextSession] = await Promise.all([
        client.getAuthMetadata(),
        client.getAuthSession(),
      ]);
      setMetadata(nextMetadata);
      setSession(nextSession);
      setStatus(deriveAuthSessionStatus(nextSession));
    } catch (cause) {
      setSession(null);
      setError(cause);
      setStatus(deriveAuthSessionStatus(null, cause));
    }
  }, [client]);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  const signIn = useCallback(async (options: AuthSignInOptions = {}) => {
    const response = await client.login({
      redirect: false,
      redirectTo: options.redirectTo,
    });
    if (options.redirect !== false && typeof window !== 'undefined') {
      window.location.assign(response.authorizationUrl);
    }
    return response;
  }, [client]);

  const signOut = useCallback(async () => {
    await client.logout();
    await refreshSession();
  }, [client, refreshSession]);

  const hasPermission = useCallback((request: string | AuthPermissionRequest) => (
    evaluateAuthPermission(session, request)
  ), [session]);

  const contextValue = useMemo<AuthSessionContextValue>(() => ({
    status,
    loading: status === 'loading',
    authenticated: status === 'authenticated',
    unauthenticated: status === 'unauthenticated',
    unauthorized: status === 'unauthorized',
    metadata,
    session,
    principal: session?.authenticated ? session : null,
    error,
    refreshSession,
    signIn,
    signOut,
    hasPermission,
  }), [error, hasPermission, metadata, refreshSession, session, signIn, signOut, status]);

  return (
    <AuthSessionContext.Provider value={contextValue}>
      {children}
    </AuthSessionContext.Provider>
  );
};

export function useAuthSession(): AuthSessionContextValue {
  const ctx = useContext(AuthSessionContext);
  if (!ctx) {
    throw new Error('useAuthSession must be used within an AuthSessionProvider');
  }
  return ctx;
}
