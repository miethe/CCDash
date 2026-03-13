import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATED_ROUTERS = (
    ROOT / "backend" / "routers" / "execution.py",
    ROOT / "backend" / "routers" / "integrations.py",
)
BANNED_IMPORT_SNIPPETS = (
    "from backend.db import connection",
    "from backend.db.factory import",
)


class RouterArchitectureBoundaryTests(unittest.TestCase):
    def test_migrated_routers_do_not_import_db_singletons(self) -> None:
        for path in MIGRATED_ROUTERS:
            source = path.read_text(encoding="utf-8")
            for snippet in BANNED_IMPORT_SNIPPETS:
                self.assertNotIn(
                    snippet,
                    source,
                    msg=f"{path.name} regressed to direct DB import: {snippet}",
                )


if __name__ == "__main__":
    unittest.main()
