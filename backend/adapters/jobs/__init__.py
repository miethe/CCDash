"""Job scheduling adapters."""

from backend.adapters.jobs.local import InProcessJobScheduler

__all__ = ["InProcessJobScheduler"]
