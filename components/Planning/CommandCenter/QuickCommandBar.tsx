import { Copy, ExternalLink, GitPullRequest, PanelRightOpen, Play, Terminal } from 'lucide-react';

import type { PlanningCommandCenterItem } from '@/types';
import { canLaunchCommandCenterItem, commandCenterPlanPath } from './commandCenterUtils';
import { BtnGhost, BtnPrimary, Chip } from '../primitives';

interface QuickCommandBarProps {
  item: PlanningCommandCenterItem;
  command: string;
  onCopy?: (command: string) => void;
  onOpenLaunch?: (featureId: string) => void;
  onOpenExecution?: (featureId: string) => void;
  onOpenPlan?: (path: string) => void;
  onOpenDetail?: () => void;
  onOpenPullRequest?: (url: string) => void;
}

export function QuickCommandBar({
  item,
  command,
  onCopy,
  onOpenLaunch,
  onOpenExecution,
  onOpenPlan,
  onOpenDetail,
  onOpenPullRequest,
}: QuickCommandBarProps) {
  const planPath = commandCenterPlanPath(item);
  const capabilities = item.command?.requiredCapabilities ?? [];
  const canLaunch = canLaunchCommandCenterItem(item);

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="command-center-quick-command-bar">
      <BtnPrimary
        size="sm"
        disabled={!canLaunch}
        onClick={() => onOpenLaunch?.(item.feature.featureId)}
        aria-label={`Launch next command for ${item.feature.featureId}`}
      >
        <Play size={13} aria-hidden />
        launch
      </BtnPrimary>
      <BtnGhost
        size="sm"
        onClick={() => onOpenExecution?.(item.feature.featureId)}
        aria-label={`Open execution workbench for ${item.feature.featureId}`}
      >
        <Terminal size={13} aria-hidden />
        workbench
      </BtnGhost>
      <BtnGhost
        size="sm"
        disabled={!command}
        onClick={() => onCopy?.(command)}
        aria-label="Copy next command"
      >
        <Copy size={13} aria-hidden />
        copy
      </BtnGhost>
      <BtnGhost
        size="sm"
        disabled={!planPath}
        onClick={() => onOpenPlan?.(planPath)}
        aria-label="Open target plan"
      >
        <ExternalLink size={13} aria-hidden />
        plan
      </BtnGhost>
      <BtnGhost
        size="sm"
        disabled={!item.pullRequest?.url}
        onClick={() => item.pullRequest?.url && onOpenPullRequest?.(item.pullRequest.url)}
        aria-label="Open pull request"
      >
        <GitPullRequest size={13} aria-hidden />
        PR
      </BtnGhost>
      <BtnGhost
        size="sm"
        disabled={!item.capabilities.review}
        aria-label="Review agents are unavailable for this item"
        title={item.capabilities.review ? 'Review-ready' : 'No review action available yet'}
      >
        review
      </BtnGhost>
      <BtnGhost
        size="sm"
        onClick={onOpenDetail}
        aria-label={`Open details for ${item.feature.featureId}`}
      >
        <PanelRightOpen size={13} aria-hidden />
        details
      </BtnGhost>
      <Chip className="planning-mono text-[10px]">
        <Terminal size={12} aria-hidden />
        {item.command?.ruleId || 'no-rule'}
      </Chip>
      {capabilities.map((capability) => (
        <Chip
          key={capability.name}
          className="planning-mono text-[10px]"
          title={capability.warning || capability.fallbackCommand}
        >
          {capability.supported ? capability.name : `${capability.name}: fallback`}
        </Chip>
      ))}
    </div>
  );
}
