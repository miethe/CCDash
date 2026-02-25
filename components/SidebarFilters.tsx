import React from 'react';
import { Filter, type LucideIcon } from 'lucide-react';
import { createPortal } from 'react-dom';

interface SidebarFiltersPortalProps {
  children: React.ReactNode;
  className?: string;
}

interface SidebarFiltersSectionProps {
  title: string;
  icon?: LucideIcon;
  children: React.ReactNode;
}

export const SidebarFiltersPortal: React.FC<SidebarFiltersPortalProps> = ({ children, className = '' }) => {
  const sidebarPortal = typeof document !== 'undefined' ? document.getElementById('sidebar-portal') : null;
  if (!sidebarPortal) return null;

  return createPortal(
    <div className={`space-y-6 animate-in slide-in-from-left-4 duration-300 w-full min-w-0 max-w-full overflow-x-hidden [&_*]:max-w-full [&_*]:min-w-0 ${className}`.trim()}>
      {children}
    </div>,
    sidebarPortal,
  );
};

export const SidebarFiltersSection: React.FC<SidebarFiltersSectionProps> = ({ title, icon: Icon = Filter, children }) => (
  <section className="w-full min-w-0">
    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
      <Icon size={12} /> {title}
    </h3>
    {children}
  </section>
);
