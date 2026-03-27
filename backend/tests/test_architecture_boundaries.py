import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATED_ROUTER_RULES = (
    (
        ROOT / "backend" / "routers" / "cache.py",
        (
            "from backend.db import connection",
            "from backend.db.factory import",
            "from backend.project_manager import",
        ),
    ),
    (
        ROOT / "backend" / "routers" / "execution.py",
        (
            "from backend.db import connection",
            "from backend.db.factory import",
        ),
    ),
    (
        ROOT / "backend" / "routers" / "integrations.py",
        (
            "from backend.db import connection",
            "from backend.db.factory import",
        ),
    ),
    (
        ROOT / "backend" / "routers" / "projects.py",
        (
            "from backend.db import connection",
            "from backend.db.factory import",
            "from backend.project_manager import",
        ),
    ),
)


class RouterArchitectureBoundaryTests(unittest.TestCase):
    def test_migrated_routers_do_not_import_db_singletons(self) -> None:
        for path, banned_snippets in MIGRATED_ROUTER_RULES:
            source = path.read_text(encoding="utf-8")
            for snippet in banned_snippets:
                self.assertNotIn(
                    snippet,
                    source,
                    msg=f"{path.name} regressed to direct DB import: {snippet}",
                )


if __name__ == "__main__":
    unittest.main()
