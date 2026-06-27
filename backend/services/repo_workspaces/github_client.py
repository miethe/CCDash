from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from backend.models import GitHubIntegrationSettings, GitRepoRef

logger = logging.getLogger("ccdash.github_client")

# Simple in-memory cache for PR status results: key → (data, expire_at)
_PR_STATUS_CACHE: dict[str, tuple[dict, float]] = {}
_PR_STATUS_TTL_SECONDS: float = 60.0


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


async def fetch_pr_status(
    repo_slug: str,
    pr_number: int,
    token: str = "",
    ttl_seconds: float = _PR_STATUS_TTL_SECONDS,
) -> dict:
    """Fetch live PR status from GitHub API for the given repo slug and PR number.

    Returns a dict with keys ``state`` (``open``/``closed``/``merged``) and
    ``review_status`` (``approved``/``changes_requested``/``pending``/``unknown``).

    Fail-soft: returns ``{}`` on ANY exception or timeout so that callers can
    fall back gracefully.  Results are cached in-process for ``ttl_seconds``
    (default 60 s) keyed by ``repo_slug + pr_number``.
    """
    cache_key = f"{repo_slug}:{pr_number}"
    now = time.monotonic()
    cached = _PR_STATUS_CACHE.get(cache_key)
    if cached is not None:
        data, expire_at = cached
        if now < expire_at:
            return dict(data)

    clean_slug = str(repo_slug or "").strip().strip("/")
    pr_num = int(pr_number or 0)
    if not clean_slug or pr_num <= 0:
        return {}

    clean_token = str(token or "").strip()
    if not clean_token:
        # No token configured — skip the API call entirely
        return {}

    headers = {
        "Authorization": f"Bearer {clean_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    pr_url = f"https://api.github.com/repos/{clean_slug}/pulls/{pr_num}"
    reviews_url = f"{pr_url}/reviews"
    timeout = aiohttp.ClientTimeout(total=10.0)

    result: dict = {}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Fetch PR state
            async with session.get(pr_url, headers=headers) as resp:
                if resp.status == 200:
                    pr_data = await resp.json()
                    merged = bool(pr_data.get("merged"))
                    if merged:
                        state = "merged"
                    else:
                        state = str(pr_data.get("state") or "open")
                    result["state"] = state
                else:
                    logger.debug(
                        "fetch_pr_status: unexpected status %s for %s#%s",
                        resp.status, clean_slug, pr_num,
                    )
                    return {}

            # Fetch review status
            async with session.get(reviews_url, headers=headers) as resp:
                review_status = "unknown"
                if resp.status == 200:
                    reviews = await resp.json()
                    if isinstance(reviews, list) and reviews:
                        # Latest non-dismissed review per reviewer
                        latest: dict[str, str] = {}
                        for review in reviews:
                            reviewer = str((review.get("user") or {}).get("login") or "")
                            state_r = str(review.get("state") or "")
                            if reviewer and state_r and state_r != "DISMISSED":
                                latest[reviewer] = state_r
                        states = set(latest.values())
                        if "APPROVED" in states and "CHANGES_REQUESTED" not in states:
                            review_status = "approved"
                        elif "CHANGES_REQUESTED" in states:
                            review_status = "changes_requested"
                        elif states:
                            review_status = "pending"
                result["review_status"] = review_status
    except Exception:
        logger.debug(
            "fetch_pr_status: failed for %s#%s (fail-soft)",
            clean_slug, pr_num, exc_info=True,
        )
        return {}

    _PR_STATUS_CACHE[cache_key] = (result, now + ttl_seconds)
    return result


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
