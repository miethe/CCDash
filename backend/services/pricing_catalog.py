"""Pricing catalog service for bundled defaults, overrides, and session cost derivation."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.model_identity import canonical_model_name
from backend.services.session_observability import calculate_context_utilization

_BUNDLED_SOURCE_UPDATED_AT = "2026-03-12T00:00:00+00:00"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pricing_key(platform_type: str, model_id: str) -> tuple[str, str]:
    return (str(platform_type or "").strip(), canonical_model_name(model_id))


def _normalize_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _serialize_entry(entry: dict[str, Any], project_id: str) -> dict[str, Any]:
    return {
        "projectId": project_id,
        "platformType": str(entry.get("platformType") or entry.get("platform_type") or ""),
        "modelId": canonical_model_name(entry.get("modelId") or entry.get("model_id") or ""),
        "contextWindowSize": _normalize_int(entry.get("contextWindowSize", entry.get("context_window_size"))),
        "inputCostPerMillion": _normalize_float(entry.get("inputCostPerMillion", entry.get("input_cost_per_million"))),
        "outputCostPerMillion": _normalize_float(entry.get("outputCostPerMillion", entry.get("output_cost_per_million"))),
        "cacheCreationCostPerMillion": _normalize_float(
            entry.get("cacheCreationCostPerMillion", entry.get("cache_creation_cost_per_million"))
        ),
        "cacheReadCostPerMillion": _normalize_float(
            entry.get("cacheReadCostPerMillion", entry.get("cache_read_cost_per_million"))
        ),
        "speedMultiplierFast": _normalize_float(entry.get("speedMultiplierFast", entry.get("speed_multiplier_fast"))),
        "sourceType": str(entry.get("sourceType") or entry.get("source_type") or "bundled"),
        "sourceUpdatedAt": str(entry.get("sourceUpdatedAt") or entry.get("source_updated_at") or ""),
        "overrideLocked": bool(entry.get("overrideLocked", entry.get("override_locked", False))),
        "syncStatus": str(entry.get("syncStatus") or entry.get("sync_status") or "never"),
        "syncError": str(entry.get("syncError") or entry.get("sync_error") or ""),
        "createdAt": str(entry.get("createdAt") or entry.get("created_at") or ""),
        "updatedAt": str(entry.get("updatedAt") or entry.get("updated_at") or ""),
    }


def _bundled_claude_code_entries() -> list[dict[str, Any]]:
    entries = [
        {
            "platformType": "Claude Code",
            "modelId": "",
            "contextWindowSize": 200000,
            "sourceType": "bundled",
            "sourceUpdatedAt": _BUNDLED_SOURCE_UPDATED_AT,
            "syncStatus": "bundled",
        },
        {
            "platformType": "Claude Code",
            "modelId": "claude-sonnet-4-5",
            "contextWindowSize": 200000,
            "inputCostPerMillion": 3.0,
            "outputCostPerMillion": 15.0,
            "cacheCreationCostPerMillion": 3.75,
            "cacheReadCostPerMillion": 0.3,
            "sourceType": "bundled",
            "sourceUpdatedAt": _BUNDLED_SOURCE_UPDATED_AT,
            "syncStatus": "bundled",
        },
        {
            "platformType": "Claude Code",
            "modelId": "claude-sonnet-4",
            "contextWindowSize": 200000,
            "inputCostPerMillion": 3.0,
            "outputCostPerMillion": 15.0,
            "cacheCreationCostPerMillion": 3.75,
            "cacheReadCostPerMillion": 0.3,
            "sourceType": "bundled",
            "sourceUpdatedAt": _BUNDLED_SOURCE_UPDATED_AT,
            "syncStatus": "bundled",
        },
        {
            "platformType": "Claude Code",
            "modelId": "claude-3-7-sonnet",
            "contextWindowSize": 200000,
            "inputCostPerMillion": 3.0,
            "outputCostPerMillion": 15.0,
            "cacheCreationCostPerMillion": 3.75,
            "cacheReadCostPerMillion": 0.3,
            "sourceType": "bundled",
            "sourceUpdatedAt": _BUNDLED_SOURCE_UPDATED_AT,
            "syncStatus": "bundled",
        },
        {
            "platformType": "Claude Code",
            "modelId": "claude-3-5-sonnet",
            "contextWindowSize": 200000,
            "inputCostPerMillion": 3.0,
            "outputCostPerMillion": 15.0,
            "cacheCreationCostPerMillion": 3.75,
            "cacheReadCostPerMillion": 0.3,
            "sourceType": "bundled",
            "sourceUpdatedAt": _BUNDLED_SOURCE_UPDATED_AT,
            "syncStatus": "bundled",
        },
        {
            "platformType": "Claude Code",
            "modelId": "claude-opus-4-1",
            "contextWindowSize": 200000,
            "inputCostPerMillion": 15.0,
            "outputCostPerMillion": 75.0,
            "cacheCreationCostPerMillion": 18.75,
            "cacheReadCostPerMillion": 1.5,
            "sourceType": "bundled",
            "sourceUpdatedAt": _BUNDLED_SOURCE_UPDATED_AT,
            "syncStatus": "bundled",
        },
        {
            "platformType": "Claude Code",
            "modelId": "claude-opus-4",
            "contextWindowSize": 200000,
            "inputCostPerMillion": 15.0,
            "outputCostPerMillion": 75.0,
            "cacheCreationCostPerMillion": 18.75,
            "cacheReadCostPerMillion": 1.5,
            "sourceType": "bundled",
            "sourceUpdatedAt": _BUNDLED_SOURCE_UPDATED_AT,
            "syncStatus": "bundled",
        },
    ]
    return [deepcopy(entry) for entry in entries]


def bundled_entries(platform_type: str | None = None) -> list[dict[str, Any]]:
    all_entries = _bundled_claude_code_entries()
    if not platform_type:
        return all_entries
    normalized_platform = str(platform_type or "").strip().lower()
    return [
        entry
        for entry in all_entries
        if str(entry.get("platformType") or "").strip().lower() == normalized_platform
    ]


class PricingCatalogService:
    def __init__(self, pricing_repo: Any):
        self.pricing_repo = pricing_repo

    async def list_entries(self, project_id: str, platform_type: str | None = None) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in bundled_entries(platform_type):
            serialized = _serialize_entry(entry, project_id)
            merged[_pricing_key(serialized["platformType"], serialized["modelId"])] = serialized

        for row in await self.pricing_repo.list_entries(project_id, platform_type):
            serialized = _serialize_entry(row, project_id)
            merged[_pricing_key(serialized["platformType"], serialized["modelId"])] = serialized

        return sorted(
            merged.values(),
            key=lambda entry: (entry["platformType"].lower(), entry["modelId"] or "", entry["sourceType"]),
        )

    async def upsert_entry(self, project_id: str, entry_data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            **entry_data,
            "platformType": str(entry_data.get("platformType") or entry_data.get("platform_type") or ""),
            "modelId": canonical_model_name(entry_data.get("modelId") or entry_data.get("model_id") or ""),
            "sourceType": str(entry_data.get("sourceType") or entry_data.get("source_type") or "manual"),
            "sourceUpdatedAt": str(entry_data.get("sourceUpdatedAt") or entry_data.get("source_updated_at") or _now_iso()),
            "syncStatus": str(entry_data.get("syncStatus") or entry_data.get("sync_status") or "manual"),
            "syncError": str(entry_data.get("syncError") or entry_data.get("sync_error") or ""),
            "overrideLocked": bool(entry_data.get("overrideLocked", entry_data.get("override_locked", False))),
        }
        saved = await self.pricing_repo.upsert_entry(payload, project_id)
        return _serialize_entry(saved or payload, project_id)

    async def sync_entries(self, project_id: str, platform_type: str) -> dict[str, Any]:
        now = _now_iso()
        platform_entries = bundled_entries(platform_type)
        warnings: list[str] = []
        if not platform_entries:
            return {
                "projectId": project_id,
                "platformType": platform_type,
                "syncedAt": now,
                "updatedEntries": 0,
                "warnings": [f"No bundled pricing defaults available for {platform_type}."],
                "entries": await self.list_entries(project_id, platform_type),
            }

        existing_entries = {
            _pricing_key(row.get("platform_type"), row.get("model_id")): row
            for row in await self.pricing_repo.list_entries(project_id, platform_type)
        }
        updated_entries = 0
        for entry in platform_entries:
            key = _pricing_key(entry.get("platformType"), entry.get("modelId"))
            existing = existing_entries.get(key)
            if existing and bool(existing.get("override_locked")) and str(existing.get("source_type") or "").strip().lower() == "manual":
                warnings.append(
                    f"Skipped locked manual override for {entry.get('modelId') or '(platform default)'}."
                )
                continue
            await self.pricing_repo.upsert_entry(
                {
                    **entry,
                    "sourceUpdatedAt": now,
                    "syncStatus": "synced",
                    "syncError": "",
                },
                project_id,
            )
            updated_entries += 1

        return {
            "projectId": project_id,
            "platformType": platform_type,
            "syncedAt": now,
            "updatedEntries": updated_entries,
            "warnings": warnings,
            "entries": await self.list_entries(project_id, platform_type),
        }

    async def reset_entry(self, project_id: str, platform_type: str, model_id: str = "") -> dict[str, Any] | None:
        canonical_model_id = canonical_model_name(model_id)
        await self.pricing_repo.delete_entry(project_id, platform_type, canonical_model_id)
        merged_entries = await self.list_entries(project_id, platform_type)
        for entry in merged_entries:
            if _pricing_key(entry["platformType"], entry["modelId"]) == _pricing_key(platform_type, canonical_model_id):
                return entry
        return None

    async def lookup_entry(
        self,
        project_id: str,
        platform_type: str,
        raw_model: str,
    ) -> tuple[dict[str, Any] | None, str]:
        canonical_model = canonical_model_name(raw_model)
        merged_entries = await self.list_entries(project_id, platform_type)
        exact_entry: dict[str, Any] | None = None
        platform_default: dict[str, Any] | None = None
        for entry in merged_entries:
            if _pricing_key(entry["platformType"], entry["modelId"]) != _pricing_key(platform_type, entry["modelId"]):
                continue
            if entry["modelId"] == canonical_model and canonical_model:
                exact_entry = entry
                break
            if not entry["modelId"]:
                platform_default = entry
        if exact_entry:
            return exact_entry, exact_entry["modelId"]
        if platform_default:
            return platform_default, ""
        return None, ""

    async def hydrate_session_observability(
        self,
        project_id: str,
        session_payload: dict[str, Any],
        observability_fields: dict[str, Any],
    ) -> dict[str, Any]:
        enriched = dict(observability_fields)
        platform_type = str(session_payload.get("platformType") or session_payload.get("platform_type") or "")
        if platform_type.strip().lower() not in {"claude code", "claude_code"}:
            return enriched

        pricing_entry, pricing_model_source = await self.lookup_entry(
            project_id,
            "Claude Code",
            str(session_payload.get("model") or ""),
        )
        if pricing_entry and int(enriched.get("context_window_size") or 0) <= 0:
            context_window_size = int(pricing_entry.get("contextWindowSize") or 0)
            if context_window_size > 0:
                enriched["context_window_size"] = context_window_size
                enriched["context_utilization_pct"] = calculate_context_utilization(
                    int(enriched.get("current_context_tokens") or 0),
                    context_window_size,
                )

        recalculated_cost_usd: float | None = None
        if pricing_entry:
            input_rate = _normalize_float(pricing_entry.get("inputCostPerMillion"))
            output_rate = _normalize_float(pricing_entry.get("outputCostPerMillion"))
            cache_creation_rate = _normalize_float(pricing_entry.get("cacheCreationCostPerMillion"))
            cache_read_rate = _normalize_float(pricing_entry.get("cacheReadCostPerMillion"))
            input_tokens = int(session_payload.get("tokensIn") or session_payload.get("tokens_in") or 0)
            output_tokens = int(session_payload.get("tokensOut") or session_payload.get("tokens_out") or 0)
            cache_creation_tokens = int(
                session_payload.get("cacheCreationInputTokens")
                or session_payload.get("cache_creation_input_tokens")
                or 0
            )
            cache_read_tokens = int(
                session_payload.get("cacheReadInputTokens")
                or session_payload.get("cache_read_input_tokens")
                or 0
            )
            missing_required_rates = any(rate is None for rate in (input_rate, output_rate))
            missing_cache_rates = (
                (cache_creation_tokens > 0 and cache_creation_rate is None)
                or (cache_read_tokens > 0 and cache_read_rate is None)
            )
            if not missing_required_rates and not missing_cache_rates:
                recalculated_cost_usd = round(
                    (input_tokens / 1_000_000.0) * float(input_rate or 0.0)
                    + (output_tokens / 1_000_000.0) * float(output_rate or 0.0)
                    + (cache_creation_tokens / 1_000_000.0) * float(cache_creation_rate or 0.0)
                    + (cache_read_tokens / 1_000_000.0) * float(cache_read_rate or 0.0),
                    6,
                )

        reported_cost_usd = _normalize_float(enriched.get("reported_cost_usd"))
        estimated_cost_usd = _normalize_float(session_payload.get("totalCost") or session_payload.get("total_cost")) or 0.0
        display_cost_usd: float | None
        cost_provenance = "unknown"
        cost_confidence = 0.0
        if reported_cost_usd is not None:
            display_cost_usd = reported_cost_usd
            cost_provenance = "reported"
            cost_confidence = 0.98 if recalculated_cost_usd is not None else 0.92
        elif recalculated_cost_usd is not None:
            display_cost_usd = recalculated_cost_usd
            cost_provenance = "recalculated"
            cost_confidence = 0.9
        elif estimated_cost_usd > 0:
            display_cost_usd = round(estimated_cost_usd, 6)
            cost_provenance = "estimated"
            cost_confidence = 0.45
        else:
            display_cost_usd = None

        cost_mismatch_pct: float | None = None
        if reported_cost_usd is not None and recalculated_cost_usd is not None:
            baseline = max(abs(reported_cost_usd), abs(recalculated_cost_usd), 1e-9)
            cost_mismatch_pct = round(abs(reported_cost_usd - recalculated_cost_usd) / baseline, 4)

        enriched.update(
            {
                "recalculated_cost_usd": recalculated_cost_usd,
                "display_cost_usd": display_cost_usd,
                "cost_provenance": cost_provenance,
                "cost_confidence": cost_confidence,
                "cost_mismatch_pct": cost_mismatch_pct,
                "pricing_model_source": pricing_model_source,
                "total_cost": float(display_cost_usd if display_cost_usd is not None else estimated_cost_usd),
            }
        )
        return enriched
