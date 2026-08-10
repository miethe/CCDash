"""Local convenience runner: sources CCDASH_DATABASE_URL out of the repo .env into
CCDASH_DSN, then execs backfill_codex_tool_usage.py with whatever argv it was given.

The DSN is never printed. Not part of the deliverable — a throwaway so the operator
does not have to materialize a credential into a shell variable or a file.
"""
import os
import pathlib
import re
import runpy
import sys

MAIN = pathlib.Path("/Users/miethe/dev/homelab/development/CCDash")
PAT = re.compile(r"^CCDASH_DATABASE_URL=(\S+)", re.MULTILINE)

dsn = None
for name in (".env", ".env.hosted", ".env.local"):
    p = MAIN / name
    if not p.is_file():
        continue
    m = PAT.search(p.read_text(errors="replace"))
    if m:
        dsn = m.group(1).strip().strip("\"'")
        print(f"[dsn source: {name}]")
        break

if not dsn:
    raise SystemExit("no CCDASH_DATABASE_URL found in .env files")

os.environ["CCDASH_DSN"] = dsn
target = pathlib.Path(__file__).with_name("backfill_codex_tool_usage.py")
sys.argv = [str(target)] + sys.argv[1:]
runpy.run_path(str(target), run_name="__main__")
