"""Contract test: ``GET /api/sessions`` must expose an explicit ``project_id`` param.

Why this exists
---------------
Cross-project reads previously had to go through the ``x-ccdash-project-id``
header, which is explicitly deprecated as a routing/selection mechanism (see
``backend/adapters/auth/dependency.py``). Without a first-class query parameter,
an unscoped ``GET /api/sessions`` silently returns only the *active* project's
sessions -- which reads exactly like "every session is attributed to the active
project" when you are inspecting a multi-project instance. That misreading sent a
prior investigation down the wrong path entirely.

This parameter was also lost once already: it was added in one commit, then
clobbered by a whole-file copy in a follow-up commit on the same branch, and the
loss was invisible because nothing asserted the signature. Hence a signature-level
test rather than a behavioural one -- it fails fast on deletion, with no DB, no
app boot, and no network.
"""
from __future__ import annotations

import inspect

from backend.routers.api import list_sessions


def test_list_sessions_accepts_project_id_kwarg() -> None:
    """The parameter must exist by exact name (callers pass ?project_id=...)."""
    params = inspect.signature(list_sessions).parameters
    assert "project_id" in params, (
        "list_sessions lost its project_id query parameter; cross-project reads "
        "would silently fall back to the active project only."
    )


def test_project_id_is_optional_and_defaults_to_none() -> None:
    """Omitting it must preserve the existing active-project fallback."""
    param = inspect.signature(list_sessions).parameters["project_id"]
    assert param.annotation in (
        "str | None",
        "typing.Optional[str]",
    ) or "None" in str(param.annotation), (
        f"project_id should be optional; got annotation {param.annotation!r}"
    )
    # FastAPI wraps the default in a Query object; the underlying default is None.
    default = param.default
    underlying = getattr(default, "default", default)
    assert underlying is None, (
        f"project_id must default to None so unscoped calls keep working; got {underlying!r}"
    )


def test_project_id_is_threaded_into_project_resolution() -> None:
    """The param must actually reach resolve_project, not just sit in the signature.

    A parameter that is accepted and then ignored is worse than no parameter at
    all -- it looks like scoping works while silently returning the active
    project. Assert the wiring at the source level.
    """
    source = inspect.getsource(list_sessions)
    assert "requested_project_id=project_id" in source, (
        "project_id is declared but never passed to resolve_project(); the "
        "endpoint would accept the param and silently ignore it."
    )
