"""Anthropic ``TextCompletionPort`` adapter -- Messages API HTTP client (M3).

Reaches either ICA (IBM's Anthropic-compatible gateway) or Anthropic direct
by ``base_url`` alone -- there is NO provider branching in this adapter
beyond the configured base URL, per the implementation plan's M3 AC
(``docs/project_plans/implementation_plans/features/
hosted-llm-anthropic-ica-lane-v1.md``). Wire-format facts below were
EMPIRICALLY SETTLED against the live ICA gateway on 2026-08-07 -- do not
re-probe, do not "improve" them:

  * Endpoint is always ``POST {base_url}/v1/messages``. ``base_url`` alone
    selects the provider: ICA is
    ``https://api.nextgen-beta.ica.ibm.com/ica``, Anthropic direct is
    ``https://api.anthropic.com``.
  * ``anthropic-version: 2023-06-01`` is sent UNCONDITIONALLY -- required by
    Anthropic direct, merely optional (ignored) on ICA.
  * The credential travels as the ``x-api-key`` request header. ICA also
    accepts ``Authorization: Bearer``, but Anthropic direct wants
    ``x-api-key``, so ``x-api-key`` is the one header that works on both --
    never in a URL, a log, or an exception message.
  * Model ids MUST be BARE (e.g. ``claude-haiku-4-5``,
    ``claude-sonnet-5``). A ``[1m]``-suffixed id (e.g.
    ``claude-haiku-4-5[1m]``) returns ``403 team_model_access_denied`` on
    ICA -- the suffix is a Claude-Code-layer delegation convention, not
    something either endpoint accepts. This adapter REJECTS a
    ``[1m]``-suffixed model id at construction time rather than silently
    stripping it -- see :meth:`AnthropicTextCompletionAdapter.__init__`'s
    docstring for the rationale.
  * The response is the standard Messages envelope
    (``content``/``id``/``model``/``role``/``stop_reason``/``type``/
    ``usage``). ICA is Bedrock-backed, so ids look like ``msg_bdrk_...`` --
    this adapter parses the envelope generically and never asserts on an id
    prefix.
  * ICA silently ignores unknown top-level request fields (200 OK) where
    Anthropic direct returns 400 for the same request -- so ICA is NOT a
    validation lane. This adapter sends only fields the Messages API
    actually defines (``model``, ``max_tokens``, ``messages``); a typo here
    would pass on ICA and break on the paid Anthropic-direct lane.

hosted-llm-anthropic-ica-lane-v1 M2: this is an EGRESS adapter, matching
``GeminiTextCompletionAdapter``'s own marker convention
(``backend/adapters/llm/gemini.py``) -- ``EGRESS = True`` is the explicit,
checkable marker other modules (e.g. a per-project consent gate) use to tell
this apart from a local-loopback adapter (``OllamaTextCompletionAdapter``,
``EGRESS = False``) without inspecting behaviour or guessing from the class
name.
"""
from __future__ import annotations

import logging

import httpx

from backend.application.ports.llm import PromptEnvelope, enforce_egress_provenance

__all__ = ["AnthropicTextCompletionAdapter"]

logger = logging.getLogger("ccdash.adapters.llm.anthropic")

DEFAULT_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 1024
_MODEL_ID_SUFFIX_MARKER = "[1m]"


class AnthropicTextCompletionAdapter:
    """``TextCompletionPort`` adapter for the Anthropic Messages API.

    Serves BOTH the ICA lane and Anthropic direct -- the only thing that
    differs between them is ``base_url``, supplied by the caller. See the
    module docstring for the empirically-settled wire-format facts this
    class encodes.
    """

    EGRESS: bool = True

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        timeout_seconds: float,
        base_url: str = DEFAULT_BASE_URL,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        """Construct the adapter.

        ``model`` MUST be a bare model id (e.g. ``claude-haiku-4-5``,
        ``claude-sonnet-5``) -- NEVER a ``[1m]``-suffixed id such as
        ``claude-haiku-4-5[1m]``. This adapter's design call is to REJECT a
        suffixed id (raise ``ValueError``) rather than silently stripping
        the suffix and continuing:

        The ``[1m]`` suffix is a Claude-Code-layer delegation convention
        used elsewhere in this codebase's operating environment (ICA
        offload via ``ica-claude.sh``/``ica-settings.json``) -- it is NOT a
        raw-API convention, and a request bearing it 403s
        (``team_model_access_denied``) against the live gateway. A
        suffixed id reaching THIS constructor therefore most likely means a
        caller copy-pasted a Claude-Code-facing model string into the
        raw-HTTP config surface (``CCDASH_LLM_ANTHROPIC_MODEL`` or
        equivalent) by mistake -- exactly the class of caller/config error
        every other gate in this feature is written to surface loudly
        rather than silently correct (``enforce_egress_provenance`` raises
        on a wrong-provenance envelope rather than dropping it;
        ``envelope_from_redacted_transcript`` raises rather than sending
        unredacted text). Silently stripping the suffix here would risk
        the adapter sending a DIFFERENT model than the one an operator
        actually configured, with no signal that a correction happened, and
        would let a config-surface bug ride quietly until the next
        provider-side rename makes the (accidentally-correct) stripped id
        wrong too. Raising at construction time -- before any egress
        attempt -- fails fast and points straight at the offending config
        value.

        ``api_key`` may be ``None``/empty -- :meth:`complete` degrades to a
        no-op (returns ``None``, no network call attempted) rather than
        sending a request that can only 401; see :meth:`complete`.
        """
        if _MODEL_ID_SUFFIX_MARKER in model:
            raise ValueError(
                "AnthropicTextCompletionAdapter: refusing to construct with "
                f"a '{_MODEL_ID_SUFFIX_MARKER}'-suffixed model id "
                f"({model!r}) -- that suffix is a Claude-Code-layer "
                "delegation convention, not something the Anthropic "
                "Messages API (direct or ICA) accepts on the wire; ICA "
                "returns 403 team_model_access_denied for a suffixed id. "
                "Pass the bare model id instead (e.g. 'claude-haiku-4-5')."
            )
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._base_url = base_url
        self._max_tokens = max_tokens

    async def complete(self, envelope: PromptEnvelope) -> str | None:
        """POST ``envelope.text`` to the Anthropic Messages API; return the raw completion.

        Degrades to ``None`` (no network call attempted) when no credential
        is configured -- this adapter's own instance of this feature's
        general "missing API key ... return ``None`` ... never a crash"
        fail-open contract (see
        ``backend/services/session_naming_hosted_backend.py``'s module
        docstring for the Gemini lane's version of the same contract). The
        check lives HERE, at the adapter, rather than only in a caller-side
        wrapper: unlike the Gemini lane (whose sole caller,
        ``HostedGeminiNamingBackend``, already re-checks the key before
        calling ``complete``), this adapter has no such caller-owned
        precondition guaranteed yet, so the degrade-on-missing-key
        guarantee has to be structural at this layer to hold regardless of
        who calls it.

        Raises on any OTHER transport/HTTP error (including
        ``httpx.HTTPStatusError``) for a reachable-but-erroring provider --
        same division of labour as
        ``GeminiTextCompletionAdapter``/``OllamaTextCompletionAdapter``: the
        caller owns the fail-open wrapping for those.
        """
        # Provenance gate FIRST, before any URL/payload construction or
        # connection -- mirrors ``GeminiTextCompletionAdapter.complete``
        # exactly; see ``enforce_egress_provenance``'s own docstring for why
        # this must be the very first thing an egress adapter does.
        enforce_egress_provenance(envelope)

        if not self._api_key:
            logger.debug(
                "anthropic adapter: no API key configured -- degrading to a "
                "no-op rather than attempting a network call that could "
                "only fail authentication."
            )
            return None

        url = f"{self._base_url}/v1/messages"
        headers = {
            "anthropic-version": ANTHROPIC_VERSION,
            "x-api-key": self._api_key,
        }
        # Only fields the Messages API actually defines -- ICA's 200-on-
        # unknown-field behaviour means a typo here would pass on ICA and
        # only break on the paid Anthropic-direct lane (see module
        # docstring). Do not add fields speculatively.
        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": envelope.text}],
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Log the status code only -- never
                # ``exc.response.text``/``.content``/a parsed body, which
                # may echo the request (including the credential-bearing
                # header) or provider-side diagnostic detail back into the
                # log stream.
                logger.warning(
                    "anthropic adapter: provider returned a non-2xx "
                    "response (status=%s)",
                    exc.response.status_code,
                )
                raise
            except httpx.HTTPError:
                logger.warning("anthropic adapter: transport error calling provider")
                raise
            data = resp.json()

        # Parse the Messages envelope generically -- ICA is Bedrock-backed
        # (``msg_bdrk_...`` ids), so this never asserts on an id prefix or
        # any provider-specific shape beyond the documented ``content``
        # array of blocks.
        content = data.get("content") if isinstance(data, dict) else None
        if not isinstance(content, list) or not content:
            return None
        first_block = content[0]
        text = first_block.get("text") if isinstance(first_block, dict) else None
        return str(text) if text else None
