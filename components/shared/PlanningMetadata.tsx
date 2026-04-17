/**
 * PCP-706 / PCP-709: Stable shared import surface for planning metadata primitives.
 *
 * Consumers should import planning metadata components from here rather than
 * reaching into @/components/Planning/primitives directly.
 *
 * Extraction candidates flipped to @miethe/ui v0.3.0 (PCP-709):
 *   - StatusChip
 *   - EffectiveStatusChips
 *   - BatchReadinessPill
 *   - MismatchBadge
 *   - PlanningNodeTypeIcon
 *
 * Not extraction candidates (planning-domain-specific, kept local):
 *   - LineageRow
 *   - castPlanningStatus
 *   - variants (planning-local re-exports)
 */

// -- Extracted to @miethe/ui (PCP-709) ----------------------------------------
export {
  StatusChip,
  EffectiveStatusChips,
  BatchReadinessPill,
  MismatchBadge,
  PlanningNodeTypeIcon,
  statusVariant,
  readinessVariant,
} from '@miethe/ui/primitives';
export type {
  StatusChipProps,
  EffectiveStatusChipsProps,
  BatchReadinessPillProps,
  MismatchBadgeProps,
  PlanningNodeTypeIconProps,
  StatusChipVariant,
  ReadinessVariant,
} from '@miethe/ui/primitives';

// -- Planning-local (not extraction candidates) --------------------------------
export { LineageRow } from '@/components/Planning/primitives/LineageRow';
export type { LineageRowProps } from '@/components/Planning/primitives/LineageRow';

export { castPlanningStatus } from '@/components/Planning/primitives/castPlanningStatus';
