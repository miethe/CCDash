import unittest
from pathlib import Path


_SUPERSEDED_SPEC_PATHS = [
    "docs/document-frontmatter-improvement-spec-2026-02-19.md",
    "docs/document-frontmatter-current-implementation-spec-2026-02-19.md",
    "docs/document-frontmatter-lineage-v2-spec-2026-02-19.md",
    "docs/document-entity-spec.md",
]

_ALLOWED_REFERENCE_FILES = {
    "docs/schemas/document_frontmatter/README.md",
    "docs/project_plans/implementation_plans/refactors/document-feature-schema-alignment-v1.md",
}


class DocumentSchemaReferenceHygieneTests(unittest.TestCase):
    def test_non_archived_docs_do_not_reference_superseded_schema_paths(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        docs_root = repo_root / "docs"

        offenders: list[str] = []
        for path in docs_root.rglob("*.md"):
            rel = path.relative_to(repo_root).as_posix()
            if rel.startswith("docs/archive/superseded/"):
                continue
            if rel in _ALLOWED_REFERENCE_FILES:
                continue

            text = path.read_text(encoding="utf-8")
            for legacy_path in _SUPERSEDED_SPEC_PATHS:
                if legacy_path in text:
                    offenders.append(f"{rel} -> {legacy_path}")

        self.assertEqual(
            offenders,
            [],
            msg="Superseded schema references found outside allowed migration docs:\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
