import React from 'react';
import { PlanDocument } from '../types';
import {
   ArrowLeft,
   FileText,
   FolderTree,
   Link2,
   ListTodo,
   Terminal,
   User,
   X,
} from 'lucide-react';
import { useData } from '../contexts/DataContext';
import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { getFeatureStatusStyle } from './featureStatus';

export const getFileContent = (doc: PlanDocument): string => {
   if (doc.content) return doc.content;
   return `# ${doc.title}

> **Status**: ${doc.status.toUpperCase()}
> **Path**: ${doc.filePath}

_Content preview not available for this document yet._`;
};

interface DocumentLinkFeature {
   id: string;
   name: string;
   status: string;
   category: string;
}

interface DocumentLinkTask {
   id: string;
   title: string;
   status: string;
   sourceFile: string;
   sessionId?: string;
   featureId?: string;
   phaseId?: string;
}

interface DocumentLinkSession {
   id: string;
   status: string;
   model: string;
   startedAt: string;
   totalCost: number;
}

interface DocumentLinkDocument {
   id: string;
   title: string;
   filePath: string;
   canonicalPath: string;
   docType: string;
   docSubtype: string;
}

interface DocumentLinksResponse {
   documentId: string;
   features: DocumentLinkFeature[];
   tasks: DocumentLinkTask[];
   sessions: DocumentLinkSession[];
   documents: DocumentLinkDocument[];
}

interface DocumentModalProps {
   doc: PlanDocument;
   onClose: () => void;
   onBack?: () => void;
   backLabel?: string;
   zIndexClassName?: string;
}

const normalizeDoc = (raw: Partial<PlanDocument>, fallback: PlanDocument): PlanDocument => ({
   id: String(raw.id || fallback.id || ''),
   title: String(raw.title || fallback.title || ''),
   filePath: String(raw.filePath || fallback.filePath || ''),
   canonicalPath: String(raw.canonicalPath || fallback.canonicalPath || raw.filePath || fallback.filePath || ''),
   status: String(raw.status || fallback.status || 'active'),
   statusNormalized: String(raw.statusNormalized || fallback.statusNormalized || ''),
   createdAt: String(raw.createdAt || fallback.createdAt || ''),
   updatedAt: String(raw.updatedAt || fallback.updatedAt || ''),
   completedAt: String(raw.completedAt || fallback.completedAt || ''),
   lastModified: String(raw.lastModified || fallback.lastModified || ''),
   author: String(raw.author || fallback.author || ''),
   content: typeof raw.content === 'string' ? raw.content : fallback.content,
   docType: raw.docType || fallback.docType,
   docSubtype: raw.docSubtype || fallback.docSubtype,
   rootKind: raw.rootKind || fallback.rootKind,
   hasFrontmatter: typeof raw.hasFrontmatter === 'boolean' ? raw.hasFrontmatter : fallback.hasFrontmatter,
   frontmatterType: raw.frontmatterType || fallback.frontmatterType,
   featureSlugHint: raw.featureSlugHint || fallback.featureSlugHint,
   featureSlugCanonical: raw.featureSlugCanonical || fallback.featureSlugCanonical,
   prdRef: raw.prdRef || fallback.prdRef,
   phaseToken: raw.phaseToken || fallback.phaseToken,
   phaseNumber: raw.phaseNumber ?? fallback.phaseNumber,
   overallProgress: raw.overallProgress ?? fallback.overallProgress,
   totalTasks: raw.totalTasks ?? fallback.totalTasks ?? 0,
   completedTasks: raw.completedTasks ?? fallback.completedTasks ?? 0,
   inProgressTasks: raw.inProgressTasks ?? fallback.inProgressTasks ?? 0,
   blockedTasks: raw.blockedTasks ?? fallback.blockedTasks ?? 0,
   category: raw.category || fallback.category,
   pathSegments: Array.isArray(raw.pathSegments) ? raw.pathSegments : (fallback.pathSegments || []),
   featureCandidates: Array.isArray(raw.featureCandidates) ? raw.featureCandidates : (fallback.featureCandidates || []),
   metadata: {
      phase: raw.metadata?.phase ?? fallback.metadata?.phase ?? '',
      phaseNumber: raw.metadata?.phaseNumber ?? fallback.metadata?.phaseNumber,
      overallProgress: raw.metadata?.overallProgress ?? fallback.metadata?.overallProgress,
      taskCounts: raw.metadata?.taskCounts ?? fallback.metadata?.taskCounts ?? {
         total: raw.totalTasks ?? fallback.totalTasks ?? 0,
         completed: raw.completedTasks ?? fallback.completedTasks ?? 0,
         inProgress: raw.inProgressTasks ?? fallback.inProgressTasks ?? 0,
         blocked: raw.blockedTasks ?? fallback.blockedTasks ?? 0,
      },
      owners: raw.metadata?.owners ?? fallback.metadata?.owners ?? [],
      contributors: raw.metadata?.contributors ?? fallback.metadata?.contributors ?? [],
      requestLogIds: raw.metadata?.requestLogIds ?? fallback.metadata?.requestLogIds ?? [],
      commitRefs: raw.metadata?.commitRefs ?? fallback.metadata?.commitRefs ?? [],
      featureSlugHint: raw.metadata?.featureSlugHint ?? fallback.metadata?.featureSlugHint ?? '',
      canonicalPath: raw.metadata?.canonicalPath ?? fallback.metadata?.canonicalPath ?? '',
   },
   linkCounts: {
      features: raw.linkCounts?.features ?? fallback.linkCounts?.features ?? 0,
      tasks: raw.linkCounts?.tasks ?? fallback.linkCounts?.tasks ?? 0,
      sessions: raw.linkCounts?.sessions ?? fallback.linkCounts?.sessions ?? 0,
      documents: raw.linkCounts?.documents ?? fallback.linkCounts?.documents ?? 0,
   },
   dates: raw.dates ?? fallback.dates,
   timeline: Array.isArray(raw.timeline) ? raw.timeline : (fallback.timeline || []),
   frontmatter: {
      tags: Array.isArray(raw.frontmatter?.tags) ? raw.frontmatter.tags : (fallback.frontmatter?.tags || []),
      linkedFeatures: Array.isArray(raw.frontmatter?.linkedFeatures) ? raw.frontmatter.linkedFeatures : (fallback.frontmatter?.linkedFeatures || []),
      linkedSessions: Array.isArray(raw.frontmatter?.linkedSessions) ? raw.frontmatter.linkedSessions : (fallback.frontmatter?.linkedSessions || []),
      relatedFiles: Array.isArray(raw.frontmatter?.relatedFiles) ? raw.frontmatter.relatedFiles : (fallback.frontmatter?.relatedFiles || []),
      version: raw.frontmatter?.version ?? fallback.frontmatter?.version,
      commits: Array.isArray(raw.frontmatter?.commits) ? raw.frontmatter.commits : (fallback.frontmatter?.commits || []),
      prs: Array.isArray(raw.frontmatter?.prs) ? raw.frontmatter.prs : (fallback.frontmatter?.prs || []),
      relatedRefs: Array.isArray(raw.frontmatter?.relatedRefs) ? raw.frontmatter.relatedRefs : (fallback.frontmatter?.relatedRefs || []),
      pathRefs: Array.isArray(raw.frontmatter?.pathRefs) ? raw.frontmatter.pathRefs : (fallback.frontmatter?.pathRefs || []),
      slugRefs: Array.isArray(raw.frontmatter?.slugRefs) ? raw.frontmatter.slugRefs : (fallback.frontmatter?.slugRefs || []),
      prd: raw.frontmatter?.prd ?? fallback.frontmatter?.prd,
      prdRefs: Array.isArray(raw.frontmatter?.prdRefs) ? raw.frontmatter.prdRefs : (fallback.frontmatter?.prdRefs || []),
      fieldKeys: Array.isArray(raw.frontmatter?.fieldKeys) ? raw.frontmatter.fieldKeys : (fallback.frontmatter?.fieldKeys || []),
      raw: raw.frontmatter?.raw ?? fallback.frontmatter?.raw,
   },
});

export const DocumentModal = ({
   doc: initialDoc,
   onClose,
   onBack,
   backLabel = 'Back',
   zIndexClassName = 'z-50',
}: DocumentModalProps) => {
   const navigate = useNavigate();
   const { sessions, features } = useData();
   const [activeTab, setActiveTab] = React.useState<'overview' | 'content' | 'linked_docs' | 'linked_entities'>('overview');
   const [fullDoc, setFullDoc] = React.useState<PlanDocument>(() => normalizeDoc(initialDoc, initialDoc));
   const [links, setLinks] = React.useState<DocumentLinksResponse | null>(null);

   React.useEffect(() => {
      let cancelled = false;
      const docId = (initialDoc.id || '').trim();
      if (!docId) {
         setFullDoc(normalizeDoc(initialDoc, initialDoc));
         setLinks(null);
         return () => {
            cancelled = true;
         };
      }

      Promise.all([
         fetch(`/api/documents/${encodeURIComponent(docId)}`),
         fetch(`/api/documents/${encodeURIComponent(docId)}/links`),
      ])
         .then(async ([docRes, linksRes]) => {
            if (!docRes.ok) throw new Error(`Failed to fetch document (${docRes.status})`);
            const docPayload = await docRes.json();
            const linksPayload = linksRes.ok ? await linksRes.json() : null;
            if (cancelled) return;
            setFullDoc(normalizeDoc((docPayload || {}) as Partial<PlanDocument>, initialDoc));
            if (linksPayload && typeof linksPayload === 'object') {
               setLinks({
                  documentId: String(linksPayload.documentId || docId),
                  features: Array.isArray(linksPayload.features) ? linksPayload.features : [],
                  tasks: Array.isArray(linksPayload.tasks) ? linksPayload.tasks : [],
                  sessions: Array.isArray(linksPayload.sessions) ? linksPayload.sessions : [],
                  documents: Array.isArray(linksPayload.documents) ? linksPayload.documents : [],
               });
            } else {
               setLinks(null);
            }
         })
         .catch(() => {
            if (cancelled) return;
            setFullDoc(normalizeDoc(initialDoc, initialDoc));
            setLinks(null);
         });

      return () => {
         cancelled = true;
      };
   }, [initialDoc.id]);

   const doc = normalizeDoc(fullDoc || initialDoc, initialDoc);
   const isProgressDoc = doc.rootKind === 'progress' || (doc.docSubtype || '').startsWith('progress_');
   const linkedFeatures = React.useMemo(() => {
      const featureById = new Map<string, { id: string; name: string; status: string; category: string }>();
      features.forEach(feature => {
         featureById.set(feature.id.toLowerCase(), {
            id: feature.id,
            name: feature.name,
            status: feature.status,
            category: feature.category,
         });
      });

      const merged = new Map<string, DocumentLinkFeature>();
      (links?.features || []).forEach(feature => {
         const matched = featureById.get((feature.id || '').toLowerCase());
         const resolvedId = matched?.id || feature.id;
         if (!resolvedId) return;
         merged.set(resolvedId, {
            id: resolvedId,
            name: feature.name || matched?.name || resolvedId,
            status: feature.status || matched?.status || 'backlog',
            category: feature.category || matched?.category || '',
         });
      });

      (doc.frontmatter.linkedFeatures || []).forEach(ref => {
         const matched = featureById.get((ref || '').toLowerCase());
         const resolvedId = matched?.id || ref;
         if (!resolvedId || merged.has(resolvedId)) return;
         merged.set(resolvedId, {
            id: resolvedId,
            name: matched?.name || resolvedId,
            status: matched?.status || 'backlog',
            category: matched?.category || '',
         });
      });

      return Array.from(merged.values());
   }, [features, links?.features, doc.frontmatter.linkedFeatures]);
   const linkedTasks = links?.tasks || [];
   const linkedSessions = React.useMemo(() => {
      if (links?.sessions && links.sessions.length > 0) return links.sessions;
      const fallbackIds = doc.frontmatter.linkedSessions || [];
      return fallbackIds
         .map(id => sessions.find(s => s.id === id))
         .filter(Boolean)
         .map(session => ({
            id: session!.id,
            status: session!.status,
            model: session!.model,
            startedAt: session!.startedAt,
            totalCost: session!.totalCost,
         }));
   }, [links?.sessions, doc.frontmatter.linkedSessions, sessions]);
   const linkedDocs = links?.documents || [];
   const taskCounts = doc.metadata?.taskCounts || {
      total: doc.totalTasks || 0,
      completed: doc.completedTasks || 0,
      inProgress: doc.inProgressTasks || 0,
      blocked: doc.blockedTasks || 0,
   };
   const formatDate = (value?: string): string => {
      if (!value) return '-';
      const parsed = Date.parse(value);
      if (Number.isNaN(parsed)) return value;
      return new Date(parsed).toLocaleDateString();
   };
   const dateChip = (key: keyof NonNullable<PlanDocument['dates']>) => {
      const value = doc.dates?.[key];
      if (!value?.value) return '';
      const confidence = value.confidence ? ` (${value.confidence})` : '';
      return `${formatDate(value.value)}${confidence}`;
   };

   return (
      <div className={`fixed inset-0 ${zIndexClassName} flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-200`} onClick={onClose}>
         <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-5xl h-[85vh] flex flex-col shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="p-6 border-b border-slate-800 flex justify-between items-start bg-slate-900">
               <div className="flex items-start gap-3 min-w-0">
                  {onBack && (
                     <button
                        onClick={onBack}
                        className="mt-0.5 p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
                        title={backLabel}
                        aria-label={backLabel}
                     >
                        <ArrowLeft size={16} />
                     </button>
                  )}
                  <div className="min-w-0">
                     <div className="flex items-center gap-2 mb-2 flex-wrap">
                        <span className="font-mono text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">{doc.id}</span>
                        <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-300">{doc.status}</span>
                        {doc.docType && <span className="text-[10px] uppercase px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">{doc.docType}</span>}
                        {doc.docSubtype && <span className="text-[10px] uppercase px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20">{doc.docSubtype}</span>}
                        {doc.rootKind && <span className="text-[10px] uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">{doc.rootKind}</span>}
                        {linkedFeatures.slice(0, 3).map(feature => {
                           const style = getFeatureStatusStyle(feature.status);
                           return (
                              <button
                                 key={feature.id}
                                 type="button"
                                 onClick={() => { onClose(); navigate(`/board?feature=${encodeURIComponent(feature.id)}`); }}
                                 className={`text-[10px] font-semibold rounded-full border px-2 py-0.5 transition-colors ${style.badge}`}
                                 title={`Open Feature ${feature.id} (${style.label})`}
                              >
                                 {feature.id}
                              </button>
                           );
                        })}
                        {linkedFeatures.length > 3 && (
                           <span className="text-[10px] rounded-full border border-slate-700 bg-slate-800 px-2 py-0.5 text-slate-300">
                              +{linkedFeatures.length - 3} features
                           </span>
                        )}
                     </div>
                     <h2 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
                        <FileText className="text-slate-400" /> {doc.title}
                     </h2>
                     <p className="text-slate-400 font-mono text-xs mt-1">{doc.canonicalPath || doc.filePath}</p>
                  </div>
               </div>
               <button onClick={onClose} className="text-slate-500 hover:text-slate-200 transition-colors p-1 hover:bg-slate-800 rounded">
                  <X size={24} />
               </button>
            </div>

            <div className="px-6 border-b border-slate-800 bg-slate-900/50 flex gap-6">
               {[
                  { id: 'overview', label: 'Overview' },
                  { id: 'content', label: 'Contents' },
                  { id: 'linked_docs', label: 'Linked Docs', count: linkedDocs.length + (doc.frontmatter.pathRefs?.length || 0) },
                  { id: 'linked_entities', label: 'Linked Entities', count: linkedFeatures.length + linkedTasks.length + linkedSessions.length },
               ].map(tab => (
                  <button
                     key={tab.id}
                     onClick={() => setActiveTab(tab.id as any)}
                     className={`flex items-center gap-2 py-4 text-sm font-medium border-b-2 transition-colors ${activeTab === tab.id
                        ? 'border-indigo-500 text-indigo-400'
                        : 'border-transparent text-slate-500 hover:text-slate-300 hover:border-slate-700'
                        }`}
                  >
                     {tab.label}
                     {tab.count !== undefined && tab.count > 0 && (
                        <span className="bg-slate-800 text-slate-400 text-[10px] px-1.5 py-0.5 rounded-full">{tab.count}</span>
                     )}
                  </button>
               ))}
            </div>

            <div className="flex-1 overflow-y-auto p-6 bg-slate-950/30">
               {activeTab === 'overview' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                     <div className="space-y-4">
                        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                           <h3 className="text-sm font-semibold text-slate-200 mb-3">Core Metadata</h3>
                           <div className="space-y-2 text-sm">
                              <div className="flex justify-between text-slate-400"><span>Status</span><span className="text-slate-200">{doc.statusNormalized || doc.status}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Author</span><span className="text-slate-200">{doc.author || '-'}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Created</span><span className="text-slate-200">{dateChip('createdAt') || formatDate(doc.createdAt)}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Updated</span><span className="text-slate-200">{dateChip('updatedAt') || formatDate(doc.updatedAt || doc.lastModified)}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Completed</span><span className="text-slate-200">{dateChip('completedAt') || formatDate(doc.completedAt)}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Category</span><span className="text-slate-200">{doc.category || '-'}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Feature Hint</span><span className="text-slate-200 font-mono">{doc.featureSlugCanonical || doc.featureSlugHint || '-'}</span></div>
                              <div className="flex justify-between text-slate-400"><span>PRD Ref</span><span className="text-slate-200 font-mono">{doc.prdRef || doc.frontmatter.prd || '-'}</span></div>
                           </div>
                        </div>

                        {isProgressDoc && (
                           <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                              <h3 className="text-sm font-semibold text-slate-200 mb-3">Progress Metrics</h3>
                              <div className="grid grid-cols-2 gap-3 text-xs">
                                 <div className="p-2 rounded bg-slate-950 border border-slate-800">
                                    <div className="text-slate-500 uppercase">Phase</div>
                                    <div className="text-slate-200 font-mono mt-1">{doc.phaseToken || doc.metadata?.phase || '-'}</div>
                                 </div>
                                 <div className="p-2 rounded bg-slate-950 border border-slate-800">
                                    <div className="text-slate-500 uppercase">Progress</div>
                                    <div className="text-slate-200 font-mono mt-1">{doc.overallProgress ?? doc.metadata?.overallProgress ?? '-'}%</div>
                                 </div>
                                 <div className="p-2 rounded bg-slate-950 border border-slate-800">
                                    <div className="text-slate-500 uppercase">Tasks</div>
                                    <div className="text-slate-200 font-mono mt-1">{taskCounts.completed}/{taskCounts.total}</div>
                                 </div>
                                 <div className="p-2 rounded bg-slate-950 border border-slate-800">
                                    <div className="text-slate-500 uppercase">In Progress/Blocked</div>
                                    <div className="text-slate-200 font-mono mt-1">{taskCounts.inProgress}/{taskCounts.blocked}</div>
                                 </div>
                              </div>
                           </div>
                        )}
                     </div>

                     <div className="space-y-4">
                        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                           <h3 className="text-sm font-semibold text-slate-200 mb-3">Refs & Ownership</h3>
                           <div className="space-y-2 text-xs">
                              <div>
                                 <div className="text-slate-500 uppercase mb-1">Owners</div>
                                 <div className="text-slate-300">{(doc.metadata?.owners || []).join(', ') || '-'}</div>
                              </div>
                              <div>
                                 <div className="text-slate-500 uppercase mb-1">Contributors</div>
                                 <div className="text-slate-300">{(doc.metadata?.contributors || []).join(', ') || '-'}</div>
                              </div>
                              <div>
                                 <div className="text-slate-500 uppercase mb-1">Request IDs</div>
                                 <div className="text-slate-300 font-mono break-all">{(doc.metadata?.requestLogIds || []).join(', ') || '-'}</div>
                              </div>
                              <div>
                                 <div className="text-slate-500 uppercase mb-1">Commit Refs</div>
                                 <div className="text-slate-300 font-mono break-all">{(doc.metadata?.commitRefs || doc.frontmatter.commits || []).join(', ') || '-'}</div>
                              </div>
                           </div>
                        </div>

                        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                           <h3 className="text-sm font-semibold text-slate-200 mb-3">Tags & Link Counts</h3>
                           <div className="flex flex-wrap gap-2 mb-3">
                              {(doc.frontmatter.tags || []).map(tag => (
                                 <span key={tag} className="text-[10px] bg-indigo-500/10 text-indigo-300 px-2 py-0.5 rounded border border-indigo-500/20">
                                    {tag}
                                 </span>
                              ))}
                              {(doc.frontmatter.tags || []).length === 0 && (
                                 <span className="text-xs text-slate-500">No tags</span>
                              )}
                           </div>
                           <div className="grid grid-cols-4 gap-2 text-[10px]">
                              <div className="bg-slate-950 border border-slate-800 rounded p-2 text-center"><div className="text-slate-500">Features</div><div className="text-slate-200 mt-1">{linkedFeatures.length}</div></div>
                              <div className="bg-slate-950 border border-slate-800 rounded p-2 text-center"><div className="text-slate-500">Tasks</div><div className="text-slate-200 mt-1">{linkedTasks.length}</div></div>
                              <div className="bg-slate-950 border border-slate-800 rounded p-2 text-center"><div className="text-slate-500">Sessions</div><div className="text-slate-200 mt-1">{linkedSessions.length}</div></div>
                              <div className="bg-slate-950 border border-slate-800 rounded p-2 text-center"><div className="text-slate-500">Docs</div><div className="text-slate-200 mt-1">{linkedDocs.length}</div></div>
                           </div>
                        </div>
                     </div>
                  </div>
               )}

               {activeTab === 'content' && (
                  <div className="bg-slate-900 border border-slate-800 rounded-lg p-6">
                     <div className="prose prose-invert prose-sm max-w-none [&_h1]:text-slate-100 [&_h2]:text-slate-200 [&_h3]:text-slate-300 [&_p]:text-slate-400 [&_li]:text-slate-400 [&_code]:bg-slate-800 [&_code]:text-indigo-300 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_pre]:bg-slate-900 [&_pre]:border [&_pre]:border-slate-800 [&_a]:text-indigo-400 [&_a:hover]:text-indigo-300 [&_blockquote]:border-l-indigo-500 [&_blockquote]:text-slate-400">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                           {getFileContent(doc)}
                        </ReactMarkdown>
                     </div>
                  </div>
               )}

               {activeTab === 'linked_docs' && (
                  <div className="space-y-2">
                     {linkedDocs.map(linkedDoc => (
                        <div key={linkedDoc.id} className="flex items-center gap-3 p-3 bg-slate-900 border border-slate-800 rounded-lg">
                           <FolderTree size={16} className="text-slate-500" />
                           <div className="min-w-0">
                              <div className="text-sm text-slate-200 truncate">{linkedDoc.title || linkedDoc.id}</div>
                              <div className="text-xs text-slate-500 font-mono truncate">{linkedDoc.canonicalPath || linkedDoc.filePath}</div>
                           </div>
                        </div>
                     ))}
                     {(doc.frontmatter.pathRefs || []).map(pathRef => (
                        <div key={pathRef} className="flex items-center gap-3 p-3 bg-slate-900 border border-slate-800 rounded-lg">
                           <Link2 size={16} className="text-slate-500" />
                           <span className="text-slate-300 font-mono text-sm">{pathRef}</span>
                        </div>
                     ))}
                     {linkedDocs.length === 0 && (doc.frontmatter.pathRefs || []).length === 0 && (
                        <p className="text-slate-500 italic">No linked documents.</p>
                     )}
                  </div>
               )}

               {activeTab === 'linked_entities' && (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                     <div>
                        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2"><User size={14} /> Features</h3>
                        <div className="space-y-2">
                           {linkedFeatures.map(feature => {
                              const style = getFeatureStatusStyle(feature.status);
                              return (
                                 <button
                                    key={feature.id}
                                    onClick={() => { onClose(); navigate(`/board?feature=${encodeURIComponent(feature.id)}`); }}
                                    className="w-full text-left p-3 bg-slate-900 border border-slate-800 rounded-lg hover:border-indigo-500/50 hover:bg-slate-800/50 transition-all"
                                 >
                                    <div className="flex items-center justify-between gap-2">
                                       <div className="text-xs font-mono text-indigo-400">{feature.id}</div>
                                       <span className={`text-[10px] font-semibold rounded-full border px-1.5 py-0.5 ${style.badge}`}>
                                          {style.label}
                                       </span>
                                    </div>
                                    <div className="text-sm text-slate-200 truncate">{feature.name || feature.id}</div>
                                 </button>
                              );
                           })}
                           {linkedFeatures.length === 0 && <p className="text-slate-500 text-sm italic">No linked features.</p>}
                        </div>
                     </div>

                     <div>
                        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2"><ListTodo size={14} /> Tasks</h3>
                        <div className="space-y-2">
                           {linkedTasks.map(task => (
                              <div key={task.id} className="p-3 bg-slate-900 border border-slate-800 rounded-lg">
                                 <div className="text-xs font-mono text-slate-500">{task.id}</div>
                                 <div className="text-sm text-slate-200 truncate">{task.title}</div>
                                 {task.sessionId && (
                                    <button
                                       onClick={() => { onClose(); navigate(`/sessions?session=${encodeURIComponent(task.sessionId || '')}`); }}
                                       className="mt-1 text-[11px] text-indigo-400 hover:text-indigo-300"
                                    >
                                       Session: {task.sessionId}
                                    </button>
                                 )}
                              </div>
                           ))}
                           {linkedTasks.length === 0 && <p className="text-slate-500 text-sm italic">No linked tasks.</p>}
                        </div>
                     </div>

                     <div>
                        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2"><Terminal size={14} /> Sessions</h3>
                        <div className="space-y-2">
                           {linkedSessions.map(session => (
                              <button
                                 key={session.id}
                                 onClick={() => { onClose(); navigate(`/sessions/${encodeURIComponent(session.id)}`); }}
                                 className="w-full text-left p-3 bg-slate-900 border border-slate-800 rounded-lg hover:border-indigo-500/50 hover:bg-slate-800/50 transition-all"
                              >
                                 <div className="flex justify-between items-center">
                                    <span className="text-xs font-mono text-indigo-400">{session.id}</span>
                                    <span className="text-[10px] text-slate-500">{session.status}</span>
                                 </div>
                                 <div className="text-xs text-slate-400 mt-1">{session.model || 'Unknown model'}</div>
                                 {session.totalCost > 0 && (
                                    <div className="text-[10px] text-emerald-400 mt-1">${session.totalCost.toFixed(2)}</div>
                                 )}
                              </button>
                           ))}
                           {linkedSessions.length === 0 && <p className="text-slate-500 text-sm italic">No linked sessions.</p>}
                        </div>
                     </div>
                  </div>
               )}
            </div>
         </div>
      </div>
   );
};
