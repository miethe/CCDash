"""Tests for backend.model_identity.derive_provider_identity (additive provider identity).

Grounding: .claude/progress/quick-features/analytics-provider-views.md — provider is modelled
as three orthogonal axes (vendor/surface/channel), only vendor+surface are live in captured
data today; channel resolves to "unknown" for 100% of rows until launch-time capture is
activated. These tests assert the derivation rules, not the current population state.
"""
from __future__ import annotations

import unittest

from backend.model_identity import derive_provider_identity


class TestProviderVendor(unittest.TestCase):
    def test_claude_vendor_is_anthropic(self) -> None:
        result = derive_provider_identity("claude-opus-4-5-20251101")
        self.assertEqual(result["providerVendor"], "Anthropic")

    def test_gpt_vendor_is_openai(self) -> None:
        result = derive_provider_identity("gpt-5.6-terra")
        self.assertEqual(result["providerVendor"], "OpenAI")

    def test_gemini_vendor_is_google(self) -> None:
        result = derive_provider_identity("gemini-3.5-flash")
        self.assertEqual(result["providerVendor"], "Google")

    def test_unrecognized_model_is_unknown_vendor(self) -> None:
        result = derive_provider_identity("mistral-large")
        self.assertEqual(result["providerVendor"], "Unknown")

    def test_synthetic_model_is_unknown_vendor(self) -> None:
        result = derive_provider_identity("<synthetic>")
        self.assertEqual(result["providerVendor"], "Unknown")

    def test_empty_model_is_unknown_vendor(self) -> None:
        result = derive_provider_identity("")
        self.assertEqual(result["providerVendor"], "Unknown")

    def test_none_model_is_unknown_vendor(self) -> None:
        result = derive_provider_identity(None)
        self.assertEqual(result["providerVendor"], "Unknown")


class TestProviderSurface(unittest.TestCase):
    def test_claude_code_surface(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", platform_type="Claude Code")
        self.assertEqual(result["providerSurface"], "Claude Code")

    def test_codex_surface(self) -> None:
        result = derive_provider_identity("gpt-5.6-terra", platform_type="Codex")
        self.assertEqual(result["providerSurface"], "Codex")

    def test_case_insensitive_surface_normalization(self) -> None:
        result = derive_provider_identity("gpt-5.6-terra", platform_type="codex")
        self.assertEqual(result["providerSurface"], "Codex")

    def test_empty_platform_type_is_unknown_surface(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", platform_type="")
        self.assertEqual(result["providerSurface"], "Unknown")

    def test_none_platform_type_is_unknown_surface(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", platform_type=None)
        self.assertEqual(result["providerSurface"], "Unknown")


class TestProviderChannel(unittest.TestCase):
    def test_launcher_containing_ica_wins(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", launcher="ica-claude")
        self.assertEqual(result["providerChannel"], "ica")

    def test_launcher_containing_ica_case_insensitive(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", launcher="ICA-Gateway")
        self.assertEqual(result["providerChannel"], "ica")

    def test_launcher_containing_api_wins(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", launcher="direct-api-runner")
        self.assertEqual(result["providerChannel"], "api")

    def test_other_launcher_is_subscription(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", launcher="claude-code-cli")
        self.assertEqual(result["providerChannel"], "subscription")

    def test_launcher_authoritative_over_model_variant(self) -> None:
        # launcher says subscription even though model_variant looks ICA-flavored.
        result = derive_provider_identity(
            "claude-sonnet-5", launcher="claude-code-cli", model_variant="[1m]"
        )
        self.assertEqual(result["providerChannel"], "subscription")

    def test_model_variant_bracketed_1m_is_ica(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", model_variant="[1m]")
        self.assertEqual(result["providerChannel"], "ica")

    def test_model_variant_bare_1m_is_ica(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", model_variant="1m")
        self.assertEqual(result["providerChannel"], "ica")

    def test_model_variant_suffixed_1m_is_ica(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", model_variant="claude-sonnet-5[1m]")
        self.assertEqual(result["providerChannel"], "ica")

    def test_model_variant_without_1m_is_unknown(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", model_variant="standard")
        self.assertEqual(result["providerChannel"], "unknown")

    def test_no_launcher_no_variant_is_unknown(self) -> None:
        result = derive_provider_identity("claude-sonnet-5")
        self.assertEqual(result["providerChannel"], "unknown")

    def test_todays_all_empty_capture_columns_yield_unknown_channel(self) -> None:
        # Mirrors the live population state (0/N launcher, 0/N model_variant) documented
        # in the analytics-provider-views grounding finding.
        result = derive_provider_identity("claude-opus-4-5", platform_type="Claude Code", launcher="", model_variant="")
        self.assertEqual(result["providerChannel"], "unknown")


class TestProviderIdAndLabel(unittest.TestCase):
    def test_provider_id_is_slugified_triple(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", platform_type="Claude Code", launcher="claude-code-cli")
        self.assertEqual(result["providerId"], "anthropic:claude-code:subscription")

    def test_provider_id_unknown_triple(self) -> None:
        result = derive_provider_identity(None)
        self.assertEqual(result["providerId"], "unknown:unknown:unknown")

    def test_provider_label_no_suffix_for_subscription(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", platform_type="Claude Code", launcher="claude-code-cli")
        self.assertEqual(result["providerLabel"], "Anthropic · Claude Code")

    def test_provider_label_no_suffix_for_unknown_channel(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", platform_type="Claude Code")
        self.assertEqual(result["providerLabel"], "Anthropic · Claude Code")

    def test_provider_label_ica_suffix(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", platform_type="Claude Code", launcher="ica-claude")
        self.assertEqual(result["providerLabel"], "Anthropic · Claude Code · ICA")

    def test_provider_label_api_suffix(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", platform_type="Claude Code", launcher="api-runner")
        self.assertEqual(result["providerLabel"], "Anthropic · Claude Code · API")


class TestReturnShape(unittest.TestCase):
    def test_returns_exactly_five_keys(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", platform_type="Claude Code")
        self.assertEqual(
            set(result.keys()),
            {"providerVendor", "providerSurface", "providerChannel", "providerId", "providerLabel"},
        )

    def test_all_values_are_strings(self) -> None:
        result = derive_provider_identity("claude-sonnet-5", platform_type="Claude Code", launcher="ica")
        for value in result.values():
            self.assertIsInstance(value, str)


class TestCodexSlugs(unittest.TestCase):
    def test_codex_gpt_terra_full_identity(self) -> None:
        result = derive_provider_identity("gpt-5.6-terra", platform_type="Codex")
        self.assertEqual(result["providerVendor"], "OpenAI")
        self.assertEqual(result["providerSurface"], "Codex")
        self.assertEqual(result["providerChannel"], "unknown")
        self.assertEqual(result["providerId"], "openai:codex:unknown")
        self.assertEqual(result["providerLabel"], "OpenAI · Codex")


if __name__ == "__main__":
    unittest.main()
