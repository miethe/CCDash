import {
  ExecutionPolicyResult,
  ExecutionRun,
  ExecutionRunEventPage,
  FeatureExecutionContext,
} from '../types';

const API_BASE = '/api/features';
const EXECUTION_API_BASE = '/api/execution';

export interface ExecutionEventPayload {
  eventType: 'execution_workbench_opened' | 'execution_begin_work_clicked' | 'execution_recommendation_generated' | 'execution_command_copied' | 'execution_source_link_clicked';
  featureId?: string;
  recommendationRuleId?: string;
  command?: string;
  metadata?: Record<string, unknown>;
}

export interface ExecutionRunRequest {
  command: string;
  cwd?: string;
  envProfile?: string;
  featureId?: string;
  recommendationRuleId?: string;
  metadata?: Record<string, unknown>;
}

export interface ExecutionRunApprovalRequest {
  decision: 'approved' | 'denied';
  reason?: string;
  actor?: string;
}

export interface ExecutionRunCancelRequest {
  reason?: string;
  actor?: string;
}

export interface ExecutionRunRetryRequest {
  acknowledgeFailure: boolean;
  actor?: string;
  metadata?: Record<string, unknown>;
}

export async function getFeatureExecutionContext(featureId: string): Promise<FeatureExecutionContext> {
  const res = await fetch(`${API_BASE}/${encodeURIComponent(featureId)}/execution-context`);
  if (!res.ok) {
    throw new Error(`Failed to fetch execution context (${res.status})`);
  }
  return res.json();
}

export async function trackExecutionEvent(payload: ExecutionEventPayload): Promise<void> {
  try {
    await fetch(`${API_BASE}/execution-events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    // Telemetry should never block UX flows.
  }
}

export async function checkExecutionPolicy(payload: {
  command: string;
  cwd?: string;
  envProfile?: string;
}): Promise<ExecutionPolicyResult> {
  const res = await fetch(`${EXECUTION_API_BASE}/policy-check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to evaluate execution policy (${res.status})`);
  }
  return res.json();
}

export async function createExecutionRun(payload: ExecutionRunRequest): Promise<ExecutionRun> {
  const res = await fetch(`${EXECUTION_API_BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to create execution run (${res.status})`);
  }
  return res.json();
}

export async function listExecutionRuns(params?: {
  featureId?: string;
  limit?: number;
  offset?: number;
}): Promise<ExecutionRun[]> {
  const query = new URLSearchParams();
  if (params?.featureId) query.set('feature_id', params.featureId);
  if (typeof params?.limit === 'number') query.set('limit', String(params.limit));
  if (typeof params?.offset === 'number') query.set('offset', String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : '';

  const res = await fetch(`${EXECUTION_API_BASE}/runs${suffix}`);
  if (!res.ok) {
    throw new Error(`Failed to list execution runs (${res.status})`);
  }
  return res.json();
}

export async function getExecutionRun(runId: string): Promise<ExecutionRun> {
  const res = await fetch(`${EXECUTION_API_BASE}/runs/${encodeURIComponent(runId)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch execution run (${res.status})`);
  }
  return res.json();
}

export async function listExecutionRunEvents(
  runId: string,
  params?: { afterSequence?: number; limit?: number },
): Promise<ExecutionRunEventPage> {
  const query = new URLSearchParams();
  if (typeof params?.afterSequence === 'number') query.set('after_sequence', String(params.afterSequence));
  if (typeof params?.limit === 'number') query.set('limit', String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await fetch(`${EXECUTION_API_BASE}/runs/${encodeURIComponent(runId)}/events${suffix}`);
  if (!res.ok) {
    throw new Error(`Failed to list run events (${res.status})`);
  }
  return res.json();
}

export async function approveExecutionRun(
  runId: string,
  payload: ExecutionRunApprovalRequest,
): Promise<ExecutionRun> {
  const res = await fetch(`${EXECUTION_API_BASE}/runs/${encodeURIComponent(runId)}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to update execution approval (${res.status})`);
  }
  return res.json();
}

export async function cancelExecutionRun(
  runId: string,
  payload: ExecutionRunCancelRequest,
): Promise<ExecutionRun> {
  const res = await fetch(`${EXECUTION_API_BASE}/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to cancel execution run (${res.status})`);
  }
  return res.json();
}

export async function retryExecutionRun(
  runId: string,
  payload: ExecutionRunRetryRequest,
): Promise<ExecutionRun> {
  const res = await fetch(`${EXECUTION_API_BASE}/runs/${encodeURIComponent(runId)}/retry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to retry execution run (${res.status})`);
  }
  return res.json();
}
