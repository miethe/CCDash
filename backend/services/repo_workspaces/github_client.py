from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from backend.models import GitHubIntegrationSettings, GitRepoRef


class GitHubRepoUrlError(ValueError):
    pass


def mask_token(token: str) -> str:
    value = str(token or "").strip()
    if not value:
        return ""
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}{'*' * (len(value) - 5)}{value[-2:]}"


def normalize_github_repo_ref(repo_ref: GitRepoRef) -> GitRepoRef:
    raw_url = str(repo_ref.repoUrl or "").strip()
    if not raw_url:
        raise GitHubRepoUrlError("GitHub repoUrl is required.")

    branch = str(repo_ref.branch or "").strip()
    repo_subpath = str(repo_ref.repoSubpath or "").strip().strip("/")

    repo_slug = str(repo_ref.repoSlug or "").strip()
    canonical_url = raw_url

    if raw_url.startswith("git@github.com:"):
        slug = raw_url.split("git@github.com:", 1)[1].strip()
        if slug.endswith(".git"):
            slug = slug[:-4]
        slug = slug.strip("/")
        parts = slug.split("/")
        if len(parts) != 2:
            raise GitHubRepoUrlError("Unsupported GitHub SSH URL format.")
        repo_slug = repo_slug or slug
        canonical_url = f"https://github.com/{slug}.git"
    else:
        parsed = urlparse(raw_url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            raise GitHubRepoUrlError("Only github.com HTTP(S) URLs are supported.")
        segments = [segment for segment in parsed.path.split("/") if segment]
        if len(segments) < 2:
            raise GitHubRepoUrlError("GitHub URLs must include an owner and repository.")
        owner, repo = segments[0], segments[1]
        repo = repo[:-4] if repo.endswith(".git") else repo
        repo_slug = repo_slug or f"{owner}/{repo}"
        canonical_url = f"https://github.com/{owner}/{repo}.git"

        if len(segments) >= 4 and segments[2] in {"tree", "blob"} and not branch:
            branch = segments[3]
            if len(segments) > 4 and not repo_subpath:
                repo_subpath = "/".join(segments[4:])

    return GitRepoRef(
        provider="github",
        repoUrl=canonical_url,
        repoSlug=repo_slug,
        branch=branch,
        repoSubpath=repo_subpath,
        writeEnabled=bool(repo_ref.writeEnabled),
    )


class GitHubClient:
    def __init__(self, settings: GitHubIntegrationSettings, cache_root: Path):
        self.settings = settings
        self.cache_root = cache_root.expanduser()

    def build_git_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"

        token = str(self.settings.token or "").strip()
        if not token:
            return env

        username = str(self.settings.username or "git").strip() or "git"
        askpass_script = self._ensure_askpass_script()
        env["GIT_ASKPASS"] = str(askpass_script)
        env["CCDASH_GITHUB_USERNAME"] = username
        env["CCDASH_GITHUB_TOKEN"] = token
        return env

    def _ensure_askpass_script(self) -> Path:
        script_path = self.cache_root / ".git-askpass.sh"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        if not script_path.exists():
            script_path.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  *Username*) printf '%s\\n' \"${CCDASH_GITHUB_USERNAME:-git}\" ;;\n"
                "  *) printf '%s\\n' \"${CCDASH_GITHUB_TOKEN:-}\" ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            script_path.chmod(0o700)
        return script_path
