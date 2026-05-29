/**
 * TanStack Query mutations for the features domain.
 *
 * T4-004: Port optimistic mutations to TQ useMutation.
 *
 * Replaces the manual `pendingFeatureStatusById` optimistic map that was in
 * `AppEntityDataContext`. Three mutation hooks:
 *
 *   useUpdateFeatureStatusMutation — PATCH /api/features/:id/status
 *   useUpdatePhaseStatusMutation   — PATCH /api/features/:id/phases/:pid/status
 *   useUpdateTaskStatusMutation    — PATCH /api/features/:id/phases/:pid/tasks/:tid/status
 *
 * Pattern: onMutate (snapshot + optimistic) → onError (rollback) → onSettled (invalidate).
 *
 * Resilience: On onError the cache is restored from the pre-mutation snapshot.
 * Consumers see the rollback within one render cycle (TQ synchronous snapshot restore).
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useDataClient } from '../../contexts/DataClientContext';
import { featuresKeys } from '../queryKeys';
import {
  aggregateFeatureFromPhases,
  matchesPhase,
} from '../../contexts/dataContextShared';
import type { Feature, TaskStatus } from '../../types';
import type { FeaturesPage } from '../queries/features';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Update a single feature in a FeaturesPage cache entry. */
function patchFeatureInPage(
  page: FeaturesPage | undefined,
  patcher: (feature: Feature) => Feature,
): FeaturesPage | undefined {
  if (!page) return page;
  return { ...page, items: page.items.map(patcher) };
}

// ─── useUpdateFeatureStatusMutation ───────────────────────────────────────────

export interface UpdateFeatureStatusVariables {
  projectId: string;
  featureId: string;
  status: string;
}

/**
 * Optimistic mutation for feature-level status updates.
 *
 * onMutate: snapshot cache, apply optimistic update.
 * onError: restore snapshot.
 * onSettled: invalidate features query so server state is authoritative.
 */
export function useUpdateFeatureStatusMutation() {
  const client = useDataClient();
  const queryClient = useQueryClient();

  return useMutation<Feature, Error, UpdateFeatureStatusVariables, { snapshot: FeaturesPage | undefined }>({
    mutationFn: ({ featureId, status }) =>
      client.updateFeatureStatus(featureId, status),

    onMutate: async ({ projectId, featureId, status }) => {
      const queryKey = featuresKeys.list(projectId, undefined, 0);
      await queryClient.cancelQueries({ queryKey });

      const snapshot = queryClient.getQueryData<FeaturesPage>(queryKey);

      queryClient.setQueryData<FeaturesPage>(queryKey, page =>
        patchFeatureInPage(page, f =>
          f.id === featureId ? { ...f, status } : f,
        ),
      );

      return { snapshot };
    },

    onError: (_err, { projectId }, context) => {
      const queryKey = featuresKeys.list(projectId, undefined, 0);
      if (context?.snapshot !== undefined) {
        queryClient.setQueryData(queryKey, context.snapshot);
      }
    },

    onSettled: (_data, _err, { projectId }) => {
      void queryClient.invalidateQueries({ queryKey: featuresKeys.all(projectId) });
    },
  });
}

// ─── useUpdatePhaseStatusMutation ─────────────────────────────────────────────

export interface UpdatePhaseStatusVariables {
  projectId: string;
  featureId: string;
  phaseId: string;
  status: string;
}

/**
 * Optimistic mutation for phase-level status updates.
 */
export function useUpdatePhaseStatusMutation() {
  const client = useDataClient();
  const queryClient = useQueryClient();

  return useMutation<Feature, Error, UpdatePhaseStatusVariables, { snapshot: FeaturesPage | undefined }>({
    mutationFn: ({ featureId, phaseId, status }) =>
      client.updatePhaseStatus(featureId, phaseId, status),

    onMutate: async ({ projectId, featureId, phaseId, status }) => {
      const queryKey = featuresKeys.list(projectId, undefined, 0);
      await queryClient.cancelQueries({ queryKey });

      const snapshot = queryClient.getQueryData<FeaturesPage>(queryKey);

      queryClient.setQueryData<FeaturesPage>(queryKey, page =>
        patchFeatureInPage(page, feature => {
          if (feature.id !== featureId) return feature;
          const nextPhases = (feature.phases || []).map(phase => {
            if (!matchesPhase(phase, phaseId)) return phase;
            const totalTasks = Math.max(phase.totalTasks || 0, 0);
            const deferredFromTasks = (phase.tasks || []).filter(t => t.status === 'deferred').length;
            const doneFromTasks = (phase.tasks || []).filter(t => t.status === 'done').length;
            let completedTasks = phase.tasks && phase.tasks.length > 0
              ? doneFromTasks + deferredFromTasks
              : Math.max(phase.completedTasks || 0, 0);
            let deferredTasks = phase.tasks && phase.tasks.length > 0
              ? deferredFromTasks
              : Math.max(phase.deferredTasks || 0, 0);
            if (status === 'deferred' && totalTasks > 0) {
              completedTasks = totalTasks;
              deferredTasks = totalTasks;
            }
            if (totalTasks > 0 && completedTasks > totalTasks) completedTasks = totalTasks;
            if (deferredTasks > completedTasks) deferredTasks = completedTasks;
            return { ...phase, status, completedTasks, deferredTasks };
          });
          return aggregateFeatureFromPhases(feature, nextPhases);
        }),
      );

      return { snapshot };
    },

    onError: (_err, { projectId }, context) => {
      const queryKey = featuresKeys.list(projectId, undefined, 0);
      if (context?.snapshot !== undefined) {
        queryClient.setQueryData(queryKey, context.snapshot);
      }
    },

    onSettled: (_data, _err, { projectId }) => {
      void queryClient.invalidateQueries({ queryKey: featuresKeys.all(projectId) });
    },
  });
}

// ─── useUpdateTaskStatusMutation ──────────────────────────────────────────────

export interface UpdateTaskStatusVariables {
  projectId: string;
  featureId: string;
  phaseId: string;
  taskId: string;
  status: TaskStatus;
  previousStatus?: TaskStatus;
}

/**
 * Optimistic mutation for task-level status updates.
 */
export function useUpdateTaskStatusMutation() {
  const client = useDataClient();
  const queryClient = useQueryClient();

  return useMutation<Feature, Error, UpdateTaskStatusVariables, { snapshot: FeaturesPage | undefined }>({
    mutationFn: ({ featureId, phaseId, taskId, status }) =>
      client.updateTaskStatus(featureId, phaseId, taskId, status),

    onMutate: async ({ projectId, featureId, phaseId, taskId, status, previousStatus }) => {
      const queryKey = featuresKeys.list(projectId, undefined, 0);
      await queryClient.cancelQueries({ queryKey });

      const snapshot = queryClient.getQueryData<FeaturesPage>(queryKey);

      queryClient.setQueryData<FeaturesPage>(queryKey, page =>
        patchFeatureInPage(page, feature => {
          if (feature.id !== featureId) return feature;
          const nextPhases = (feature.phases || []).map(phase => {
            if (!matchesPhase(phase, phaseId)) return phase;

            let tasks = phase.tasks || [];
            let changed = false;
            if (Array.isArray(phase.tasks) && phase.tasks.length > 0) {
              tasks = phase.tasks.map(task => {
                if (task.id !== taskId) return task;
                changed = true;
                return { ...task, status };
              });
            } else if (previousStatus && previousStatus !== status) {
              changed = true;
            }
            if (!changed) return phase;

            const totalTasks = Math.max(phase.totalTasks || 0, tasks.length);
            let completedTasks = Math.max(phase.completedTasks || 0, 0);
            let deferredTasks = Math.max(phase.deferredTasks || 0, 0);

            if (tasks.length > 0) {
              const doneCount = tasks.filter(t => t.status === 'done').length;
              const deferredCount = tasks.filter(t => t.status === 'deferred').length;
              completedTasks = doneCount + deferredCount;
              deferredTasks = deferredCount;
            } else if (previousStatus && previousStatus !== status) {
              if (previousStatus === 'done') completedTasks -= 1;
              if (previousStatus === 'deferred') { completedTasks -= 1; deferredTasks -= 1; }
              if (status === 'done') completedTasks += 1;
              if (status === 'deferred') { completedTasks += 1; deferredTasks += 1; }
            }

            if (phase.status === 'deferred' && totalTasks > 0) {
              completedTasks = totalTasks;
              deferredTasks = totalTasks;
            }
            if (completedTasks < 0) completedTasks = 0;
            if (deferredTasks < 0) deferredTasks = 0;
            if (totalTasks > 0 && completedTasks > totalTasks) completedTasks = totalTasks;

            return {
              ...phase,
              tasks,
              completedTasks,
              deferredTasks: Math.min(deferredTasks, completedTasks),
            };
          });
          return aggregateFeatureFromPhases(feature, nextPhases);
        }),
      );

      return { snapshot };
    },

    onError: (_err, { projectId }, context) => {
      const queryKey = featuresKeys.list(projectId, undefined, 0);
      if (context?.snapshot !== undefined) {
        queryClient.setQueryData(queryKey, context.snapshot);
      }
    },

    onSettled: (_data, _err, { projectId }) => {
      void queryClient.invalidateQueries({ queryKey: featuresKeys.all(projectId) });
    },
  });
}
