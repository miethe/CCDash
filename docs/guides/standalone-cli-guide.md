# Standalone CCDash CLI Operator Guide

This guide covers the standalone `ccdash-cli` package, which can be installed globally and used to query any running CCDash server over HTTP. Unlike the repo-local CLI (documented in `cli-user-guide.md`), the standalone CLI requires no access to the CCDash repository code and is designed for remote server targeting.

## Installation

### Prerequisites

- Python 3.10 or higher
- A running CCDash server (local or remote)

### Install via pipx (Recommended)

The recommended installation method uses `pipx`, which isolates the CLI in its own virtual environment:

```bash
pipx install ccdash-cli
```

This command installs from PyPI. It only works after `ccdash-cli` and its dependency
`ccdash-contracts` have been published.

Verify installation:

```bash
ccdash --version
ccdash target show
ccdash doctor
```

### Install via pip

Alternatively, install directly into your Python environment:

```bash
pip install ccdash-cli
```

Then run commands as:

```bash
ccdash --version
ccdash target show
ccdash doctor
```

### Upgrade

If you have an existing installation and need to update:

```bash
pipx upgrade ccdash-cli
# Or with pip:
pip install --upgrade ccdash-cli
```

### Local package smoke test before publishing

If you are validating the standalone CLI from a repo checkout before publishing to PyPI,
use a fresh virtual environment and install both local packages directly:

```bash
python3 -m venv .venv-standalone-cli
source .venv-standalone-cli/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install ./packages/ccdash_contracts ./packages/ccdash_cli
```

Then run the same smoke checks:

```bash
ccdash --version
ccdash target show
ccdash doctor
```

If you want editable installs while iterating on the package:

```bash
python -m pip install -e ./packages/ccdash_contracts -e ./packages/ccdash_cli
```

Use `pipx install ccdash-cli` only once the package artifacts exist on PyPI.

## Architecture

The standalone CLI communicates with a CCDash server over HTTP. It does NOT:

- Import backend code from the repository
- Require the CCDash repository to be present
- Run local parsers or sync engines
- Maintain a local database

Instead, it:

- Targets a running server by URL (default `http://localhost:8000`)
- Sends HTTP requests to the server's REST API
- Receives and formats responses locally
- Supports multiple named targets with saved configuration

This architecture makes it suitable for:

- Remote operations (staging, production servers)
- CI/CD pipelines
- Local development of server integrations
- Multi-project workflows

## Global Flags

All commands accept these global flags:

### --version

Print the CLI version and exit from the root command:

```bash
ccdash --version
```

The `ccdash version` subcommand is still available, but the root flag is the preferred quick check for installs and automation.

### --target NAME

Use a named target from your configuration instead of the default. Resolves targets in order:

1. `--target NAME` (explicit flag)
2. `CCDASH_TARGET` environment variable
3. `active_target` from `~/.config/ccdash/config.toml`
4. Implicit `local` target (`http://localhost:8000`)

Example:

```bash
ccdash --target staging status project
ccdash --target production feature list
```

### --output FORMAT

Set the output format for all commands. Defaults depend on command type:

- Report commands (`ccdash report aar`, `ccdash report feature`) default to `markdown`
- All other commands default to `human`

Supported formats: `human`, `json`, `markdown`

```bash
ccdash status project --output json
ccdash feature list --output markdown
```

Shortcuts:

```bash
ccdash status project --json       # Equivalent to --output json
ccdash report aar --md             # Equivalent to --output markdown
```

### Project Override

Per-target and per-invocation project selection:

- `--project ID` — override the target's default project for this command
- `CCDASH_PROJECT` environment variable — override for all commands in this shell session

```bash
ccdash --project my-project status project
CCDASH_PROJECT=my-project ccdash feature list
```

## Target Management Commands

Target management commands control which servers the CLI targets and how authentication is configured.

### ccdash target list

List all configured targets with their URLs, stored token refs, and active status.

```bash
ccdash target list
```

Output:

```
  Name     URL                           Token Ref        Project      Active
------------------------------------------------------------------------
* local    http://localhost:8000                                       *
  staging  https://ccdash-staging.com    target:staging   my-project
  prod     https://ccdash-prod.com                      production
```

### ccdash target add NAME URL

Add a new named target with optional project default.

```bash
ccdash target add local http://localhost:8000
ccdash target add staging https://ccdash-staging.example.com --project my-project
ccdash target add prod https://ccdash-prod.example.com
```

The CLI warns when a non-localhost target uses plain `http://`. Prefer `https://` for remote targets.

### ccdash target remove NAME

Remove a named target and its stored credentials.

```bash
ccdash target remove staging
```

### ccdash target use NAME

Set the active target for all future commands (unless overridden with `--target`).

```bash
ccdash target use staging
```

Updates `active_target` in `~/.config/ccdash/config.toml`.

### ccdash target show [NAME]

Show the resolved target state the CLI will use, including auth source and whether it came from config or the implicit local fallback.

```bash
ccdash target show
ccdash target show staging
```

Example output:

```
Name: staging
URL: https://ccdash-staging.example.com
Project: my-project
Authentication: token ref 'target:staging' (token loaded)
Source: configured target
```

### ccdash target login NAME [--token TOKEN]

Store bearer token authentication for a target. Tokens are stored securely in the OS keyring (macOS Keychain, Linux Secret Service, Windows Credential Manager). If no keyring backend is available, use `CCDASH_TOKEN` instead.

Interactive prompt:

```bash
ccdash target login staging
# Prompts: "Enter bearer token for 'staging':"
```

Non-interactive (pass token as flag):

```bash
ccdash target login staging --token "sk-xyz123..."
```

The token is used for all subsequent requests to that target via the `Authorization: Bearer <token>` header.

### ccdash target logout NAME

Remove stored credentials for a target.

```bash
ccdash target logout staging
```

Future requests to this target will not include an `Authorization` header.

### ccdash target check NAME

Verify connectivity and authentication for a target. Use `target show` to inspect the resolved config locally; use `target check` to confirm live server reachability and whether the server accepts the current credentials.

```bash
ccdash target check staging
```

Output on success:

```
Checking target 'staging' at https://ccdash-staging.example.com ...
  Connection: OK
  Auth:       OK
  Instance:   staging  (version 0.1.0  env=api)
```

Output on failure:

```
Checking target 'staging' at https://ccdash-staging.example.com ...
  Connection: OK
  Auth:       FAILED (HTTP 401 — invalid or missing bearer token)
  Tip: run 'ccdash target login staging' to store credentials.
```

## Status Commands

### ccdash status project [--project ID]

Show a summary of the active project, including counts, recent activity, and health status.

```bash
ccdash status project
ccdash status project --project my-other-project
```

Output (human format):

```
Project: my-project
Status: HEALTHY

Sessions: 42 total
  - Active: 3
  - Completed: 39
  - Failed: 0

Features: 8 in progress
  - Completed: 12
  - At risk: 1

Recent Activity:
  - FEAT-123 session added 2 hours ago
  - FEAT-122 completed 6 hours ago
  - FEAT-121 session added 1 day ago
```

Output (JSON format):

```bash
ccdash status project --json
```

```json
{
  "project_id": "my-project",
  "status": "HEALTHY",
  "sessions": {
    "total": 42,
    "active": 3,
    "completed": 39,
    "failed": 0
  },
  "features": {
    "in_progress": 8,
    "completed": 12,
    "at_risk": 1
  },
  "last_updated": "2026-04-13T14:22:45Z"
}
```

## Feature Commands

### ccdash feature list [OPTIONS]

List features with optional filtering, sorting, and pagination.

```bash
ccdash feature list
ccdash feature list --status in-progress
ccdash feature list --category refactor --limit 10 --offset 0
ccdash feature list --json
```

Options:

- `--status STATUS` — filter by status (all, in-progress, completed, at-risk, blocked)
- `--category CAT` — filter by category tag
- `--limit N` — maximum number of results (default 20)
- `--offset N` — skip first N results for pagination (default 0)
- `--json`, `--md` — output format override

Output (human format):

```
ID        Title                Status         Category    Sessions
--        -----                ------         --------    --------
FEAT-123  Auth refactor        in-progress    refactor    5
FEAT-122  Dashboard redesign   completed      feature     12
FEAT-121  API caching          at-risk        backend     8
```

### ccdash feature show FEATURE_ID

Display comprehensive forensic details for a single feature, including sessions, documents, execution timeline, and rework signals.

```bash
ccdash feature show FEAT-123
ccdash feature show FEAT-123 --json
```

Output (human format):

```
Feature: FEAT-123
Title: Auth refactor
Status: IN-PROGRESS
Category: refactor
Created: 2026-03-15T10:00:00Z
Updated: 2026-04-13T14:00:00Z

Sessions: 5 total
  - sess-001 (3.2h): ✓ Completed
  - sess-002 (2.1h): ✓ Completed
  - sess-003 (1.5h): ✓ Completed
  - sess-004 (4.2h): ⏳ In-progress
  - sess-005 (1.8h): ✗ Failed

Documents: 3 linked
  - design-doc.md (updated 2h ago)
  - progress.md (updated 30m ago)
  - api-contract.md

Rework Signals:
  - High churn in auth-service (3 rewrites)
  - Scope drift: +4 sessions vs plan
  - Tool usage: {claude: 42%, search: 31%, git: 27%}

Representative Failure: sess-005
  Issue: Database connection timeout during migration
  Timestamp: 2026-04-13T11:30:00Z
```

### ccdash feature sessions FEATURE_ID [--limit N] [--offset N]

List all sessions linked to a feature with optional pagination.

```bash
ccdash feature sessions FEAT-123
ccdash feature sessions FEAT-123 --limit 5 --json
```

Options:

- `--limit N` — maximum sessions to return (default 20)
- `--offset N` — pagination offset (default 0)
- `--json`, `--md` — output format override

Output (human format):

```
Feature FEAT-123 sessions:
ID        Duration   Status      Started             Tools
--        --------   ------      -------             -----
sess-001  3h 12m     completed   2026-04-10 09:00    claude, search, git
sess-002  2h 06m     completed   2026-04-10 15:30    claude, search
sess-003  1h 45m     completed   2026-04-11 10:00    claude, browser
sess-004  4h 22m     in-progress 2026-04-13 08:00    claude, search, git
sess-005  1h 48m     failed      2026-04-13 11:00    claude, search
```

### ccdash feature documents FEATURE_ID

List all documents linked to a feature.

```bash
ccdash feature documents FEAT-123
ccdash feature documents FEAT-123 --json
```

Output (human format):

```
Feature FEAT-123 documents:
Name                  Type        Status      Updated
----                  ----        ------      -------
design-doc.md         markdown    active      2h ago
progress.md           markdown    active      30m ago
api-contract.md       markdown    active      1d ago
meeting-notes.md      markdown    archived    3d ago
```

## Session Commands

### ccdash session list [OPTIONS]

List sessions with optional filtering by feature, root-session, and pagination.

```bash
ccdash session list
ccdash session list --feature FEAT-123
ccdash session list --root-session sess-001 --limit 10
ccdash session list --json
```

Options:

- `--feature ID` — filter to sessions linked to feature ID
- `--root-session ID` — filter to sessions in same family tree
- `--limit N` — maximum results (default 20)
- `--offset N` — pagination offset (default 0)
- `--json`, `--md` — output format override

Output (human format):

```
ID        Feature   Duration   Status      Started             Tokens
--        -------   --------   ------      -------             ------
sess-001  FEAT-123  3h 12m     completed   2026-04-10 09:00    45,320
sess-002  FEAT-123  2h 06m     completed   2026-04-10 15:30    32,110
sess-003  FEAT-122  1h 45m     completed   2026-04-11 10:00    28,950
sess-004  FEAT-123  4h 22m     in-progress 2026-04-13 08:00    67,200
sess-005  (none)    1h 48m     failed      2026-04-13 11:00    31,450
```

### ccdash session show SESSION_ID

Display comprehensive session intelligence, including transcript, tool usage, token metrics, and anomalies.

```bash
ccdash session show sess-001
ccdash session show sess-001 --json
```

Output (human format):

```
Session: sess-001
Feature: FEAT-123
Status: COMPLETED
Duration: 3h 12m
Started: 2026-04-10 09:00:00Z
Ended: 2026-04-10 12:15:00Z

Tokens: 45,320 total
  - Input: 21,100 (46%)
  - Output: 24,220 (54%)

Tool Usage:
  - claude (API): 34 calls, 2.5h
  - search: 12 calls, 0.3h
  - git: 8 calls, 0.4h

Output Artifacts:
  - 3 code changes
  - 2 documents updated
  - 1 branch created

Sentiment: POSITIVE
  - Messages: 127 total
  - Tone: Productive, problem-solving focus
  - No significant concern flags

Anomalies: None detected
```

### ccdash session search QUERY [--feature ID] [--limit N]

Search session transcripts by query string.

```bash
ccdash session search "authentication"
ccdash session search "timeout error" --feature FEAT-123 --limit 5
ccdash session search "FEAT-123" --json
```

Options:

- `--feature ID` — restrict search to sessions in feature
- `--limit N` — maximum results (default 10)
- `--json`, `--md` — output format override

Output (human format):

```
Found 3 results matching "authentication":

sess-001 (FEAT-123):
  Snippet: "...implementing oauth2 for authentication..."
  Context: Claude discussion about auth design
  Timestamp: 2026-04-10 09:30:00Z

sess-002 (FEAT-123):
  Snippet: "...test basic authentication flow..."
  Context: Testing phase discussion
  Timestamp: 2026-04-10 16:15:00Z

sess-003 (FEAT-122):
  Snippet: "...refactor authentication middleware..."
  Context: Code review notes
  Timestamp: 2026-04-11 10:45:00Z
```

### ccdash session drilldown SESSION_ID --concern CONCERN

Drill into a specific concern (sentiment, churn, scope_drift) with detailed analysis and recommendations.

```bash
ccdash session drilldown sess-004 --concern sentiment
ccdash session drilldown sess-005 --concern churn
ccdash session drilldown sess-001 --concern scope_drift --json
```

Supported concerns:

- `sentiment` — analyze emotional tone and productivity signals
- `churn` — examine code rewrites and rework patterns
- `scope_drift` — compare planned vs actual feature scope

Output (human format, sentiment example):

```
Session: sess-004
Concern: SENTIMENT
Feature: FEAT-123
Duration: 4h 22m

Sentiment Timeline:
  09:00-10:00  POSITIVE  Setup and planning
  10:00-12:00  POSITIVE  Active development
  12:00-13:00  NEUTRAL   Testing phase
  13:00-15:00  NEGATIVE  Debugging failures
  15:00-16:22  POSITIVE  Issue resolution

Overall Sentiment: MIXED (some concern)

Concern Flags:
  - 2x error debugging phase
  - 2x "seems stuck" messages
  - 1x request for external help

Recommendations:
  - Review database migration step (repeated 3 times)
  - Consider adding integration test for migration flow
  - Schedule sync with domain expert for scope clarification
```

### ccdash session family SESSION_ID

List all sessions in the same root-session family tree (for hierarchical session workflows).

```bash
ccdash session family sess-004
ccdash session family sess-004 --json
```

Output (human format):

```
Root Session: sess-001

Family Tree (4 sessions):
├─ sess-001 (root)
│  Duration: 3h 12m
│  Status: completed
│  ├─ sess-002 (child)
│  │  Duration: 2h 06m
│  │  Status: completed
│  │  └─ sess-003 (child)
│  │     Duration: 1h 45m
│  │     Status: completed
│  │     └─ sess-004 (child)
│  │        Duration: 4h 22m
│  │        Status: in-progress
```

## Workflow Commands

### ccdash workflow failures [--feature ID]

Show the highest-impact workflow failure patterns, ranked by frequency and scope impact.

```bash
ccdash workflow failures
ccdash workflow failures --feature FEAT-123
ccdash workflow failures --json
```

Options:

- `--feature ID` — filter to failures in a specific feature
- `--json`, `--md` — output format override

Output (human format):

```
Workflow Failure Patterns (ranked by impact):

1. Database Migration Timeout
   Frequency: 8 occurrences
   Features: FEAT-123 (5), FEAT-121 (3)
   Impact: High (blocks feature completion)
   Trend: Increasing (last 3 days)
   
   Representative Session: sess-005
   Error: "Connection pool exhausted during schema migration"
   
   Recommendation:
   - Increase connection pool size
   - Add retry logic with exponential backoff
   - Consider async migration approach

2. Authentication Token Expiry
   Frequency: 4 occurrences
   Features: FEAT-122 (4)
   Impact: Medium (requires manual retry)
   Trend: Stable
   
   Recommendation:
   - Implement token refresh mechanism
   - Add proactive expiry warnings

3. Search Index Lag
   Frequency: 2 occurrences
   Features: FEAT-124 (2)
   Impact: Low (workaround available)
   Trend: Decreasing
   
   Status: Monitoring
```

## Report Commands

### ccdash report aar --feature FEATURE_ID [OPTIONS]

Generate an after-action report (AAR) for a feature. Outputs markdown by default.

```bash
ccdash report aar --feature FEAT-123
ccdash report aar --feature FEAT-123 --json
ccdash report aar --feature FEAT-123 --output markdown > report.md
```

Options:

- `--feature FEATURE_ID` — required; feature to report on
- `--output FORMAT` — override default markdown output
- `--json`, `--md` — format shortcuts

Output (markdown format):

```markdown
# After-Action Report: FEAT-123

## Summary

**Feature:** Auth Refactor  
**Status:** In-Progress  
**Duration:** 11h 21m across 5 sessions  
**Completion:** 80%

## Execution

- Started: 2026-04-10 09:00:00Z
- Last Updated: 2026-04-13 15:22:00Z
- Sessions: 5 total (4 completed, 1 in-progress)
- Tokens: 165,230 total (avg 33,046 per session)

## Outcomes

### Completed
- OAuth2 provider integration
- JWT token generation and validation
- API endpoint authentication layer
- Unit test coverage (85%)

### In-Progress
- Integration testing
- Performance benchmarking

### Blocked
- User session state persistence (awaiting DB schema)

## Signals

### Positive
- Strong code review feedback (2 approvals)
- Zero critical test failures
- Sentiment remains positive (87%)

### Concerns
- 3 rework cycles on auth service
- 1 failed session (database connection timeout)
- Scope expanded (+2 sessions vs initial plan)

## Tool Usage Summary
- claude: 42% of session time
- search: 31%
- git: 27%

## Recommendations
1. Address database migration performance
2. Add integration test for OAuth flow
3. Schedule architecture review for scope alignment
```

### ccdash report feature FEATURE_ID [OPTIONS]

Generate a comprehensive narrative feature report including background, execution, outcomes, and next steps.

```bash
ccdash report feature FEAT-123
ccdash report feature FEAT-123 --json
ccdash report feature FEAT-123 --output json | jq .
```

Options:

- `--feature FEATURE_ID` — required; feature to report on
- `--output FORMAT` — override default markdown output
- `--json`, `--md` — format shortcuts

Output structure (markdown):

```markdown
# Feature Report: FEAT-123

## Overview
[Feature summary, status, timeline]

## Context
[Background, requirements, related features]

## Execution Timeline
[Session sequence, milestones, blockers]

## Deliverables
[Code changes, documents, tests, deployments]

## Metrics
[Token usage, session count, tool distribution]

## Observations
[Sentiment, churn patterns, scope drift]

## Next Steps
[Remaining work, recommendations, risks]
```

## Diagnostics Commands

### ccdash doctor

Run comprehensive diagnostics on the current target configuration. Checks target resolution, connectivity, authentication, and API version compatibility.

```bash
ccdash doctor
```

Output:

```
CCDash CLI Doctor
========================================

Target
  Name:                 staging
  URL:                  https://ccdash-staging.example.com
  Source:               staging (from config)
  Project:              my-project
  Auth token:           present

Server
  Reachable:            PASS
  Instance ID:          staging
  Server version:       0.1.0
  Environment:          api
  Capabilities:         feature-documents, feature-sessions, instance
```

Output on failure:

```
CCDash CLI Doctor
========================================

Target
  Name:                 prod
  URL:                  https://ccdash-prod.example.com
  Source:               prod (from config)
  Auth token:           not set (unauthenticated)

Server
  Reachable:            FAIL

  Connection error: Cannot connect to CCDash server at https://ccdash-prod.example.com.

  Verify the server is running and the URL is correct:
    https://ccdash-prod.example.com
```

### ccdash --version

Display the standalone CLI package version.

```bash
ccdash --version
```

Output:

```
ccdash-cli 0.1.0
```

Use `ccdash doctor` when you also need live server version and instance metadata.

If CLI and server versions differ significantly:

```
Error: API version mismatch. The server did not accept the expected /api/v1 surface.
Try: pipx upgrade ccdash-cli
```

## Target Configuration

The standalone CLI stores all target configuration in `~/.config/ccdash/config.toml`, respecting the `$XDG_CONFIG_HOME` environment variable on Unix-like systems.

### Configuration File Location

- **Linux/macOS:** `~/.config/ccdash/config.toml`
- **Windows:** `%APPDATA%\ccdash\config.toml`
- **Custom:** `$XDG_CONFIG_HOME/ccdash/config.toml`

### Configuration Format

```toml
[defaults]
active_target = "staging"

[targets.local]
url = "http://localhost:8000"
# token_ref optional; omit if no token

[targets.staging]
url = "https://ccdash-staging.example.com"
project = "my-project"
# token stored securely in keyring, not in file

[targets.prod]
url = "https://ccdash-prod.example.com"
project = "production"
# token stored securely in keyring
```

### Configuration Sections

**[defaults]**

- `active_target` — the target to use by default (applied if `--target` not specified and `CCDASH_TARGET` not set)

**[targets.NAME]**

- `url` — HTTP/HTTPS URL of the CCDash server (required)
- `project` — default project ID for this target (optional; can be overridden with `--project`)

Tokens are NOT stored in the config file; they are stored securely in the OS keyring via `ccdash target login`, or supplied per-process with `CCDASH_TOKEN`.

### Target Resolution Order

When resolving which target to use:

1. `--target NAME` flag (explicit)
2. `CCDASH_TARGET` environment variable
3. `active_target` from config file
4. Implicit `local` target pointing to `http://localhost:8000`

After target is resolved, per-field environment variables are applied:

- `CCDASH_URL` — overrides target's URL
- `CCDASH_TOKEN` — overrides keyring token (useful for CI/CD)
- `CCDASH_PROJECT` — overrides target's project default

### Example Workflows

**Single Local Server**

```bash
# No config needed; implicit 'local' target is http://localhost:8000
ccdash status project
ccdash feature list
```

**Multiple Servers**

```bash
# Add targets
ccdash target add local http://localhost:8000
ccdash target add staging https://ccdash-staging.example.com --project my-project
ccdash target add prod https://ccdash-prod.example.com --project production

# Set default to staging
ccdash target use staging

# All commands now use staging unless overridden
ccdash status project  # Uses staging

# Switch to prod for one command
ccdash --target prod feature list

# View all targets
ccdash target list
```

**CI/CD Environment (No Keyring)**

```bash
# In CI/CD pipeline, use environment variables to bypass keyring
export CCDASH_TARGET=prod
export CCDASH_URL=https://ccdash-prod.example.com
export CCDASH_TOKEN=sk-...
export CCDASH_PROJECT=my-project

# All commands use provided environment values
ccdash status project
ccdash feature list
ccdash report aar --feature FEAT-123 > report.md
```

## Authentication

### Local Server (No Auth)

For local development with the implicit `local` target at `http://localhost:8000`:

```bash
ccdash target show
ccdash status project
# Authentication: not configured
```

If the server itself runs in a protected profile, local unauthenticated requests may still be rejected. The CLI only sends a bearer token when one resolves from the environment or keyring.

### Remote Server with Token

For remote servers that require authentication:

**Step 1: Add the target**

```bash
ccdash target add staging https://ccdash-staging.example.com --project my-project
```

**Step 2: Store the token**

Interactive (secure prompt):

```bash
ccdash target login staging
# Prompts: "Enter bearer token for 'staging':"
# Stores token in OS keyring, never echoed to terminal
```

Non-interactive (for CI/CD):

```bash
ccdash target login staging --token "sk-xyz123..."
```

**Step 3: Inspect and verify**

```bash
ccdash target show staging
ccdash target check staging
# target show: resolved URL, project, auth source
# target check: live connectivity and auth validation
```

**Step 4: Use the target**

```bash
ccdash --target staging status project
ccdash --target staging feature list
```

### Token Expiry and Refresh

If a token expires:

1. You'll see an authentication error:
   ```
   Error: Authentication failed (HTTP 401). Check your bearer token and retry.
   ```

2. Re-login with a fresh token:
   ```bash
   ccdash target login staging
   # Re-enter the new token when prompted
   ```

### CI/CD Authentication (Environment Variables)

For unattended CI/CD workflows, bypass the keyring by setting environment variables:

```bash
export CCDASH_TARGET=prod
export CCDASH_URL=https://ccdash-prod.example.com
export CCDASH_TOKEN=$DEPLOY_TOKEN
export CCDASH_PROJECT=my-project

# All commands use the provided token without keyring access
ccdash status project
ccdash report aar --feature FEAT-123 > aar.md
```

This approach is essential for:

- GitHub Actions, GitLab CI, Jenkins, etc.
- Containerized environments (where keyring may not be available)
- Automation scripts running in headless contexts

## Error Codes and Exit Status

The CLI returns standardized exit codes to support scripting and CI/CD error handling:

| Code | Meaning | Example |
|------|---------|---------|
| 0 | Success | Command completed successfully |
| 1 | General error | Server error, resource not found, malformed request |
| 2 | Authentication failure | HTTP 401, invalid token, credentials required |
| 3 | Permission denied | HTTP 403, insufficient permissions |
| 4 | Network/connection failure | Connection refused, timeout, DNS resolution failure |
| 5 | API version mismatch | CLI and server versions incompatible |

### Using Exit Codes in Scripts

```bash
#!/bin/bash

ccdash --target staging status project --json > status.json
EXIT_CODE=$?

case $EXIT_CODE in
  0)
    echo "Status check succeeded"
    cat status.json
    ;;
  2)
    echo "Authentication failed; re-login required"
    ccdash target login staging
    exit 1
    ;;
  4)
    echo "Cannot reach staging server; trying local fallback"
    ccdash --target local status project
    ;;
  *)
    echo "Unexpected error (code: $EXIT_CODE)"
    exit 1
    ;;
esac
```

## Common Workflows

### Check Status and List Features

```bash
# View project health
ccdash status project

# List all in-progress features
ccdash feature list --status in-progress

# Count completed features
ccdash feature list --status completed --json | jq '.features | length'
```

### Investigate a Feature

```bash
# Show feature details
ccdash feature show FEAT-123

# List all sessions for the feature
ccdash feature sessions FEAT-123

# View linked documents
ccdash feature documents FEAT-123

# Generate after-action report
ccdash report aar --feature FEAT-123 > aar.md
```

### Debug a Failed Session

```bash
# List failed sessions
ccdash session list --json | jq '.[] | select(.status == "failed")'

# Show detailed information about a session
ccdash session show sess-005

# Drill into the sentiment concern
ccdash session drilldown sess-005 --concern sentiment

# Search for error messages in that session
ccdash session search "error" --limit 5 --json
```

### Monitor Feature Progress

```bash
# Set active target to staging
ccdash target use staging

# Check project status
ccdash status project

# List at-risk features
ccdash feature list --status at-risk

# Show failure patterns
ccdash workflow failures
```

### Generate Multiple Reports

```bash
# Set up environment for non-interactive report generation
export CCDASH_TARGET=prod
export CCDASH_TOKEN=$AUTOMATION_TOKEN
export CCDASH_PROJECT=my-project

# Generate reports for multiple features
for feature in FEAT-120 FEAT-121 FEAT-122; do
  echo "Generating report for $feature..."
  ccdash report aar --feature $feature --md > "reports/${feature}-aar.md"
  ccdash report feature $feature --md > "reports/${feature}-report.md"
done
```

### CI/CD Integration Example (GitHub Actions)

```yaml
name: Generate CCDash Reports

on:
  schedule:
    - cron: '0 9 * * 1'  # Monday mornings

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - name: Install ccdash-cli
        run: pip install ccdash-cli

      - name: Check connectivity
        run: ccdash doctor
        env:
          CCDASH_TARGET: prod
          CCDASH_URL: ${{ secrets.CCDASH_PROD_URL }}
          CCDASH_TOKEN: ${{ secrets.CCDASH_PROD_TOKEN }}
          CCDASH_PROJECT: my-project

      - name: Generate AAR for FEAT-123
        run: ccdash report aar --feature FEAT-123 > aar.md
        env:
          CCDASH_TARGET: prod
          CCDASH_URL: ${{ secrets.CCDASH_PROD_URL }}
          CCDASH_TOKEN: ${{ secrets.CCDASH_PROD_TOKEN }}
          CCDASH_PROJECT: my-project

      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: ccdash-reports
          path: aar.md
```

## Troubleshooting

### Connection Refused

**Symptom:** `Error: Cannot reach http://localhost:8000`

**Causes:**
- CCDash server is not running
- Server is running on a different port
- Firewall or network blocking

**Solutions:**

1. Check if server is running:
   ```bash
   curl http://localhost:8000/health
   # If this fails, start the server
   cd /path/to/CCDash
   npm run dev
   ```

2. If server is on a different URL, update target:
   ```bash
   ccdash target add local http://localhost:8001  # If on port 8001
   ccdash target use local
   ```

3. For remote servers, verify network connectivity:
   ```bash
   ccdash target check staging
   # Shows detailed connectivity diagnostics
   ```

### Authentication Failures

**Symptom:** `Error: HTTP 401 - Unauthorized`

**Causes:**
- Token is missing or expired
- Token was revoked
- Token is for a different server

**Solutions:**

1. Check auth status:
   ```bash
   ccdash target show staging
   ccdash target check staging
   # target show: token source and resolved target
   # target check: live credential validation
   ```

2. Re-authenticate:
   ```bash
   ccdash target login staging
   # Enter new token when prompted
   ```

3. Verify token is stored:
   ```bash
   ccdash target login staging --token "your-token"
   # Non-interactive token update
   ```

4. For CI/CD, verify environment variables:
   ```bash
   echo $CCDASH_TOKEN
   # Should be set and non-empty
   ```

### Version Mismatch

**Symptom:** `Error: API version mismatch. CLI 0.7.0, Server 0.8.0`

**Causes:**
- CLI was updated but server wasn't (or vice versa)
- Multiple CCDash deployments at different versions

**Solutions:**

1. Upgrade CLI to match server:
   ```bash
   pipx upgrade ccdash-cli
   # Or: pip install --upgrade ccdash-cli
   ```

2. Check versions:
   ```bash
   ccdash --version
   ccdash doctor
   # --version shows the CLI package version; doctor shows live server metadata
   ```

3. If multiple targets have different versions, use explicit `--target`:
   ```bash
   ccdash --target prod status project  # Uses prod server
   ccdash --target staging status project  # Uses staging server
   ```

### Wrong Project Selected

**Symptom:** `Error: Feature FEAT-123 not found` (but you know it exists)

**Causes:**
- Feature is in a different project than active project
- Wrong target selected

**Solutions:**

1. Check active project:
   ```bash
   ccdash target list
   # Shows which target is active and its default project
   ```

2. Explicitly specify project:
   ```bash
   ccdash --project my-other-project feature show FEAT-123
   ```

3. Change active target:
   ```bash
   ccdash target use staging
   # If staging has correct project as default
   ```

4. Use environment variable:
   ```bash
   export CCDASH_PROJECT=my-other-project
   ccdash feature show FEAT-123
   ```

### No Output or Truncated Output

**Symptom:** Command runs but produces no output, or output is incomplete

**Causes:**
- Output format is unsupported
- Network timeout
- Server is slow

**Solutions:**

1. Check output format:
   ```bash
   ccdash feature list --output human  # Explicit format
   ```

2. Increase verbosity for debugging:
   ```bash
   ccdash feature list --json | jq .
   # JSON output allows inspection of full data
   ```

3. For large result sets, paginate:
   ```bash
   ccdash session list --limit 10 --offset 0
   ccdash session list --limit 10 --offset 10  # Next page
   ```

4. Check server health:
   ```bash
   ccdash doctor
   # Comprehensive diagnostics
   ```

### Config File Issues

**Symptom:** `Error: Cannot read config file`

**Solutions:**

1. Check config file location:
   ```bash
   echo $XDG_CONFIG_HOME  # Unix-like
   # Should be set or default to ~/.config/
   ```

2. Verify file exists:
   ```bash
   cat ~/.config/ccdash/config.toml
   # If missing, create with target add
   ```

3. Reset configuration:
   ```bash
   rm ~/.config/ccdash/config.toml
   ccdash target add local http://localhost:8000
   ccdash target use local
   # Config is recreated automatically
   ```

### Keyring Issues (macOS/Linux)

**Symptom:** `Error: Cannot access system keyring`

**Causes:**
- Keyring daemon not running (Linux)
- SSH session without terminal (Linux)
- Containerized environment

**Solutions:**

1. For CI/CD, use environment variables instead of keyring:
   ```bash
   export CCDASH_TOKEN=$MY_TOKEN
   ccdash status project
   # Bypasses keyring entirely
   ```

2. On Linux, ensure keyring daemon is running:
   ```bash
   # For GNOME Secret Service
   sudo systemctl start gnome-keyring-daemon
   ```

3. For headless SSH, store token in environment file:
   ```bash
   # In ~/.bashrc or similar
   export CCDASH_TOKEN=$(cat ~/.ccdash-token)
   # chmod 600 ~/.ccdash-token
   ```

## Getting Help

**View CLI help:**

```bash
ccdash --help
ccdash target --help
ccdash feature --help
ccdash report --help
```

**Report issues:**

If you encounter bugs or unexpected behavior, open an issue on the CCDash repository with:

- CLI version: `ccdash --version`
- Server version: `ccdash doctor`
- Full error message with `--json` output
- Reproduction steps

**Check logs:**

For detailed error information:

```bash
# Enable debug output (if available in your CLI version)
CCDASH_DEBUG=1 ccdash status project

# Or check server logs at the CCDash repository
cd /path/to/CCDash
npm run dev  # Backend logs appear in this terminal
```
