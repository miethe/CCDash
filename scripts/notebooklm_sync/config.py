"""Configuration constants for NotebookLM sync scripts."""

from pathlib import Path

# Root-level .md files to include (by exact filename)
ROOT_INCLUDE_FILES = ['README.md', 'CHANGELOG.md', 'CLAUDE.md']

# Directories to include recursively (all .md files within each dir)
INCLUDE_DIRS = ['docs', '.claude/progress', '.claude/worknotes']

# Fine-grained exclusion patterns (glob patterns relative to project root)
EXCLUDE_PATTERNS: list[str] = ['docs/archive/**']

# Mapping file location
MAPPING_PATH = Path.home() / ".notebooklm" / "ccdash-sources.json"

# Default notebook settings
DEFAULT_NOTEBOOK_TITLE = "CCDash"
