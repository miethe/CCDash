import React, { useEffect, useMemo, useState } from 'react';
import { ChevronRight } from 'lucide-react';

import { DomainHealthRollup } from '../../types';
import { HealthGauge } from './HealthGauge';

interface DomainTreeViewProps {
  domains: DomainHealthRollup[];
  selectedDomainId?: string | null;
  onSelectDomain?: (domain: DomainHealthRollup | null) => void;
  className?: string;
}

interface FlatNode {
  node: DomainHealthRollup;
  depth: number;
  parentId: string | null;
}

const flattenVisibleNodes = (
  nodes: DomainHealthRollup[],
  expanded: Set<string>,
  depth = 0,
  parentId: string | null = null,
): FlatNode[] => {
  const flat: FlatNode[] = [];
  nodes.forEach(node => {
    flat.push({ node, depth, parentId });
    if (node.children.length > 0 && expanded.has(node.domainId)) {
      flat.push(...flattenVisibleNodes(node.children, expanded, depth + 1, node.domainId));
    }
  });
  return flat;
};

const findById = (nodes: DomainHealthRollup[], id: string): DomainHealthRollup | null => {
  for (const node of nodes) {
    if (node.domainId === id) return node;
    const child = findById(node.children, id);
    if (child) return child;
  }
  return null;
};

const findPathToId = (nodes: DomainHealthRollup[], id: string, trail: string[] = []): string[] | null => {
  for (const node of nodes) {
    const nextTrail = [...trail, node.domainId];
    if (node.domainId === id) return nextTrail;
    const childTrail = findPathToId(node.children, id, nextTrail);
    if (childTrail) return childTrail;
  }
  return null;
};

export const DomainTreeView: React.FC<DomainTreeViewProps> = ({
  domains,
  selectedDomainId = null,
  onSelectDomain,
  className = '',
}) => {
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    domains.forEach(domain => initial.add(domain.domainId));
    return initial;
  });
  const [focusedDomainId, setFocusedDomainId] = useState<string | null>(selectedDomainId);

  useEffect(() => {
    if (domains.length === 0) return;
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.size === 0) {
        domains.forEach(domain => next.add(domain.domainId));
      }
      if (selectedDomainId) {
        const selectionPath = findPathToId(domains, selectedDomainId) || [];
        selectionPath.forEach(domainId => next.add(domainId));
      }
      return next;
    });
  }, [domains, selectedDomainId]);

  const flatNodes = useMemo(() => flattenVisibleNodes(domains, expanded), [domains, expanded]);

  const focusedIndex = flatNodes.findIndex(entry => entry.node.domainId === (focusedDomainId || selectedDomainId));

  const toggleExpanded = (domainId: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(domainId)) next.delete(domainId);
      else next.add(domainId);
      return next;
    });
  };

  const moveFocus = (nextIndex: number) => {
    if (nextIndex < 0 || nextIndex >= flatNodes.length) return;
    setFocusedDomainId(flatNodes[nextIndex].node.domainId);
  };

  const onTreeKeyDown: React.KeyboardEventHandler<HTMLDivElement> = event => {
    if (flatNodes.length === 0) return;
    const currentIndex = focusedIndex >= 0 ? focusedIndex : 0;
    const current = flatNodes[currentIndex];

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      moveFocus(currentIndex + 1);
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      moveFocus(currentIndex - 1);
      return;
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      if (current.node.children.length > 0 && !expanded.has(current.node.domainId)) {
        toggleExpanded(current.node.domainId);
      }
      return;
    }
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      if (expanded.has(current.node.domainId) && current.node.children.length > 0) {
        toggleExpanded(current.node.domainId);
      } else if (current.parentId) {
        setFocusedDomainId(current.parentId);
      }
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      onSelectDomain?.(current.node);
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      onSelectDomain?.(null);
      setFocusedDomainId(null);
    }
  };

  const renderNode = (node: DomainHealthRollup, depth: number) => {
    const isExpanded = expanded.has(node.domainId);
    const isSelected = selectedDomainId === node.domainId;
    const isFocused = (focusedDomainId || selectedDomainId) === node.domainId;
    const hasChildren = node.children.length > 0;

    return (
      <li key={node.domainId}>
        <div
          className={`group flex items-center gap-2 rounded-lg border px-2 py-2 ${isSelected ? 'border-indigo-500 bg-indigo-500/10' : 'border-transparent hover:border-slate-700 hover:bg-slate-800/50'} ${isFocused ? 'ring-1 ring-indigo-500/50' : ''}`.trim()}
          style={{ paddingLeft: `${depth * 14 + 8}px` }}
        >
          {hasChildren ? (
            <button
              type="button"
              onClick={() => toggleExpanded(node.domainId)}
              className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-slate-700/80 bg-slate-900 text-slate-400 transition-colors hover:border-slate-500 hover:text-slate-200"
              aria-label={`${isExpanded ? 'Collapse' : 'Expand'} ${node.domainName} (${node.children.length} sub-domains)`}
            >
              <ChevronRight
                size={14}
                className={`transition-transform duration-150 ${isExpanded ? 'rotate-90' : ''}`.trim()}
              />
            </button>
          ) : (
            <span
              className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-dashed border-slate-700/70 bg-slate-900/70 text-[10px] font-semibold uppercase tracking-wide text-slate-500"
              title="Leaf domain (no sub-domains)"
              aria-label="Leaf domain (no sub-domains)"
            >
              •
            </span>
          )}
          <button
            type="button"
            onClick={() => {
              setFocusedDomainId(node.domainId);
              onSelectDomain?.(node);
            }}
            className="flex flex-1 items-center justify-between gap-2 text-left"
          >
            <div>
              <p className="text-sm font-medium text-slate-200">{node.domainName}</p>
              <p className="text-[11px] uppercase tracking-wide text-slate-500">
                {node.tier}
                {hasChildren ? ` · ${node.children.length} sub-domains` : ' · leaf'}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <HealthGauge passRate={node.passRate} integrityScore={node.integrityScore} size="sm" showLabel={false} />
            </div>
          </button>
        </div>
        {hasChildren && isExpanded && <ul className="mt-1 space-y-1">{node.children.map(child => renderNode(child, depth + 1))}</ul>}
      </li>
    );
  };

  if (domains.length === 0) {
    return (
      <div className={`rounded-xl border border-slate-800 bg-slate-900 p-4 text-sm text-slate-500 ${className}`.trim()}>
        No domains found.
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border border-slate-800 bg-slate-900 p-2 ${className}`.trim()}
      role="tree"
      tabIndex={0}
      onKeyDown={onTreeKeyDown}
      aria-label="Domain health tree"
    >
      <ul className="space-y-1">{domains.map(domain => renderNode(domain, 0))}</ul>
      {selectedDomainId && findById(domains, selectedDomainId) === null && (
        <p className="mt-2 text-xs text-amber-300">Selected domain no longer exists in this view.</p>
      )}
    </div>
  );
};

export type { DomainTreeViewProps };
