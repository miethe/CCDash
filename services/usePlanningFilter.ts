// P13-003: Hook for reading/mutating planning filter URL params.
// Separated from planningRoutes.ts to keep that file free of React/RR6 deps.

import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

import {
  resolvePlanningFilterState,
  type PlanningFilterState,
  type PlanningStatusBucket,
  type PlanningSignal,
} from './planningRoutes';

export type { PlanningFilterState };

export function usePlanningFilter(): {
  filter: PlanningFilterState;
  setStatusBucket: (bucket: PlanningStatusBucket) => void;
  setSignal: (signal: PlanningSignal) => void;
  clearFilter: () => void;
} {
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = resolvePlanningFilterState(searchParams);

  const setStatusBucket = useCallback(
    (bucket: PlanningStatusBucket) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        const current = next.get('statusBucket');
        if (current === bucket) {
          next.delete('statusBucket');
        } else {
          next.set('statusBucket', bucket);
        }
        return next;
      });
    },
    [setSearchParams],
  );

  const setSignal = useCallback(
    (signal: PlanningSignal) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        const current = next.get('signal');
        if (current === signal) {
          next.delete('signal');
        } else {
          next.set('signal', signal);
        }
        return next;
      });
    },
    [setSearchParams],
  );

  const clearFilter = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete('statusBucket');
      next.delete('signal');
      return next;
    });
  }, [setSearchParams]);

  return { filter, setStatusBucket, setSignal, clearFilter };
}
