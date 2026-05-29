import { QueryClient } from '@tanstack/react-query';

/**
 * Returns true if the error represents a client-side (4xx) HTTP failure.
 * These are not transient — retrying them wastes quota and is user-visible.
 */
function isClientError(err: unknown): boolean {
  if (err !== null && typeof err === 'object' && 'status' in err) {
    const status = (err as { status: unknown }).status;
    if (typeof status === 'number') {
      return status >= 400 && status < 500;
    }
  }
  return false;
}

/**
 * Create a QueryClient scoped to a project session.
 *
 * Defaults:
 *   staleTime          30 s  — data is considered fresh for 30 seconds
 *   gcTime            300 s  — inactive queries are kept in cache for 5 minutes
 *   refetchOnWindowFocus false — avoid noisy refetches when user alt-tabs
 *   retry             up to 3 times, never on 4xx errors
 *
 * Call `queryClient.clear()` when the active project changes so stale
 * cross-project data is not served to the new project's components.
 */
export function createProjectQueryClient(_projectId: string): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 300_000,
        refetchOnWindowFocus: false,
        retry: (failureCount: number, err: unknown) =>
          failureCount < 3 && !isClientError(err),
      },
    },
  });
}
