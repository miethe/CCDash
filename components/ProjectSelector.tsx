import React, { useState } from 'react';
import { ChevronDown, FolderPlus, Check } from 'lucide-react';
import { useData } from '../contexts/DataContext';
import { AddProjectModal } from './AddProjectModal';

export const ProjectSelector: React.FC = () => {
    const { projects, activeProject, switchProject } = useData();
    const [isOpen, setIsOpen] = useState(false);
    const [isModalOpen, setIsModalOpen] = useState(false);

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
                                    <span className="text-sm text-slate-300 group-hover:text-white truncate">
                                        {p.name}
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
                                    setIsOpen(false);
                                    setIsModalOpen(true);
                                }}
                                className="w-full text-left px-3 py-2 hover:bg-slate-700 flex items-center text-indigo-400 hover:text-indigo-300 transition-colors"
                            >
                                <FolderPlus size={14} className="mr-2" />
                                <span className="text-sm font-medium">Add New Project</span>
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
