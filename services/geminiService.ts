import { GoogleGenAI } from "@google/genai";
import { AnalyticsMetric, ProjectTask } from "../types";

export const generateDashboardInsight = async (
  metrics: AnalyticsMetric[],
  tasks: ProjectTask[]
): Promise<string> => {
  // Graceful degradation for demo without API key
  if (!process.env.API_KEY) {
    console.warn("No API_KEY found in process.env. Returning mock insight.");
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve(
          "Analysis (Simulated): Cost efficiency has improved by 15% over the last 3 days. 'Refactor Authentication' is currently the main cost driver due to high token usage in search tools. Recommend using 'Claude Haiku' for initial context gathering on this task."
        );
      }, 1500);
    });
  }

  try {
    const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
    
    // Construct a context-rich prompt
    const tasksSummary = tasks.map(t => `${t.title} (${t.status}, Cost: $${t.cost})`).join(', ');
    const metricsSummary = JSON.stringify(metrics.slice(-3)); // Last 3 days

    const prompt = `
      Act as a senior technical project manager. Analyze the following project data for "CCDash".
      
      Recent Metrics (Last 3 days): ${metricsSummary}
      Active Tasks: ${tasksSummary}
      
      Provide a concise, 2-sentence executive summary of project health, identifying the biggest risk or the biggest win. 
      Focus on cost vs. delivery velocity.
    `;

    const response = await ai.models.generateContent({
      model: 'gemini-3-flash-preview',
      contents: prompt,
    });

    return response.text || "Could not generate insight.";
  } catch (error) {
    console.error("Gemini API Error:", error);
    return "Error connecting to AI Insight service. Please check your network or API key configuration.";
  }
};