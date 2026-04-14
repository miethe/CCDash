---
schema_version: "1.0"
doc_type: design-spec
title: "CCDash CLI Target Model and Authentication Storage"
status: draft
created: "2026-04-12"
feature_slug: "ccdash-standalone-global-cli"
prd_ref: "docs/project_plans/PRDs/features/ccdash-standalone-global-cli-v1.md"
plan_ref: "docs/project_plans/implementation_plans/features/ccdash-standalone-global-cli-v1.md"
---

# CCDash CLI Target Model and Authentication Storage

This document specifies the target configuration schema (P1-T2) and secret storage
strategy (P1-T5) for the CCDash standalone global CLI. It covers the decisions that
must be locked before Phase 3 implementation begins.

---

## 1. Target Model

### 1.1 Concept

A **target** is a named reference to a running CCDash instance. It bundles a base URL,
an optional project override, and an optional reference to an auth credential. The CLI
resolves exactly one target per invocation.

Targets are modeled after the kubectl context pattern: names are stable identifiers,
and a single active target is tracked in the config file. The local CCDash instance is
always available as an implicit default, requiring zero configuration from the operator.

### 1.2 Config file location

```
~/.config/ccdash/config.toml
```

XDG Base Directory Specification compliant. The path respects `$XDG_CONFIG_HOME` if
set; otherwise it falls back to `~/.config`. The directory is created on first write
with permissions `0o700`.

### 1.3 Persisted schema (TOML)

```toml
[defaults]
active_target = "local"

[targets.local]
url = "http://localhost:8000"

[targets.staging]
url = "https://ccdash-staging.example.com"
token_ref = "staging-token"

[targets.prod]
url = "https://ccdash.internal.example.com"
token_ref = "prod-token"
project = "platform"
```

**Field reference:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | yes | Base URL of the CCDash HTTP instance, no trailing slash |
| `token_ref` | string | no | Logical name used to look up the bearer token in the system keyring |
| `project` | string | no | Project slug override; when set, prepended to API requests as `?project=<slug>` |

`[defaults]` holds the active target name only. All target records live under
`[targets.<name>]`. The name `local` is reserved for the implicit localhost default and
is created automatically if missing.

### 1.4 Active target resolution order

Resolution is evaluated from highest to lowest priority on every CLI invocation:

```
1. --target <name>          CLI flag (highest)
2. CCDASH_TARGET            Environment variable (target name)
3. config.toml active_target Named target from config file
4. "local" implicit default  http://localhost:8000, no auth (lowest)
```

Once the target is resolved to a record, individual fields within that record are
subject to further env var overrides (see section 1.5).

**Invariant:** A missing or unreadable config file is not an error. The CLI falls
through to the implicit local default silently. An explicit `--target` flag for a name
that does not exist in the config file is an error with a non-zero exit.

### 1.5 Per-field environment variable overrides

These override the resolved target's fields, not the target selection itself:

| Environment variable | Overrides |
|----------------------|-----------|
| `CCDASH_URL` | `targets.<name>.url` of the active target |
| `CCDASH_TOKEN` | Token value directly; bypasses keyring lookup entirely |
| `CCDASH_PROJECT` | `targets.<name>.project` of the active target |

`CCDASH_URL` and `CCDASH_TOKEN` together can fully specify a target at runtime with no
config file, enabling headless and CI environments to operate without persisted state.

### 1.6 Implicit local default behavior

When the active target resolves to `local` (whether explicitly or by fallback):

- Base URL is `http://localhost:8000` unless `CCDASH_URL` is set.
- No auth token is required or expected.
- The target record does not need to exist in the config file.
- `ccdash doctor` reports "local (implicit default)" in target display when no config
  file entry exists.

The local default is intentionally zero-configuration to preserve the common developer
workflow where `ccdash status project` just works.

### 1.7 Federation readiness

Each target record stores enough metadata to support future multi-instance work:

- `url` provides stable instance identity for response correlation.
- `token_ref` names credentials per instance, not globally.
- `project` allows per-instance project scope overrides.
- The target name is an opaque logical identifier that can map to a broader instance
  registry in future federation designs without a schema migration.

v1 resolves exactly one target per invocation. Fan-out, aggregation, and conflict
resolution across instances are out of scope and will be addressed by a future
federation design spec.

---

## 2. Secret Storage Strategy

### 2.1 Decision

Tokens are stored in the **OS system keyring** via the `keyring` Python library, with
`CCDASH_TOKEN` environment variable as a plaintext fallback for CI/headless
environments.

No tokens are ever written to the TOML config file.

### 2.2 Keyring mapping

The `token_ref` field in a target record is the logical name used to construct the
keyring lookup:

| Keyring field | Value |
|---------------|-------|
| Service name | `ccdash` |
| Account (username) | `token_ref` value (e.g. `staging-token`) |

Example: a target with `token_ref = "staging-token"` causes the CLI to call:

```python
keyring.get_password("ccdash", "staging-token")
```

Tokens are stored with the corresponding write call:

```python
keyring.set_password("ccdash", "staging-token", "<bearer-token-value>")
```

This is exposed to the operator as `ccdash target set-token <name>`, which prompts for
the token value without echoing it to the terminal.

### 2.3 Resolution priority for the active token

```
1. CCDASH_TOKEN env var          Direct value; keyring is never consulted
2. keyring.get_password(...)     Looked up by token_ref of the active target
3. (no auth)                     Local targets with no token_ref proceed unauthenticated
```

### 2.4 Plaintext fallback for CI and headless environments

When the `keyring` library cannot reach a backend (no D-Bus session, no macOS
Keychain, running in a minimal container), it raises `keyring.errors.NoKeyringError`
or returns `None`. The CLI handles both cases:

- If `CCDASH_TOKEN` is set: use it directly.
- If `keyring` fails and `CCDASH_TOKEN` is not set: emit a warning and proceed
  unauthenticated (which will produce an auth error from the server if the target
  requires a token).

There is no file-based secret fallback in v1. Operators who cannot use the system
keyring must supply `CCDASH_TOKEN` via the environment.

### 2.5 Token lifecycle

- **No v1 token refresh.** Tokens are bearer tokens issued out-of-band by the CCDash
  server operator. The CLI presents them as-is in the `Authorization: Bearer <token>`
  header.
- **No token rotation logic.** If a token expires, the operator re-runs
  `ccdash target set-token <name>`.
- **No server-side token issuance in v1.** The CLI does not implement OAuth flows,
  device authorization, or any credential exchange protocol.

### 2.6 Security boundaries

**Stored in keyring (acceptable):**
- Bearer token values, keyed by `token_ref`.

**Stored in config file (acceptable):**
- Target names, base URLs, `token_ref` logical names, project slugs.
- `token_ref` is a reference, not the secret itself. Knowing the ref name without
  keyring access yields nothing.

**Never stored anywhere by the CLI:**
- Token values in `config.toml`.
- Token values in log output, `--debug` traces, or `ccdash doctor` display.
- Token values in shell history (interactive `set-token` uses `getpass`).

**Auth error behavior:**
- HTTP 401 from the server produces exit code 2 and the message:
  `Authentication failed for target '<name>'. Check the stored token with: ccdash target set-token <name>`
- HTTP 403 produces exit code 3 and a distinct permissions message.
- Connection failure produces exit code 4.
- These exit codes are stable and scriptable.

---

## 3. Open Questions and Deferred Decisions

| Question | Disposition |
|----------|-------------|
| Should `keyring` be a hard dependency or optional with graceful degradation? | Make it a required dependency; its optional backends (macOS Keychain, SecretService, Windows Credential Manager) are OS-provided. The `keyrings.alt` package can be added as an optional extra for environments that need a file-backed keyring with explicit operator opt-in. |
| Should `ccdash target add` auto-prompt for a token? | Prompt is opt-in via `--set-token` flag; keep add/set-token as separate commands to avoid forcing token entry for local targets. |
| Multi-project target overrides vs. project command flags? | `project` in the target record is a persistent default; `--project` flag on individual commands overrides it for that invocation. Resolution order mirrors target resolution. |
| File permissions for `config.toml`? | Written with `0o600`; CLI warns if the file is world-readable on Unix. |
| Support for client TLS certificates (mTLS remote targets)? | Deferred to post-v1 federation work. The target schema can be extended with `cert_ref` and `key_ref` fields following the same `token_ref` pattern. |
