import { describe, expect, it } from 'vitest';

import { buildDocumentFileTree } from '../documentFileTree';
import type { PlanDocument } from '../../types';

const createDocument = (filePath: string): PlanDocument => ({
  id: filePath,
  title: filePath.split('/').pop() || filePath,
  filePath,
  canonicalPath: filePath,
  status: 'active',
  createdAt: '',
  updatedAt: '',
  completedAt: '',
  lastModified: '',
  author: '',
  docType: 'implementation_plan',
  category: '',
  docSubtype: '',
  rootKind: 'project_plans',
  hasFrontmatter: true,
  frontmatterType: 'yaml',
  frontmatter: {
    tags: [],
    linkedFeatures: [],
    linkedFeatureRefs: [],
    blockedBy: [],
    linkedSessions: [],
    linkedTasks: [],
    lineageChildren: [],
    relatedFiles: [],
    commits: [],
    prs: [],
    requestLogIds: [],
    commitRefs: [],
    prRefs: [],
    relatedRefs: [],
    pathRefs: [],
    slugRefs: [],
    prdRefs: [],
    sourceDocuments: [],
    filesAffected: [],
    filesModified: [],
    contextFiles: [],
    integritySignalRefs: [],
    fieldKeys: [],
    raw: {},
  },
  metadata: {
    phase: '',
    taskCounts: {
      total: 0,
      completed: 0,
      inProgress: 0,
      blocked: 0,
    },
    owners: [],
    contributors: [],
    reviewers: [],
    approvers: [],
    audience: [],
    labels: [],
    blockedBy: [],
    requestLogIds: [],
    commitRefs: [],
    prRefs: [],
    sourceDocuments: [],
    filesAffected: [],
    filesModified: [],
    contextFiles: [],
    integritySignalRefs: [],
    linkedTasks: [],
    executionEntrypoints: [],
    linkedFeatureRefs: [],
    docTypeFields: {},
    featureSlugHint: '',
    canonicalPath: filePath,
  },
  pathSegments: filePath.split('/'),
  featureCandidates: [],
  totalTasks: 0,
  completedTasks: 0,
  inProgressTasks: 0,
  blockedTasks: 0,
});

describe('buildDocumentFileTree', () => {
  it('creates a nested file tree sorted by folders before files', () => {
    const tree = buildDocumentFileTree([
      createDocument('docs/project_plans/plan-b.md'),
      createDocument('docs/project_plans/sub/plan-a.md'),
      createDocument('docs/project_plans/plan-a.md'),
    ]);

    expect(tree).toEqual([
      {
        name: 'docs',
        path: 'docs',
        type: 'directory',
        children: [
          {
            name: 'project_plans',
            path: 'docs/project_plans',
            type: 'directory',
            children: [
              {
                name: 'sub',
                path: 'docs/project_plans/sub',
                type: 'directory',
                children: [
                  {
                    name: 'plan-a.md',
                    path: 'docs/project_plans/sub/plan-a.md',
                    type: 'file',
                  },
                ],
              },
              {
                name: 'plan-a.md',
                path: 'docs/project_plans/plan-a.md',
                type: 'file',
              },
              {
                name: 'plan-b.md',
                path: 'docs/project_plans/plan-b.md',
                type: 'file',
              },
            ],
          },
        ],
      },
    ]);
  });

  it('ignores documents without a usable path', () => {
    const tree = buildDocumentFileTree([
      createDocument(''),
      createDocument('./docs/project_plans/plan.md'),
    ]);

    expect(tree[0]?.children?.[0]?.children).toEqual([
      {
        name: 'plan.md',
        path: 'docs/project_plans/plan.md',
        type: 'file',
      },
    ]);
  });
});
