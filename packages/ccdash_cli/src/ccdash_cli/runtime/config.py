"""TOML-based target configuration store for the CCDash standalone CLI.

Config file location: ~/.config/ccdash/config.toml (respects $XDG_CONFIG_HOME).

Target resolution order (highest to lowest priority):
  1. --target <name>   CLI flag
  2. CCDASH_TARGET     Environment variable (target name)
  3. active_target     Value from config.toml [defaults]
  4. "local"           Implicit default (http://localhost:8000, no auth)

Per-field env var overrides applied after target resolution:
  CCDASH_URL      -> url
  CCDASH_TOKEN    -> token (bypasses keyring entirely)
  CCDASH_PROJECT  -> project
"""

from __future__ import annotations

import dataclasses
import logging
import os
import stat
import warnings
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-reuse-imports]

import tomli_w

logger = logging.getLogger(__name__)

_IMPLICIT_LOCAL_URL = "http://localhost:8000"
_DEFAULT_TARGET_NAME = "local"
_KEYRING_SERVICE = "ccdash"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class TargetConfig:
    """Resolved, ready-to-use representation of a CCDash target.

    Instances are produced by :func:`resolve_target` and should be treated as
    immutable after construction.  All optional fields default to ``None``
    rather than sentinel strings so callers can use simple truthiness checks.
    """

    name: str
    url: str
    token: str | None = None
    project: str | None = None
    is_implicit_local: bool = False  # True when using the fallback default


# ---------------------------------------------------------------------------
# Config store
# ---------------------------------------------------------------------------


class ConfigStore:
    """Manages reading and writing the CCDash TOML configuration file.

    Parameters
    ----------
    config_path:
        Explicit path to the TOML file.  When *None* the XDG-compliant
        default path is used (``~/.config/ccdash/config.toml``).
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._path: Path = config_path or self.default_config_path()

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    @staticmethod
    def default_config_path() -> Path:
        """Return the XDG-compliant config file path.

        Respects ``$XDG_CONFIG_HOME``; falls back to ``~/.config``.
        """
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        if xdg:
            base = Path(xdg)
        else:
            base = Path.home() / ".config"
        return base / "ccdash" / "config.toml"

    @property
    def path(self) -> Path:
        """The resolved path to the config file."""
        return self._path

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load(self) -> dict[str, Any]:
        """Load and return the parsed TOML config.

        Returns an empty dict when the file is missing or unreadable rather
        than raising an exception — a missing config is not an error.
        """
        if not self._path.exists():
            return {}
        try:
            with self._path.open("rb") as fh:
                return tomllib.load(fh)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read config file %s: %s", self._path, exc)
            return {}

    def save(self, config: dict[str, Any]) -> None:
        """Persist *config* to the TOML file.

        Creates the parent directory (mode ``0o700``) and writes the file
        with mode ``0o600``.  Emits a warning if the file ends up
        world-readable on Unix (e.g. because of a restrictive umask override).
        """
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

        content = tomli_w.dumps(config).encode()
        # Write via a low-level open so we can set the initial mode atomically.
        fd = os.open(
            self._path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            os.write(fd, content)
        finally:
            os.close(fd)

        self._warn_if_world_readable()

    def _warn_if_world_readable(self) -> None:
        """Emit a warning when the config file is world-readable on POSIX."""
        if os.name == "nt":
            return
        try:
            mode = self._path.stat().st_mode
            if mode & stat.S_IROTH:
                warnings.warn(
                    f"Config file {self._path} is world-readable. "
                    "Run: chmod 600 {self._path}",
                    stacklevel=3,
                )
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Target accessors
    # ------------------------------------------------------------------

    def list_targets(self) -> dict[str, dict[str, Any]]:
        """Return all target records keyed by target name."""
        config = self.load()
        return dict(config.get("targets", {}))

    def get_target(self, name: str) -> dict[str, Any] | None:
        """Return the raw record for *name*, or ``None`` if it does not exist."""
        return self.list_targets().get(name)

    def add_target(
        self,
        name: str,
        url: str,
        token_ref: str | None = None,
        project: str | None = None,
    ) -> None:
        """Add or fully replace a named target.

        Existing targets are overwritten; only the explicitly supplied fields
        are stored (``None`` values are omitted from the TOML record).
        """
        config = self.load()
        config.setdefault("targets", {})
        record: dict[str, Any] = {"url": url}
        if token_ref is not None:
            record["token_ref"] = token_ref
        if project is not None:
            record["project"] = project
        config["targets"][name] = record
        self.save(config)

    def remove_target(self, name: str) -> bool:
        """Remove *name* from the config.

        Returns ``True`` if the target existed and was removed, ``False`` if
        it was not found.  If the removed target was the active one the
        ``active_target`` key is also cleared.
        """
        config = self.load()
        targets: dict[str, Any] = config.get("targets", {})
        if name not in targets:
            return False
        del targets[name]
        config["targets"] = targets
        # Clear the active_target pointer if it pointed at the removed target.
        defaults = config.get("defaults", {})
        if defaults.get("active_target") == name:
            del defaults["active_target"]
            config["defaults"] = defaults
        self.save(config)
        return True

    # ------------------------------------------------------------------
    # Active target
    # ------------------------------------------------------------------

    def get_active_target_name(self) -> str:
        """Return the configured active target name, or ``'local'`` as default."""
        config = self.load()
        return config.get("defaults", {}).get("active_target", _DEFAULT_TARGET_NAME)

    def set_active_target(self, name: str) -> None:
        """Persist *name* as the active target in ``[defaults]``."""
        config = self.load()
        config.setdefault("defaults", {})["active_target"] = name
        self.save(config)


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def _resolve_token(token_ref: str | None) -> str | None:
    """Resolve the bearer token for the active target.

    Priority:
    1. ``CCDASH_TOKEN`` environment variable — used directly, keyring skipped.
    2. ``keyring.get_password("ccdash", token_ref)`` — if *token_ref* is set.
    3. ``None`` — no auth token available.

    ``keyring.errors.NoKeyringError`` is caught and logged as a warning;
    callers should treat the resulting ``None`` as "unauthenticated".
    """
    env_token = os.environ.get("CCDASH_TOKEN")
    if env_token:
        return env_token

    if not token_ref:
        return None

    try:
        import keyring  # lazy import — avoids hard failure if backend absent
        import keyring.errors

        try:
            value = keyring.get_password(_KEYRING_SERVICE, token_ref)
        except keyring.errors.NoKeyringError:
            warnings.warn(
                f"No keyring backend available; cannot retrieve token for ref "
                f"'{token_ref}'. Set CCDASH_TOKEN to authenticate.",
                stacklevel=3,
            )
            return None
        return value  # may be None if not stored
    except ImportError:
        logger.debug("keyring package not installed; token resolution skipped.")
        return None


def set_token(token_ref: str, token_value: str) -> None:
    """Store *token_value* in the OS keyring under *token_ref*.

    Raises ``RuntimeError`` when no keyring backend is available.
    """
    try:
        import keyring
        import keyring.errors

        try:
            keyring.set_password(_KEYRING_SERVICE, token_ref, token_value)
        except keyring.errors.NoKeyringError as exc:
            raise RuntimeError(
                "No keyring backend is available on this system. "
                "Install a suitable backend (e.g. `pip install keyrings.alt`) "
                "or supply CCDASH_TOKEN via the environment."
            ) from exc
    except ImportError as exc:
        raise RuntimeError(
            "The 'keyring' package is not installed. "
            "Install it with: pip install keyring"
        ) from exc


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------


def resolve_target(
    *,
    target_flag: str | None = None,
    config_store: ConfigStore | None = None,
) -> TargetConfig:
    """Resolve the active :class:`TargetConfig` following the priority chain.

    Resolution steps
    ----------------
    1. ``target_flag`` (``--target`` CLI argument).
    2. ``CCDASH_TARGET`` environment variable.
    3. ``active_target`` stored in ``config.toml`` ``[defaults]``.
    4. ``"local"`` implicit default (``http://localhost:8000``, no auth).

    After the target *name* is determined, the corresponding record is looked
    up in the config file.  For the ``"local"`` name, a missing record is
    silently replaced by the implicit default values.

    Per-field env var overrides are applied last:

    - ``CCDASH_URL``     overrides the resolved URL.
    - ``CCDASH_TOKEN``   provides the token directly (keyring is not consulted).
    - ``CCDASH_PROJECT`` overrides the resolved project slug.

    Parameters
    ----------
    target_flag:
        The value of the ``--target`` CLI option, or ``None`` if not provided.
    config_store:
        A :class:`ConfigStore` instance.  A default one is created when
        *None* — callers that already hold a store should pass it in to
        avoid double-loading the config file.

    Raises
    ------
    SystemExit
        When *target_flag* names a target that does not exist in the config
        file (exit code 1).
    """
    store = config_store or ConfigStore()

    # --- Step 1: determine target name ---
    is_implicit_local = False
    if target_flag:
        target_name = target_flag
    elif (env_target := os.environ.get("CCDASH_TARGET")):
        target_name = env_target
    else:
        target_name = store.get_active_target_name()
        # get_active_target_name already returns "local" as fallback, so we
        # detect the implicit case by checking whether the config truly had
        # an entry.
        if target_name == _DEFAULT_TARGET_NAME:
            config = store.load()
            if not config.get("defaults", {}).get("active_target"):
                is_implicit_local = True

    # --- Step 2: look up the target record ---
    record = store.get_target(target_name)

    if record is None:
        if target_flag:
            # Explicit --target for a non-existent name is a hard error.
            import sys
            print(
                f"error: target '{target_name}' not found in config. "
                f"Add it with: ccdash target add {target_name} <url>",
                file=sys.stderr,
            )
            sys.exit(1)

        if target_name == _DEFAULT_TARGET_NAME:
            # Implicit local fallback — synthesise a minimal record.
            record = {"url": _IMPLICIT_LOCAL_URL}
            is_implicit_local = True
        else:
            # Named target from env/config but not present in file — treat as
            # implicit local with a warning so the user is alerted.
            warnings.warn(
                f"Target '{target_name}' referenced but not found in config; "
                f"falling back to implicit local default.",
                stacklevel=2,
            )
            record = {"url": _IMPLICIT_LOCAL_URL}
            is_implicit_local = True

    # --- Step 3: extract base fields from record ---
    url: str = record.get("url", _IMPLICIT_LOCAL_URL)
    token_ref: str | None = record.get("token_ref")
    project: str | None = record.get("project")

    # --- Step 4: resolve token (env > keyring) ---
    token = _resolve_token(token_ref)

    # --- Step 5: apply per-field env var overrides ---
    if (env_url := os.environ.get("CCDASH_URL")):
        url = env_url
    # CCDASH_TOKEN is already applied inside _resolve_token; if it was set the
    # token is already correct.  We still check here to handle the edge case
    # where token_ref was absent but CCDASH_TOKEN is set.
    if token is None:
        env_token = os.environ.get("CCDASH_TOKEN")
        if env_token:
            token = env_token
    if (env_project := os.environ.get("CCDASH_PROJECT")):
        project = env_project

    # Normalise URL: strip trailing slash for consistency.
    url = url.rstrip("/")

    return TargetConfig(
        name=target_name,
        url=url,
        token=token,
        project=project,
        is_implicit_local=is_implicit_local,
    )
