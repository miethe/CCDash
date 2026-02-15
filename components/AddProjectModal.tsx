import React, { useState } from 'react';
import { X } from 'lucide-react';
import { useData } from '../contexts/DataContext';
import { Project } from '../types';

interface AddProjectModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export const AddProjectModal: React.FC<AddProjectModalProps> = ({ isOpen, onClose }) => {
    const { addProject } = useData();
    const [name, setName] = useState('');
    const [path, setPath] = useState('');
    const [description, setDescription] = useState('');
    const [repoUrl, setRepoUrl] = useState('');
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const [agentPlatforms, setAgentPlatforms] = useState<string[]>(['Claude Code']);
    const [planDocsPath, setPlanDocsPath] = useState('docs/project_plans/');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);

        try {
            const newProject: Project = {
                id: crypto.randomUUID(),
                name,
                path,
                description,
                repoUrl,
                agentPlatforms,
                planDocsPath
            };
            await addProject(newProject);
            onClose();
            // Reset form
            setName('');
            setPath('');
            setDescription('');
            setRepoUrl('');
            setPlanDocsPath('docs/project_plans/');
        } catch (e: any) {
            setError(e.message || 'Failed to add project');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
            <div className="bg-gray-800 rounded-lg shadow-xl w-full max-w-md p-6 border border-gray-700" onClick={e => e.stopPropagation()}>
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-xl font-bold text-gray-100">Add New Project</h2>
                    <button onClick={onClose} className="text-gray-400 hover:text-white">
                        <X size={20} />
                    </button>
                </div>

                {error && (
                    <div className="mb-4 p-3 bg-red-900/50 border border-red-700 text-red-200 rounded text-sm">
                        {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-400 mb-1">Project Name</label>
                        <input
                            type="text"
                            required
                            value={name}
                            onChange={e => setName(e.target.value)}
                            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500"
                            placeholder="My Awesome Project"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-400 mb-1">Local Path</label>
                        <input
                            type="text"
                            required
                            value={path}
                            onChange={e => setPath(e.target.value)}
                            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500"
                            placeholder="/absolute/path/to/project"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-400 mb-1">Description (Optional)</label>
                        <textarea
                            value={description}
                            onChange={e => setDescription(e.target.value)}
                            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500 h-20"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-400 mb-1">Repo URL (Optional)</label>
                        <input
                            type="url"
                            value={repoUrl}
                            onChange={e => setRepoUrl(e.target.value)}
                            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-400 mb-1">Plan Docs Path</label>
                        <input
                            type="text"
                            value={planDocsPath}
                            onChange={e => setPlanDocsPath(e.target.value)}
                            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500"
                            placeholder="docs/project_plans/"
                        />
                        <p className="text-xs text-gray-500 mt-1">Relative to project root</p>
                    </div>

                    <div className="flex justify-end pt-4 space-x-3">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 text-gray-300 hover:text-white"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={loading}
                            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded disabled:opacity-50"
                        >
                            {loading ? 'Adding...' : 'Add Project'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};
