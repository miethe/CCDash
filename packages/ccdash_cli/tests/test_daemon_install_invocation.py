"""Regression coverage for the daemon-install-emits-an-inert-invocation defect.

`packages/ccdash_cli/src/ccdash_cli/main.py` used to define a Typer `app`
without an `if __name__ == "__main__": app()` guard. That made
`python -m ccdash_cli.main <anything>` import the module, build the Typer
app, and exit 0 having run nothing — while the `ccdash-cli` console script
(`[project.scripts] ccdash-cli = "ccdash_cli.main:app"`) worked correctly.

The three `ccdash-cli daemon install` templates (launchd/systemd/schtasks)
all emit `<python> -m ccdash_cli.main daemon start` as the supervised
command, so the missing guard meant every platform's install template
produced a supervisor unit that starts, prints nothing, and exits 0 —
either a restart loop under `Restart=always` or a silently "successful"
unit under `Restart=on-failure`. Either way: zero ingest.

These tests assert AC3 directly: the emitted invocation, executed exactly
as printed (minus swapping the daemon subcommand for a harmless one), must
actually produce CLI output — not just exit 0. A test that only checked
`returncode == 0` would be worthless here, since that was already true
while doing nothing.

Extraction is done against the real template functions
(`_print_launchd_template`, `_print_systemd_template`,
`_print_schtasks_template`) rather than a hardcoded copy of the expected
string, so a future template regression (e.g. dropping the `-m` flag, or
pointing at the wrong module) is caught here rather than only in the
hardcoded literal.
"""
from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys

import pytest

from ccdash_cli.commands import daemon as daemon_module

# The subcommand every template supervises. Swapped out for `version` below
# so the subprocess check is harmless (no real daemon config required).
_SUPERVISED_SUBCOMMAND = ["daemon", "start"]


# ---------------------------------------------------------------------------
# Extraction helpers — pull the actual invoked argv out of each template's
# real output, rather than re-deriving an expected string by hand.
# ---------------------------------------------------------------------------


@pytest.fixture()
def capture_stdout(capsys: pytest.CaptureFixture[str]):
    def _run(fn) -> str:
        capsys.readouterr()  # clear anything buffered so far
        fn()
        return capsys.readouterr().out

    return _run


def _extract_launchd_argv(template_text: str) -> list[str]:
    match = re.search(
        r"<key>ProgramArguments</key>\s*<array>(.*?)</array>", template_text, re.DOTALL
    )
    assert match, f"ProgramArguments array not found in launchd template:\n{template_text}"
    return re.findall(r"<string>(.*?)</string>", match.group(1))


def _extract_systemd_argv(template_text: str) -> list[str]:
    match = re.search(r"^ExecStart=(.+)$", template_text, re.MULTILINE)
    assert match, f"ExecStart line not found in systemd template:\n{template_text}"
    return match.group(1).split()


def _extract_schtasks_argv(template_text: str) -> list[str]:
    match = re.search(r'/tr\s+"(.*?)"\s*\^', template_text)
    assert match, f"/tr argument not found in schtasks template:\n{template_text}"
    raw = match.group(1).replace('\\"', '"')
    return shlex.split(raw)


_TEMPLATE_CASES = [
    ("launchd", daemon_module._print_launchd_template, _extract_launchd_argv),
    ("systemd", daemon_module._print_systemd_template, _extract_systemd_argv),
    ("schtasks", daemon_module._print_schtasks_template, _extract_schtasks_argv),
]


@pytest.mark.parametrize("name,print_fn,extract", _TEMPLATE_CASES, ids=[c[0] for c in _TEMPLATE_CASES])
def test_template_supervises_the_module_invocation(
    name: str, print_fn, extract, capture_stdout
) -> None:
    """Each template's supervised command must invoke `<python> -m ccdash_cli.main`.

    Extracted from the real template output (not a hardcoded literal), so a
    future edit that drops the `-m` flag or points at the wrong module fails
    this test rather than only surfacing at runtime.
    """
    text = capture_stdout(print_fn)
    argv = extract(text)

    assert argv, f"{name}: extracted an empty argv from:\n{text}"
    assert argv[0] == sys.executable, (
        f"{name}: expected the interpreter running this process "
        f"({sys.executable!r}) as argv[0], got {argv[0]!r}"
    )
    assert "-m" in argv, f"{name}: no '-m' flag in extracted argv {argv!r}"
    m_index = argv.index("-m")
    assert argv[m_index + 1] == "ccdash_cli.main", (
        f"{name}: expected module 'ccdash_cli.main' after '-m', "
        f"got {argv[m_index + 1]!r} in {argv!r}"
    )
    assert argv[-2:] == _SUPERVISED_SUBCOMMAND, (
        f"{name}: expected the supervised command to end with "
        f"{_SUPERVISED_SUBCOMMAND!r}, got {argv[-2:]!r} in full argv {argv!r}"
    )


@pytest.mark.parametrize("name,print_fn,extract", _TEMPLATE_CASES, ids=[c[0] for c in _TEMPLATE_CASES])
def test_template_invocation_actually_runs_the_cli(
    name: str, print_fn, extract, capture_stdout
) -> None:
    """AC3: executing the emitted invocation must produce CLI output, not a
    silent `exit 0`.

    Swaps the supervised `daemon start` subcommand for the harmless
    `version` subcommand (so no daemon config is required) but otherwise
    runs exactly the argv the template printed, as a real subprocess.

    Before the `if __name__ == "__main__": app()` fix, this assertion
    failed: the process exited 0 but produced zero bytes of stdout, because
    `python -m ccdash_cli.main` only defined the Typer app without ever
    calling it.
    """
    text = capture_stdout(print_fn)
    argv = extract(text)
    assert argv[-2:] == _SUPERVISED_SUBCOMMAND, f"{name}: unexpected argv {argv!r}"

    harmless_argv = argv[:-2] + ["version"]

    result = subprocess.run(
        harmless_argv,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"{name}: {harmless_argv!r} exited {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    # The whole point of AC3: rc==0 alone proved nothing before the fix
    # (the inert module also exited 0). Non-empty, content-bearing stdout
    # is the actual signal that the CLI ran.
    assert result.stdout.strip(), (
        f"{name}: {harmless_argv!r} produced NO stdout (rc=0) — this is "
        "exactly the silent-no-op failure mode this test exists to catch.\n"
        f"stderr={result.stderr!r}"
    )
    assert "ccdash-cli" in result.stdout, (
        f"{name}: {harmless_argv!r} stdout did not contain 'ccdash-cli': "
        f"{result.stdout!r}"
    )


def test_module_form_and_console_script_agree_on_version() -> None:
    """Two-sided check (AC1): `python -m ccdash_cli.main version` and the
    `ccdash-cli` console script must produce identical output.

    Before the fix, the `-m` form produced no output at all while the
    console script worked — this test would have failed on that asymmetry.
    """
    module_result = subprocess.run(
        [sys.executable, "-m", "ccdash_cli.main", "version"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert module_result.returncode == 0, (
        f"`-m ccdash_cli.main version` exited {module_result.returncode}\n"
        f"stdout={module_result.stdout!r}\nstderr={module_result.stderr!r}"
    )
    assert module_result.stdout.strip(), (
        "`-m ccdash_cli.main version` produced no stdout — the inert-module "
        "regression this test exists to catch."
    )

    console_script = shutil.which("ccdash-cli")
    if console_script is None:
        pytest.skip("ccdash-cli console script not found on PATH")

    script_result = subprocess.run(
        [console_script, "version"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert script_result.returncode == 0, (
        f"`ccdash-cli version` exited {script_result.returncode}\n"
        f"stdout={script_result.stdout!r}\nstderr={script_result.stderr!r}"
    )

    assert module_result.stdout == script_result.stdout, (
        "`-m ccdash_cli.main version` and `ccdash-cli version` disagree:\n"
        f"module form:  {module_result.stdout!r}\n"
        f"console form: {script_result.stdout!r}"
    )
    assert "ccdash-cli" in module_result.stdout


def test_package_form_also_runs() -> None:
    """`python -m ccdash_cli` (the idiomatic package form) must also work,
    via the thin `__main__.py` re-export added alongside the main.py fix.
    """
    result = subprocess.run(
        [sys.executable, "-m", "ccdash_cli", "version"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"`-m ccdash_cli version` exited {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert result.stdout.strip(), "`-m ccdash_cli version` produced no stdout"
    assert "ccdash-cli" in result.stdout
