# CCDash Documentation

This directory contains current CCDash documentation outside the feature-planning archive. Planning artifacts remain under `docs/project_plans/` and are intentionally not reorganized with the operational docs.

## Start Here

| Need | Document |
|------|----------|
| Set up or troubleshoot CCDash | [guides/setup.md](guides/setup.md) |
| Choose runtime and storage posture | [guides/runtime-storage-and-performance-quickstart.md](guides/runtime-storage-and-performance-quickstart.md), [guides/storage-profiles-guide.md](guides/storage-profiles-guide.md) |
| Use CLI or MCP surfaces | [guides/standalone-cli-guide.md](guides/standalone-cli-guide.md), [guides/cli-user-guide.md](guides/cli-user-guide.md), [guides/mcp-setup-guide.md](guides/mcp-setup-guide.md) |
| Operate telemetry and sync flows | [guides/operations-panel.md](guides/operations-panel.md), [guides/telemetry-exporter-guide.md](guides/telemetry-exporter-guide.md) |
| Understand session intelligence | [guides/agentic-sdlc-intelligence.md](guides/agentic-sdlc-intelligence.md), [guides/session-usage-attribution.md](guides/session-usage-attribution.md), [guides/session-block-insights.md](guides/session-block-insights.md) |
| Work with documents and linking | [guides/document-entity-and-linking.md](guides/document-entity-and-linking.md), [schemas/document_frontmatter/README.md](schemas/document_frontmatter/README.md) |
| Find implementation-only references | [developer/](developer/) |

## Organization

- `guides/` contains user, operator, and topic guides. When a feature has both user and developer details, they are consolidated into one topic guide.
- `developer/` contains implementation-only references that are not primary operator workflows.
- `schemas/` contains canonical document-frontmatter contracts and should stay colocated with the schema YAML files.
- `archive/` contains superseded historical material.
- `wireframes/` contains retained visual assets referenced by current or historical docs.
- `project_plans/` contains planning artifacts and is managed separately.
