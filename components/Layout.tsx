import React, { useState } from 'react';
import { LayoutDashboard, ListTodo, Settings, Box, Terminal, Database, Bell, FileText, ChevronLeft, ChevronRight } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { MOCK_NOTIFICATIONS } from '../constants';

const NavItem = ({ to, icon: Icon, label, active, isCollapsed }: { to: string; icon: any; label: string; active: boolean; isCollapsed: boolean }) => (
  <Link
    to={to}
    className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 group ${
      active
        ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
        : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
    }`}
  >
    <Icon size={20} className="shrink-0" />
    {!isCollapsed && <span className="font-medium text-sm truncate">{label}</span>}
    {isCollapsed && (
        <div className="absolute left-16 bg-slate-900 border border-slate-800 px-2 py-1 rounded text-xs text-slate-200 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50 whitespace-nowrap">
            {label}
        </div>
    )}
  </Link>
);

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const location = useLocation();
  const unreadCount = MOCK_NOTIFICATIONS.filter(n => !n.isRead).length;

  return (
    <div className="flex h-screen bg-slate-950 overflow-hidden">
      {/* Sidebar */}
      <aside 
        className={`border-r border-slate-800 bg-slate-900 flex flex-col shrink-0 transition-all duration-300 ease-in-out relative ${
          isCollapsed ? 'w-20' : 'w-64'
        }`}
      >
        <div className="p-6 border-b border-slate-800 flex items-center justify-between overflow-hidden">
          <div className="flex items-center gap-2 text-indigo-500 shrink-0">
            <Box size={24} className="fill-indigo-500/20" />
            {!isCollapsed && <h1 className="font-bold text-xl tracking-tight text-slate-100">CCDash</h1>}
          </div>
        </div>

        {/* Collapse Toggle */}
        <button 
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="absolute -right-3 top-20 w-6 h-6 bg-slate-800 border border-slate-700 rounded-full flex items-center justify-center text-slate-400 hover:text-white hover:bg-indigo-600 transition-all z-40"
        >
          {isCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>

        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          <NavItem to="/" icon={LayoutDashboard} label="Overview" active={location.pathname === '/'} isCollapsed={isCollapsed} />
          <NavItem to="/board" icon={ListTodo} label="Project Board" active={location.pathname === '/board'} isCollapsed={isCollapsed} />
          <NavItem to="/plans" icon={FileText} label="Documents" active={location.pathname === '/plans'} isCollapsed={isCollapsed} />
          <NavItem to="/sessions" icon={Terminal} label="Session Forensics" active={location.pathname === '/sessions'} isCollapsed={isCollapsed} />
          <NavItem to="/skills" icon={Database} label="SkillMeat Context" active={location.pathname === '/skills'} isCollapsed={isCollapsed} />
          
          <div id="sidebar-portal" className={`mt-6 pt-6 border-t border-slate-800 empty:hidden ${isCollapsed ? 'hidden' : ''}`}></div>
        </nav>

        <div className="p-4 border-t border-slate-800 space-y-1">
          <Link
            to="/settings"
            className={`flex items-center justify-between px-4 py-3 rounded-lg transition-colors group relative ${
              location.pathname === '/settings'
                ? 'bg-indigo-500/10 text-indigo-400'
                : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'
            }`}
          >
             <div className="flex items-center gap-3">
                <Bell size={20} className="shrink-0" />
                {!isCollapsed && <span className="font-medium text-sm">Notifications</span>}
             </div>
             {unreadCount > 0 && (
                 <span className={`${isCollapsed ? 'absolute -top-1 -right-1' : ''} bg-rose-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center`}>
                    {unreadCount}
                 </span>
             )}
          </Link>
          <NavItem to="/settings" icon={Settings} label="Settings" active={location.pathname === '/settings'} isCollapsed={isCollapsed} />
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-x-auto overflow-y-hidden bg-slate-950">
        <div className="flex-1 min-w-[1024px] h-full overflow-y-auto p-4 md:p-8 scroll-smooth">
          {children}
        </div>
      </main>
    </div>
  );
};