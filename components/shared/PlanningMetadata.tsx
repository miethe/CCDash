/**
 * PCP-706: Stable shared import surface for planning metadata primitives.
 *
 * Consumers should import planning metadata components from here rather than
 * reaching into @/components/Planning/primitives directly. After PCP-709
 * extracts these to @miethe/ui, re-export sources flip from local primitives
 * to @miethe/ui without requiring changes in every consumer.
 *
 * NOT extraction candidates (planning-domain-specific, kept local):
 *   - LineageRow (single-use, planning-domain-specific)
 *   - castPlanningStatus (planning-type-specific utility)
 *   - variants (planning-local enums)
 *
 * Extraction candidates (PCP-709 will flip these to @miethe/ui):
 *   - StatusChip
 *   - EffectiveStatusChips
 *   - BatchReadinessPill
 *   - MismatchBadge
 *   - PlanningNodeTypeIcon
 */

// -- Extraction candidates (will re-export from @miethe/ui after PCP-709) ------
export { StatusChip } from '@/components/Planning/primitives/StatusChip';
export type { StatusChipProps } from '@/components/Planning/primitives/StatusChip';

export { EffectiveStatusChips } from '@/components/Planning/primitives/EffectiveStatusChips';
export type { EffectiveStatusChipsProps } from '@/components/Planning/primitives/EffectiveStatusChips';

export { BatchReadinessPill } from '@/components/Planning/primitives/BatchReadinessPill';
export type { BatchReadinessPillProps } from '@/components/Planning/primitives/BatchReadinessPill';

export { MismatchBadge } from '@/components/Planning/primitives/MismatchBadge';
export type { MismatchBadgeProps } from '@/components/Planning/primitives/MismatchBadge';

export { PlanningNodeTypeIcon } from '@/components/Planning/primitives/PlanningNodeTypeIcon';
export type { PlanningNodeTypeIconProps } from '@/components/Planning/primitives/PlanningNodeTypeIcon';

// -- Planning-local (not extraction candidates) --------------------------------
export { LineageRow } from '@/components/Planning/primitives/LineageRow';
export type { LineageRowProps } from '@/components/Planning/primitives/LineageRow';

export { castPlanningStatus } from '@/components/Planning/primitives/castPlanningStatus';

export { statusVariant, readinessVariant } from '@/components/Planning/primitives/variants';
export type { StatusChipVariant, ReadinessVariant } from '@/components/Planning/primitives/variants';
