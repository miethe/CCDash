"""fix/runtime-root-logging — root logger configuration.

Covers the observability defect: no code path in this repo ever called
``logging.basicConfig`` (or otherwise attached a handler to the root
logger), so every ``ccdash.*`` INFO/DEBUG record was silently dropped in
every runtime profile (only Python's WARNING-level ``lastResort`` handler
ever fired).

These tests drive ``backend.runtime.container._configure_root_logging``
directly -- NOT ``RuntimeContainer.startup()``, which touches the DB and
hangs under this repo's unscoped test collection (see other worker-bootstrap
test modules' own warnings against calling ``startup()`` directly).

Run as a NAMED file (this repo's unscoped pytest collection hangs)::

    backend/.venv/bin/python -m pytest \\
        backend/tests/test_root_logging_configuration.py -v
"""
from __future__ import annotations

import io
import logging
import unittest
from unittest.mock import patch

from backend import config
from backend.runtime.container import _configure_root_logging


class _RootLoggerIsolationMixin:
    """Snapshot and restore root logger state around each test.

    ``_configure_root_logging`` mutates process-global state (the root
    logger's handlers and level), so tests must not leak that mutation into
    each other or into the rest of the suite.
    """

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        self._root_logger = logging.getLogger()
        self._saved_handlers = list(self._root_logger.handlers)
        self._saved_level = self._root_logger.level
        # Start every test from a clean slate (no handlers) so the
        # "already configured" idempotency tests can add their own handler
        # deterministically.
        self._root_logger.handlers = []

    def tearDown(self) -> None:
        self._root_logger.handlers = self._saved_handlers
        self._root_logger.setLevel(self._saved_level)
        super().tearDown()  # type: ignore[misc]


class ConfiguresRootLoggerTests(_RootLoggerIsolationMixin, unittest.TestCase):
    """An INFO record through a ``ccdash.*`` logger is actually handled."""

    def test_info_record_is_handled_after_configuration(self) -> None:
        _configure_root_logging()

        stream = io.StringIO()
        capture_handler = logging.StreamHandler(stream)
        logging.getLogger().addHandler(capture_handler)
        try:
            logger = logging.getLogger("ccdash.test_root_logging")
            logger.info("hello from ccdash INFO record")
        finally:
            logging.getLogger().removeHandler(capture_handler)

        self.assertIn("hello from ccdash INFO record", stream.getvalue())

    def test_root_logger_gets_at_least_one_handler(self) -> None:
        self.assertEqual(len(logging.getLogger().handlers), 0)

        _configure_root_logging()

        self.assertGreaterEqual(len(logging.getLogger().handlers), 1)

    def test_default_level_is_info(self) -> None:
        with patch.object(config, "CCDASH_LOG_LEVEL", "INFO"):
            _configure_root_logging()

        self.assertEqual(logging.getLogger().level, logging.INFO)

    def test_level_is_overridable_via_config(self) -> None:
        with patch.object(config, "CCDASH_LOG_LEVEL", "DEBUG"):
            _configure_root_logging()

        self.assertEqual(logging.getLogger().level, logging.DEBUG)

    def test_unrecognised_level_falls_back_to_info(self) -> None:
        with patch.object(config, "CCDASH_LOG_LEVEL", "NOT_A_REAL_LEVEL"):
            _configure_root_logging()

        self.assertEqual(logging.getLogger().level, logging.INFO)


class IdempotencyTests(_RootLoggerIsolationMixin, unittest.TestCase):
    """Repeat calls (e.g. ``startup()`` running more than once in a
    process, as it does under tests) must not duplicate handlers.
    """

    def test_calling_twice_does_not_duplicate_handlers(self) -> None:
        _configure_root_logging()
        first_count = len(logging.getLogger().handlers)
        self.assertGreaterEqual(first_count, 1)

        _configure_root_logging()
        second_count = len(logging.getLogger().handlers)

        self.assertEqual(first_count, second_count)


class RespectsExistingHandlersTests(_RootLoggerIsolationMixin, unittest.TestCase):
    """Pre-existing root handlers (uvicorn, pytest's ``caplog``, or any
    other embedding application) must be respected, not replaced.
    """

    def test_preexisting_handler_is_not_replaced_or_duplicated(self) -> None:
        sentinel_handler = logging.StreamHandler()
        logging.getLogger().addHandler(sentinel_handler)

        _configure_root_logging()

        handlers = logging.getLogger().handlers
        self.assertEqual(len(handlers), 1)
        self.assertIs(handlers[0], sentinel_handler)

    def test_preexisting_handler_level_is_not_overridden(self) -> None:
        logging.getLogger().addHandler(logging.StreamHandler())
        logging.getLogger().setLevel(logging.ERROR)

        with patch.object(config, "CCDASH_LOG_LEVEL", "DEBUG"):
            _configure_root_logging()

        # _configure_root_logging must bail out entirely when a handler is
        # already present -- it must not even touch the level.
        self.assertEqual(logging.getLogger().level, logging.ERROR)


if __name__ == "__main__":
    unittest.main()
