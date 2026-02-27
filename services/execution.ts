import { FeatureExecutionContext } from '../types';

const API_BASE = '/api/features';

export interface ExecutionEventPayload {
  eventType: 'execution_workbench_opened' | 'execution_begin_work_clicked' | 'execution_recommendation_generated' | 'execution_command_copied' | 'execution_source_link_clicked';
  featureId?: string;
  recommendationRuleId?: string;
  command?: string;
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
