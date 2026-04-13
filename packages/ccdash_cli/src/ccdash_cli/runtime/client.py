"""HTTP client for the standalone CCDash CLI.

All CLI commands use this module to communicate with a running CCDash server
via the versioned REST API at /api/v1/.  The client is intentionally
synchronous (httpx.Client) because Typer commands are sync functions.

Exit code contract (mirrors the design spec):
    1 — General / server / not-found errors
    2 — HTTP 401 authentication failure
    3 — HTTP 403 permission denied
    4 — Network / connection failure
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ccdash_contracts.envelopes import ClientV1ErrorEnvelope
from ccdash_contracts.models import InstanceMetaDTO

__all__ = [
    # Exceptions
    "CCDashClientError",
    "AuthenticationError",
    "PermissionError",
    "ConnectionError",
    "ServerError",
    "NotFoundError",
    # Client
    "CCDashClient",
]

_LOG = logging.getLogger(__name__)

_CLI_USER_AGENT = "ccdash-cli/0.1.0"

# HTTP status codes that are safe to retry (transient server-side conditions).
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({502, 503, 504})
_DEFAULT_RETRIES = 2
_DEFAULT_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class CCDashClientError(Exception):
    """Base exception for all CCDash HTTP client errors.

    Attributes:
        exit_code: Process exit code the CLI layer should use.
        message:   Human-readable description suitable for stderr output.
    """

    exit_code: int = 1

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if exit_code is not None:
            self.exit_code = exit_code


class AuthenticationError(CCDashClientError):
    """Raised when the server returns HTTP 401.

    Indicates missing or invalid bearer token.
    """

    exit_code = 2


class PermissionError(CCDashClientError):
    """Raised when the server returns HTTP 403.

    Indicates valid credentials but insufficient access rights.
    """

    exit_code = 3


class ConnectionError(CCDashClientError):
    """Raised when the client cannot reach the server at all.

    Covers TCP-level failures and request timeouts.
    """

    exit_code = 4


class ServerError(CCDashClientError):
    """Raised for HTTP 5xx responses or error-status envelope payloads."""

    exit_code = 1


class NotFoundError(CCDashClientError):
    """Raised when the server returns HTTP 404."""

    exit_code = 1


# ---------------------------------------------------------------------------
# Retry transport
# ---------------------------------------------------------------------------


class _RetryTransport(httpx.HTTPTransport):
    """Minimal retry transport that re-attempts on transient status codes.

    httpx's built-in ``retries`` kwarg on HTTPTransport only retries on
    connection errors, not on HTTP 5xx responses.  This subclass adds a thin
    layer on top that re-sends the request when the response carries one of
    the retryable status codes.

    Args:
        retries: Maximum number of *additional* attempts after the first.
        **kwargs: Forwarded verbatim to :class:`httpx.HTTPTransport`.
    """

    def __init__(self, *, retries: int = _DEFAULT_RETRIES, **kwargs: Any) -> None:
        # Pass retries to the parent so connection-level errors are also
        # covered, then remember the value for our own response-level logic.
        super().__init__(retries=retries, **kwargs)
        self._max_retries = retries

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        last_response: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = super().handle_request(request)
            except (httpx.ConnectError, httpx.TimeoutException):
                # Let the caller handle connection-level failures.
                raise

            if response.status_code not in _RETRYABLE_STATUS_CODES:
                return response

            last_response = response
            if attempt < self._max_retries:
                _LOG.debug(
                    "Retrying request (attempt %d/%d) after %d response",
                    attempt + 1,
                    self._max_retries,
                    response.status_code,
                )

        # All retries exhausted — return the last bad response for mapping.
        assert last_response is not None
        return last_response


# ---------------------------------------------------------------------------
# CCDashClient
# ---------------------------------------------------------------------------


class CCDashClient:
    """Synchronous HTTP client for the CCDash server API.

    All paths passed to :meth:`get` and :meth:`post` should be rooted at
    ``/api/v1/``, e.g. ``/api/v1/instance``.  The *base_url* must NOT include
    that prefix.

    Args:
        base_url: Origin of the CCDash server, e.g. ``http://localhost:8000``.
        token:    Optional bearer token sent as ``Authorization: Bearer …``.
        timeout:  Per-request timeout in seconds (default 30 s).

    Example::

        client = CCDashClient("http://localhost:8000", token=None)
        data = client.get("/api/v1/project/status")
    """

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")

        headers: dict[str, str] = {"User-Agent": _CLI_USER_AGENT}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        self._client = httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=timeout,
            transport=_RetryTransport(retries=_DEFAULT_RETRIES),
            follow_redirects=True,
        )

    # ------------------------------------------------------------------
    # Public transport methods
    # ------------------------------------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform a GET request and return the parsed JSON response body.

        Args:
            path:   URL path relative to *base_url*, e.g. ``/api/v1/instance``.
            params: Optional query-string parameters.

        Returns:
            The full parsed JSON dict (envelope included).

        Raises:
            CCDashClientError: On any HTTP or network error.
        """
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform a POST request and return the parsed JSON response body.

        Args:
            path:      URL path relative to *base_url*.
            params:    Optional query-string parameters.
            json_body: Optional JSON-serialisable request body.

        Returns:
            The full parsed JSON dict (envelope included).

        Raises:
            CCDashClientError: On any HTTP or network error.
        """
        return self._request("POST", path, params=params, json_body=json_body)

    # ------------------------------------------------------------------
    # Higher-level helpers
    # ------------------------------------------------------------------

    def get_instance(self) -> InstanceMetaDTO:
        """Fetch ``/api/v1/instance`` and return a parsed :class:`InstanceMetaDTO`.

        Returns:
            Parsed server instance metadata.

        Raises:
            CCDashClientError: On any HTTP or network error.
        """
        body = self.get("/api/v1/instance")
        data = body.get("data", {})
        return InstanceMetaDTO.model_validate(data)

    def check_health(self) -> bool:
        """Return ``True`` if the server is reachable and reports a healthy status.

        The check is intentionally lenient: any non-error HTTP response from
        ``/api/v1/instance`` is treated as healthy.  Connection failures
        return ``False`` rather than raising.
        """
        try:
            self.get_instance()
            return True
        except ConnectionError:
            return False
        except CCDashClientError:
            # Server is reachable but returned an error envelope — still up.
            return True

    def close(self) -> None:
        """Close the underlying :class:`httpx.Client` and release resources."""
        self._client.close()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "CCDashClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an HTTP request and return the parsed JSON body.

        Handles all retry, status-code mapping, and envelope error extraction
        in one place so that :meth:`get` and :meth:`post` stay thin.
        """
        url = path if path.startswith("/") else f"/{path}"

        try:
            response = self._client.request(
                method,
                url,
                params=params,
                json=json_body,
            )
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Cannot connect to CCDash server at {self._base_url}: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ConnectionError(
                f"Request to {self._base_url}{url} timed out: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ConnectionError(
                f"Unexpected network error communicating with {self._base_url}: {exc}"
            ) from exc

        _LOG.debug("%s %s → %d", method, url, response.status_code)

        self._raise_for_status(response, url)
        return self._parse_body(response, url)

    @staticmethod
    def _raise_for_status(response: httpx.Response, url: str) -> None:
        """Map HTTP error status codes to :class:`CCDashClientError` subclasses.

        Args:
            response: The raw httpx response.
            url:      The path used in the request (for error messages).

        Raises:
            AuthenticationError: On HTTP 401.
            PermissionError:     On HTTP 403.
            NotFoundError:       On HTTP 404.
            ServerError:         On HTTP 5xx.
        """
        status = response.status_code
        if status == 401:
            raise AuthenticationError(
                "Authentication failed: check your bearer token (HTTP 401)"
            )
        if status == 403:
            raise PermissionError(
                f"Permission denied accessing {url} (HTTP 403)"
            )
        if status == 404:
            raise NotFoundError(f"Resource not found: {url} (HTTP 404)")
        if status >= 500:
            raise ServerError(
                f"Server error {status} from {url}: {response.text[:200]}"
            )

    @staticmethod
    def _parse_body(response: httpx.Response, url: str) -> dict[str, Any]:
        """Parse the JSON response and surface envelope-level errors.

        The CCDash API always returns a JSON envelope.  If the ``status``
        field equals ``"error"``, the error details are extracted and a
        :class:`ServerError` is raised even when the HTTP status was 2xx.

        Args:
            response: The raw httpx response (HTTP status already checked).
            url:      The request path (used in error messages).

        Returns:
            The full parsed response dict.

        Raises:
            ServerError: When the envelope ``status`` is ``"error"``.
            ServerError: When the response body is not valid JSON.
        """
        try:
            body: dict[str, Any] = response.json()
        except Exception as exc:
            raise ServerError(
                f"Invalid JSON response from {url}: {exc}; "
                f"body={response.text[:200]!r}"
            ) from exc

        if body.get("status") == "error":
            try:
                envelope = ClientV1ErrorEnvelope.model_validate(body)
                err = envelope.error
                message = (
                    f"[{err.code}] {err.message}" if err.code else err.message
                ) or f"Server returned an error response for {url}"
            except Exception:
                message = f"Server returned an error response for {url}"
            raise ServerError(message)

        return body
