"""Repository tests for the three provider dimension tables (M1-002).

``provider_dimensions`` / ``provider_channels`` / ``provider_credentials``
(``provider-channel-credential-entities-v1`` M1, SCHEMA_VERSION 52; DDL in
``backend/db/sqlite_migrations.py``'s ``_PROVIDER_DIMENSION_TABLES`` block).

Covers:
1. ADR-007 direct-count assertion for every write path (write, then a fresh
   ``SELECT COUNT(*)`` -- never trust the method's own return value) plus
   idempotency (same upsert twice -> exactly one row, second call updates).
2. The secret-shaped-value guard on ``credential_name``: every documented
   reject shape raises ``ValueError`` and writes nothing; legitimate short
   names pass and persist.
3. Unknown ``channel`` tokens never raise and round-trip unchanged.

Run as a named module (unscoped collection can hang this repo):
    backend/.venv/bin/python -m pytest backend/tests/test_provider_dimensions_repo.py -q -p no:cacheprovider
"""
from __future__ import annotations

import unittest

import aiosqlite

from backend.db.repositories.provider_dimensions import (
    SqliteProviderDimensionsRepository,
    _reject_if_secret_shaped,
)
from backend.db.sqlite_migrations import run_migrations


class _RepoTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        # Independent SQLite connection MUST issue PRAGMA busy_timeout = 30000.
        await self.db.execute("PRAGMA busy_timeout = 30000")
        await run_migrations(self.db)
        self.repo = SqliteProviderDimensionsRepository(self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()

    async def _count(self, table: str) -> int:
        cursor = await self.db.execute(f"SELECT COUNT(*) FROM {table}")
        (count,) = await cursor.fetchone()
        return int(count)


# ── provider_dimensions ──────────────────────────────────────────────────


class ProviderDimensionsDirectCountTests(_RepoTestBase):
    async def test_upsert_writes_row_and_direct_count_matches(self) -> None:
        self.assertEqual(await self._count("provider_dimensions"), 0)
        await self.repo.upsert_provider_dimension(
            provider_id="anthropic:claude-code:subscription",
            provider_vendor="Anthropic",
            provider_surface="Claude Code",
            provider_channel="subscription",
            provider_label="Anthropic · Claude Code",
        )
        self.assertEqual(await self._count("provider_dimensions"), 1)

    async def test_upsert_is_idempotent_and_updates_in_place(self) -> None:
        await self.repo.upsert_provider_dimension(
            provider_id="anthropic:claude-code:ica",
            provider_vendor="Anthropic",
            provider_surface="Claude Code",
            provider_channel="ica",
            provider_label="Anthropic · Claude Code · ICA",
        )
        first = await self.repo.get_provider_dimension("anthropic:claude-code:ica")
        assert first is not None

        # Second call with a changed label -- same key, must update not duplicate.
        await self.repo.upsert_provider_dimension(
            provider_id="anthropic:claude-code:ica",
            provider_vendor="Anthropic",
            provider_surface="Claude Code",
            provider_channel="ica",
            provider_label="Anthropic · Claude Code · ICA (updated)",
        )
        self.assertEqual(await self._count("provider_dimensions"), 1)

        second = await self.repo.get_provider_dimension("anthropic:claude-code:ica")
        assert second is not None
        self.assertEqual(second["provider_label"], "Anthropic · Claude Code · ICA (updated)")
        # first_seen_at must be preserved across the update.
        self.assertEqual(first["first_seen_at"], second["first_seen_at"])

    async def test_list_provider_dimensions_returns_all_rows(self) -> None:
        await self.repo.upsert_provider_dimension(provider_id="a:b:c")
        await self.repo.upsert_provider_dimension(provider_id="d:e:f")
        rows = await self.repo.list_provider_dimensions()
        self.assertEqual(len(rows), 2)
        self.assertEqual(await self._count("provider_dimensions"), 2)


# ── provider_channels ─────────────────────────────────────────────────────


class ProviderChannelsDirectCountTests(_RepoTestBase):
    async def test_upsert_writes_row_and_direct_count_matches(self) -> None:
        self.assertEqual(await self._count("provider_channels"), 0)
        await self.repo.upsert_provider_channel(channel="subscription", label="Subscription")
        self.assertEqual(await self._count("provider_channels"), 1)

    async def test_upsert_is_idempotent(self) -> None:
        await self.repo.upsert_provider_channel(channel="api", label="API")
        await self.repo.upsert_provider_channel(channel="api", label="API (relabeled)")
        self.assertEqual(await self._count("provider_channels"), 1)
        row = await self.repo.get_provider_channel("api")
        assert row is not None
        self.assertEqual(row["label"], "API (relabeled)")

    async def test_unknown_channel_token_never_raises_and_round_trips(self) -> None:
        """An unrecognised channel value must store and read back fine (no closed vocab)."""
        weird_channel = "totally-unrecognized-future-channel-v9"
        await self.repo.upsert_provider_channel(channel=weird_channel, label="")
        row = await self.repo.get_provider_channel(weird_channel)
        assert row is not None
        self.assertEqual(row["channel"], weird_channel)
        self.assertEqual(await self._count("provider_channels"), 1)


# ── provider_credentials: direct-count + idempotency ─────────────────────


class ProviderCredentialsDirectCountTests(_RepoTestBase):
    async def test_upsert_writes_row_and_direct_count_matches(self) -> None:
        self.assertEqual(await self._count("provider_credentials"), 0)
        await self.repo.upsert_provider_credential(
            channel="ica", credential_name="CC1", provider_id="anthropic:claude-code:ica"
        )
        self.assertEqual(await self._count("provider_credentials"), 1)

    async def test_upsert_is_idempotent_and_updates_in_place(self) -> None:
        await self.repo.upsert_provider_credential(
            channel="ica", credential_name="CC1", provider_id="anthropic:claude-code:ica"
        )
        first = await self.repo.get_provider_credential("ica", "CC1")
        assert first is not None

        await self.repo.upsert_provider_credential(
            channel="ica", credential_name="CC1", provider_id="anthropic:claude-code:ica-v2"
        )
        self.assertEqual(await self._count("provider_credentials"), 1)
        second = await self.repo.get_provider_credential("ica", "CC1")
        assert second is not None
        self.assertEqual(second["provider_id"], "anthropic:claude-code:ica-v2")
        self.assertEqual(first["first_seen_at"], second["first_seen_at"])

    async def test_same_credential_name_different_channel_is_a_distinct_row(self) -> None:
        """Key is (channel, credential_name) -- same name under two channels is two rows."""
        await self.repo.upsert_provider_credential(channel="ica", credential_name="CC1")
        await self.repo.upsert_provider_credential(channel="api", credential_name="CC1")
        self.assertEqual(await self._count("provider_credentials"), 2)

    async def test_rotated_from_id_is_never_set_by_upsert(self) -> None:
        await self.repo.upsert_provider_credential(channel="ica", credential_name="CC1")
        row = await self.repo.get_provider_credential("ica", "CC1")
        assert row is not None
        self.assertIsNone(row["rotated_from_id"])
        self.assertIsNone(row["rotation_declared_at"])
        self.assertIsNone(row["rotation_declared_by"])

    async def test_list_provider_credentials_returns_all_rows(self) -> None:
        await self.repo.upsert_provider_credential(channel="ica", credential_name="CC1")
        await self.repo.upsert_provider_credential(channel="ica", credential_name="CC2")
        rows = await self.repo.list_provider_credentials()
        self.assertEqual(len(rows), 2)
        self.assertEqual(await self._count("provider_credentials"), 2)


# ── secret-shaped-value guard ──────────────────────────────────────────────


class SecretGuardUnitTests(unittest.TestCase):
    """Direct unit coverage of the guard function, independent of the DB."""

    def test_legitimate_names_pass(self) -> None:
        for name in ("CC1", "CC6", "prod-api-key-name", "team-seat-3"):
            # Must not raise.
            _reject_if_secret_shaped(name, field="credential_name")

    def test_rejects_anthropic_api_key_shape(self) -> None:
        with self.assertRaises(ValueError):
            _reject_if_secret_shaped("sk-ant-api03-" + ("x" * 40), field="credential_name")

    def test_rejects_openai_style_key_shape(self) -> None:
        with self.assertRaises(ValueError):
            _reject_if_secret_shaped("sk-" + ("a" * 48), field="credential_name")

    def test_rejects_github_pat_shape(self) -> None:
        with self.assertRaises(ValueError):
            _reject_if_secret_shaped("ghp_" + ("A1b2C3" * 6), field="credential_name")

    def test_rejects_slack_bot_token_shape(self) -> None:
        with self.assertRaises(ValueError):
            _reject_if_secret_shaped("xoxb-" + "1234567890-1234567890-" + "abcdefghijklmnop", field="credential_name")

    def test_rejects_bare_jwt_shape(self) -> None:
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ_abcdefghijklmnop"
        with self.assertRaises(ValueError):
            _reject_if_secret_shaped(jwt, field="credential_name")

    def test_rejects_over_length_value(self) -> None:
        with self.assertRaises(ValueError):
            _reject_if_secret_shaped("a" * 129, field="credential_name")

    def test_rejects_high_entropy_hex_run(self) -> None:
        with self.assertRaises(ValueError):
            _reject_if_secret_shaped("a1b2c3d4e5f60718293a4b5c6d7e8f90" * 1, field="credential_name")

    def test_rejects_high_entropy_base64_run(self) -> None:
        with self.assertRaises(ValueError):
            _reject_if_secret_shaped("QWxhZGRpbjpvcGVuIHNlc2FtZS1hbmQtbW9yZQ", field="credential_name")


class ProviderCredentialUpsertGuardTests(_RepoTestBase):
    """The guard must run BEFORE any write; a rejected call writes nothing."""

    async def test_secret_shaped_credential_name_raises_and_writes_nothing(self) -> None:
        with self.assertRaises(ValueError):
            await self.repo.upsert_provider_credential(
                channel="ica", credential_name="sk-ant-api03-" + ("x" * 40)
            )
        self.assertEqual(await self._count("provider_credentials"), 0)

    async def test_legitimate_name_persists_via_upsert(self) -> None:
        await self.repo.upsert_provider_credential(channel="ica", credential_name="team-seat-3")
        row = await self.repo.get_provider_credential("ica", "team-seat-3")
        assert row is not None
        self.assertEqual(row["credential_name"], "team-seat-3")


# ── secret material must never appear in the raised message (regression lock) ──


class SecretNeverInErrorMessageTests(unittest.TestCase):
    """Locks in the fix for the coordinator-reported defect: a ValueError raised by the
    guard must never echo the offending value, a prefix/suffix of it, a partial
    redaction, or a hash -- only the field name, the matched rule CLASS, and length.

    This repo has an adjacent open defect for credentials leaking into
    logs/error bodies (IntentTree node_01KZEXSPEKDRCSY3FGEVZPEWMV); this test
    exists specifically so a future refactor cannot silently regress it here.
    """

    # A distinctive sentinel embedded in every test secret below -- if this
    # substring (or any long substring of the full secret) ever appears in a
    # raised message, the test fails.
    _SENTINEL = "SUPERSECRETVALUE123"

    def _assert_message_leaks_nothing(self, secret_value: str) -> None:
        with self.assertRaises(ValueError) as ctx:
            _reject_if_secret_shaped(secret_value, field="credential_name")
        message = str(ctx.exception)
        self.assertNotIn(self._SENTINEL, message)
        self.assertNotIn(secret_value, message)
        # No long substring (>4 chars) of the raw secret should survive into
        # the message either -- guards against partial-redaction leaks like
        # "sk-ant-...123".
        for start in range(0, len(secret_value) - 4):
            fragment = secret_value[start : start + 5]
            self.assertNotIn(
                fragment, message,
                msg=f"message leaked a fragment of the secret: {fragment!r}",
            )

    def test_secret_prefix_shape_message_leaks_nothing(self) -> None:
        self._assert_message_leaks_nothing("sk-ant-api03-" + self._SENTINEL)

    def test_high_entropy_shape_message_leaks_nothing(self) -> None:
        self._assert_message_leaks_nothing("a1b2c3d4e5f6" + self._SENTINEL + "789xyz")

    def test_over_length_shape_message_leaks_nothing(self) -> None:
        self._assert_message_leaks_nothing(self._SENTINEL * 10)

    def test_jwt_shape_message_leaks_nothing(self) -> None:
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0." + self._SENTINEL
        self._assert_message_leaks_nothing(jwt)

    def test_message_matches_target_shape_field_and_rule_only(self) -> None:
        """Sanity check on the positive contract: field name and rule class ARE
        present (that's the useful, non-leaking part of the message)."""
        with self.assertRaises(ValueError) as ctx:
            _reject_if_secret_shaped("sk-ant-api03-" + self._SENTINEL, field="credential_name")
        message = str(ctx.exception)
        self.assertIn("credential_name", message)
        self.assertIn("secret-prefix", message)
        self.assertIn("length", message)


class ProviderCredentialUpsertGuardMessageLeakTests(_RepoTestBase):
    """Same leak-lock, but through the full repository call path (channel +
    credential_name), not just the bare guard function."""

    async def test_repository_rejection_message_leaks_nothing(self) -> None:
        secret = "sk-ant-api03-SUPERSECRETVALUE123"
        with self.assertRaises(ValueError) as ctx:
            await self.repo.upsert_provider_credential(channel="ica", credential_name=secret)
        message = str(ctx.exception)
        self.assertNotIn("SUPERSECRETVALUE123", message)
        self.assertNotIn(secret, message)
        self.assertEqual(await self._count("provider_credentials"), 0)


# ── Fix 1 (guard-broadening): realistic legitimate values across every field ──


class RealisticLegitimateValuesAcceptedTests(_RepoTestBase):
    """Every field the broadened guard now covers must still accept every
    realistic real-world value it is documented to carry -- a slug
    ("anthropic:claude-code:ica"), a short vendor/surface/channel token
    ("Anthropic", "Claude Code", "subscription"), or a "vendor · surface"
    display string ("Anthropic · Claude Code · ICA"). This is the
    verification the task required before broadening the guard: run every
    legitimate shape through every write path and assert acceptance.
    """

    async def test_all_provider_dimension_fields_accept_realistic_values(self) -> None:
        await self.repo.upsert_provider_dimension(
            provider_id="anthropic:claude-code:ica",
            provider_vendor="Anthropic",
            provider_surface="Claude Code",
            provider_channel="ica",
            provider_label="Anthropic · Claude Code · ICA",
        )
        row = await self.repo.get_provider_dimension("anthropic:claude-code:ica")
        assert row is not None
        self.assertEqual(row["provider_vendor"], "Anthropic")
        self.assertEqual(row["provider_surface"], "Claude Code")
        self.assertEqual(row["provider_label"], "Anthropic · Claude Code · ICA")
        self.assertEqual(await self._count("provider_dimensions"), 1)

    async def test_all_provider_dimension_vendor_shapes_accepted(self) -> None:
        """The full closed vendor/surface enum derive_provider_identity emits."""
        for vendor, surface, channel in (
            ("Anthropic", "Claude Code", "subscription"),
            ("OpenAI", "Codex", "api"),
            ("Google", "Unknown", "unknown"),
            ("Unknown", "Unknown", "unknown"),
        ):
            provider_id = f"{vendor.lower()}:{surface.lower().replace(' ', '-')}:{channel}"
            await self.repo.upsert_provider_dimension(
                provider_id=provider_id,
                provider_vendor=vendor,
                provider_surface=surface,
                provider_channel=channel,
                provider_label=f"{vendor} · {surface}",
            )
        self.assertEqual(await self._count("provider_dimensions"), 4)

    async def test_provider_channel_label_accepts_realistic_values(self) -> None:
        await self.repo.upsert_provider_channel(channel="ica", label="ICA")
        await self.repo.upsert_provider_channel(channel="subscription", label="Subscription")
        await self.repo.upsert_provider_channel(channel="api", label="API")
        self.assertEqual(await self._count("provider_channels"), 3)

    async def test_provider_credential_fields_accept_realistic_values(self) -> None:
        for channel, credential_name, provider_id in (
            ("ica", "CC1", "anthropic:claude-code:ica"),
            ("ica", "CC6", "anthropic:claude-code:ica"),
            ("api", "prod-api-key-name", "anthropic:claude-code:api"),
            ("subscription", "team-seat-3", "anthropic:claude-code:subscription"),
        ):
            await self.repo.upsert_provider_credential(
                channel=channel, credential_name=credential_name, provider_id=provider_id
            )
        self.assertEqual(await self._count("provider_credentials"), 4)

    async def test_unrecognized_future_channel_slug_still_accepted(self) -> None:
        """Regression lock for the false-reject found while broadening this
        guard: a long/hyphenated future channel token must NOT be rejected --
        ``channel`` and ``provider_channel`` ARE guarded (like every other
        field), but the narrowed ``_HIGH_ENTROPY_RUN_PATTERN`` (excludes ``-``
        and ``_`` from the run alphabet -- see the module docstring) means a
        hyphenated slug no longer reads as one unbroken high-entropy run.

        This also covers the compound case a prior version of this test
        explicitly could NOT cover: ``provider_id`` embeds the channel
        segment (``derive_provider_identity`` builds it as
        ``"{vendor}:{surface}:{channel}"``), so a *derived* ``provider_id``
        containing the same long hyphenated channel token must also be
        accepted now -- the hyphens inside that embedded segment no longer
        contribute to any run either.
        """
        long_channel = "vertex-ai-workbench-preview-2027-rollout"
        await self.repo.upsert_provider_dimension(
            provider_id="google:unknown:" + long_channel,
            provider_channel=long_channel,
        )
        await self.repo.upsert_provider_channel(channel=long_channel)
        await self.repo.upsert_provider_credential(channel=long_channel, credential_name="CC1")
        self.assertEqual(await self._count("provider_dimensions"), 1)
        self.assertEqual(await self._count("provider_channels"), 1)
        self.assertEqual(await self._count("provider_credentials"), 1)


# ── Fix 1: per-field rejection + direct-count-zero proof ────────────────────


class ProviderDimensionFieldGuardTests(_RepoTestBase):
    """Every newly-guarded field on ``upsert_provider_dimension`` rejects a
    secret-shaped value and writes nothing (ADR-007 direct-count proof)."""

    _SECRET = "sk-ant-api03-" + ("x" * 40)

    async def test_secret_shaped_provider_id_raises_and_writes_nothing(self) -> None:
        with self.assertRaises(ValueError):
            await self.repo.upsert_provider_dimension(provider_id=self._SECRET)
        self.assertEqual(await self._count("provider_dimensions"), 0)

    async def test_secret_shaped_provider_vendor_raises_and_writes_nothing(self) -> None:
        with self.assertRaises(ValueError):
            await self.repo.upsert_provider_dimension(
                provider_id="anthropic:claude-code:ica", provider_vendor=self._SECRET
            )
        self.assertEqual(await self._count("provider_dimensions"), 0)

    async def test_secret_shaped_provider_surface_raises_and_writes_nothing(self) -> None:
        with self.assertRaises(ValueError):
            await self.repo.upsert_provider_dimension(
                provider_id="anthropic:claude-code:ica", provider_surface=self._SECRET
            )
        self.assertEqual(await self._count("provider_dimensions"), 0)

    async def test_secret_shaped_provider_label_raises_and_writes_nothing(self) -> None:
        with self.assertRaises(ValueError):
            await self.repo.upsert_provider_dimension(
                provider_id="anthropic:claude-code:ica", provider_label=self._SECRET
            )
        self.assertEqual(await self._count("provider_dimensions"), 0)

    async def test_secret_shaped_provider_channel_raises_and_writes_nothing(self) -> None:
        """provider_channel IS guarded (like every other field) since the
        entropy-alphabet narrowing -- a secret-shaped value here raises and
        writes nothing, same as every other guarded field."""
        with self.assertRaises(ValueError):
            await self.repo.upsert_provider_dimension(
                provider_id="anthropic:claude-code:x", provider_channel=self._SECRET
            )
        self.assertEqual(await self._count("provider_dimensions"), 0)


class ProviderChannelFieldGuardTests(_RepoTestBase):
    """``upsert_provider_channel``'s ``channel`` and ``label`` fields both
    reject secret-shaped values (channel is guarded like every other field
    since the entropy-alphabet narrowing -- see the module docstring)."""

    _SECRET = "ghp_" + ("A1b2C3" * 6)

    async def test_secret_shaped_label_raises_and_writes_nothing(self) -> None:
        with self.assertRaises(ValueError):
            await self.repo.upsert_provider_channel(channel="ica", label=self._SECRET)
        self.assertEqual(await self._count("provider_channels"), 0)

    async def test_secret_shaped_channel_raises_and_writes_nothing(self) -> None:
        with self.assertRaises(ValueError):
            await self.repo.upsert_provider_channel(channel=self._SECRET)
        self.assertEqual(await self._count("provider_channels"), 0)


class ProviderCredentialFieldGuardTests(_RepoTestBase):
    """``upsert_provider_credential``'s ``provider_id`` and ``channel`` fields
    reject secret-shaped values too (``credential_name`` already covered
    above)."""

    _SECRET = "xoxb-" + "1234567890-1234567890-" + "abcdefghijklmnop"

    async def test_secret_shaped_provider_id_raises_and_writes_nothing(self) -> None:
        with self.assertRaises(ValueError):
            await self.repo.upsert_provider_credential(
                channel="ica", credential_name="CC1", provider_id=self._SECRET
            )
        self.assertEqual(await self._count("provider_credentials"), 0)

    async def test_secret_shaped_channel_raises_and_writes_nothing(self) -> None:
        with self.assertRaises(ValueError):
            await self.repo.upsert_provider_credential(
                channel=self._SECRET, credential_name="CC1"
            )
        self.assertEqual(await self._count("provider_credentials"), 0)


# ── Coordinator-directed fix: narrowed high-entropy-run alphabet ────────────


class NarrowedEntropyAlphabetTests(unittest.TestCase):
    """Direct unit coverage of the coordinator-directed resolution: ``-`` and
    ``_`` are separators, not entropy characters, in
    ``_HIGH_ENTROPY_RUN_PATTERN``. This is the regression lock the module
    docstring's "why -/_ are excluded" section points at -- if a future edit
    widens the alphabet back to include them, this suite fails loudly.
    """

    def test_long_hyphenated_slug_is_accepted(self) -> None:
        """The exact false-reject this fix resolves: must NOT raise."""
        _reject_if_secret_shaped(
            "totally-unrecognized-future-channel-v9", field="channel"
        )
        _reject_if_secret_shaped(
            "vertex-ai-workbench-preview-2027-rollout", field="channel"
        )

    def test_32_char_contiguous_alphanumeric_run_is_still_rejected(self) -> None:
        """A future widening of the alphabet back to include -/_ (or any
        other regression that stops treating them as separators) must fail
        THIS test loudly: a 32-char run with no separators at all is exactly
        the shape the guard exists to catch, hyphen-narrowing notwithstanding."""
        with self.assertRaises(ValueError):
            _reject_if_secret_shaped("a" * 32, field="channel")
        with self.assertRaises(ValueError):
            _reject_if_secret_shaped("Ab3" * 11, field="channel")  # 33 chars, mixed case

    def test_hyphen_or_underscore_breaks_an_otherwise_qualifying_run(self) -> None:
        """32 contiguous alnum chars rejects; inserting one separator at the
        midpoint (splitting it into two <32-char halves) must not."""
        unbroken = "a" * 32
        with self.assertRaises(ValueError):
            _reject_if_secret_shaped(unbroken, field="channel")
        # Not a raise -- inserting a hyphen breaks the run into two 16-char halves.
        _reject_if_secret_shaped(unbroken[:16] + "-" + unbroken[16:], field="channel")
        _reject_if_secret_shaped(unbroken[:16] + "_" + unbroken[16:], field="channel")

    def test_documented_secret_shapes_still_all_caught(self) -> None:
        """Every secret shape this guard is documented to catch must still be
        caught after narrowing -- most via their own prefix/JWT/over-length
        rule (independent of the entropy alphabet), and the two bare
        high-entropy cases via an unbroken >=32-char alnum run that survives
        narrowing on its own merits."""
        secrets = (
            "sk-ant-api03-" + "x" * 40,
            "sk-" + "a" * 48,
            "ghp_" + ("A1b2C3" * 6),
            "gho_" + ("A1b2C3" * 6),
            "github_pat_" + ("A1b2C3" * 8),
            "xoxb-" + "1234567890-1234567890-" + "abcdefghijklmnop",
            "AIza" + "A" * 35,
            "AKIA" + "A" * 16,
            (
                "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
                "dQw4w9WgXcQ_abcdefghijklmnop"
            ),
            "a" * 129,
            "a1b2c3d4e5f60718293a4b5c6d7e8f90",  # bare 32-char hex run
            "QWxhZGRpbjpvcGVuIHNlc2FtZS1hbmQtbW9yZQ",  # bare base64 run
            "deadbeefcafebabedeadbeefcafebabe",  # bare 32-char hex run
            "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmE=",  # bare base64 run
        )
        for secret in secrets:
            with self.assertRaises(ValueError, msg=f"expected reject for {secret!r}"):
                _reject_if_secret_shaped(secret, field="channel")

    def test_documented_legitimate_shapes_all_still_accepted(self) -> None:
        """Every legitimate value shape any guarded field carries must still
        pass, across the full realistic vocabulary (short tokens, slugs,
        display labels, and now long hyphenated channel tokens too)."""
        legitimate = (
            "totally-unrecognized-future-channel-v9",
            "vertex-ai-workbench-preview-2027-rollout",
            "subscription", "ica", "api", "unknown",
            "anthropic:claude-code:subscription",
            "anthropic:claude-code:vertex-ai-workbench-preview-2027-rollout",
            "Anthropic", "Claude Code", "Anthropic · Claude Code · ICA",
            "CC1", "CC6", "prod-api-key-name", "team-seat-3",
        )
        for value in legitimate:
            # Must not raise.
            _reject_if_secret_shaped(value, field="channel")


if __name__ == "__main__":
    unittest.main()
