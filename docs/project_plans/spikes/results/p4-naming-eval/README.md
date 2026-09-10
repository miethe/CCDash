# P4 naming-eval results

Output of `python -m backend.scripts.p4_naming_eval` (hosted-llm-provider-strategy SPIKE,
phase P4). Never written to `sessions.session_name` -- NDJSON only, per the SPIKE's design.

- `p4-results.ndjson` -- the local-arm (`qwen2.5:14b` via Ollama) run against the frozen
  16-case sample. See the P4 report for the full result table, deviations from the N=200
  design, and the pre-registered-decision-rule verdict.
- `p4-anthropic-credential-probe.ndjson` -- NOT an experiment result. Confirms the
  Anthropic/ICA arm degrades fail-open (no crash, `title: null`) when
  `CCDASH_LLM_ANTHROPIC_API_KEY` is unset, which is this leg's actual state (see report).
