import React, { useState } from 'react';
import { LayoutDashboard, ListTodo, Settings, Box, Terminal, Database, Bell, FileText, ChevronLeft, ChevronRight, LineChart, SlidersHorizontal, Activity, FolderTree, Command, TestTube2, Workflow, GitBranch } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useData } from '../contexts/DataContext';
import { cn } from '../lib/utils';
import { ProjectSelector } from './ProjectSelector';

const NavItem = ({ to, icon: Icon, label, active, isCollapsed }: { to: string; icon: any; label: string; active: boolean; isCollapsed: boolean }) => (
  <Link
    to={to}
    className={cn(
      'group relative flex items-center gap-3 rounded-lg border px-4 py-3 transition-all duration-200',
      active
        ? 'border-sidebar-border bg-sidebar-accent text-sidebar-foreground shadow-sm'
        : 'border-transparent text-muted-foreground hover:bg-hover/60 hover:text-sidebar-foreground',
    )}
  >
    <Icon size={20} className="shrink-0" />
    {!isCollapsed && <span className="font-medium text-sm truncate">{label}</span>}
    {isCollapsed && (
      <div className="absolute left-16 z-50 whitespace-nowrap rounded-lg border border-panel-border bg-surface-overlay px-2 py-1 text-xs text-panel-foreground opacity-0 shadow-lg pointer-events-none transition-opacity group-hover:opacity-100">
        {label}
      </div>
    )}
  </Link>
);

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const location = useLocation();
  const { notifications } = useData();
  const unreadCount = notifications.filter(n => !n.isRead).length;

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
          <div className="flex shrink-0 items-center gap-2 text-info">
            <Box size={24} className="fill-info/15" />
            {!isCollapsed && <h1 className="text-xl font-bold tracking-tight text-sidebar-foreground">CCDash</h1>}
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
          <NavItem to="/" icon={LayoutDashboard} label="Overview" active={location.pathname === '/'} isCollapsed={isCollapsed} />
          <NavItem to="/planning" icon={GitBranch} label="Planning" active={location.pathname === '/planning'} isCollapsed={isCollapsed} />
          <NavItem to="/board" icon={ListTodo} label="Project Board" active={location.pathname === '/board'} isCollapsed={isCollapsed} />
          <NavItem to="/execution" icon={Command} label="Execution" active={location.pathname === '/execution'} isCollapsed={isCollapsed} />
          <NavItem to="/tests" icon={TestTube2} label="Testing" active={location.pathname === '/tests'} isCollapsed={isCollapsed} />
          <NavItem to="/plans" icon={FileText} label="Documents" active={location.pathname === '/plans'} isCollapsed={isCollapsed} />
          <NavItem to="/sessions" icon={Terminal} label="Session Forensics" active={location.pathname === '/sessions'} isCollapsed={isCollapsed} />
          <NavItem to="/codebase" icon={FolderTree} label="Codebase Explorer" active={location.pathname === '/codebase'} isCollapsed={isCollapsed} />
          <NavItem to="/session-mappings" icon={SlidersHorizontal} label="Session Mappings" active={location.pathname === '/session-mappings'} isCollapsed={isCollapsed} />
          <NavItem to="/ops" icon={Activity} label="Operations" active={location.pathname === '/ops'} isCollapsed={isCollapsed} />
          <NavItem to="/analytics" icon={LineChart} label="Analytics" active={location.pathname === '/analytics'} isCollapsed={isCollapsed} />
          <NavItem to="/workflows" icon={Workflow} label="Workflows" active={location.pathname.startsWith('/workflows')} isCollapsed={isCollapsed} />
          <NavItem to="/skills" icon={Database} label="SkillMeat Context" active={location.pathname === '/skills'} isCollapsed={isCollapsed} />

          <div id="sidebar-portal" className={`mt-6 w-full min-w-0 overflow-x-hidden border-t border-sidebar-border pt-6 empty:hidden ${isCollapsed ? 'hidden' : ''}`}></div>
        </nav>

        <div className="space-y-1 border-t border-sidebar-border p-4">
          <Link
            to="/settings"
            className={cn(
              'group relative flex items-center justify-between rounded-lg border px-4 py-3 transition-colors',
              location.pathname === '/settings'
                ? 'border-sidebar-border bg-sidebar-accent text-sidebar-foreground shadow-sm'
                : 'border-transparent text-muted-foreground hover:bg-hover/60 hover:text-sidebar-foreground',
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
          <NavItem to="/settings" icon={Settings} label="Settings" active={location.pathname === '/settings'} isCollapsed={isCollapsed} />
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex min-w-0 flex-1 flex-col overflow-x-auto overflow-y-hidden bg-app-background">
        <div className="flex-1 min-w-[1024px] h-full overflow-y-auto p-4 md:p-8 scroll-smooth">
          {children}
        </div>
      </main>
    </div>
  );
};
