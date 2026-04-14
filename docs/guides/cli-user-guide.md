# CLI User Guide (Repo-Local)

This guide covers the repo-local CCDash CLI entry point installed from the backend's editable Python package.

> **Looking for the standalone CLI?** For the globally installable CLI that works from any terminal, see [`standalone-cli-guide.md`](standalone-cli-guide.md). For migration guidance, see [`cli-migration-guide.md`](cli-migration-guide.md).

## Setup

Prerequisites:

- Python 3.10+
- `npm run setup` completed successfully
- A resolved CCDash project in the local data store

`npm run setup` creates `backend/.venv` and installs the `ccdash` entry point in editable mode. On Windows, use `backend\\.venv\\Scripts\\ccdash.exe`; on Unix-like shells, use `backend/.venv/bin/ccdash`.

Verify the install with:

```bash
backend/.venv/bin/ccdash --help
```

## Commands

CCDash ships four CLI commands:

- `ccdash status project` shows the current project summary.
- `ccdash feature report <feature-id>` shows feature forensics for one feature.
- `ccdash workflow failures` shows the highest observed workflow failure burden.
- `ccdash report aar --feature <feature-id>` generates an after-action report.

## Global Flags

The root CLI accepts `--project <project-id>` to override the active project for the whole invocation. Use it when the default project is not the one you want:

```bash
backend/.venv/bin/ccdash --project my-project status project
backend/.venv/bin/ccdash --project my-project feature report FEAT-123
```

## Output Modes

Each command supports the same output modes:

- Human-readable output is the default.
- `--output json` or `--json` renders JSON.
- `--output markdown` or `--md` renders markdown.

Examples:

```bash
backend/.venv/bin/ccdash feature report FEAT-123 --json
backend/.venv/bin/ccdash workflow failures --output markdown
backend/.venv/bin/ccdash report aar --feature FEAT-123 --md
```

`--json` and `--md` are shortcuts for the same formatter selection. Do not combine them in the same invocation.

## Examples

```bash
backend/.venv/bin/ccdash status project
backend/.venv/bin/ccdash feature report FEAT-123 --json
backend/.venv/bin/ccdash workflow failures --md
backend/.venv/bin/ccdash report aar --feature FEAT-123
```

## Troubleshooting

- If the CLI says it cannot resolve a project, pass `--project <project-id>` or confirm the active CCDash project is configured.
- If you see `Choose only one of --json or --md.`, remove one of the two flags.
- If `ccdash` is not found, rerun `npm run setup` and make sure `backend/.venv/bin` is on your PATH or call the binary directly.

## Testing

Run the CLI smoke tests with:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_cli_commands.py -q
```

The test suite covers the four commands, project override handling, and output-mode conflicts.
