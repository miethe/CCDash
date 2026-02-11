import React, { useState, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useData } from '../contexts/DataContext';
import { PlanDocument } from '../types';
import { FileText, Folder, LayoutGrid, List, Search, Filter, FolderTree, ChevronRight, ChevronDown, User, Maximize2 } from 'lucide-react';
import { DocumentModal, getFileContent } from './DocumentModal';

// --- Types ---
type ViewMode = 'card' | 'list' | 'folder';

const FolderTreeItem = ({
    name,
    path,
    type,
    children,
    level = 0,
    onSelect,
    activePath
}: {
    name: string;
    path: string;
    type: 'file' | 'folder';
    children?: any[];
    level?: number;
    onSelect: (path: string) => void;
    activePath: string | null;
}) => {
    const [isOpen, setIsOpen] = useState(true);
    const isSelected = activePath === path;

    return (
        <div>
            <div
                className={`flex items-center gap-2 px-2 py-1.5 cursor-pointer text-sm hover:bg-slate-800 transition-colors ${isSelected ? 'bg-indigo-500/20 text-indigo-300' : 'text-slate-400'}`}
                style={{ paddingLeft: `${level * 12 + 8}px` }}
                onClick={() => {
                    if (type === 'folder') setIsOpen(!isOpen);
                    else onSelect(path);
                }}
            >
                {type === 'folder' ? (
                    isOpen ? <ChevronDown size={14} className="text-slate-500" /> : <ChevronRight size={14} className="text-slate-500" />
                ) : (
                    <span className="w-3.5"></span>
                )}
                {type === 'folder' ? <Folder size={16} className="fill-slate-700 text-slate-500" /> : <FileText size={16} className="text-slate-500" />}
                <span className="truncate">{name}</span>
            </div>
            {isOpen && children && children.map((child: any) => (
                <FolderTreeItem
                    key={child.path}
                    {...child}
                    level={level + 1}
                    onSelect={onSelect}
                    activePath={activePath}
                />
            ))}
        </div>
    );
};

// --- Main Page Component ---

export const PlanCatalog: React.FC = () => {
    const { documents } = useData();
    const [viewMode, setViewMode] = useState<ViewMode>('card');
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedDoc, setSelectedDoc] = useState<PlanDocument | null>(null);

    // State for Folder View
    const [activeFilePath, setActiveFilePath] = useState<string | null>(null);

    // Filter Logic
    const filteredDocs = useMemo(() => {
        return documents.filter(d =>
            d.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
            d.filePath.toLowerCase().includes(searchQuery.toLowerCase())
        );
    }, [searchQuery, documents]);

    // Tree Building Logic
    const fileTree = useMemo(() => {
        const tree: any[] = [];
        filteredDocs.forEach(doc => {
            const parts = doc.filePath.split('/');
            let currentLevel = tree;

            parts.forEach((part, idx) => {
                const isFile = idx === parts.length - 1;
                const path = parts.slice(0, idx + 1).join('/');
                const existing = currentLevel.find(n => n.name === part);

                if (existing) {
                    currentLevel = existing.children;
                } else {
                    const newNode = {
                        name: part,
                        path: path,
                        type: isFile ? 'file' : 'folder',
                        children: isFile ? undefined : [],
                        doc: isFile ? doc : undefined
                    };
                    currentLevel.push(newNode);
                    currentLevel = newNode.children || [];
                }
            });
        });
        return tree;
    }, [filteredDocs]);

    // Sidebar Portal
    const sidebarPortal = document.getElementById('sidebar-portal');

    // Handle tree Selection
    const activeDoc = activeFilePath ? documents.find(d => d.filePath === activeFilePath) : null;

    return (
        <div className="h-full flex flex-col relative">
            {/* Sidebar Filters */}
            {sidebarPortal && createPortal(
                <div className="space-y-6 animate-in slide-in-from-left-4 duration-300">
                    <div>
                        <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                            <Filter size={12} /> Filter Documents
                        </h3>
                        <div className="relative">
                            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                            <input
                                type="text"
                                placeholder="Search files..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none transition-colors"
                            />
                        </div>
                    </div>
                </div>,
                sidebarPortal
            )}

            {/* Page Header */}
            <div className="mb-6 flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-bold text-slate-100">Plan Documents</h2>
                    <p className="text-slate-400 text-sm">Catalog of project plans, PRDs, and architecture decisions.</p>
                </div>
                <div className="flex gap-3">
                    <div className="bg-slate-900 border border-slate-800 p-1 rounded-lg flex gap-1">
                        <button onClick={() => setViewMode('card')} className={`p-1.5 rounded-md transition-all ${viewMode === 'card' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'}`} title="Card View"><LayoutGrid size={18} /></button>
                        <button onClick={() => setViewMode('list')} className={`p-1.5 rounded-md transition-all ${viewMode === 'list' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'}`} title="List View"><List size={18} /></button>
                        <button onClick={() => setViewMode('folder')} className={`p-1.5 rounded-md transition-all ${viewMode === 'folder' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'}`} title="Folder View"><FolderTree size={18} /></button>
                    </div>
                </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-hidden">

                {/* CARD VIEW */}
                {viewMode === 'card' && (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 overflow-y-auto h-full pb-6">
                        {filteredDocs.map(doc => (
                            <div key={doc.id} onClick={() => setSelectedDoc(doc)} className="bg-slate-900 border border-slate-800 rounded-xl p-5 hover:border-indigo-500/50 transition-all cursor-pointer group hover:shadow-lg">
                                <div className="flex items-start justify-between mb-4">
                                    <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-lg">
                                        <FileText size={24} />
                                    </div>
                                    <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${doc.status === 'active' ? 'bg-emerald-500/10 text-emerald-500' :
                                            doc.status === 'draft' ? 'bg-indigo-500/10 text-indigo-500' : 'bg-slate-700 text-slate-400'
                                        }`}>{doc.status}</span>
                                </div>
                                <h3 className="font-bold text-slate-200 mb-1 group-hover:text-indigo-400 transition-colors">{doc.title}</h3>
                                <p className="text-xs text-slate-500 font-mono mb-4 truncate">{doc.filePath}</p>

                                <div className="flex flex-wrap gap-2 mb-4">
                                    {doc.frontmatter.tags.slice(0, 3).map(tag => (
                                        <span key={tag} className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full border border-slate-700">{tag}</span>
                                    ))}
                                </div>

                                <div className="border-t border-slate-800 pt-3 flex justify-between items-center text-xs text-slate-500">
                                    <span>{doc.author}</span>
                                    <span>{new Date(doc.lastModified).toLocaleDateString()}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* LIST VIEW */}
                {viewMode === 'list' && (
                    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden h-full flex flex-col">
                        <div className="grid grid-cols-12 gap-4 p-4 border-b border-slate-800 bg-slate-950/50 text-xs font-bold text-slate-500 uppercase tracking-wider">
                            <div className="col-span-4">Name</div>
                            <div className="col-span-3">Path</div>
                            <div className="col-span-2">Status</div>
                            <div className="col-span-2">Author</div>
                            <div className="col-span-1">Version</div>
                        </div>
                        <div className="overflow-y-auto flex-1">
                            {filteredDocs.map(doc => (
                                <div key={doc.id} onClick={() => setSelectedDoc(doc)} className="grid grid-cols-12 gap-4 p-4 border-b border-slate-800 hover:bg-slate-800/30 cursor-pointer transition-colors items-center text-sm">
                                    <div className="col-span-4 font-semibold text-slate-200 flex items-center gap-2">
                                        <FileText size={16} className="text-indigo-400" /> {doc.title}
                                    </div>
                                    <div className="col-span-3 text-slate-500 font-mono text-xs truncate">{doc.filePath}</div>
                                    <div className="col-span-2">
                                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${doc.status === 'active' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-slate-700 text-slate-400'
                                            }`}>{doc.status}</span>
                                    </div>
                                    <div className="col-span-2 text-slate-400">{doc.author}</div>
                                    <div className="col-span-1 font-mono text-xs text-slate-500">{doc.frontmatter.version || '-'}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* FOLDER VIEW (3-PANE) */}
                {viewMode === 'folder' && (
                    <div className="h-full flex border border-slate-800 rounded-xl bg-slate-900 overflow-hidden">
                        {/* Left Pane: Tree */}
                        <div className="w-1/4 border-r border-slate-800 bg-slate-950 flex flex-col">
                            <div className="p-3 border-b border-slate-800 text-xs font-bold text-slate-500 uppercase">Explorer</div>
                            <div className="flex-1 overflow-y-auto p-2">
                                {fileTree.map(node => (
                                    <FolderTreeItem key={node.path} {...node} onSelect={setActiveFilePath} activePath={activeFilePath} />
                                ))}
                            </div>
                        </div>

                        {/* Middle Pane: Preview */}
                        <div className="flex-1 flex flex-col border-r border-slate-800 bg-slate-900">
                            {activeDoc ? (
                                <>
                                    <div className="h-10 border-b border-slate-800 flex items-center justify-between px-4 bg-slate-950">
                                        <div className="flex items-center gap-2 text-sm text-slate-300">
                                            <FileText size={14} className="text-indigo-400" />
                                            {activeDoc.title}
                                        </div>
                                        <button
                                            onClick={() => setSelectedDoc(activeDoc)}
                                            className="flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10 px-2 py-1 rounded transition-colors"
                                        >
                                            <Maximize2 size={12} /> Expand
                                        </button>
                                    </div>
                                    <div className="flex-1 overflow-y-auto p-6">
                                        <div className="prose prose-invert prose-sm max-w-none">
                                            <pre className="bg-transparent p-0 m-0 font-mono text-xs text-slate-400 whitespace-pre-wrap">
                                                {getFileContent(activeDoc)}
                                            </pre>
                                        </div>
                                    </div>
                                </>
                            ) : (
                                <div className="flex-1 flex items-center justify-center text-slate-600 flex-col">
                                    <FolderTree size={48} className="mb-4 opacity-20" />
                                    <p>Select a file to preview</p>
                                </div>
                            )}
                        </div>

                        {/* Right Pane: Metadata */}
                        <div className="w-64 bg-slate-950 flex flex-col overflow-y-auto">
                            <div className="p-3 border-b border-slate-800 text-xs font-bold text-slate-500 uppercase">Metadata</div>
                            {activeDoc ? (
                                <div className="p-4 space-y-6">
                                    <div>
                                        <div className="text-[10px] text-slate-500 uppercase mb-1">Status</div>
                                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${activeDoc.status === 'active' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-slate-700 text-slate-400'
                                            }`}>{activeDoc.status}</span>
                                    </div>
                                    <div>
                                        <div className="text-[10px] text-slate-500 uppercase mb-1">Author</div>
                                        <div className="text-sm text-slate-300 flex items-center gap-2">
                                            <User size={12} /> {activeDoc.author}
                                        </div>
                                    </div>
                                    <div>
                                        <div className="text-[10px] text-slate-500 uppercase mb-1">Modified</div>
                                        <div className="text-sm text-slate-300">{new Date(activeDoc.lastModified).toLocaleDateString()}</div>
                                    </div>
                                    <div>
                                        <div className="text-[10px] text-slate-500 uppercase mb-2">Tags</div>
                                        <div className="flex flex-wrap gap-2">
                                            {activeDoc.frontmatter.tags.map(t => (
                                                <span key={t} className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700">{t}</span>
                                            ))}
                                        </div>
                                    </div>
                                    {activeDoc.frontmatter.linkedFeatures && (
                                        <div>
                                            <div className="text-[10px] text-slate-500 uppercase mb-2">Linked Features</div>
                                            {activeDoc.frontmatter.linkedFeatures.map(f => (
                                                <div key={f} className="text-xs text-indigo-400 font-mono mb-1">{f}</div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <div className="p-4 text-xs text-slate-600 italic">No document selected.</div>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {selectedDoc && <DocumentModal doc={selectedDoc} onClose={() => setSelectedDoc(null)} />}
        </div>
    );
};