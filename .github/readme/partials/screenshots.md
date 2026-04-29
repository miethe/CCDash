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
| Landing | `/` | Product overview, docs entrypoint, and public release positioning |
| Dashboard | `/dashboard` | KPI cards, cost/velocity chart, model usage breakdown, and AI-generated project health summary |
| Planning Control Plane | `/planning` | Planning summary, triage inbox, graph view, and feature drill-down surfaces |
| Feature Board | `/board` | Kanban columns grouped by stage with drill-down modals showing phases, tasks, and linked docs |
| Execution Workbench | `/execution` | Recommended stack card, pre-run review modal, safety pipeline, and streaming run output |
| Testing | `/tests` | Test ingestion, health, integrity, and feature/test correlation surfaces |
| Documents | `/plans` | Documentation catalog with document modal, local editing, and GitHub write-back support |
| Docs | `/docs` | Curated public docs site rendered from repo Markdown |
| Session Inspector | `/sessions` | 3-pane transcript with tool call expansion, forensics payload, and session analytics |
| Codebase Explorer | `/codebase` | File tree, activity correlation, and feature/session references |
| Session Mappings | `/session-mappings` | Mapping integrity and semantic correlation controls |
| Operations | `/ops` | Sync, cache, telemetry, and runtime maintenance controls |
| Analytics | `/analytics` | Workflow intelligence, session intelligence, and alert/notification surfaces |
| Workflow Registry | `/workflows` | Searchable catalog with effectiveness scores, composition summary, and issue cards |
| Settings | `/settings` | Project paths, integrations, alert rules, pricing, and runtime configuration |

> Screenshots are being captured. Run `npm run dev` to explore these surfaces live.
{{/unless}}
