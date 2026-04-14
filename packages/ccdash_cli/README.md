# `ccdash-cli`

Standalone CCDash operator CLI.

This package installs the global `ccdash` command. It talks to a running CCDash server over HTTP and does not import the backend runtime from the repository.

## Install

Recommended:

```bash
pipx install ccdash-cli
```

This installs from PyPI and only works after `ccdash-cli` and `ccdash-contracts` are
published.

Alternative:

```bash
pip install ccdash-cli
```

For local testing from a repo checkout before publish:

```bash
python3 -m venv .venv-standalone-cli
source .venv-standalone-cli/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install ./packages/ccdash_contracts ./packages/ccdash_cli
```

Verify the install:

```bash
ccdash --version
ccdash target show
```

## Quick Start

Use the implicit local target with a local server on `http://localhost:8000`:

```bash
ccdash status project
ccdash feature list
ccdash report feature FEAT-123
ccdash report aar --feature FEAT-123
```

Add and use a named remote target:

```bash
ccdash target add staging https://ccdash-staging.example.com --project my-project
ccdash target use staging
ccdash target show
ccdash target check staging
```

## Config And Auth

Configuration is stored in `~/.config/ccdash/config.toml` (or `$XDG_CONFIG_HOME/ccdash/config.toml`).

Target resolution order:

1. `--target <name>`
2. `CCDASH_TARGET`
3. `active_target` in config
4. Implicit `local` target at `http://localhost:8000`

Per-field overrides:

- `CCDASH_URL`
- `CCDASH_TOKEN`
- `CCDASH_PROJECT`

Authentication behavior:

- The CLI sends a bearer token only when one resolves from `CCDASH_TOKEN` or the OS keyring.
- `ccdash target login <name>` stores a token in the keyring under `target:<name>`.
- `ccdash target show` reports the resolved URL, project, auth state, and whether the target came from config or the implicit local fallback.
- `ccdash target check <name>` verifies reachability first, then confirms whether the server accepts the resolved credentials.
- The implicit local target is unauthenticated by default. Remote servers may still reject requests without a token, depending on server configuration.

## Troubleshooting

- `ccdash target show` to confirm the resolved target, project, and auth source.
- `ccdash doctor` to check live connectivity and inspect the reported server instance metadata.
- `ccdash target check <name>` when you need an explicit auth validation for a named target.
- If no keyring backend is available, set `CCDASH_TOKEN` instead of using `target login`.
- The CLI warns when a non-localhost target uses plain `http://`; prefer `https://` for remote targets.

## Smoke Check

These commands are the shortest end-to-end operator sanity check after install:

```bash
ccdash --version
ccdash target show
ccdash doctor
```
