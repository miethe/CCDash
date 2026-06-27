import { FilePlus2 } from 'lucide-react';

import type { PlanningCommandCenterRelatedFile } from '@/types';
import { compactPath } from './commandCenterUtils';
import { BtnGhost, Chip } from '../primitives';

interface RelatedFilesPickerProps {
  files: PlanningCommandCenterRelatedFile[];
  onAddFile: (path: string) => void;
}

export function RelatedFilesPicker({ files, onAddFile }: RelatedFilesPickerProps) {
  if (files.length === 0) {
    return (
      <div className="rounded-[var(--radius-sm)] border border-dashed border-[color:var(--line-1)] px-3 py-2 text-[11px] text-[color:var(--ink-4)]">
        No related files were discovered for this item.
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="command-center-related-files">
      <div className="planning-caps text-[10px] text-[color:var(--ink-3)]">related files</div>
      <div className="grid gap-2 lg:grid-cols-2">
        {files.map((file) => (
          <div
            key={`${file.docType}:${file.path}`}
            className="flex min-w-0 items-center gap-2 rounded-[var(--radius-sm)] border border-[color:var(--line-1)] bg-[color:var(--bg-1)] px-2.5 py-2"
          >
            <Chip className="planning-mono shrink-0 text-[9.5px]">{file.docType || 'file'}</Chip>
            <span className="planning-mono min-w-0 flex-1 truncate text-[10.5px] text-[color:var(--ink-2)]" title={file.path}>
              {compactPath(file.path, 70)}
            </span>
            <BtnGhost
              size="xs"
              disabled={!file.addable}
              onClick={() => onAddFile(file.path)}
              aria-label={`Add ${file.path} to command context`}
            >
              <FilePlus2 size={12} aria-hidden />
              add
            </BtnGhost>
          </div>
        ))}
      </div>
    </div>
  );
}
