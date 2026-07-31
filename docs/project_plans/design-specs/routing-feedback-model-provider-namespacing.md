---
title: "Design Spec: Routing Feedback Model/Provider Namespacing (DI-2)"
doc_type: design-spec
maturity: shaping
feature_slug: proof-to-routing-loop
prd_ref: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
status: draft
created: 2026-07-31
updated: 2026-07-31
audience: developers
category: cross-repo-integration
tags:
  - routing-feedback
  - model-namespacing
  - provider-identity
  - cross-repo-contract
  - deferred-item
related_documents:
  - docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md
  - docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1.md
  - docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md
  - /Users/miethe/dev/homelab/development/agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback.md
description: |
  Deferred item DI-2: Cross-repo model-string and provider-identity namespacing.
  Specifies the contract for how CCDash emits `model` and derives `provider` fields,
  and how these map to MeatySkills/delegation-router's canonical model-naming scheme.
  This item is deferred because no canonical cross-repo model-string format exists yet.
  Documents the current CCDash approach, namespacing candidates, and promotion criteria.
schema_version: 2
---

# Design Spec: Routing Feedback Model/Provider Namespacing (DI-2)

## Deferral Rationale

**Status**: Research-needed — No canonical cross-repo model-string format is currently negotiated
between CCDash and the delegation-router. CCDash emits `model` verbatim from session telemetry and
derives `provider` via a simple heuristic (`derive_model_identity()`). Router's own model naming
(scorecard keys, RoutingRecord fields) may differ, creating a mismatch.

**CCDash's Current Approach (Phase 1–6)**: Emit raw session telemetry and best-effort provider
derivation. No renaming or normalization of model strings.

**Router's Current Approach (Status Unknown)**: Hand-maintained scorecard uses model strings as
registry keys. Format is unstandardized and drifts over time.

**Trigger for Promotion**: A cross-repo model-naming negotiation is opened. Parties agree on:
  1. Canonical format (e.g., `<provider>:<family>:<variant>` or `<provider>/<model-id>`)
  2. Version-management strategy (e.g., vendor lockfile, periodic sync)
  3. Mapping enforcement mechanism (e.g., CI guard, runtime normalization)

---

## 1. Current State (Phase 1–6)

### 1.1 CCDash Telemetry Collection

**Source**: Agent session logs capture `model` strings as-is from Claude Code / AOS agents:

```typescript
// From session JSONL / backend/parsers/sessions.py
session.model = string;  // e.g., "claude-sonnet-4-6", "claude-haiku-4-5", "gpt-5.6-terra"

// CCDash does NO renaming or normalization; this is the canonical source
```

**Examples in the wild**:
- `"claude-opus-4.1"` (legacy Anthropic format, pre-2026)
- `"claude-sonnet-4-6"` (2026 Anthropic naming)
- `"claude-sonnet-5"` (2026 Sonnet family, assumed latest)
- `"claude-haiku-4-5"` (2026 Haiku designation)
- `"gpt-5.6-terra"` (2026 OpenAI format)
- `"gpt-5.6-sol"` (2026 OpenAI frontier)
- `"gemini-3.5-flash"` (2026 Google Gemini)
- `"claude-opus-5[1m]"` (ICA offload, 1M context variant)

### 1.2 Provider Derivation (Phase 1–6)

**CCDash Logic**: Simple heuristic in `backend/application/services/agent_queries/routing_rollup.py`:

```python
def derive_model_identity(model_string: str) -> str:
    """
    Derive provider from model string.
    
    Returns one of: "anthropic", "openai", "google", "ibm", "unknown"
    """
    model_lower = model_string.lower()
    
    if "claude" in model_lower or "opus" in model_lower:
        return "anthropic"
    elif "gpt" in model_lower or "gpt-" in model_lower:
        return "openai"
    elif "gemini" in model_lower:
        return "google"
    elif "bob" in model_lower or "ibm" in model_lower:
        return "ibm"
    else:
        return "unknown"
```

**Limitations**:
- Case-insensitive substring matching (fragile)
- No handling for future providers or naming schemes
- Treats `[1m]` suffixes (ICA context-length marker) as opaque
- Cannot distinguish sub-models within a provider (e.g., "sonnet-4-6" vs "sonnet-5")

### 1.3 Routing Feedback Emission (Current)

**RoutingFeedbackKeyDTO** fields emitted by CCDash:

```typescript
{
  model: string,      // verbatim from session.model, e.g., "claude-sonnet-5"
  provider: string,   // derived via heuristic above, e.g., "anthropic"
  // ... other fields
}
```

**Router's assumption (not validated)**: Router's RoutingRecord uses the same `model` and `provider`
strings when constructing its own routing decisions. If router's scorecard keys differ (e.g.,
`"sonnet-5"` vs `"claude-sonnet-5"`), signals fail to join.

---

## 2. Namespacing Problem

### 2.1 Mismatch Scenarios

**Scenario A: Model String Normalization**

- CCDash emits: `model = "claude-sonnet-4-6"` (from old session logs)
- Router scorecard has: `"claude-sonnet-5"` (newer, different generation)
- Result: No join; the scorecard entry for sonnet-5 is never updated by feedback from sonnet-4-6 sessions

**Scenario B: Provider-Level Variation**

- CCDash emits: `provider = "anthropic"` (heuristic)
- Router scorecard has: `provider = "anthropic-commercial"` (distinguishes commercial vs research)
- Result: Provider mismatch; router cannot correlate CCDash's feedback to its own scorecard

**Scenario C: Context-Length Variant**

- CCDash emits: `model = "claude-opus-5[1m]"` (ICA offload with 1M context)
- Router scorecard has entries for: `"claude-opus-5"` (standard) and `"claude-opus-5-1m"` (variant)
- Result: Unclear whether `[1m]` is part of the model identity or a runtime annotation

**Scenario D: Future Vendor Additions**

- A new vendor joins the ecosystem (e.g., Anthropic Research, Claude Labs, etc.)
- CCDash's heuristic returns `"unknown"`
- Router cannot route on signals for the new vendor until CCDash is updated

---

## 3. Proposed Namespacing Candidates

This section documents candidate approaches. **None are implemented in CCDash Phase 1–6.**
Router owner + CCDash owner MUST negotiate and select one during Phase 7+ (if promoted).

### 3.1 Candidate A: Vendor Lockfile (Recommended for Stability)

**Approach**: Maintain a shared model-registry lockfile (e.g., YAML) that both CCDash and router
consult at runtime.

```yaml
# ~/.claude/config/model-registry.yaml (canonical source, maintained by operator)
model_catalog:
  version: "1.0.0"
  providers:
    anthropic:
      canonical_name: "anthropic"
      models:
        opus-5:
          aliases: ["claude-opus-5", "claude-opus-5.1", "opus-5"]
          context_window: 200000
          tags: ["flagship", "reasoning"]
        sonnet-5:
          aliases: ["claude-sonnet-5", "sonnet-5"]
          context_window: 200000
          tags: ["default", "balanced"]
        sonnet-4-6:
          aliases: ["claude-sonnet-4-6", "sonnet-4-6"]
          context_window: 200000
          tags: ["legacy"]
        haiku-4-5:
          aliases: ["claude-haiku-4-5", "haiku-4-5"]
          context_window: 100000
          tags: ["cheap", "fast"]
    openai:
      canonical_name: "openai"
      models:
        gpt-5-6-terra:
          aliases: ["gpt-5.6-terra", "gpt-5.6-terra"]
          context_window: 200000
          tags: ["workhouse"]
        gpt-5-6-sol:
          aliases: ["gpt-5.6-sol"]
          context_window: 200000
          tags: ["frontier", "hardest"]
```

**CCDash Implementation** (Phase 7+ if promoted):
```python
# Load registry at startup
model_registry = load_model_registry("~/.claude/config/model-registry.yaml")

def normalize_model_string(model_string: str) -> str:
    """Normalize raw model string to canonical form."""
    for provider in model_registry.providers.values():
        for canonical_name, model_info in provider.models.items():
            if model_string in model_info.aliases:
                return f"{provider.canonical_name}:{canonical_name}"
    # Fallback for unknown models
    return f"unknown:{model_string}"
```

**Advantages**:
- Single source of truth for operator
- Aliases handle legacy/variant names
- Version management via lockfile versioning
- Works for future vendors without code changes

**Disadvantages**:
- Requires new file/process for synchronization
- Potential for stale lockfiles across deployments
- Adds startup dependency on file availability

### 3.2 Candidate B: Convention-Based Normalization (Lightweight)

**Approach**: Define a naming convention and apply it via regex/formatting rules in both projects.

**Convention**:
```
<provider>:<family>:<generation>
  or
<provider>/<model-id>
```

**Examples**:
- `"claude-sonnet-5"` → `"anthropic:sonnet:5"` or `"anthropic/sonnet-5"`
- `"gpt-5.6-terra"` → `"openai:gpt:5.6-terra"` or `"openai/gpt-5.6-terra"`
- `"gemini-3.5-flash"` → `"google:gemini:3.5-flash"` or `"google/gemini-3.5-flash"`

**Regex Normalizer**:
```python
def normalize_model_string_convention(model_string: str) -> str:
    """Apply naming convention."""
    model_lower = model_string.lower()
    
    # Remove context-length markers (e.g., [1m] → empty)
    model_clean = re.sub(r'\[\d+m\]$', '', model_lower)
    
    # Detect provider and extract model
    if "claude" in model_clean or "opus" in model_clean or "sonnet" in model_clean or "haiku" in model_clean:
        # Replace dashes with colons for parsing
        # "claude-sonnet-5" -> "anthropic:sonnet:5"
        parts = model_clean.replace("claude-", "").split("-")
        return f"anthropic:{':'.join(parts)}"
    elif "gpt" in model_clean:
        # "gpt-5.6-terra" -> "openai:gpt:5.6-terra"
        return f"openai:{model_clean}"
    elif "gemini" in model_clean:
        # "gemini-3.5-flash" -> "google:gemini:3.5-flash"
        return f"google:{model_clean}"
    else:
        return f"unknown:{model_clean}"
```

**Advantages**:
- Simple, no external dependency
- Works offline
- Easy to document as a shared spec

**Disadvantages**:
- Fragile regex logic; breaks with unexpected names
- No single source of truth for valid models
- Both projects must implement the same logic

### 3.3 Candidate C: Canonical Model URL / URI (Decentralized)

**Approach**: Model is identified by a unique, parseable URI.

**Format**:
```
ccdash://models/<provider>/<model-id>[?context=<size>&variant=<name>]
```

**Examples**:
- `ccdash://models/anthropic/claude-sonnet-5`
- `ccdash://models/anthropic/claude-opus-5?context=200k&variant=1m`
- `ccdash://models/openai/gpt-5.6-terra?context=200k`

**CCDash Implementation**:
```python
def model_to_uri(model_string: str, context_window: int = None) -> str:
    """Convert model string to canonical URI."""
    provider = derive_model_identity(model_string)
    context_query = f"?context={context_window}" if context_window else ""
    return f"ccdash://models/{provider}/{model_string}{context_query}"
```

**Advantages**:
- Globally unique identifier
- Extensible with query parameters
- Machine-readable and link-friendly

**Disadvantages**:
- More verbose
- Requires URI parsing logic in router
- May not align with router's own internal naming

---

## 4. Promotion Criteria

### 4.1 Before Negotiation Starts

- [ ] **Router owner identifies** the model-naming scheme used in MeatySkills/ibm-main scorecard
  - Is it flat (`"claude-sonnet-5"` as key)?
  - Is it hierarchical (`{provider: "anthropic", model: "sonnet-5"}`)?
  - Are there sub-dimensions (e.g., context size, inference provider)?

- [ ] **CCDash owner documents current approach** (§1–2 above)
  - Review heuristic logic and identify gaps
  - Document all model strings seen in production

### 4.2 Negotiation Checklist

- [ ] **Agree on normalization strategy** (Candidate A, B, C, or other)
  - Document the chosen approach in a **shared spec** (not CCDash-only or router-only)
  - Ensure both projects can implement it independently and reach the same normalized form

- [ ] **Define version management**
  - If Candidate A: how is lockfile versioned and distributed? (e.g., CI artifact, GitHub release)
  - If Candidate B: document the convention in a shared RFC or ADR
  - If Candidate C: define URI scheme registry and governance

- [ ] **Handle ICA context-length variants**
  - Is `[1m]` part of the model identity or a runtime parameter?
  - If parameter: normalize it out in CCDash (e.g., `"claude-opus-5[1m]"` → `"anthropic:opus:5"` + context=1m)
  - If identity: include it in the normalized form (e.g., `"anthropic:opus:5-1m"`)

- [ ] **Identify unmappable/future models**
  - Define fallback behavior when router encounters a model not in the catalog/convention
  - Should unmapped models be rejected, logged, or treated as `unknown`?

### 4.3 Implementation Checklist

- [ ] **CCDash Implementation** (if promoted to Phase 7+)
  - Add normalization function (Candidate A/B/C as chosen)
  - Update `RoutingFeedbackKeyDTO` to include both `model_raw` (original) and `model_canonical` (normalized)
  - Add test for normalization (spot-check 10+ real model strings)
  - Publish capability version update (e.g., `"routing:feedback-v1.0.0-normalized-models"`)

- [ ] **Router Implementation** (owned by MeatySkills)
  - Implement same normalization logic
  - Update scorecard to use normalized model keys
  - Add integration test: consume CCDash feedback, normalize models, verify join with scorecard

- [ ] **Operator Guidance**
  - Document the chosen normalization scheme in `/docs/guides/routing-feedback-loop.md`
  - Provide troubleshooting guide: "Model signals not updating? Check normalization…"
  - Link to router's documentation if scheme differs

---

## 5. Context-Length Handling (Special Case)

### 5.1 ICA `[1m]` Designator

**Current State**: Session telemetry captures `model = "claude-opus-5[1m]"` for ICA offloads.

**Question**: Is context-length part of the **model identity** or a **runtime annotation**?

**Decision A: Part of Identity** (Recommended for routing)
- Treat `"claude-opus-5[1m]"` as a distinct model from `"claude-opus-5"`
- Normalize to: `"anthropic:opus:5-1m"` (Candidate B) or `"ccdash://models/anthropic/claude-opus-5?variant=1m"` (Candidate C)
- Rationale: Cost and performance profiles may differ (1M context may be slower/more expensive), so routing should treat them separately

**Decision B: Runtime Annotation** (If negligible difference)
- Normalize all context-length variants to same model
- Strip `[1m]` in CCDash before emitting: `"claude-opus-5[1m]"` → `"anthropic:opus:5"`
- Rationale: If cost/perf are identical, separate routing keys add noise without signal

**Recommendation**: Decision A (part of identity). Empirical validation in Phase 7+ can downgrade to Decision B if data shows no difference.

---

## 6. Deferred Tasks & Next Steps

### 6.1 No CCDash Changes Required Today

All work for DI-2 is deferred. CCDash Phase 1–6 emits raw model strings as-is (§1.1) with
best-effort provider derivation (§1.2).

### 6.2 Next Steps (If Promoted)

1. **Router owner + CCDash owner meet** to discuss model-naming strategy
   - Share current schemas (router scorecard, CCDash telemetry samples)
   - Review the three candidates (§3.1–3.3) or propose alternatives

2. **Co-author a shared spec** (e.g., RFC in agentic_meta_dev)
   - Define normalization algorithm
   - Document version management and governance
   - Specify context-length handling (§5)

3. **Implement in both projects** (Phase 7+ timeline)
   - CCDash: add normalization + test
   - Router: update scorecard + implement same normalization

4. **Validate in staging** before production
   - Confirm model joins work end-to-end
   - Check for signal loss due to normalization mismatch

---

## 7. Risk Mitigation

### 7.1 Normalization Divergence (R-P3)

**Risk**: CCDash and router implement the normalization differently and produce non-matching strings.
Models fail to join silently.

**Mitigation**:
- Implement normalization logic in a **shared library** or **locked test case**
- Add integration test to router's CI: consume CCDash feedback, normalize, verify deterministic output
- Include test assertions for all 50+ model strings seen in production

### 7.2 Legacy Model Orphaning

**Risk**: Old model strings (e.g., `"claude-opus-4.1"`) are dropped or normalized incorrectly,
losing historical feedback.

**Mitigation**:
- Maintain a comprehensive alias list (Candidate A) that includes all legacy models
- Document the sunset timeline for old models (e.g., "opus-4.1 data migrated to opus-5 bucket")
- Never silently drop a model; use `"unknown:<raw>"` as fallback

---

## References

- **CCDash Routing Feedback Consumer Contract**: `docs/project_plans/design-specs/ccdash-routing-feedback-consumer-contract-v1.md`
- **Proof→Routing Loop PRD**: `docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md` (§3, Problem Statement; Open Question OQ-2)
- **CCDash Model Telemetry Collection**: `backend/parsers/sessions.py`
- **CCDash Provider Derivation Logic**: `backend/application/services/agent_queries/routing_rollup.py::derive_model_identity`
- **Current Model Registry**: `~/.claude/config/model-registry.yaml`
