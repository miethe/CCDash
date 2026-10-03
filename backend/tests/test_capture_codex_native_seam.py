"""Synthetic native capture → registry parser → real in-memory DB → detail."""
import json
import os
from unittest.mock import AsyncMock, patch

from backend.tests.test_capture_codex_native import rollout, payload, hook, SID, _freshness_function
from backend.tests.test_capture_seam_integrity import _SeamBase, _PROJECT_ID
from backend.application.services.agent_queries.session_detail import get_session_detail


class NativeCaptureSeamTests(_SeamBase):
    async def test_late_sidecar_reparse_preserves_native_metadata_to_detail(self):
        path = rollout(self.workdir)
        os.utime(path, (100, 100))
        freshness = _freshness_function()
        await self._parse_and_persist(path)
        session_id = f"S-{path.stem}"
        before = await self.session_repo.get_by_id(session_id, _PROJECT_ID)
        self.assertIsNone(before["profile"])
        cached_key = freshness(path)
        with patch.object(hook, "_settings_effort_level", side_effect=AssertionError("Claude settings read")), patch.object(hook, "_probe_key_spend", side_effect=AssertionError("ICA transport")):
            sidecar = hook.write_capture_sidecar(payload(path, model="gpt-6-luna", effort="medium", launcher="codex", launcherSource="codex_payload_launcher", profile="native", profileSource="codex_payload_profile"), {"CCDASH_LAUNCHER":"codex","CCDASH_LAUNCH_PROFILE":"native"})
        os.utime(sidecar, (200, 200))
        self.assertGreater(freshness(path), cached_key)
        await self._parse_and_persist(path)
        row = await self.session_repo.get_by_id(session_id, _PROJECT_ID)
        self.assertEqual(row["profile"], "native")
        self.assertEqual(row["model_variant"], "gpt-6-luna")
        self.assertEqual(row["effort_tier"], "medium")
        self.assertEqual(row["effort_tier_source"], "codex_payload_effort")
        with patch("backend.application.services.agent_queries.session_detail._transcript_service.list_session_logs", new=AsyncMock(return_value=[])):
            detail = await get_session_detail(_PROJECT_ID, session_id, self.ports)
        self.assertEqual(detail.session["profile"], "native")
        self.assertEqual(detail.session["modelVariant"], "gpt-6-luna")
        self.assertEqual(detail.session["effortTier"], "medium")
        self.assertEqual(detail.session["effortTierSource"], "codex_payload_effort")
