"""Pricing catalog service for defaults, discovered models, and cost derivation."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.model_identity import canonical_model_name
from backend.services.provider_pricing import fetch_anthropic_pricing, fetch_openai_codex_pricing
from backend.services.session_observability import calculate_context_utilization

GLOBAL_PRICING_PROJECT_ID = "__pricing_global__"
FAMILY_PREFIX = "family:"
_BUNDLED_SOURCE_UPDATED_AT = "2026-03-12T00:00:00+00:00"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _pricing_key(platform_type: str, model_id: str) -> tuple[str, str]:
    normalized_platform = str(platform_type or "").strip()
    normalized_model = str(model_id or "").strip().lower()
    if normalized_model and not normalized_model.startswith(FAMILY_PREFIX):
        normalized_model = canonical_model_name(normalized_model)
    return normalized_platform, normalized_model


def _family_entry_id(family: str) -> str:
    return f"{FAMILY_PREFIX}{str(family or '').strip().lower()}"


def _entry_kind(model_id: str) -> str:
    normalized = str(model_id or "").strip().lower()
    if not normalized:
        return "platform_default"
    if normalized.startswith(FAMILY_PREFIX):
        return "family_default"
    return "model"


def _family_id(model_id: str) -> str:
    normalized = str(model_id or "").strip().lower()
    if normalized.startswith(FAMILY_PREFIX):
        return normalized[len(FAMILY_PREFIX):]
    return ""


def _title_case(value: str) -> str:
    return " ".join(part.capitalize() for part in str(value or "").split() if part)


def _display_label(model_id: str) -> str:
    kind = _entry_kind(model_id)
    if kind == "platform_default":
        return "Platform Default"
    if kind == "family_default":
        return f"{_title_case(_family_id(model_id))} Family"
    return str(model_id or "").strip()


def _pricing_family(raw_model: str) -> str:
    canonical = canonical_model_name(raw_model)
    if not canonical:
        return ""
    if "opus" in canonical:
        return "opus"
    if "sonnet" in canonical:
        return "sonnet"
    if "haiku" in canonical:
        return "haiku"
    if "codex" in canonical:
        return "codex"
    return ""


def _platform_for_model(raw_model: str) -> str:
    canonical = canonical_model_name(raw_model)
    if not canonical:
        return ""
    if canonical.startswith("claude-"):
        return "Claude Code"
    if "codex" in canonical or canonical.startswith("gpt-"):
        return "Codex"
    return ""


def _serialize_entry(
    entry: dict[str, Any],
    project_id: str,
    *,
    is_persisted: bool = False,
    is_detected: bool = False,
    derived_from: str = "",
) -> dict[str, Any]:
    model_id = str(entry.get("modelId") or entry.get("model_id") or "").strip()
    if model_id and not model_id.startswith(FAMILY_PREFIX):
        model_id = canonical_model_name(model_id)
    kind = _entry_kind(model_id)
    source_type = str(entry.get("sourceType") or entry.get("source_type") or "bundled")
    return {
        "projectId": project_id,
        "platformType": str(entry.get("platformType") or entry.get("platform_type") or ""),
        "modelId": model_id,
        "displayLabel": str(entry.get("displayLabel") or _display_label(model_id)),
        "entryKind": str(entry.get("entryKind") or kind),
        "familyId": str(entry.get("familyId") or _family_id(model_id)),
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
        "sourceType": source_type,
        "sourceUpdatedAt": str(entry.get("sourceUpdatedAt") or entry.get("source_updated_at") or ""),
        "overrideLocked": bool(entry.get("overrideLocked", entry.get("override_locked", False))),
        "syncStatus": str(entry.get("syncStatus") or entry.get("sync_status") or "never"),
        "syncError": str(entry.get("syncError") or entry.get("sync_error") or ""),
        "derivedFrom": str(entry.get("derivedFrom") or derived_from or ""),
        "isPersisted": bool(entry.get("isPersisted", False) or is_persisted),
        "isDetected": bool(entry.get("isDetected", False) or is_detected),
        "isRequiredDefault": bool(entry.get("isRequiredDefault", kind != "model")),
        "canDelete": bool(entry.get("canDelete", is_persisted and kind == "model" and source_type == "manual")),
        "createdAt": str(entry.get("createdAt") or entry.get("created_at") or ""),
        "updatedAt": str(entry.get("updatedAt") or entry.get("updated_at") or ""),
    }


def _should_apply_fast_multiplier(session_payload: dict[str, Any]) -> bool:
    forensics = session_payload.get("sessionForensics") or session_payload.get("session_forensics_json") or {}
    if not isinstance(forensics, dict):
        return False
    usage_summary = forensics.get("usageSummary") or {}
    if not isinstance(usage_summary, dict):
        return False
    speed_counts = usage_summary.get("speedCounts") or {}
    if not isinstance(speed_counts, dict):
        return False
    normalized = {
        str(key or "").strip().lower(): _normalize_int(value) or 0
        for key, value in speed_counts.items()
    }
    fast_count = int(normalized.get("fast") or 0)
    non_fast_count = sum(count for key, count in normalized.items() if key and key != "fast")
    return fast_count > 0 and non_fast_count == 0


def _entry(
    platform_type: str,
    model_id: str,
    *,
    context_window_size: int | None = None,
    input_cost: float | None = None,
    output_cost: float | None = None,
    cache_creation_cost: float | None = None,
    cache_read_cost: float | None = None,
    speed_multiplier_fast: float | None = None,
) -> dict[str, Any]:
    return {
        "platformType": platform_type,
        "modelId": model_id,
        "contextWindowSize": context_window_size,
        "inputCostPerMillion": input_cost,
        "outputCostPerMillion": output_cost,
        "cacheCreationCostPerMillion": cache_creation_cost,
        "cacheReadCostPerMillion": cache_read_cost,
        "speedMultiplierFast": speed_multiplier_fast,
        "sourceType": "bundled",
        "sourceUpdatedAt": _BUNDLED_SOURCE_UPDATED_AT,
        "syncStatus": "bundled",
    }


def _bundled_default_entries() -> list[dict[str, Any]]:
    entries = [
        _entry("Claude Code", "", context_window_size=200000),
        _entry("Claude Code", _family_entry_id("sonnet"), context_window_size=200000, input_cost=3.0, output_cost=15.0, cache_creation_cost=3.75, cache_read_cost=0.3),
        _entry("Claude Code", _family_entry_id("opus"), context_window_size=200000, input_cost=5.0, output_cost=25.0, cache_creation_cost=6.25, cache_read_cost=0.5),
        _entry("Claude Code", _family_entry_id("haiku"), context_window_size=200000, input_cost=1.0, output_cost=5.0, cache_creation_cost=1.25, cache_read_cost=0.1),
        _entry("Codex", ""),
        _entry("Codex", _family_entry_id("codex"), input_cost=1.75, output_cost=14.0, cache_read_cost=0.175),
    ]
    return [deepcopy(entry) for entry in entries]


def _bundled_exact_reference_entries() -> list[dict[str, Any]]:
    entries = [
        _entry("Claude Code", "claude-sonnet-4-6", context_window_size=200000, input_cost=3.0, output_cost=15.0, cache_creation_cost=3.75, cache_read_cost=0.3),
        _entry("Claude Code", "claude-sonnet-4-5", context_window_size=200000, input_cost=3.0, output_cost=15.0, cache_creation_cost=3.75, cache_read_cost=0.3),
        _entry("Claude Code", "claude-sonnet-4", context_window_size=200000, input_cost=3.0, output_cost=15.0, cache_creation_cost=3.75, cache_read_cost=0.3),
        _entry("Claude Code", "claude-3-7-sonnet", context_window_size=200000, input_cost=3.0, output_cost=15.0, cache_creation_cost=3.75, cache_read_cost=0.3),
        _entry("Claude Code", "claude-3-5-sonnet", context_window_size=200000, input_cost=3.0, output_cost=15.0, cache_creation_cost=3.75, cache_read_cost=0.3),
        _entry("Claude Code", "claude-opus-4-6", context_window_size=200000, input_cost=5.0, output_cost=25.0, cache_creation_cost=6.25, cache_read_cost=0.5),
        _entry("Claude Code", "claude-opus-4-5", context_window_size=200000, input_cost=5.0, output_cost=25.0, cache_creation_cost=6.25, cache_read_cost=0.5),
        _entry("Claude Code", "claude-opus-4-1", context_window_size=200000, input_cost=15.0, output_cost=75.0, cache_creation_cost=18.75, cache_read_cost=1.5),
        _entry("Claude Code", "claude-opus-4", context_window_size=200000, input_cost=15.0, output_cost=75.0, cache_creation_cost=18.75, cache_read_cost=1.5),
        _entry("Claude Code", "claude-haiku-4-5", context_window_size=200000, input_cost=1.0, output_cost=5.0, cache_creation_cost=1.25, cache_read_cost=0.1),
        _entry("Claude Code", "claude-haiku-3-5", context_window_size=200000, input_cost=0.8, output_cost=4.0, cache_creation_cost=1.0, cache_read_cost=0.08),
        _entry("Claude Code", "claude-3-opus", context_window_size=200000, input_cost=15.0, output_cost=75.0, cache_creation_cost=18.75, cache_read_cost=1.5),
        _entry("Claude Code", "claude-3-haiku", context_window_size=200000, input_cost=0.25, output_cost=1.25, cache_creation_cost=0.3, cache_read_cost=0.03),
        _entry("Codex", "gpt-5.2-codex", input_cost=1.75, output_cost=14.0, cache_read_cost=0.175),
        _entry("Codex", "gpt-5.1-codex-max", input_cost=1.25, output_cost=10.0, cache_read_cost=0.125),
        _entry("Codex", "gpt-5.1-codex", input_cost=1.25, output_cost=10.0, cache_read_cost=0.125),
        _entry("Codex", "gpt-5-codex", input_cost=1.25, output_cost=10.0, cache_read_cost=0.125),
        _entry("Codex", "codex-mini-latest", input_cost=1.5, output_cost=6.0, cache_read_cost=0.375),
    ]
    return [deepcopy(entry) for entry in entries]


def bundled_entries(platform_type: str | None = None, *, include_exact: bool = False) -> list[dict[str, Any]]:
    all_entries = _bundled_default_entries()
    if include_exact:
        all_entries.extend(_bundled_exact_reference_entries())
    if not platform_type:
        return all_entries
    normalized_platform = str(platform_type or "").strip().lower()
    return [
        entry
        for entry in all_entries
        if str(entry.get("platformType") or "").strip().lower() == normalized_platform
    ]


def _reference_entries(platform_type: str | None = None) -> list[dict[str, Any]]:
    return bundled_entries(platform_type, include_exact=True)


def _preferred_family_models() -> dict[str, str]:
    return {
        "Claude Code:sonnet": "claude-sonnet-4-6",
        "Claude Code:opus": "claude-opus-4-6",
        "Claude Code:haiku": "claude-haiku-4-5",
        "Codex:codex": "gpt-5.2-codex",
    }


def _latest_synced_defaults(platform_type: str, fetched_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    family_targets = _preferred_family_models()
    exact_by_key = {
        _pricing_key(entry.get("platformType"), entry.get("modelId")): deepcopy(entry)
        for entry in fetched_entries
    }
    defaults: list[dict[str, Any]] = []
    for entry in bundled_entries(platform_type):
        cloned = deepcopy(entry)
        key = f"{platform_type}:{_family_id(cloned.get('modelId', ''))}"
        target_model = family_targets.get(key, "")
        exact = exact_by_key.get(_pricing_key(platform_type, target_model))
        if exact and _entry_kind(cloned.get("modelId", "")) == "family_default":
            for field in (
                "inputCostPerMillion",
                "outputCostPerMillion",
                "cacheCreationCostPerMillion",
                "cacheReadCostPerMillion",
                "speedMultiplierFast",
            ):
                if field in exact and exact[field] is not None:
                    cloned[field] = exact[field]
            cloned["sourceType"] = "fetched"
            cloned["syncStatus"] = "fetched"
        defaults.append(cloned)
    return defaults


class PricingCatalogService:
    def __init__(self, pricing_repo: Any, session_repo: Any | None = None):
        self.pricing_repo = pricing_repo
        self.session_repo = session_repo

    def _catalog_scope(self) -> str:
        return GLOBAL_PRICING_PROJECT_ID

    async def _repo_entries(self, project_id: str, platform_type: str | None = None) -> list[dict[str, Any]]:
        return await self.pricing_repo.list_entries(project_id, platform_type)

    async def _merged_reference_entries(self, project_id: str, platform_type: str | None = None) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in bundled_entries(platform_type, include_exact=True):
            serialized = _serialize_entry(entry, self._catalog_scope())
            merged[_pricing_key(serialized["platformType"], serialized["modelId"])] = serialized

        for row in await self._repo_entries(self._catalog_scope(), platform_type):
            serialized = _serialize_entry(row, self._catalog_scope(), is_persisted=True)
            merged[_pricing_key(serialized["platformType"], serialized["modelId"])] = serialized

        if project_id and project_id != self._catalog_scope():
            for row in await self._repo_entries(project_id, platform_type):
                serialized = _serialize_entry(row, project_id, is_persisted=True)
                merged[_pricing_key(serialized["platformType"], serialized["modelId"])] = serialized

        return list(merged.values())

    async def _detected_inventory_entries(self, platform_type: str | None = None) -> list[dict[str, Any]]:
        if self.session_repo is None:
            return []
        model_rows = await self.session_repo.get_model_facets(None, include_subagents=True)
        reference_entries = await self._merged_reference_entries(self._catalog_scope(), platform_type)
        reference_by_key = {
            _pricing_key(entry["platformType"], entry["modelId"]): entry
            for entry in reference_entries
        }
        detected_entries: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        for row in model_rows:
            raw_model = str(row.get("model") or "").strip()
            canonical_model = canonical_model_name(raw_model)
            resolved_platform = _platform_for_model(canonical_model)
            if not canonical_model or not resolved_platform:
                continue
            if platform_type and resolved_platform.lower() != str(platform_type).strip().lower():
                continue
            key = _pricing_key(resolved_platform, canonical_model)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            family_key = _pricing_key(resolved_platform, _family_entry_id(_pricing_family(canonical_model)))
            platform_key = _pricing_key(resolved_platform, "")
            base_entry = reference_by_key.get(key) or reference_by_key.get(family_key) or reference_by_key.get(platform_key)
            derived_from = ""
            if base_entry:
                derived_from = base_entry["modelId"] or "platform_default"
            entry = _serialize_entry(
                {
                    **(base_entry or {"platformType": resolved_platform, "modelId": canonical_model}),
                    "platformType": resolved_platform,
                    "modelId": canonical_model,
                    "sourceType": "detected",
                    "syncStatus": "detected",
                    "displayLabel": canonical_model,
                },
                self._catalog_scope(),
                is_detected=True,
                derived_from=derived_from,
            )
            detected_entries.append(entry)
        return detected_entries

    async def list_entries(self, project_id: str, platform_type: str | None = None) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in bundled_entries(platform_type):
            serialized = _serialize_entry(entry, self._catalog_scope())
            merged[_pricing_key(serialized["platformType"], serialized["modelId"])] = serialized

        for row in await self._repo_entries(self._catalog_scope(), platform_type):
            serialized = _serialize_entry(row, self._catalog_scope(), is_persisted=True)
            merged[_pricing_key(serialized["platformType"], serialized["modelId"])] = serialized

        if project_id and project_id != self._catalog_scope():
            for row in await self._repo_entries(project_id, platform_type):
                serialized = _serialize_entry(row, project_id, is_persisted=True)
                merged[_pricing_key(serialized["platformType"], serialized["modelId"])] = serialized

        return sorted(
            merged.values(),
            key=lambda entry: (
                entry["platformType"].lower(),
                {"platform_default": 0, "family_default": 1, "model": 2}.get(entry["entryKind"], 9),
                entry["familyId"],
                entry["modelId"],
            ),
        )

    async def list_catalog_entries(self, platform_type: str | None = None) -> list[dict[str, Any]]:
        merged = {
            _pricing_key(entry["platformType"], entry["modelId"]): entry
            for entry in await self.list_entries(self._catalog_scope(), platform_type)
        }
        for entry in await self._detected_inventory_entries(platform_type):
            merged.setdefault(_pricing_key(entry["platformType"], entry["modelId"]), entry)
        return sorted(
            merged.values(),
            key=lambda entry: (
                entry["platformType"].lower(),
                {"platform_default": 0, "family_default": 1, "model": 2}.get(entry["entryKind"], 9),
                entry["familyId"],
                entry["modelId"],
            ),
        )

    async def upsert_entry(self, project_id: str, entry_data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            **entry_data,
            "platformType": str(entry_data.get("platformType") or entry_data.get("platform_type") or ""),
            "modelId": str(entry_data.get("modelId") or entry_data.get("model_id") or "").strip().lower(),
            "sourceType": str(entry_data.get("sourceType") or entry_data.get("source_type") or "manual"),
            "sourceUpdatedAt": str(entry_data.get("sourceUpdatedAt") or entry_data.get("source_updated_at") or _now_iso()),
            "syncStatus": str(entry_data.get("syncStatus") or entry_data.get("sync_status") or "manual"),
            "syncError": str(entry_data.get("syncError") or entry_data.get("sync_error") or ""),
            "overrideLocked": bool(entry_data.get("overrideLocked", entry_data.get("override_locked", False))),
        }
        if payload["modelId"] and not payload["modelId"].startswith(FAMILY_PREFIX):
            payload["modelId"] = canonical_model_name(payload["modelId"])
        saved = await self.pricing_repo.upsert_entry(payload, project_id)
        return _serialize_entry(saved or payload, project_id, is_persisted=True)

    async def upsert_catalog_entry(self, entry_data: dict[str, Any]) -> dict[str, Any]:
        return await self.upsert_entry(self._catalog_scope(), entry_data)

    async def sync_entries(self, project_id: str, platform_type: str) -> dict[str, Any]:
        now = _now_iso()
        warnings: list[str] = []
        fetched_entries: list[dict[str, Any]] = []
        try:
            if platform_type == "Claude Code":
                fetched_entries = fetch_anthropic_pricing()
            elif platform_type == "Codex":
                fetched_entries = fetch_openai_codex_pricing()
        except Exception as exc:
            warnings.append(f"Live pricing fetch failed for {platform_type}: {exc}")

        platform_entries = _latest_synced_defaults(platform_type, fetched_entries) if fetched_entries else bundled_entries(platform_type)
        if not platform_entries:
            return {
                "projectId": project_id,
                "platformType": platform_type,
                "syncedAt": now,
                "updatedEntries": 0,
                "warnings": [f"No pricing defaults available for {platform_type}.", *warnings],
                "entries": await self.list_catalog_entries(platform_type),
            }

        existing_entries = {
            _pricing_key(row.get("platform_type"), row.get("model_id")): row
            for row in await self._repo_entries(project_id, platform_type)
        }
        if fetched_entries:
            for existing in existing_entries.values():
                normalized_model_id = str(existing.get("model_id") or "").strip().lower()
                source_type = str(existing.get("source_type") or "").strip().lower()
                override_locked = bool(existing.get("override_locked"))
                if (
                    normalized_model_id
                    and not normalized_model_id.startswith(FAMILY_PREFIX)
                    and source_type in {"bundled", "fetched"}
                    and not override_locked
                ):
                    await self.pricing_repo.delete_entry(project_id, platform_type, normalized_model_id)

        updated_entries = 0
        for entry in platform_entries:
            key = _pricing_key(entry.get("platformType"), entry.get("modelId"))
            existing = existing_entries.get(key)
            if existing and bool(existing.get("override_locked")) and str(existing.get("source_type") or "").strip().lower() == "manual":
                warnings.append(f"Skipped locked manual override for {entry.get('modelId') or '(platform default)'}.")
                continue
            await self.pricing_repo.upsert_entry(
                {
                    **entry,
                    "sourceType": "fetched" if fetched_entries else "bundled",
                    "sourceUpdatedAt": now,
                    "syncStatus": "fetched" if fetched_entries else "bundled",
                    "syncError": "",
                },
                project_id,
            )
            updated_entries += 1

        if fetched_entries:
            for entry in fetched_entries:
                key = _pricing_key(entry.get("platformType"), entry.get("modelId"))
                existing = existing_entries.get(key)
                if existing and bool(existing.get("override_locked")) and str(existing.get("source_type") or "").strip().lower() == "manual":
                    warnings.append(f"Skipped locked manual override for {entry.get('modelId') or '(platform default)'}.")
                    continue
                await self.pricing_repo.upsert_entry(
                    {
                        **entry,
                        "sourceType": "fetched",
                        "sourceUpdatedAt": now,
                        "syncStatus": "fetched",
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
            "entries": await self.list_catalog_entries(platform_type),
        }

    async def sync_catalog_entries(self, platform_type: str) -> dict[str, Any]:
        return await self.sync_entries(self._catalog_scope(), platform_type)

    async def reset_entry(self, project_id: str, platform_type: str, model_id: str = "") -> dict[str, Any] | None:
        normalized_model_id = str(model_id or "").strip().lower()
        if normalized_model_id and not normalized_model_id.startswith(FAMILY_PREFIX):
            normalized_model_id = canonical_model_name(normalized_model_id)
        await self.pricing_repo.delete_entry(project_id, platform_type, normalized_model_id)
        merged_entries = await self.list_entries(project_id, platform_type)
        for entry in merged_entries:
            if _pricing_key(entry["platformType"], entry["modelId"]) == _pricing_key(platform_type, normalized_model_id):
                return entry
        return None

    async def reset_catalog_entry(self, platform_type: str, model_id: str = "") -> dict[str, Any] | None:
        return await self.reset_entry(self._catalog_scope(), platform_type, model_id)

    async def delete_catalog_entry(self, platform_type: str, model_id: str) -> None:
        normalized_model_id = canonical_model_name(model_id)
        if not normalized_model_id:
            raise ValueError("Only exact model overrides can be deleted.")
        await self.pricing_repo.delete_entry(self._catalog_scope(), platform_type, normalized_model_id)

    async def lookup_entry(
        self,
        project_id: str,
        platform_type: str,
        raw_model: str,
    ) -> tuple[dict[str, Any] | None, str]:
        canonical_model = canonical_model_name(raw_model)
        pricing_family = _pricing_family(canonical_model)
        entries = await self._merged_reference_entries(project_id, platform_type)
        exact_entry: dict[str, Any] | None = None
        family_entry: dict[str, Any] | None = None
        platform_default: dict[str, Any] | None = None
        for entry in entries:
            if str(entry.get("platformType") or "").strip().lower() != str(platform_type or "").strip().lower():
                continue
            entry_model = str(entry.get("modelId") or "")
            if canonical_model and entry_model == canonical_model:
                exact_entry = entry
                break
            if pricing_family and entry_model == _family_entry_id(pricing_family):
                family_entry = entry
            if not entry_model:
                platform_default = entry
        if exact_entry:
            return exact_entry, exact_entry["modelId"]
        if family_entry:
            return family_entry, family_entry["modelId"]
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
            if context_window_size and context_window_size > 0:
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
            speed_multiplier_fast = _normalize_float(pricing_entry.get("speedMultiplierFast")) or 1.0
            input_tokens = int(session_payload.get("tokensIn") or session_payload.get("tokens_in") or 0)
            output_tokens = int(session_payload.get("tokensOut") or session_payload.get("tokens_out") or 0)
            cache_creation_tokens = int(session_payload.get("cacheCreationInputTokens") or session_payload.get("cache_creation_input_tokens") or 0)
            cache_read_tokens = int(session_payload.get("cacheReadInputTokens") or session_payload.get("cache_read_input_tokens") or 0)
            missing_required_rates = any(rate is None for rate in (input_rate, output_rate))
            missing_cache_rates = (
                (cache_creation_tokens > 0 and cache_creation_rate is None)
                or (cache_read_tokens > 0 and cache_read_rate is None)
            )
            if not missing_required_rates and not missing_cache_rates:
                multiplier = speed_multiplier_fast if _should_apply_fast_multiplier(session_payload) else 1.0
                recalculated_cost_usd = round(
                    (
                        (input_tokens / 1_000_000.0) * float(input_rate or 0.0)
                        + (output_tokens / 1_000_000.0) * float(output_rate or 0.0)
                        + (cache_creation_tokens / 1_000_000.0) * float(cache_creation_rate or 0.0)
                        + (cache_read_tokens / 1_000_000.0) * float(cache_read_rate or 0.0)
                    ) * multiplier,
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
