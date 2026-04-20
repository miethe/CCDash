/**
 * Planning primitives barrel.
 *
 * Most visual primitives (StatusChip, EffectiveStatusChips, MismatchBadge,
 * BatchReadinessPill, PlanningNodeTypeIcon, statusVariant, readinessVariant)
 * now live in @miethe/ui (PCP-709). Consumers should import from
 * `@/components/shared/PlanningMetadata` instead of reaching in here.
 *
 * Re-exports below are kept for planning-local items and for a compatibility
 * bridge to the extracted primitives so existing deep imports still resolve.
 */
export {
  StatusChip,
  EffectiveStatusChips,
  MismatchBadge,
  BatchReadinessPill,
  PlanningNodeTypeIcon,
  statusVariant,
  readinessVariant,
} from '@miethe/ui/primitives';
export type {
  StatusChipProps,
  EffectiveStatusChipsProps,
  MismatchBadgeProps,
  BatchReadinessPillProps,
  PlanningNodeTypeIconProps,
  StatusChipVariant,
  ReadinessVariant,
} from '@miethe/ui/primitives';

export { LineageRow } from './LineageRow';
export type { LineageRowProps } from './LineageRow';

export { castPlanningStatus } from './castPlanningStatus';

export {
  Panel,
  Tile,
  Chip,
  Btn,
  BtnGhost,
  BtnPrimary,
  Dot,
  StatusPill,
  ArtifactChip,
  MetricTile,
  SectionHeader,
  Spark,
  ExecBtn,
} from './PhaseZeroPrimitives';

export { PhaseOperationsPanel } from './PhaseOperationsPanel';
export type { PhaseOperationsPanelProps } from './PhaseOperationsPanel';
export {
  PhaseOperationsContent,
  PhaseOperationsBatchSection,
  PhaseOperationsTaskSection,
  PhaseOperationsDependencySection,
  PhaseOperationsEvidenceSection,
} from './PhaseOperationsPanel';
