---

## Screenshots

Visual previews of CCDash across its core surfaces. Screenshots are captured against a running local instance — see the [Getting Started](#getting-started) section to run CCDash with your own project data.

{{#each (screenshotsByCategory screenshots.screenshots "readme")}}
### {{this.alt}}

![{{this.alt}}]({{this.file}})

---

{{/each}}
{{#unless (screenshotsByCategory screenshots.screenshots "readme")}}
### Surfaces Overview

| Surface | Route | What You'll See |
|---------|-------|----------------|
| Dashboard | `/` | KPI cards, cost/velocity chart, model usage breakdown, and AI-generated project health summary |
| Session Inspector | `/sessions` | 3-pane transcript with tool call expansion, forensics payload, and session analytics |
| Feature Board | `/board` | Kanban columns grouped by stage with drill-down modals showing phases, tasks, and linked docs |
| Execution Workbench | `/execution` | Recommended stack card, pre-run review modal, safety pipeline, and streaming run output |
| Workflow Registry | `/workflows` | Searchable catalog with effectiveness scores, composition summary, and issue cards |
| Analytics — Workflow Intelligence | `/analytics?tab=workflow_intelligence` | Workflow leaderboard with failure-pattern clustering and attribution signals |

> Screenshots are being captured. Run `npm run dev` to explore these surfaces live.
{{/unless}}
