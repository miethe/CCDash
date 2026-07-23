/**
 * TanStack Query hook for the AAR-review read surface.
 *
 * T4-001 (ccdash-automated-aar-review-v1, Phase 4): FeatureAARReviewPanel.tsx
 * consumes the persisted `aar_reviews` rollup for a project via this hook.
 *
 * DATA SOURCE: There is no internal `/api/agent/...` route that lists the
 * project-wide `aar_reviews` rollup (the existing internal route,
 * `GET /agent/aar-review/{document_id}`, resolves exactly one AAR document —
 * see backend/routers/agent.py — not a project-level list). This hook
 * therefore consumes `GET /api/v1/project/aar-review?project_id=<projectId>`
 * (landed by the parallel T4-002 task at
 * `backend/routers/_client_v1_aar_review.py` / `client_v1.py`), following the
 * same `apiRequestJson<ClientV1Envelope<T>>('/api/v1/...')` + local wire-type
 * pattern already used by `services/queries/dashboard.ts`
 * (useDashboardBundleQuery) and `services/featureSurface.ts` for other
 * `/api/v1/` reads.
 *
 * Response shape (verified against `backend/routers/client_v1_models.py::AARReviewListDTO`
 * + `backend/tests/test_client_v1_aar_review.py`):
 * `ClientV1Envelope<AARReviewListDTO>` = `{ status, data: { project_id, total,
 * reviews: AarReviewWireDTO[] }, meta }`. `extractAarReviewWireItems` also
 * tolerates a bare array or `{items: [...]}` shape defensively, so a future
 * envelope-shape change degrades to `[]` rather than crashing this hook.
 *
 * Resilience contract (hard AC, T4-001): every §7.2 field is optional/null-
 * tolerant. A missing/absent field degrades to a defined FE fallback (see
 * `adaptAarReviewEntry` below) — never a thrown error, never an omitted row.
 */

import { useQuery } from '@tanstack/react-query';

import type { AarReviewCorrelation, AarReviewEntry, AarReviewFlag, AarReviewTriageVerdict } from '../../types';
import { apiRequestJson } from '../apiClient';
import { aarReviewKeys } from '../queryKeys';

// ── Wire shapes (PRD §7.2, snake_case — mirrors backend AARReviewDTO verbatim) ─

/** Wire shape of one `AARReviewFlag` (backend `models.py::AARReviewFlag`). */
export interface AarReviewFlagWire {
  flag_id?: string | null;
  triggered?: boolean | null;
  severity?: 'low' | 'medium' | 'high' | null;
  evidence_refs?: string[] | null;
  rationale?: string | null;
}

/** Wire shape of the nested `correlation` object (backend `AARReviewCorrelation`). */
export interface AarReviewCorrelationWire {
  strategy?: string | null;
  confidence?: number | null;
  session_ids?: string[] | null;
  feature_id?: string | null;
}

/**
 * Wire shape of one persisted `aar_reviews` row, per PRD §7.2 (backend
 * `AARReviewDTO`). DEPRECATED flat aliases (`session_refs`,
 * `correlation_confidence`, `correlation_strategy`, `verdict`) may be present
 * on the wire for one release window — intentionally NOT read here; new code
 * reads only the nested/canonical fields.
 */
export interface AarReviewWireDTO {
  schema_version?: number | null;
  status?: 'ok' | 'error' | null;
  document_id?: string | null;
  correlation?: AarReviewCorrelationWire | null;
  flags?: AarReviewFlagWire[] | null;
  triage_verdict?: AarReviewTriageVerdict | null;
  reasons?: string[] | null;
  generated_at?: string | null;
  source_refs?: string[] | null;
}

/**
 * Wire shape of `AARReviewListDTO` (backend `client_v1_models.py`) — the
 * `data` payload of `GET /api/v1/project/aar-review`'s `ClientV1Envelope`.
 */
export interface AarReviewListWireDTO {
  project_id?: string | null;
  total?: number | null;
  reviews?: AarReviewWireDTO[] | null;
}

/** `ClientV1Envelope`-shaped wrapper (see ccdash_contracts/envelopes.py). */
interface ClientV1EnvelopeWire<T> {
  status?: 'ok' | 'partial' | 'error';
  data?: T | null;
  meta?: Record<string, unknown>;
}

// ── Adapters ──────────────────────────────────────────────────────────────────

/**
 * Extracts the `reviews[]` list from a `GET /api/v1/project/aar-review`
 * response (`ClientV1Envelope<AARReviewListDTO>` → `data.reviews`).
 * Defensively tolerates a bare array, `{data: [...]}` (in case the envelope
 * ever flattens to a plain list), or `{items: [...]}` (seen elsewhere in
 * this codebase, e.g. `ResearchRunListResponse`) so an envelope-shape drift
 * degrades to `[]` — "no rows yet" is a contract state, never a crash.
 */
export function extractAarReviewWireItems(payload: unknown): AarReviewWireDTO[] {
  if (Array.isArray(payload)) return payload as AarReviewWireDTO[];
  if (payload && typeof payload === 'object') {
    const envelope = payload as ClientV1EnvelopeWire<AarReviewListWireDTO | AarReviewWireDTO[]>;
    const data = envelope.data;
    if (Array.isArray(data)) return data;
    if (data && typeof data === 'object' && Array.isArray((data as AarReviewListWireDTO).reviews)) {
      return (data as AarReviewListWireDTO).reviews ?? [];
    }
    const obj = payload as { items?: AarReviewWireDTO[]; reviews?: AarReviewWireDTO[] };
    if (Array.isArray(obj.reviews)) return obj.reviews;
    if (Array.isArray(obj.items)) return obj.items;
  }
  return [];
}

function adaptCorrelation(wire: AarReviewCorrelationWire | null | undefined): AarReviewCorrelation {
  return {
    strategy: wire?.strategy ?? null,
    confidence: wire?.confidence ?? null,
    sessionIds: wire?.session_ids ?? [],
    featureId: wire?.feature_id ?? null,
  };
}

function adaptFlag(wire: AarReviewFlagWire): AarReviewFlag {
  return {
    flagId: wire.flag_id ?? '',
    triggered: wire.triggered ?? false,
    severity: wire.severity ?? null,
    evidenceRefs: wire.evidence_refs ?? [],
    rationale: wire.rationale ?? null,
  };
}

/** Adapts one wire `AARReviewDTO` row to the camelCase FE shape. Never throws. */
export function adaptAarReviewEntry(wire: AarReviewWireDTO): AarReviewEntry {
  return {
    schemaVersion: wire.schema_version ?? null,
    status: wire.status ?? null,
    documentId: wire.document_id ?? '',
    correlation: adaptCorrelation(wire.correlation),
    flags: (wire.flags ?? []).map(adaptFlag),
    triageVerdict: wire.triage_verdict ?? null,
    reasons: wire.reasons ?? [],
    generatedAt: wire.generated_at ?? null,
    sourceRefs: wire.source_refs ?? [],
  };
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface UseAarReviewRollupQueryOptions {
  projectId: string | null | undefined;
  /**
   * Optional feature-scoping filter. When set, the returned `data` is
   * narrowed to entries whose `correlation.featureId` matches — applied
   * client-side via TanStack Query's `select` so the underlying
   * project-wide fetch and cache entry are unaffected (no new endpoint,
   * no extra request). Absent/null → project-wide behavior (unchanged).
   */
  featureId?: string | null;
  /** Set false to suppress the query (e.g. project not yet loaded). */
  enabled?: boolean;
}

/**
 * Fetches the persisted `aar_reviews` rollup for a project, optionally
 * narrowed to one feature.
 *
 * Returns the standard TQ query result (`data`, `isLoading`, `isError`, ...);
 * `data` is always a fully-adapted `AarReviewEntry[]` (never the raw wire
 * shape) — `[]` when the project (or feature, when `featureId` is set) has
 * no AAR reviews yet, not an error.
 */
export function useAarReviewRollupQuery({
  projectId,
  featureId,
  enabled = true,
}: UseAarReviewRollupQueryOptions) {
  return useQuery<AarReviewEntry[], Error, AarReviewEntry[]>({
    queryKey: aarReviewKeys.list(projectId ?? ''),
    queryFn: async (): Promise<AarReviewEntry[]> => {
      if (!projectId) throw new Error('projectId is required');
      const params = new URLSearchParams({ project_id: projectId });
      const payload = await apiRequestJson<unknown>(`/api/v1/project/aar-review?${params.toString()}`);
      return extractAarReviewWireItems(payload).map(adaptAarReviewEntry);
    },
    select: (entries) =>
      featureId ? entries.filter((entry) => entry.correlation.featureId === featureId) : entries,
    staleTime: 30_000,
    gcTime: 300_000,
    enabled: !!projectId && enabled,
  });
}
