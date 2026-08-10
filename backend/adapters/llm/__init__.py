"""TextCompletionPort adapters (P1 seam) -- httpx-only, no provider SDK.

Both adapters implement ``backend.application.ports.llm.TextCompletionPort``.
Neither is imported from any read-path router/service -- only from the two
derived-naming backends (``backend/services/session_naming_local_backend.py``,
``backend/services/session_naming_hosted_backend.py``) and
``backend/services/ai_insight.py``. See
``backend/tests/test_session_naming_read_path_no_model_client.py``.
"""
from __future__ import annotations

from backend.adapters.llm.gemini import GeminiTextCompletionAdapter
from backend.adapters.llm.ollama import OllamaTextCompletionAdapter

__all__ = [
    "GeminiTextCompletionAdapter",
    "OllamaTextCompletionAdapter",
]
