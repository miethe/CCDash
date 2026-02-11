import React, { useState } from 'react';
import { PlanDocument } from '../types';
import { FileText, X, Tag, User, Calendar, GitCommit, GitBranch, GitPullRequest, ListTodo, Terminal, Maximize2 } from 'lucide-react';
import { useData } from '../contexts/DataContext';

// --- Mock Content Helper ---
export const getFileContent = (doc: PlanDocument): string => {
   // If we have real content from the API, use it
   if (doc.content) return doc.content;
   return `# ${doc.title}

> **Status**: ${doc.status.toUpperCase()}
> **Author**: ${doc.author}
> **Version**: ${doc.frontmatter.version || '1.0'}

## 1. Overview
This is a placeholder content block for **${doc.filePath}**. In a real application, this would stream the actual markdown content from the filesystem.

## 2. Requirements
- [x] Requirement A
- [ ] Requirement B
- [ ] Requirement C

## 3. Architecture
The system utilizes a modular approach...

## 4. Metadata (Parsed from Frontmatter)
\`\`\`json
${JSON.stringify(doc.frontmatter, null, 2)}
\`\`\`
  `;
};

export const DocumentModal = ({ doc, onClose }: { doc: PlanDocument; onClose: () => void }) => {
   const { tasks, sessions } = useData();
   const [activeTab, setActiveTab] = useState<'overview' | 'content' | 'linked_files' | 'linked_entities'>('overview');

   const linkedTasks = tasks.filter(t => doc.frontmatter.linkedFeatures?.includes(t.id));
   const linkedSessions = sessions.filter(s => doc.frontmatter.linkedSessions?.includes(s.id));

   return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-200">
         <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-5xl h-[85vh] flex flex-col shadow-2xl overflow-hidden">

            {/* Header */}
            <div className="p-6 border-b border-slate-800 flex justify-between items-start bg-slate-900">
               <div>
                  <div className="flex items-center gap-3 mb-2">
                     <span className="font-mono text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">{doc.id}</span>
                     <span className={`text-xs font-bold uppercase px-2 py-0.5 rounded ${doc.status === 'active' ? 'bg-emerald-500/10 text-emerald-500' :
                           doc.status === 'draft' ? 'bg-indigo-500/10 text-indigo-500' :
                              'bg-slate-500/10 text-slate-500'
                        }`}>
                        {doc.status}
                     </span>
                  </div>
                  <h2 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
                     <FileText className="text-slate-400" /> {doc.title}
                  </h2>
                  <p className="text-slate-400 font-mono text-xs mt-1">{doc.filePath}</p>
               </div>
               <button onClick={onClose} className="text-slate-500 hover:text-slate-200 transition-colors p-1 hover:bg-slate-800 rounded">
                  <X size={24} />
               </button>
            </div>

            {/* Tabs */}
            <div className="px-6 border-b border-slate-800 bg-slate-900/50 flex gap-6">
               {[
                  { id: 'overview', label: 'Overview' },
                  { id: 'content', label: 'Contents' },
                  { id: 'linked_files', label: 'Linked Files', count: doc.frontmatter.relatedFiles?.length },
                  { id: 'linked_entities', label: 'Linked Entities', count: (linkedTasks.length + linkedSessions.length) }
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

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6 bg-slate-950/30">

               {/* OVERVIEW TAB */}
               {activeTab === 'overview' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                     <div className="space-y-6">
                        <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
                           <h3 className="text-sm font-semibold text-slate-200 mb-4">Metadata</h3>
                           <div className="space-y-3">
                              <div className="flex justify-between">
                                 <span className="text-sm text-slate-500 flex items-center gap-2"><User size={14} /> Author</span>
                                 <span className="text-sm text-slate-300">{doc.author}</span>
                              </div>
                              <div className="flex justify-between">
                                 <span className="text-sm text-slate-500 flex items-center gap-2"><Calendar size={14} /> Modified</span>
                                 <span className="text-sm text-slate-300">{new Date(doc.lastModified).toLocaleDateString()}</span>
                              </div>
                              <div className="flex justify-between">
                                 <span className="text-sm text-slate-500 flex items-center gap-2"><GitBranch size={14} /> Version</span>
                                 <span className="text-sm text-slate-300 font-mono">{doc.frontmatter.version || 'HEAD'}</span>
                              </div>
                           </div>
                        </div>

                        <div>
                           <h3 className="text-sm font-semibold text-slate-400 mb-2 uppercase tracking-wider">Tags</h3>
                           <div className="flex flex-wrap gap-2">
                              {doc.frontmatter.tags.map(tag => (
                                 <span key={tag} className="flex items-center gap-1 text-xs bg-indigo-500/10 text-indigo-400 px-2 py-1 rounded-full border border-indigo-500/20">
                                    <Tag size={12} /> {tag}
                                 </span>
                              ))}
                           </div>
                        </div>
                     </div>

                     <div className="space-y-6">
                        {(doc.frontmatter.commits || doc.frontmatter.prs) && (
                           <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
                              <h3 className="text-sm font-semibold text-slate-200 mb-4">Version Control</h3>
                              <div className="space-y-2">
                                 {doc.frontmatter.commits?.map(c => (
                                    <div key={c} className="flex items-center gap-2 text-sm text-slate-300">
                                       <GitCommit size={14} className="text-purple-400" />
                                       <span className="font-mono">{c}</span>
                                    </div>
                                 ))}
                                 {doc.frontmatter.prs?.map(pr => (
                                    <div key={pr} className="flex items-center gap-2 text-sm text-slate-300">
                                       <GitPullRequest size={14} className="text-blue-400" />
                                       <span className="font-mono">{pr}</span>
                                    </div>
                                 ))}
                              </div>
                           </div>
                        )}
                     </div>
                  </div>
               )}

               {/* CONTENT TAB */}
               {activeTab === 'content' && (
                  <div className="bg-slate-900 border border-slate-800 rounded-lg p-6">
                     <pre className="font-mono text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">
                        {getFileContent(doc)}
                     </pre>
                  </div>
               )}

               {/* LINKED FILES TAB */}
               {activeTab === 'linked_files' && (
                  <div className="space-y-2">
                     {doc.frontmatter.relatedFiles?.map(f => (
                        <div key={f} className="flex items-center gap-3 p-3 bg-slate-900 border border-slate-800 rounded-lg">
                           <FileText size={16} className="text-slate-500" />
                           <span className="text-slate-300 font-mono text-sm">{f}</span>
                        </div>
                     ))}
                     {(!doc.frontmatter.relatedFiles || doc.frontmatter.relatedFiles.length === 0) && (
                        <p className="text-slate-500 italic">No related files defined in frontmatter.</p>
                     )}
                  </div>
               )}

               {/* LINKED ENTITIES TAB */}
               {activeTab === 'linked_entities' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                     <div>
                        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2"><ListTodo size={14} /> Features / Tasks</h3>
                        <div className="space-y-2">
                           {linkedTasks.map(task => (
                              <div key={task.id} className="p-3 bg-slate-900 border border-slate-800 rounded-lg">
                                 <div className="flex justify-between items-center mb-1">
                                    <span className="text-xs font-mono text-slate-500">{task.id}</span>
                                    <span className="text-[10px] uppercase text-emerald-500 bg-emerald-500/10 px-1.5 py-0.5 rounded">{task.status}</span>
                                 </div>
                                 <div className="text-sm text-slate-200 font-medium">{task.title}</div>
                              </div>
                           ))}
                           {linkedTasks.length === 0 && <p className="text-slate-500 text-sm italic">No linked tasks.</p>}
                        </div>
                     </div>

                     <div>
                        <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2"><Terminal size={14} /> Sessions</h3>
                        <div className="space-y-2">
                           {linkedSessions.map(session => (
                              <div key={session.id} className="p-3 bg-slate-900 border border-slate-800 rounded-lg">
                                 <div className="flex justify-between items-center mb-1">
                                    <span className="text-xs font-mono text-indigo-400 font-bold">{session.id}</span>
                                    <span className="text-xs text-slate-500">{new Date(session.startedAt).toLocaleDateString()}</span>
                                 </div>
                                 <div className="text-xs text-slate-400 mt-1">
                                    Model: <span className="text-slate-300">{session.model}</span>
                                 </div>
                              </div>
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