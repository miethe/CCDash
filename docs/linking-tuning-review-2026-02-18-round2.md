# Mapping Tuning Review Pack (Round 2)

Date: 2026-02-18

- Rows: `112`
- Heuristics: `{'LIKELY_VALID': 105, 'LIKELY_NOISE': 6, 'UNCERTAIN': 1}`

- CSV: `/Users/miethe/dev/homelab/development/CCDash/docs/linking-tuning-review-2026-02-18-round2.csv`

| Review ID | Entity | Feature | Target | Confidence | Fanout | SignalType | PrimaryCommand | Heuristic | Why | Your Verdict | Your Notes |
|---|---|---|---|---:|---:|---|---|---|---|---|---|
| R2-D-001 | Doc->Feature | `marketplace-source-detection-improvements-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/implementation_plans/features/marketplace-source-detection-improvements-v1.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-002 | Doc->Feature | `marketplace-source-detection-improvements-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/PRDs/features/marketplace-source-detection-improvements-v1.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-003 | Doc->Feature | `marketplace-source-detection-improvements-v1` | `progress/marketplace-source-detection-improvements/phase-1-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-004 | Doc->Feature | `marketplace-source-detection-improvements-v1` | `progress/marketplace-source-detection-improvements/phase-2-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-005 | Doc->Feature | `marketplace-source-detection-improvements-v1` | `progress/marketplace-source-detection-improvements/phase-3-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-006 | Doc->Feature | `marketplace-source-detection-improvements-v1` | `progress/marketplace-source-detection-improvements/phase-4-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-007 | Doc->Feature | `marketplace-source-detection-improvements-v1` | `progress/marketplace-source-detection-improvements/phase-5-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-008 | Doc->Feature | `marketplace-source-detection-improvements-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/PRDs/features/marketplace-folder-view-v1.md` |  |  |  |  | LIKELY_NOISE | doc points to other feature: marketplace-folder-view-v1 |  |  |
| R2-S-009 | Session->Feature | `marketplace-source-detection-improvements-v1` | `S-2eebf848-7afe-4025-a161-72fe98549e68` | 0.950 | 1 | file_read | /dev:execute-phase | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-010 | Session->Feature | `marketplace-source-detection-improvements-v1` | `S-23d0f95c-6952-455a-b384-f20551341984` | 0.800 | 1 | file_read | /dev:execute-phase | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-011 | Session->Feature | `marketplace-source-detection-improvements-v1` | `S-5819855c-4e7e-4acc-b97f-a6e9f0346792` | 0.800 | 1 | file_read | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-012 | Session->Feature | `marketplace-source-detection-improvements-v1` | `S-6ce3ec8f-3a8e-453f-9400-40a26b93dec5` | 0.800 | 1 | file_read | /fix:debug | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-013 | Session->Feature | `marketplace-source-detection-improvements-v1` | `S-94f71371-4408-4444-8219-f4e101a84bc5` | 0.350 | 1 | file_read | /plan:plan-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-D-014 | Doc->Feature | `artifact-metadata-cache-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/implementation_plans/refactors/artifact-metadata-cache-v1.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-015 | Doc->Feature | `artifact-metadata-cache-v1` | `progress/artifact-metadata-cache/all-phases-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-016 | Doc->Feature | `artifact-metadata-cache-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/PRDs/tools-api-support-v1.md` |  |  |  |  | LIKELY_NOISE | doc points to other feature: tools-api-support-v1 |  |  |
| R2-D-017 | Doc->Feature | `artifact-metadata-cache-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/implementation_plans/refactors/data-flow-standardization-v1.md` |  |  |  |  | LIKELY_NOISE | doc points to other feature: data-flow-standardization-v1 |  |  |
| R2-D-018 | Doc->Feature | `artifact-metadata-cache-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/implementation_plans/refactors/tag-storage-consolidation-v1.md` |  |  |  |  | LIKELY_NOISE | doc points to other feature: tag-storage-consolidation-v1 |  |  |
| R2-D-019 | Doc->Feature | `artifact-metadata-cache-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/reports/data-flow-standardization-report.md` |  |  |  |  | LIKELY_NOISE | doc points to other feature: data-flow-standardization |  |  |
| R2-S-020 | Session->Feature | `artifact-metadata-cache-v1` | `S-28f6a6c8-fbc6-4094-9fcb-16af95fc16c4` | 0.950 | 1 | file_read | /dev:execute-phase | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-021 | Session->Feature | `artifact-metadata-cache-v1` | `S-3b321b9b-f7a8-41e3-b5af-736693eb7e46` | 0.950 | 1 | file_read | /dev:execute-phase | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-022 | Session->Feature | `artifact-metadata-cache-v1` | `S-agent-a00f3ee` | 0.820 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-023 | Session->Feature | `artifact-metadata-cache-v1` | `S-agent-a0370ce` | 0.820 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-024 | Session->Feature | `artifact-metadata-cache-v1` | `S-agent-a938c99` | 0.820 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-025 | Session->Feature | `artifact-metadata-cache-v1` | `S-c6c8724c-a83f-4e74-bc07-f602eec32030` | 0.820 | 2 | file_read | /plan:plan-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-026 | Session->Feature | `artifact-metadata-cache-v1` | `S-agent-aa634c7` | 0.800 | 2 | file_write |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-027 | Session->Feature | `artifact-metadata-cache-v1` | `S-decf6d6d-74d1-433e-b678-54a5340a8830` | 0.800 | 1 | file_read | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-028 | Session->Feature | `artifact-metadata-cache-v1` | `S-cd58ebdd-4270-459f-bda5-050d682c9755` | 0.780 | 1 | command_args_path | /fix:debug | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-029 | Session->Feature | `artifact-metadata-cache-v1` | `S-1015b408-f82a-492e-8e7f-291907bd3cdb` | 0.350 | 5 | file_read | /release-notes | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-030 | Session->Feature | `artifact-metadata-cache-v1` | `S-6b29bbf6-16c5-4507-bb1b-98f27fac223d` | 0.350 | 5 | file_read | /fix:debug | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-031 | Session->Feature | `artifact-metadata-cache-v1` | `S-agent-a07ef8a` | 0.350 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-032 | Session->Feature | `artifact-metadata-cache-v1` | `S-agent-a22e7f5` | 0.350 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-033 | Session->Feature | `artifact-metadata-cache-v1` | `S-agent-a597d69` | 0.350 | 3 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-D-034 | Doc->Feature | `marketplace-sources-enhancement-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/implementation_plans/enhancements/marketplace-sources-enhancement-v1.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-035 | Doc->Feature | `marketplace-sources-enhancement-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/PRDs/enhancements/marketplace-sources-enhancement-v1.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-036 | Doc->Feature | `marketplace-sources-enhancement-v1` | `progress/marketplace-sources-enhancement/phase-1-3-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-037 | Doc->Feature | `marketplace-sources-enhancement-v1` | `progress/marketplace-sources-enhancement/phase-4-6-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-038 | Doc->Feature | `marketplace-sources-enhancement-v1` | `progress/marketplace-sources-enhancement/phase-7-8-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-039 | Doc->Feature | `marketplace-sources-enhancement-v1` | `progress/marketplace-sources-enhancement-v1/phase-4-6-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-040 | Doc->Feature | `marketplace-sources-enhancement-v1` | `progress/marketplace-sources-enhancement-v1/phase-7-8-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-041 | Doc->Feature | `marketplace-sources-enhancement-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/implementation_plans/enhancements/marketplace-sources-enhancement-v1/phase-1-3-backend.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-S-042 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-6f6b7630-1db9-40e7-9cb9-3325fef5f20a` | 0.950 | 1 | file_read | /dev:execute-phase | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-043 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-agent-a05ede3` | 0.820 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-044 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-agent-a7c4311` | 0.820 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-045 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-agent-ae8821f` | 0.820 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-046 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-28d4b4f4-d196-420c-af23-dc219a4b5a66` | 0.800 | 1 | file_read | /dev:execute-phase | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-047 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-46595155-7695-4c88-89a4-e481f11a4b6d` | 0.800 | 1 | file_read | /dev:execute-phase | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-048 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-agent-a16ed72` | 0.800 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-049 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-agent-a7623dd` | 0.800 | 2 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-050 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-agent-abc4346` | 0.800 | 1 | file_write |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-051 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-agent-aecde08` | 0.800 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-052 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-f1bc94e4-1242-4299-a880-543031c6faf9` | 0.800 | 1 | file_read | /fix:debug | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-053 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-f378d814-7c17-42fd-8895-5777533de564` | 0.800 | 1 | file_read | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-054 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-agent-a16d194` | 0.350 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-055 | Session->Feature | `marketplace-sources-enhancement-v1` | `S-agent-af69147` | 0.350 | 2 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-D-056 | Doc->Feature | `multi-platform-project-deployments-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/implementation_plans/features/multi-platform-project-deployments-v1.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-057 | Doc->Feature | `multi-platform-project-deployments-v1` | `progress/multi-platform-project-deployments/phase-0-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-058 | Doc->Feature | `multi-platform-project-deployments-v1` | `progress/multi-platform-project-deployments/phase-1-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-059 | Doc->Feature | `multi-platform-project-deployments-v1` | `progress/multi-platform-project-deployments/phase-2-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-060 | Doc->Feature | `multi-platform-project-deployments-v1` | `progress/multi-platform-project-deployments/phase-3-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-061 | Doc->Feature | `multi-platform-project-deployments-v1` | `progress/multi-platform-project-deployments/phase-4-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-062 | Doc->Feature | `multi-platform-project-deployments-v1` | `progress/multi-platform-project-deployments/phase-5-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-063 | Doc->Feature | `multi-platform-project-deployments-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/implementation_plans/features/multi-platform-project-deployments-v1/phase-0-adapter-baseline.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-S-064 | Session->Feature | `multi-platform-project-deployments-v1` | `S-agent-a199233` | 0.820 | 2 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-065 | Session->Feature | `multi-platform-project-deployments-v1` | `S-agent-a5e8ec6` | 0.820 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-066 | Session->Feature | `multi-platform-project-deployments-v1` | `S-agent-ac55032` | 0.820 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-067 | Session->Feature | `multi-platform-project-deployments-v1` | `S-6afb88b3-67ae-43b2-b1ab-73513186ef26` | 0.800 | 1 | file_read | /plan:plan-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-068 | Session->Feature | `multi-platform-project-deployments-v1` | `S-agent-adb04c1` | 0.350 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-D-069 | Doc->Feature | `collection-data-consistency-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/implementation_plans/refactors/collection-data-consistency-v1.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-070 | Doc->Feature | `collection-data-consistency-v1` | `progress/collection-data-consistency/phase-1-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-071 | Doc->Feature | `collection-data-consistency-v1` | `progress/collection-data-consistency/phase-2-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-072 | Doc->Feature | `collection-data-consistency-v1` | `progress/collection-data-consistency/phase-3-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-073 | Doc->Feature | `collection-data-consistency-v1` | `progress/collection-data-consistency/phase-4-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-074 | Doc->Feature | `collection-data-consistency-v1` | `progress/collection-data-consistency/phase-5-progress.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-075 | Doc->Feature | `collection-data-consistency-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/implementation_plans/refactors/artifact-metadata-cache-v1.md` |  |  |  |  | LIKELY_NOISE | doc points to other feature: artifact-metadata-cache-v1 |  |  |
| R2-D-076 | Doc->Feature | `collection-data-consistency-v1` | `/Users/miethe/dev/homelab/development/skillmeat/docs/project_plans/reports/dual-collection-system-architecture-analysis.md` |  |  |  |  | UNCERTAIN | needs human review |  |  |
| R2-S-077 | Session->Feature | `collection-data-consistency-v1` | `S-a65c1238-8a5a-480c-bf6b-8b137fb86151` | 0.950 | 2 | file_read | /dev:execute-phase | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-078 | Session->Feature | `collection-data-consistency-v1` | `S-agent-a715475` | 0.820 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-079 | Session->Feature | `collection-data-consistency-v1` | `S-01d0730a-c3dd-4792-8a06-7654c3099975` | 0.800 | 1 | file_read | /dev:execute-phase | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-080 | Session->Feature | `collection-data-consistency-v1` | `S-5f4b6911-406f-43a9-be18-98da89876db9` | 0.800 | 1 | file_read | /dev:execute-phase | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-081 | Session->Feature | `collection-data-consistency-v1` | `S-68da4c8b-493b-4c46-b076-ef9e1d0af541` | 0.800 | 1 | file_read | /dev:execute-phase | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-082 | Session->Feature | `collection-data-consistency-v1` | `S-4db96e85-1c46-4ad1-965e-92fee88d13b0` | 0.780 | 1 | command_args_path | /dev:execute-phase | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-083 | Session->Feature | `collection-data-consistency-v1` | `S-agent-a050964` | 0.770 | 1 | file_write |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-084 | Session->Feature | `collection-data-consistency-v1` | `S-c6c8724c-a83f-4e74-bc07-f602eec32030` | 0.600 | 2 | file_read | /plan:plan-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-085 | Session->Feature | `collection-data-consistency-v1` | `S-6b29bbf6-16c5-4507-bb1b-98f27fac223d` | 0.350 | 5 | file_read | /fix:debug | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-086 | Session->Feature | `collection-data-consistency-v1` | `S-94ebb095-4004-45e9-a7dd-afb6cf01ecc9` | 0.350 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-087 | Session->Feature | `collection-data-consistency-v1` | `S-agent-a777ed2` | 0.350 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-088 | Session->Feature | `collection-data-consistency-v1` | `S-agent-a8a1ef3` | 0.350 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-089 | Session->Feature | `collection-data-consistency-v1` | `S-agent-aa634c7` | 0.350 | 2 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-090 | Session->Feature | `collection-data-consistency-v1` | `S-agent-ab8d2a2` | 0.350 | 1 | file_read |  | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-D-091 | Doc->Feature | `quick-features` | `progress/quick-features/artifact-card-menu-consolidation.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-092 | Doc->Feature | `quick-features` | `progress/quick-features/artifact-indexing-all-types.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-093 | Doc->Feature | `quick-features` | `progress/quick-features/clickable-deployment-cards.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-094 | Doc->Feature | `quick-features` | `progress/quick-features/collection-badges-modal.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-095 | Doc->Feature | `quick-features` | `progress/quick-features/collection-card-enhancements.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-096 | Doc->Feature | `quick-features` | `progress/quick-features/collection-card-group-badges.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-097 | Doc->Feature | `quick-features` | `progress/quick-features/collection-card-ux-enhancements.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-D-098 | Doc->Feature | `quick-features` | `progress/quick-features/collection-group-ordering.md` |  |  |  |  | LIKELY_VALID | feature token in doc path/prd/slug |  |  |
| R2-S-099 | Session->Feature | `quick-features` | `S-c8e3dfbf-45d0-46d6-988b-fa0a736b8e80` | 0.850 | 2 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-100 | Session->Feature | `quick-features` | `S-062b634a-903e-4751-963e-da1ce07136aa` | 0.820 | 1 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-101 | Session->Feature | `quick-features` | `S-0f57dc25-85cd-4853-848e-c613fc495587` | 0.820 | 1 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-102 | Session->Feature | `quick-features` | `S-1b42ecc3-e10e-4517-aa13-2452a5109516` | 0.820 | 1 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-103 | Session->Feature | `quick-features` | `S-1e0a2205-3de4-4247-b0ba-24ca1832b40c` | 0.820 | 1 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-104 | Session->Feature | `quick-features` | `S-1e74b054-8821-4d2e-86bb-dd40398f7646` | 0.820 | 1 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-105 | Session->Feature | `quick-features` | `S-1fcf113b-9b22-40ea-a6ee-028435356fa9` | 0.820 | 1 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-106 | Session->Feature | `quick-features` | `S-281e0805-e908-478f-8641-137705a5baa8` | 0.820 | 1 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-107 | Session->Feature | `quick-features` | `S-29dab117-3590-411a-bb1d-badc47bbeae5` | 0.820 | 1 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-108 | Session->Feature | `quick-features` | `S-2b1ba240-0e32-4009-a54f-4cc6961a7b81` | 0.820 | 1 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-109 | Session->Feature | `quick-features` | `S-38c2b66b-76bc-4797-acfb-43bf39ec23d3` | 0.820 | 1 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-110 | Session->Feature | `quick-features` | `S-3b429575-33b7-4ed6-ba12-53572778a1b7` | 0.820 | 1 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-111 | Session->Feature | `quick-features` | `S-3ea344c9-d268-4b2d-bb3d-a68d4fb0f198` | 0.820 | 1 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
| R2-S-112 | Session->Feature | `quick-features` | `S-3f6a6ed1-c881-4e72-8d86-7f5102aa0f4c` | 0.820 | 1 | file_write | /dev:quick-feature | LIKELY_VALID | feature token in title/signal path |  |  |
