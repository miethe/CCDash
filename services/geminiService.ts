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

export const generateDashboardInsight = async (
  metrics: AnalyticsMetric[],
  tasks: ProjectTask[]
): Promise<string> => {
  try {
    const response = await fetch("/api/ai/insight", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ metrics, tasks }),
    });

    if (!response.ok) {
      console.error("AI insight endpoint returned", response.status);
      return "Error connecting to AI Insight service. Please check your network or API key configuration.";
    }

    const data: AIInsightResponse = await response.json();

    if (data.disabled) {
      // Server has no API key configured — degrade gracefully
      console.warn("AI insight is disabled (no API key configured server-side).");
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
