"""Run db4_verify.py (the DI-4e AC2 / D-b4 family-split gate) without putting the
node-Postgres DSN into a shell variable or a file.

Sources CCDASH_DATABASE_URL out of the repo .env into CCDASH_DSN, then execs
db4_verify.py. The DSN is never printed. Read-only: one SELECT, no writes.

Usage:
    backend/.venv/bin/python .claude/worknotes/di-4e-routing-success-rate/run_db4_verify.py
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
target = pathlib.Path(__file__).with_name("db4_verify.py")
sys.argv = [str(target)] + sys.argv[1:]
runpy.run_path(str(target), run_name="__main__")
