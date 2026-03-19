import type { FileNode } from '@miethe/ui';

import type { PlanDocument } from '../types';

const compareNodes = (left: FileNode, right: FileNode): number => {
  if (left.type !== right.type) {
    return left.type === 'directory' ? -1 : 1;
  }
  return left.name.localeCompare(right.name);
};

const sortTree = (nodes: FileNode[]): FileNode[] => (
  nodes
    .map((node) => (
      node.type === 'directory' && node.children
        ? { ...node, children: sortTree(node.children) }
        : node
    ))
    .sort(compareNodes)
);

export const buildDocumentFileTree = (documents: PlanDocument[]): FileNode[] => {
  const root: FileNode[] = [];

  documents.forEach((document) => {
    const normalizedPath = String(document.filePath || document.canonicalPath || '')
      .replace(/\\/g, '/')
      .replace(/^\.?\//, '')
      .trim();

    if (!normalizedPath) {
      return;
    }

    const parts = normalizedPath.split('/').filter(Boolean);
    let currentLevel = root;

    parts.forEach((part, index) => {
      const nodePath = parts.slice(0, index + 1).join('/');
      const isFile = index === parts.length - 1;
      const existingNode = currentLevel.find((node) => node.path === nodePath);

      if (existingNode) {
        if (existingNode.type === 'directory' && existingNode.children) {
          currentLevel = existingNode.children;
        }
        return;
      }

      const nextNode: FileNode = isFile
        ? {
            name: part,
            path: nodePath,
            type: 'file',
          }
        : {
            name: part,
            path: nodePath,
            type: 'directory',
            children: [],
          };

      currentLevel.push(nextNode);
      if (nextNode.type === 'directory' && nextNode.children) {
        currentLevel = nextNode.children;
      }
    });
  });

  return sortTree(root);
};
