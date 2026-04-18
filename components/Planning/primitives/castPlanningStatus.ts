import type { PlanningEffectiveStatus } from '../../../types';

/**
 * Defensively cast a `Record<string, unknown>` planningStatus dict (as returned
 * by the backend serialiser) to a PlanningEffectiveStatus-shaped object.
 * Only accesses known keys via narrowing; returns null when the input is empty
 * or does not contain at minimum one of rawStatus / effectiveStatus.
 */
export function castPlanningStatus(raw: Record<string, unknown>): PlanningEffectiveStatus | null {
  if (!raw || typeof raw !== 'object') return null;
  const rawStatus =
    typeof raw.rawStatus === 'string'
      ? raw.rawStatus
      : typeof raw.raw_status === 'string'
        ? raw.raw_status
        : '';
  const effectiveStatus =
    typeof raw.effectiveStatus === 'string'
      ? raw.effectiveStatus
      : typeof raw.effective_status === 'string'
        ? raw.effective_status
        : '';
  if (!rawStatus && !effectiveStatus) return null;

  const provenanceRaw = raw.provenance;
  const provenanceObj =
    provenanceRaw && typeof provenanceRaw === 'object' && !Array.isArray(provenanceRaw)
      ? (provenanceRaw as Record<string, unknown>)
      : null;

  const mismatchRaw = raw.mismatchState ?? raw.mismatch_state;
  const mismatchObj =
    mismatchRaw && typeof mismatchRaw === 'object' && !Array.isArray(mismatchRaw)
      ? (mismatchRaw as Record<string, unknown>)
      : null;

  return {
    rawStatus,
    effectiveStatus,
    provenance: {
      source: (
        typeof provenanceObj?.source === 'string' ? provenanceObj.source : 'unknown'
      ) as PlanningEffectiveStatus['provenance']['source'],
      reason: typeof provenanceObj?.reason === 'string' ? provenanceObj.reason : '',
      evidence: Array.isArray(provenanceObj?.evidence)
        ? (provenanceObj.evidence as PlanningEffectiveStatus['provenance']['evidence'])
        : [],
    },
    mismatchState: {
      state: (
        typeof mismatchObj?.state === 'string' ? mismatchObj.state : 'unknown'
      ) as PlanningEffectiveStatus['mismatchState']['state'],
      reason: typeof mismatchObj?.reason === 'string' ? mismatchObj.reason : '',
      isMismatch: mismatchObj?.isMismatch === true || mismatchObj?.is_mismatch === true,
      evidence: Array.isArray(mismatchObj?.evidence)
        ? (mismatchObj.evidence as PlanningEffectiveStatus['mismatchState']['evidence'])
        : [],
    },
  };
}
