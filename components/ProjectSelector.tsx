import React, { useState } from 'react';
import { ChevronDown, FolderPlus, Check, Lock } from 'lucide-react';
import { useData } from '../contexts/DataContext';
import { summarizeAuthMembershipContext, useAuthSession } from '../contexts/AuthSessionContext';
import { AddProjectModal } from './AddProjectModal';

const PROJECT_OPERATOR_ROLES = ['EA', 'TA', 'PM', 'owner', 'admin', 'operator', 'project_maintainer', 'project-maintainer', 'project:maintainer'];

export const ProjectSelector: React.FC<{ initialOpen?: boolean }> = ({ initialOpen = false }) => {
    const { projects, activeProject, switchProject } = useData();
    const auth = useAuthSession();
    const [isOpen, setIsOpen] = useState(initialOpen);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const canCreateProject = auth.hasPermission({
        scopes: ['project:create'],
        roles: ['EA', 'TA', ...PROJECT_OPERATOR_ROLES],
    });
    const membershipContext = summarizeAuthMembershipContext(auth.session);
    const activeProjectMembership = (auth.session?.memberships ?? []).find(membership => (
        membership.scopeType === 'project' && membership.scopeId === activeProject?.id
    ));
    const contextLine = auth.session?.localMode || auth.metadata?.localMode
        ? 'Local workspace controls'
        : [
            membershipContext.enterpriseIds[0] ? `Ent ${membershipContext.enterpriseIds[0]}` : '',
            membershipContext.teamIds[0] ? `Team ${membershipContext.teamIds[0]}` : '',
            membershipContext.workspaceIds[0] ? `Workspace ${membershipContext.workspaceIds[0]}` : '',
            activeProjectMembership?.role ? `Role ${activeProjectMembership.role}` : membershipContext.roles[0] ? `Role ${membershipContext.roles[0]}` : '',
        ].filter(Boolean).join(' / ');

    const handleSwitch = async (projectId: string) => {
        if (projectId !== activeProject?.id) {
            await switchProject(projectId);
        }
        setIsOpen(false);
    };

    return (
        <div className="relative mx-4 mt-4 mb-2">
            <div
                className="flex items-center justify-between px-3 py-2 bg-slate-800 rounded border border-slate-700 cursor-pointer hover:bg-slate-700 transition-colors"
                onClick={() => setIsOpen(!isOpen)}
            >
                <div className="flex flex-col overflow-hidden">
                    <span className="text-[10px] text-slate-500 uppercase font-semibold tracking-wider">Project</span>
                    <span className="text-sm font-medium text-slate-200 truncate pr-2">
                        {activeProject?.name || 'Select Project'}
                    </span>
                </div>
                <ChevronDown size={16} className={`text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </div>

            {isOpen && (
                <>
                    <div
                        className="fixed inset-0 z-10"
                        onClick={() => setIsOpen(false)}
                    />
                    <div className="absolute top-full left-0 right-0 mt-1 bg-slate-800 rounded-md shadow-xl border border-slate-700 z-50 overflow-hidden">
                        <div className="max-h-60 overflow-y-auto py-1">
                            {projects.map(p => (
                                <button
                                    key={p.id}
                                    onClick={() => handleSwitch(p.id)}
                                    className="w-full text-left px-3 py-2 hover:bg-slate-700 flex items-center justify-between group transition-colors"
                                >
                                    <span className="min-w-0">
                                        <span className="block text-sm text-slate-300 group-hover:text-white truncate">
                                            {p.name}
                                        </span>
                                        {p.id === activeProject?.id && contextLine && (
                                            <span className="mt-0.5 block truncate text-[10px] text-slate-500">
                                                {contextLine}
                                            </span>
                                        )}
                                    </span>
                                    {activeProject?.id === p.id && (
                                        <Check size={14} className="text-indigo-400 flex-shrink-0 ml-2" />
                                    )}
                                </button>
                            ))}
                        </div>
                        <div className="border-t border-slate-700">
                            <button
                                onClick={() => {
                                    if (!canCreateProject) return;
                                    setIsOpen(false);
                                    setIsModalOpen(true);
                                }}
                                disabled={!canCreateProject}
                                title={!canCreateProject ? 'Permission hint only; backend authorization remains authoritative.' : undefined}
                                className="w-full text-left px-3 py-2 hover:bg-slate-700 flex items-center text-indigo-400 hover:text-indigo-300 transition-colors disabled:cursor-not-allowed disabled:text-slate-500 disabled:hover:bg-transparent"
                            >
                                {canCreateProject ? <FolderPlus size={14} className="mr-2" /> : <Lock size={14} className="mr-2" />}
                                <span className="text-sm font-medium">
                                    {canCreateProject ? 'Add New Project' : 'Add Project Requires Permission'}
                                </span>
                            </button>
                        </div>
                    </div>
                </>
            )}

            <AddProjectModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
            />
        </div>
    );
};
