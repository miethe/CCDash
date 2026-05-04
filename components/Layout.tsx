import React, { useMemo, useState } from 'react';
import { LayoutDashboard, ListTodo, Settings, Terminal, Database, Bell, FileText, ChevronLeft, ChevronRight, LineChart, SlidersHorizontal, Activity, FolderTree, Command, TestTube2, Workflow, GitBranch, WifiOff, RefreshCw, BookOpen, LogOut, ShieldAlert, ShieldCheck, UserRound, Lock } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useData } from '../contexts/DataContext';
import { useAppRuntime } from '../contexts/AppRuntimeContext';
import { summarizeAuthMembershipContext, useAuthSession } from '../contexts/AuthSessionContext';
import { cn } from '../lib/utils';
import { ProjectSelector } from './ProjectSelector';

// Brand color for the Planning nav item active ring (matches planning-tokens.css --brand)
const PLANNING_BRAND = 'oklch(75% 0.14 195)';
const assetUrl = (path: string) => `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`;
const SIDEBAR_LOGO_SRC = assetUrl('/branding/ccdash-logo-primary.png');
const SIDEBAR_ICON_SRC = assetUrl('/branding/ccdash-app-icon.png');
const READ_ROLES = ['EA', 'TA', 'PM', 'PV', 'AA', 'owner', 'admin', 'operator', 'viewer', 'member', 'analyst', 'auditor'];
const OPERATOR_ROLES = ['EA', 'TA', 'PM', 'owner', 'admin', 'operator', 'project_maintainer', 'project-maintainer', 'project:maintainer'];
const ADMIN_ROLES = ['EA', 'TA', 'enterprise_admin', 'enterprise-admin', 'enterprise:admin', 'team_admin', 'team-admin', 'team:admin'];
const EXECUTION_ROLES = [...OPERATOR_ROLES, 'XA', 'execution_approver', 'execution-approver', 'execution:approver'];

const isLocalRuntimeAuth = (auth: ReturnType<typeof useAuthSession>): boolean => Boolean(
  auth.session?.localMode
  || auth.metadata?.localMode
  || auth.session?.authMode === 'local'
  || auth.metadata?.authMode === 'local'
);

const isStaticBearerRuntimeAuth = (auth: ReturnType<typeof useAuthSession>): boolean => (
  auth.session?.provider === 'static_bearer' || auth.metadata?.provider === 'static_bearer'
);

const runtimeLabelForAuth = (auth: ReturnType<typeof useAuthSession>): string => {
  if (isLocalRuntimeAuth(auth)) {
    return 'Local runtime';
  }
  if (isStaticBearerRuntimeAuth(auth)) {
    return 'Bearer-proxied runtime';
  }
  return 'Hosted session';
};

const sessionIdentityLabel = (auth: ReturnType<typeof useAuthSession>): string => {
  if (auth.principal?.displayName) return auth.principal.displayName;
  if (auth.principal?.email) return auth.principal.email;
  if (auth.principal?.subject) return auth.principal.subject;
  if (isLocalRuntimeAuth(auth)) return 'Local operator';
  if (isStaticBearerRuntimeAuth(auth)) return 'Container operator';
  return auth.metadata?.provider ? `${auth.metadata.provider} auth` : 'Not signed in';
};

const NavItem = ({
  to,
  icon: Icon,
  label,
  active,
  isCollapsed,
  planningHighlight,
  restricted,
  restrictedHint,
}: {
  to: string;
  icon: any;
  label: string;
  active: boolean;
  isCollapsed: boolean;
  planningHighlight?: boolean;
  restricted?: boolean;
  restrictedHint?: string;
}) => {
  const brandActiveStyle =
    planningHighlight && active
      ? {
          background: `color-mix(in oklab, ${PLANNING_BRAND} 16%, hsl(var(--sidebar)))`,
          borderColor: `color-mix(in oklab, ${PLANNING_BRAND} 40%, hsl(var(--sidebar-border)))`,
          color: PLANNING_BRAND,
          boxShadow: `0 0 0 1px color-mix(in oklab, ${PLANNING_BRAND} 22%, transparent), inset 0 0 12px color-mix(in oklab, ${PLANNING_BRAND} 8%, transparent)`,
        }
      : undefined;

  return (
    <Link
      to={to}
      aria-disabled={restricted && !active ? true : undefined}
      title={restricted ? restrictedHint : undefined}
      onClick={(event) => {
        if (restricted && !active) event.preventDefault();
      }}
      style={brandActiveStyle}
      className={cn(
        'group relative flex items-center gap-3 rounded-lg border px-4 py-3 transition-all duration-200',
        active && !planningHighlight
          ? 'border-sidebar-border bg-sidebar-accent text-sidebar-foreground shadow-sm'
          : !active
            ? 'border-transparent text-muted-foreground hover:bg-hover/60 hover:text-sidebar-foreground'
            : '',
        restricted && !active && 'cursor-not-allowed opacity-50 hover:bg-transparent hover:text-muted-foreground',
      )}
    >
      <Icon size={20} className="shrink-0" />
      {!isCollapsed && <span className="font-medium text-sm truncate">{label}</span>}
      {!isCollapsed && restricted && (
        <Lock size={13} className="ml-auto shrink-0 text-muted-foreground" aria-label="Permission required" />
      )}
      {isCollapsed && (
        <div className="absolute left-16 z-50 whitespace-nowrap rounded-lg border border-panel-border bg-surface-overlay px-2 py-1 text-xs text-panel-foreground opacity-0 shadow-lg pointer-events-none transition-opacity group-hover:opacity-100">
          {restricted ? `${label} - ${restrictedHint}` : label}
        </div>
      )}
    </Link>
  );
};

const AuthShellState: React.FC<{
  auth: ReturnType<typeof useAuthSession>;
}> = ({ auth }) => {
  const location = useLocation();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const runtimeLabel = runtimeLabelForAuth(auth);
  const isUnauthorized = auth.unauthorized;
  const title = auth.loading
    ? 'Checking session'
    : isUnauthorized
      ? 'Access restricted'
      : 'Sign in to continue';
  const message = auth.loading
    ? 'Validating your CCDash session.'
    : isUnauthorized
      ? 'Your session is active, but it does not have access to this CCDash workspace.'
      : 'Hosted CCDash requires an active browser session.';

  const redirectTo = useMemo(() => {
    const path = `${location.pathname}${location.search}${location.hash}`;
    return path && path !== '/' ? path : '/dashboard';
  }, [location.hash, location.pathname, location.search]);

  const handleSignIn = async () => {
    setBusy(true);
    setActionError(null);
    try {
      await auth.signIn({ redirectTo });
    } catch (cause) {
      const detail = cause instanceof Error ? cause.message : 'Sign-in could not be started.';
      setActionError(detail);
    } finally {
      setBusy(false);
    }
  };

  const handleSignOut = async () => {
    setBusy(true);
    setActionError(null);
    try {
      await auth.signOut();
    } catch (cause) {
      const detail = cause instanceof Error ? cause.message : 'Sign-out failed.';
      setActionError(detail);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-screen bg-app-background text-app-foreground">
      <main className="flex min-h-0 flex-1 items-center justify-center px-6 py-10">
        <section className="w-full max-w-md rounded-lg border border-panel-border bg-surface-elevated p-6 shadow-sm" aria-live="polite">
          <div className="mb-6 flex items-center gap-3">
            <img src={SIDEBAR_ICON_SRC} alt="CCDash" className="h-10 w-10 object-contain" />
            <div>
              <p className="text-xs font-semibold uppercase text-muted-foreground">{runtimeLabel}</p>
              <h1 className="text-xl font-semibold text-panel-foreground">{title}</h1>
            </div>
          </div>
          <p className="text-sm leading-6 text-muted-foreground">{message}</p>
          {actionError && (
            <div className="mt-4 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
              {actionError}
            </div>
          )}
          <div className="mt-6 flex flex-wrap items-center gap-3">
            {!auth.loading && !isUnauthorized && (
              <button
                type="button"
                onClick={handleSignIn}
                disabled={busy}
                className="inline-flex items-center gap-2 rounded-md border border-focus bg-focus px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-focus/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <ShieldCheck size={16} />
                {busy ? 'Starting...' : 'Sign in'}
              </button>
            )}
            {isUnauthorized && (
              <>
                <button
                  type="button"
                  onClick={auth.refreshSession}
                  disabled={busy}
                  className="inline-flex items-center gap-2 rounded-md border border-panel-border bg-surface-overlay px-3 py-2 text-sm font-medium text-panel-foreground transition-colors hover:bg-hover disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <RefreshCw size={16} />
                  Retry
                </button>
                <button
                  type="button"
                  onClick={handleSignOut}
                  disabled={busy}
                  className="inline-flex items-center gap-2 rounded-md border border-panel-border bg-surface-overlay px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-hover hover:text-panel-foreground disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <LogOut size={16} />
                  Sign out
                </button>
              </>
            )}
          </div>
        </section>
      </main>
    </div>
  );
};

const SessionContextPanel: React.FC<{
  auth: ReturnType<typeof useAuthSession>;
  isCollapsed: boolean;
}> = ({ auth, isCollapsed }) => {
  const runtimeLabel = runtimeLabelForAuth(auth);
  const identityLabel = sessionIdentityLabel(auth);
  const isLocal = runtimeLabel === 'Local runtime';
  const membershipContext = summarizeAuthMembershipContext(auth.session);
  const contextItems = [
    ...membershipContext.enterpriseIds.slice(0, 1).map(value => `Enterprise ${value}`),
    ...membershipContext.teamIds.slice(0, 1).map(value => `Team ${value}`),
    ...membershipContext.workspaceIds.slice(0, 1).map(value => `Workspace ${value}`),
    ...membershipContext.projectIds.slice(0, 1).map(value => `Project ${value}`),
  ];
  const roleLabel = membershipContext.roles.length > 0 ? membershipContext.roles.slice(0, 2).join(', ') : '';

  if (isCollapsed) {
    return (
      <div className="flex justify-center border-t border-sidebar-border p-4 text-muted-foreground" title={`${runtimeLabel}: ${identityLabel}`}>
        {isLocal ? <Terminal size={18} /> : <UserRound size={18} />}
      </div>
    );
  }

  return (
    <div className="border-t border-sidebar-border p-4">
      <div className="rounded-lg border border-sidebar-border bg-sidebar-accent/45 px-3 py-2">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
          {isLocal ? <Terminal size={14} /> : <ShieldCheck size={14} />}
          <span>{runtimeLabel}</span>
        </div>
        <div className="mt-1 truncate text-sm font-medium text-sidebar-foreground">{identityLabel}</div>
        {isLocal ? (
          <div className="mt-2 rounded-md border border-sidebar-border bg-sidebar/80 px-2 py-1 text-xs text-muted-foreground">
            Local mode keeps workspace actions available.
          </div>
        ) : auth.authenticated && (
          <div className="mt-2 space-y-1 text-xs text-muted-foreground">
            {contextItems.length > 0 && (
              <div className="truncate" title={contextItems.join(' / ')}>
                {contextItems.join(' / ')}
              </div>
            )}
            {roleLabel && (
              <div className="truncate" title={membershipContext.roles.join(', ')}>
                Roles: {roleLabel}
              </div>
            )}
          </div>
        )}
        {!isLocal && auth.authenticated && (
          <button
            type="button"
            onClick={() => void auth.signOut()}
            className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-sidebar-border bg-sidebar px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-hover hover:text-sidebar-foreground"
          >
            <LogOut size={13} />
            Sign out
          </button>
        )}
      </div>
    </div>
  );
};

const AuthenticatedLayout: React.FC<{ children: React.ReactNode; auth: ReturnType<typeof useAuthSession> }> = ({ children, auth }) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const location = useLocation();
  const { notifications, error } = useData();
  const { runtimeUnreachable, retryRuntime } = useAppRuntime();
  const isStaticBearerRuntime = isStaticBearerRuntimeAuth(auth);
  const unreadCount = notifications.filter(n => !n.isRead).length;
  const isPlanningRoute = location.pathname.startsWith('/planning');
  const authDataError = error?.includes('API error: 401') || error?.includes('API error: 403');
  const canAccessExecution = isStaticBearerRuntime || auth.hasPermission({ scopes: ['execution:read'], roles: [...READ_ROLES, ...EXECUTION_ROLES] });
  const canAccessCodebase = isStaticBearerRuntime || auth.hasPermission({ scopes: ['codebase:read_tree', 'codebase:file_read', 'codebase:activity_read'], roles: READ_ROLES });
  const canAccessSessionMappings = isStaticBearerRuntime || auth.hasPermission({ scopes: ['session_mapping:read', 'session_mapping:diagnose'], roles: READ_ROLES });
  const canAccessOperations = isStaticBearerRuntime || auth.hasPermission({ scopes: ['cache:read_status', 'cache.operation:read'], roles: READ_ROLES });
  const canAccessSettings = isStaticBearerRuntime || auth.hasPermission({ scopes: ['admin.settings:read', 'project:update', 'integration:read'], roles: [...ADMIN_ROLES, ...OPERATOR_ROLES, 'IO', 'integration_operator'] });
  const permissionHint = 'Permission hint only; backend authorization remains authoritative.';

  return (
    <div className="flex h-screen overflow-hidden bg-app-background text-app-foreground">
      {/* Sidebar */}
      <aside
        className={cn(
          'relative flex shrink-0 flex-col overflow-x-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-all duration-300 ease-in-out',
          isCollapsed ? 'w-20' : 'w-64',
        )}
      >
        <div className="flex items-center justify-between overflow-hidden border-b border-sidebar-border p-6">
          <div className="flex min-w-0 shrink-0 items-center">
            {isCollapsed ? (
              <img
                src={SIDEBAR_ICON_SRC}
                alt="CCDash"
                className="h-9 w-9 shrink-0 object-contain"
              />
            ) : (
              <img
                src={SIDEBAR_LOGO_SRC}
                alt="CCDash"
                className="h-10 w-auto max-w-[180px] object-contain"
              />
            )}
          </div>
        </div>

        {!isCollapsed && <ProjectSelector />}

        {/* Collapse Toggle */}
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="absolute -right-3 top-20 z-40 flex h-6 w-6 items-center justify-center rounded-full border border-panel-border bg-surface-elevated text-muted-foreground transition-all hover:border-focus hover:bg-hover hover:text-panel-foreground"
        >
          {isCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>

        <nav className="flex-1 p-4 space-y-1 overflow-y-auto overflow-x-hidden">
          <NavItem to="/dashboard" icon={LayoutDashboard} label="Overview" active={location.pathname === '/dashboard'} isCollapsed={isCollapsed} />
          <NavItem to="/planning" icon={GitBranch} label="Planning" active={location.pathname.startsWith('/planning')} isCollapsed={isCollapsed} planningHighlight />
          <NavItem to="/board" icon={ListTodo} label="Project Board" active={location.pathname === '/board'} isCollapsed={isCollapsed} />
          <NavItem to="/execution" icon={Command} label="Execution" active={location.pathname === '/execution'} isCollapsed={isCollapsed} restricted={!canAccessExecution} restrictedHint={permissionHint} />
          <NavItem to="/tests" icon={TestTube2} label="Testing" active={location.pathname === '/tests'} isCollapsed={isCollapsed} />
          <NavItem to="/plans" icon={FileText} label="Documents" active={location.pathname === '/plans'} isCollapsed={isCollapsed} />
          <NavItem to="/docs" icon={BookOpen} label="Docs" active={location.pathname === '/docs'} isCollapsed={isCollapsed} />
          <NavItem to="/sessions" icon={Terminal} label="Session Forensics" active={location.pathname === '/sessions'} isCollapsed={isCollapsed} />
          <NavItem to="/codebase" icon={FolderTree} label="Codebase Explorer" active={location.pathname === '/codebase'} isCollapsed={isCollapsed} restricted={!canAccessCodebase} restrictedHint={permissionHint} />
          <NavItem to="/session-mappings" icon={SlidersHorizontal} label="Session Mappings" active={location.pathname === '/session-mappings'} isCollapsed={isCollapsed} restricted={!canAccessSessionMappings} restrictedHint={permissionHint} />
          <NavItem to="/ops" icon={Activity} label="Operations" active={location.pathname === '/ops'} isCollapsed={isCollapsed} restricted={!canAccessOperations} restrictedHint={permissionHint} />
          <NavItem to="/analytics" icon={LineChart} label="Analytics" active={location.pathname === '/analytics'} isCollapsed={isCollapsed} />
          <NavItem to="/workflows" icon={Workflow} label="Workflows" active={location.pathname.startsWith('/workflows')} isCollapsed={isCollapsed} />
          <NavItem to="/skills" icon={Database} label="SkillMeat Context" active={location.pathname === '/skills'} isCollapsed={isCollapsed} />

          <div id="sidebar-portal" className={`mt-6 w-full min-w-0 overflow-x-hidden border-t border-sidebar-border pt-6 empty:hidden ${isCollapsed ? 'hidden' : ''}`}></div>
        </nav>

        <div className="space-y-1 border-t border-sidebar-border p-4">
          <Link
            to="/settings"
            aria-disabled={!canAccessSettings ? true : undefined}
            title={!canAccessSettings ? permissionHint : undefined}
            onClick={(event) => {
              if (!canAccessSettings && location.pathname !== '/settings') event.preventDefault();
            }}
            className={cn(
              'group relative flex items-center justify-between rounded-lg border px-4 py-3 transition-colors',
              location.pathname === '/settings'
                ? 'border-sidebar-border bg-sidebar-accent text-sidebar-foreground shadow-sm'
                : 'border-transparent text-muted-foreground hover:bg-hover/60 hover:text-sidebar-foreground',
              !canAccessSettings && location.pathname !== '/settings' && 'cursor-not-allowed opacity-50 hover:bg-transparent hover:text-muted-foreground',
            )}
          >
            <div className="flex items-center gap-3">
              <Bell size={20} className="shrink-0" />
              {!isCollapsed && <span className="font-medium text-sm">Notifications</span>}
            </div>
            {unreadCount > 0 && (
              <span className={`${isCollapsed ? 'absolute -top-1 -right-1' : ''} min-w-[18px] rounded-full bg-danger px-1.5 py-0.5 text-center text-[10px] font-bold text-danger-foreground`}>
                {unreadCount}
              </span>
            )}
          </Link>
          <NavItem to="/settings" icon={Settings} label="Settings" active={location.pathname === '/settings'} isCollapsed={isCollapsed} restricted={!canAccessSettings} restrictedHint={permissionHint} />
        </div>
        <SessionContextPanel auth={auth} isCollapsed={isCollapsed} />
      </aside>

      {/* Main Content */}
      <main className="flex min-w-0 flex-1 flex-col overflow-x-auto overflow-y-hidden bg-app-background">
        {authDataError && (
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-warning/30 bg-warning/10 px-4 py-2 text-sm text-warning">
            <div className="flex items-center gap-2">
              <ShieldAlert size={14} className="shrink-0" />
              <span>Session access changed. Refresh your session or sign in again.</span>
            </div>
            <button
              onClick={auth.refreshSession}
              className="flex items-center gap-1.5 rounded border border-warning/40 bg-warning/10 px-2.5 py-1 text-xs font-medium text-warning transition-colors hover:bg-warning/20"
            >
              <RefreshCw size={12} />
              Refresh
            </button>
          </div>
        )}
        {/* FE-104: Backend disconnected banner */}
        {runtimeUnreachable && (
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
            <div className="flex items-center gap-2">
              <WifiOff size={14} className="shrink-0" />
              <span>Backend disconnected — live updates paused.</span>
            </div>
            <button
              onClick={retryRuntime}
              className="flex items-center gap-1.5 rounded border border-danger/40 bg-danger/10 px-2.5 py-1 text-xs font-medium text-danger transition-colors hover:bg-danger/20"
            >
              <RefreshCw size={12} />
              Retry
            </button>
          </div>
        )}
        <div
          className={cn(
            'flex-1 min-w-[1024px] h-full min-h-0 scroll-smooth',
            isPlanningRoute ? 'overflow-hidden p-0' : 'overflow-y-auto p-4 md:p-8',
          )}
        >
          {children}
        </div>
      </main>
    </div>
  );
};

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const auth = useAuthSession();
  const canUseRuntimeWithoutHostedLogin = isLocalRuntimeAuth(auth) || isStaticBearerRuntimeAuth(auth);

  if (auth.loading) {
    return <AuthShellState auth={auth} />;
  }

  if (!canUseRuntimeWithoutHostedLogin && (auth.unauthenticated || auth.unauthorized)) {
    return <AuthShellState auth={auth} />;
  }

  return <AuthenticatedLayout auth={auth}>{children}</AuthenticatedLayout>;
};
