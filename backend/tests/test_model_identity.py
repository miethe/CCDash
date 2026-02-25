import unittest

from backend.model_identity import (
    canonical_model_name,
    derive_model_identity,
    model_family_name,
    model_filter_tokens,
)


class ModelIdentityTests(unittest.TestCase):
    def test_derive_model_identity_for_claude(self) -> None:
        identity = derive_model_identity("claude-opus-4-5-20251101")
        self.assertEqual(identity["modelProvider"], "Claude")
        self.assertEqual(identity["modelFamily"], "Opus")
        self.assertEqual(identity["modelVersion"], "Opus 4.5")
        self.assertEqual(identity["modelDisplayName"], "Claude Opus 4.5")

    def test_model_filter_tokens_include_version_variants(self) -> None:
        tokens = model_filter_tokens("Opus 4.5")
        self.assertIn("opus", tokens)
        self.assertIn("4-5", tokens)

    def test_canonical_model_strips_trailing_date_suffixes(self) -> None:
        self.assertEqual(
            canonical_model_name("claude-opus-4-5-20251101"),
            "claude-opus-4-5",
        )
        self.assertEqual(
            canonical_model_name("gpt-5-mini-2026-01-15"),
            "gpt-5-mini",
        )

    def test_model_family_name_uses_family_token(self) -> None:
        self.assertEqual(model_family_name("claude-opus-4-5-20251101"), "Opus")
        self.assertEqual(model_family_name(""), "Unknown")


if __name__ == "__main__":
    unittest.main()
