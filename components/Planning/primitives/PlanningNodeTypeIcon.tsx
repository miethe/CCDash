import {
  AlertCircle,
  BookOpen,
  FileCheck2,
  FileText,
  FolderSearch,
  Tag,
} from 'lucide-react';

import type { PlanningNodeType } from '../../../types';

export interface PlanningNodeTypeIconProps {
  type: PlanningNodeType;
  /** Icon size in pixels. Defaults to 13. */
  size?: number;
  /** Additional className applied to the icon element. */
  className?: string;
}

/**
 * Reusable icon component for PlanningNodeType values. Matches the inline
 * NodeTypeIcon used in PlanningNodeDetail and PlanningGraphPanel.
 */
export function PlanningNodeTypeIcon({
  type,
  size = 13,
  className = 'shrink-0 text-muted-foreground',
}: PlanningNodeTypeIconProps) {
  const p = { size, className };
  switch (type) {
    case 'design_spec':        return <FolderSearch {...p} />;
    case 'prd':                return <FileText {...p} />;
    case 'implementation_plan': return <FileCheck2 {...p} />;
    case 'progress':           return <BookOpen {...p} />;
    case 'context':            return <Tag {...p} />;
    case 'tracker':            return <AlertCircle {...p} />;
    case 'report':             return <FileText {...p} />;
    default:                   return <FileText {...p} />;
  }
}
