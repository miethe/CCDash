import React, { useState, useMemo, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useData } from '../contexts/DataContext';
import { PlanDocument } from '../types';
import { FileText, Folder, LayoutGrid, List, Search, Filter, FolderTree, ChevronRight, ChevronDown, User, Maximize2 } from 'lucide-react';
import { DocumentModal, getFileContent } from './DocumentModal';
import { getFeatureStatusStyle } from './featureStatus';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// --- Types ---
type ViewMode = 'card' | 'list' | 'folder';
type ScopeMode = 'plans' | 'prds' | 'reports' | 'progress' | 'all';
type ResolvedLinkedFeature = { id: string; status: string };

const normalizeToken = (value: string): string =>
    (value || '')
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/_+/g, '_')
        .replace(/^_+|_+$/g, '');

const normalizeDocumentStatus = (value: string): string => {
    const token = normalizeToken(value);
    const aliases: Record<string, string> = {
        completed: 'completed',
        complete: 'completed',
        done: 'completed',
        active: 'in_progress',
        in_progress: 'in_progress',
        inprogress: 'in_progress',
        working: 'in_progress',
        review: 'review',
        draft: 'pending',
        planning: 'pending',
        pending: 'pending',
        backlog: 'pending',
        deferred: 'deferred',
        blocked: 'blocked',
        archived: 'archived',
        inferred_complete: 'inferred_complete',
    };
    return aliases[token] || 'pending';
};

const normalizeDocumentType = (value: string): string => {
    const token = normalizeToken(value);
    const aliases: Record<string, string> = {
        prd: 'prd',
        product_requirements: 'prd',
        requirements: 'prd',
        implementation_plan: 'implementation_plan',
        implementationplan: 'implementation_plan',
        phase_plan: 'phase_plan',
        phaseplan: 'phase_plan',
        report: 'report',
        implementation_report: 'report',
        status_report: 'report',
        qa_report: 'report',
        benchmark: 'report',
        postmortem: 'report',
        spec: 'spec',
        technical_spec: 'spec',
        api_spec: 'spec',
        progress: 'progress',
    };
    return aliases[token] || 'document';
};

const normalizeDocumentSubtype = (value: string, rootKind: string, docType: string): string => {
    const token = normalizeToken(value);
    const aliases: Record<string, string> = {
        implementation_plan: 'implementation_plan',
        implementationplan: 'implementation_plan',
        phase_plan: 'phase_plan',
        phaseplan: 'phase_plan',
        prd: 'prd',
        product_requirements: 'prd',
        report: 'report',
        implementation_report: 'report',
        status_report: 'report',
        qa_report: 'report',
        postmortem: 'report',
        benchmark: 'report',
        spec: 'spec',
        technical_spec: 'spec',
        api_spec: 'spec',
        design_spec: 'design_spec',
        design_doc: 'design_doc',
        spike: 'spike',
        idea: 'idea',
        bug_doc: 'bug_doc',
        progress_phase: 'progress_phase',
        phase_progress: 'progress_phase',
        progress_all_phases: 'progress_all_phases',
        all_phases_progress: 'progress_all_phases',
        progress_quick_feature: 'progress_quick_feature',
        quick_feature_progress: 'progress_quick_feature',
        progress_other: 'progress_other',
        document: 'document',
    };
    if (aliases[token]) return aliases[token];

    if (rootKind === 'progress' || docType === 'progress') {
        if (token.includes('quick')) return 'progress_quick_feature';
        if (token.includes('all') && token.includes('phase')) return 'progress_all_phases';
        if (token.startsWith('phase') || token.includes('phase')) return 'progress_phase';
        return 'progress_other';
    }
    return 'document';
};

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
    const { documents, features } = useData();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const [viewMode, setViewMode] = useState<ViewMode>('card');
    const [searchQuery, setSearchQuery] = useState('');
    const [scopeMode, setScopeMode] = useState<ScopeMode>('plans');
    const [docSubtypeFilter, setDocSubtypeFilter] = useState<string>('all');
    const [docTypeFilter, setDocTypeFilter] = useState<string>('all');
    const [statusFilter, setStatusFilter] = useState<string>('all');
    const [categoryFilter, setCategoryFilter] = useState<string>('all');
    const [featureFilter, setFeatureFilter] = useState<string>('all');
    const [prdFilter, setPrdFilter] = useState<string>('all');
    const [phaseFilter, setPhaseFilter] = useState<string>('all');
    const [frontmatterFilter, setFrontmatterFilter] = useState<'all' | 'with' | 'without'>('all');
    const [selectedDoc, setSelectedDoc] = useState<PlanDocument | null>(null);

    // Auto-select document from URL search params (e.g. /plans?doc=DOC-xxx)
    useEffect(() => {
        const docParam = searchParams.get('doc');
        if (docParam && documents.length > 0) {
            const doc = documents.find(d => d.id === docParam);
            if (doc) {
                setSelectedDoc(doc);
                // Clear the param so it doesn't re-trigger
                setSearchParams({}, { replace: true });
            }
        }
    }, [searchParams, documents, setSearchParams]);

    // State for Folder View
    const [activeFilePath, setActiveFilePath] = useState<string | null>(null);
    const featureById = useMemo(() => {
        const map = new Map<string, { id: string; status: string }>();
        features.forEach(feature => {
            map.set(feature.id.toLowerCase(), { id: feature.id, status: feature.status });
        });
        return map;
    }, [features]);

    const resolveLinkedFeatures = (doc: PlanDocument): ResolvedLinkedFeature[] => {
        const refs = Array.from(new Set((doc.frontmatter?.linkedFeatures || []).filter(Boolean)));
        return refs.map(ref => {
            const matched = featureById.get(ref.toLowerCase());
            return {
                id: matched?.id || ref,
                status: matched?.status || 'backlog',
            };
        });
    };

    const facetOptions = useMemo(() => {
        const collect = (values: (string | undefined | null)[]) => (
            Array.from(new Set(values.map(v => String(v || '').trim()).filter(Boolean))).sort()
        );
        return {
            docSubtypes: collect(documents.map(d => normalizeDocumentSubtype(d.docSubtype || '', d.rootKind || '', d.docType || ''))),
            docTypes: collect(documents.map(d => normalizeDocumentType(d.docType || ''))),
            statuses: collect(documents.map(d => normalizeDocumentStatus(d.statusNormalized || d.status || ''))),
            categories: collect(documents.map(d => d.category)),
            features: collect(documents.map(d => d.featureSlugCanonical || d.featureSlugHint)),
            prds: collect(documents.map(d => d.prdRef || d.frontmatter?.prd)),
            phases: collect(documents.map(d => d.phaseToken || d.metadata?.phase)),
        };
    }, [documents]);

    const filteredDocs = useMemo(() => {
        const query = searchQuery.trim().toLowerCase();
        return documents.filter(doc => {
            if (scopeMode === 'plans') {
                if (doc.rootKind === 'progress') return false;
                if (doc.docType === 'prd' || doc.docType === 'report') return false;
            } else if (scopeMode === 'prds') {
                if (doc.docType !== 'prd') return false;
            } else if (scopeMode === 'reports') {
                if (doc.docType !== 'report') return false;
            } else if (scopeMode === 'progress') {
                if (doc.rootKind !== 'progress') return false;
            }

            if (
                docSubtypeFilter !== 'all'
                && normalizeDocumentSubtype(doc.docSubtype || '', doc.rootKind || '', doc.docType || '') !== docSubtypeFilter
            ) return false;
            if (docTypeFilter !== 'all' && normalizeDocumentType(doc.docType || '') !== docTypeFilter) return false;
            if (statusFilter !== 'all' && normalizeDocumentStatus(doc.statusNormalized || doc.status || '') !== statusFilter) return false;
            if (categoryFilter !== 'all' && (doc.category || '') !== categoryFilter) return false;
            if (featureFilter !== 'all' && (doc.featureSlugCanonical || doc.featureSlugHint || '') !== featureFilter) return false;
            if (prdFilter !== 'all' && (doc.prdRef || doc.frontmatter?.prd || '') !== prdFilter) return false;
            if (phaseFilter !== 'all' && (doc.phaseToken || doc.metadata?.phase || '') !== phaseFilter) return false;
            if (frontmatterFilter === 'with' && !doc.hasFrontmatter) return false;
            if (frontmatterFilter === 'without' && doc.hasFrontmatter) return false;

            if (!query) return true;
            const searchHaystack = [
                doc.title,
                doc.filePath,
                doc.canonicalPath,
                doc.status,
                doc.statusNormalized,
                doc.docType,
                doc.docSubtype,
                doc.category,
                doc.featureSlugHint,
                doc.featureSlugCanonical,
                doc.prdRef,
                doc.phaseToken,
                ...(doc.metadata?.owners || []),
                ...(doc.metadata?.contributors || []),
                ...(doc.metadata?.requestLogIds || []),
                ...(doc.metadata?.commitRefs || []),
                ...(doc.frontmatter?.relatedRefs || []),
                ...(doc.frontmatter?.pathRefs || []),
                ...(doc.frontmatter?.slugRefs || []),
                ...(doc.frontmatter?.linkedFeatures || []),
                ...(doc.frontmatter?.linkedSessions || []),
            ].map(v => String(v || '').toLowerCase());
            return searchHaystack.some(value => value.includes(query));
        });
    }, [
        documents,
        scopeMode,
        searchQuery,
        docSubtypeFilter,
        docTypeFilter,
        statusFilter,
        categoryFilter,
        featureFilter,
        prdFilter,
        phaseFilter,
        frontmatterFilter,
    ]);

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
    const activeDoc = activeFilePath ? filteredDocs.find(d => d.filePath === activeFilePath) : null;

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
                        <div className="mt-3 space-y-2">
                            {[
                                { label: 'Subtype', value: docSubtypeFilter, onChange: setDocSubtypeFilter, options: facetOptions.docSubtypes },
                                { label: 'Type', value: docTypeFilter, onChange: setDocTypeFilter, options: facetOptions.docTypes },
                                { label: 'Status', value: statusFilter, onChange: setStatusFilter, options: facetOptions.statuses },
                                { label: 'Category', value: categoryFilter, onChange: setCategoryFilter, options: facetOptions.categories },
                                { label: 'Feature', value: featureFilter, onChange: setFeatureFilter, options: facetOptions.features },
                                { label: 'PRD', value: prdFilter, onChange: setPrdFilter, options: facetOptions.prds },
                                { label: 'Phase', value: phaseFilter, onChange: setPhaseFilter, options: facetOptions.phases },
                            ].map(filter => (
                                <div key={filter.label} className="grid grid-cols-[56px_1fr] items-center gap-2">
                                    <label className="text-[10px] text-slate-500 uppercase tracking-wider">{filter.label}</label>
                                    <select
                                        value={filter.value}
                                        onChange={(e) => filter.onChange(e.target.value)}
                                        className="w-full bg-slate-950 border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-300 focus:border-indigo-500 focus:outline-none"
                                    >
                                        <option value="all">All</option>
                                        {filter.options.map(option => (
                                            <option key={option} value={option}>{option}</option>
                                        ))}
                                    </select>
                                </div>
                            ))}
                            <div className="grid grid-cols-[56px_1fr] items-center gap-2">
                                <label className="text-[10px] text-slate-500 uppercase tracking-wider">FM</label>
                                <select
                                    value={frontmatterFilter}
                                    onChange={(e) => setFrontmatterFilter(e.target.value as any)}
                                    className="w-full bg-slate-950 border border-slate-800 rounded-md px-2 py-1.5 text-[11px] text-slate-300 focus:border-indigo-500 focus:outline-none"
                                >
                                    <option value="all">All</option>
                                    <option value="with">With frontmatter</option>
                                    <option value="without">Without frontmatter</option>
                                </select>
                            </div>
                        </div>
                    </div>
                </div>,
                sidebarPortal
            )}

            {/* Page Header */}
            <div className="mb-6 flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-bold text-slate-100">Plan Documents</h2>
                    <p className="text-slate-400 text-sm">Catalog of project plans, PRDs, reports, and progress artifacts.</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                        {([
                            ['plans', 'Plans'],
                            ['prds', 'PRDs'],
                            ['reports', 'Reports'],
                            ['progress', 'Progress'],
                            ['all', 'All'],
                        ] as Array<[ScopeMode, string]>).map(([value, label]) => (
                            <button
                                key={value}
                                onClick={() => setScopeMode(value)}
                                className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                                    scopeMode === value
                                        ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-300'
                                        : 'bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                                }`}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
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
                        {filteredDocs.map(doc => {
                            const linkedFeatures = resolveLinkedFeatures(doc);
                            return (
                                <div key={doc.id} onClick={() => setSelectedDoc(doc)} className="bg-slate-900 border border-slate-800 rounded-xl p-5 hover:border-indigo-500/50 transition-all cursor-pointer group hover:shadow-lg">
                                    {linkedFeatures.length > 0 && (
                                        <div className="mb-3 flex flex-wrap gap-1.5">
                                            {linkedFeatures.slice(0, 2).map(linkedFeature => {
                                                const style = getFeatureStatusStyle(linkedFeature.status);
                                                return (
                                                    <button
                                                        key={linkedFeature.id}
                                                        type="button"
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            navigate(`/board?feature=${encodeURIComponent(linkedFeature.id)}`);
                                                        }}
                                                        className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold transition-colors ${style.badge}`}
                                                        title={`Open Feature ${linkedFeature.id} (${style.label})`}
                                                    >
                                                        {linkedFeature.id}
                                                    </button>
                                                );
                                            })}
                                            {linkedFeatures.length > 2 && (
                                                <span className="inline-flex items-center rounded-full border border-slate-700 bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300">
                                                    +{linkedFeatures.length - 2}
                                                </span>
                                            )}
                                        </div>
                                    )}
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
                            );
                        })}
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
                                        <div className="prose prose-invert prose-sm max-w-none [&_h1]:text-slate-100 [&_h2]:text-slate-200 [&_h3]:text-slate-300 [&_p]:text-slate-400 [&_li]:text-slate-400 [&_code]:bg-slate-800 [&_code]:text-indigo-300 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_pre]:bg-slate-900 [&_pre]:border [&_pre]:border-slate-800 [&_a]:text-indigo-400 [&_a:hover]:text-indigo-300 [&_blockquote]:border-l-indigo-500 [&_blockquote]:text-slate-400 [&_table]:border-collapse [&_th]:bg-slate-800 [&_th]:text-slate-300 [&_th]:px-3 [&_th]:py-2 [&_td]:px-3 [&_td]:py-2 [&_td]:border-t [&_td]:border-slate-800">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                {getFileContent(activeDoc)}
                                            </ReactMarkdown>
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
                                            <div className="flex flex-wrap gap-1.5">
                                                {resolveLinkedFeatures(activeDoc).map(linkedFeature => {
                                                    const style = getFeatureStatusStyle(linkedFeature.status);
                                                    return (
                                                        <button
                                                            key={linkedFeature.id}
                                                            type="button"
                                                            onClick={() => navigate(`/board?feature=${encodeURIComponent(linkedFeature.id)}`)}
                                                            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold transition-colors ${style.badge}`}
                                                        >
                                                            {linkedFeature.id}
                                                        </button>
                                                    );
                                                })}
                                            </div>
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
