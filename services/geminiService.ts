/**
 * geminiService — thin proxy layer over the server-side AI insight endpoint.
 *
 * The Gemini API key is never embedded in the browser bundle. All credential
 * handling lives in backend/services/ai_insight.py.
 *
 * Exported function signatures are stable; callers need no changes.
 */
import { AnalyticsMetric, ProjectTask } from "../types";

interface AIInsightResponse {
  text: string;
  disabled: boolean;
  error: string;
}

/**
 * `projectId` is the project whose data `metrics`/`tasks` describe. The server
 * requires that project's `llm_egress_consent` before any prompt leaves the
 * box — the per-project half of a two-level egress consent gate. Omitting it
 * is not a shortcut: the server REFUSES (returns `disabled: true`) rather than
 * falling back to the global flag alone, so a caller with no active project
 * gets the disabled degrade, which is the intended behaviour.
 */
export const generateDashboardInsight = async (
  metrics: AnalyticsMetric[],
  tasks: ProjectTask[],
  projectId?: string
): Promise<string> => {
  try {
    const response = await fetch("/api/ai/insight", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ metrics, tasks, project_id: projectId ?? null }),
    });

    if (!response.ok) {
      console.error("AI insight endpoint returned", response.status);
      return "Error connecting to AI Insight service. Please check your network or API key configuration.";
    }

    const data: AIInsightResponse = await response.json();

    if (data.disabled) {
      // `disabled` is the server's single graceful-refusal state and it now has
      // several causes, so this message must NOT name only one of them: no
      // Gemini key, the global CCDASH_LLM_EGRESS_CONSENT flag off, or this
      // project's `llm_egress_consent` not granted (including the
      // no-project-selected case, which refuses by design). The server does not
      // report which — deliberately, so a refusal reveals nothing about
      // deployment config to a caller.
      console.warn(
        "AI insight is disabled server-side (missing API key, or hosted-LLM " +
          "egress consent not granted for this project).",
      );
      return (
        "Analysis (Simulated): Cost efficiency has improved by 15% over the last 3 days. " +
        "'Refactor Authentication' is currently the main cost driver due to high token usage " +
        "in search tools. Recommend using 'Claude Haiku' for initial context gathering on this task."
      );
    }

    if (data.error) {
      console.error("AI insight service error:", data.error);
      return "Error connecting to AI Insight service. Please check your network or API key configuration.";
    }

    return data.text || "Could not generate insight.";
  } catch (error) {
    console.error("AI insight fetch error:", error);
    return "Error connecting to AI Insight service. Please check your network or API key configuration.";
  }
};
