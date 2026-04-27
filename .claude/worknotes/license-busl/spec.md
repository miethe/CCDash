# Spec: Add BUSL-1.1 License to CCDash

## Goal

Add a Business Source License 1.1 (BUSL-1.1) to the CCDash repo with a 2-year conversion to Apache 2.0. Preserve the sole copyright holder's freedom to relicense in the future.

## Context

- Repo: `/Users/miethe/dev/homelab/development/CCDash`
- Currently has **no LICENSE file** and no `license` field in `package.json`.
- Sole copyright holder: **Nick Miethe** (no outside contributors yet).
- Project is a local-first dashboard for orchestrating AI agent sessions. Primary commercial risk to protect against: someone wrapping CCDash as a paid hosted/managed SaaS.

## Decisions (already made — do not re-litigate)

| Parameter | Value |
|---|---|
| License | Business Source License 1.1 (BUSL-1.1), official template verbatim |
| Licensor | Nick Miethe |
| Licensed Work | CCDash (and the version, e.g. current `package.json` version) |
| Change Date | **2028-04-27** (2 years from 2026-04-27) |
| Change License | Apache License, Version 2.0 |
| Additional Use Grant | MariaDB-style: any use permitted **except** offering the Licensed Work, or a substantially similar derivative, as a hosted or managed service to third parties. Internal company use, individual use, modification, and self-hosting for the user's own purposes are all allowed. |

## Deliverables

1. **`LICENSE`** at repo root
   - Use the official BUSL-1.1 template from <https://mariadb.com/bsl11/> (or the spdx text). Do not paraphrase the body.
   - Fill in the four parameters above (Licensor, Licensed Work, Additional Use Grant, Change Date, Change License).
   - Include the standard "Notice" block at the bottom, as in the template.
   - Add a copyright header above the template:
     ```
     Copyright (c) 2026 Nick Miethe. All rights reserved.
     ```

2. **`package.json`** — add `"license": "BUSL-1.1"` field. (BUSL-1.1 is a valid SPDX identifier.)

3. **Backend `pyproject.toml` / setup files** — if any Python package metadata declares a license, set it to `BUSL-1.1` (SPDX). Check:
   - `packages/ccdash_cli/pyproject.toml`
   - `packages/ccdash_contracts/pyproject.toml`
   - `backend/pyproject.toml` (if present)
   - Root `pyproject.toml` (if present)

4. **`README.md`** — append a short "License" section near the bottom:
   - One-line summary: "CCDash is licensed under the Business Source License 1.1. It converts to Apache 2.0 on 2028-04-27. See [LICENSE](./LICENSE)."
   - One-line on the use grant: "You may use, modify, and self-host CCDash freely. You may not offer it as a hosted or managed service to third parties before the Change Date."
   - Do not editorialize beyond that.

5. **`CONTRIBUTING.md`** — if it exists, append (or create a brief one with) a DCO note:
   - "Contributions to CCDash require a `Signed-off-by:` line in each commit, indicating agreement to the [Developer Certificate of Origin](https://developercertificate.org/). Use `git commit -s` to add it automatically."
   - Rationale (not in the file, just for the agent): the DCO preserves the maintainer's ability to relicense in the future without per-contributor permission.

## Non-goals

- Do **not** add a CLA, CLA bot, or any GitHub Actions workflow for license enforcement.
- Do **not** add SPDX headers to source files.
- Do **not** modify the existing `CHANGELOG.md` format or add a license entry there (the next `/release:bump` will surface it).
- Do **not** change any code behavior.

## Verification

- `LICENSE` file present at repo root, contains literal BUSL-1.1 template text with correct parameters.
- `grep -r "BUSL-1.1"` shows it referenced in `package.json`, README, and any Python project metadata files that declare a license.
- `git diff` shows only documentation/metadata changes, no source code changes.

## Notes for the implementing agent

- The official BUSL-1.1 template lives at <https://mariadb.com/bsl11/>. The body is fixed; only the four parameter lines (Licensor, Licensed Work, Additional Use Grant, Change Date, Change License) are filled in. The "Notice" block at the bottom is also part of the template — keep it.
- BUSL-1.1's SPDX identifier is `BUSL-1.1`.
- Today's date for the copyright year is 2026.
- If `package.json` already has a `"license"` field set to something else (e.g. `"UNLICENSED"`), replace it. If it has none, add it.
