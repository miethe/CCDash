import unittest

from backend.model_identity import derive_model_identity, model_filter_tokens


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


if __name__ == "__main__":
    unittest.main()
