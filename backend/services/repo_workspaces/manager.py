from __future__ import annotations

import logging
from pathlib import Path

from backend.models import GitHubIntegrationSettings, GitRepoRef
from backend.services.repo_workspaces.cache import RepoWorkspaceCache
from backend.services.repo_workspaces.git_runner import GitCommandError, GitRunner
from backend.services.repo_workspaces.github_client import GitHubClient, normalize_github_repo_ref

logger = logging.getLogger("ccdash.repo_workspaces")


class RepoWorkspaceError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


class RepoWorkspaceManager:
    def __init__(
        self,
        cache: RepoWorkspaceCache,
        *,
        git_runner: GitRunner | None = None,
    ):
        self.cache = cache
        self.git_runner = git_runner or GitRunner()

    def ensure_workspace(
        self,
        repo_ref: GitRepoRef,
        settings: GitHubIntegrationSettings,
        *,
        refresh: bool = False,
    ) -> Path:
        normalized = normalize_github_repo_ref(repo_ref)
        if not normalized.branch:
            normalized = normalized.model_copy(update={"branch": self._detect_default_branch(normalized, settings)})

        paths = self.cache.paths_for(normalized)
        workspace_dir = paths.workspace_dir
        workspace_dir.parent.mkdir(parents=True, exist_ok=True)

        client = GitHubClient(settings, paths.cache_root)
        env = client.build_git_env()
        if not workspace_dir.exists():
            self._clone_workspace(workspace_dir, normalized, env)
        else:
            self._refresh_workspace(workspace_dir, normalized, env, hard_reset=refresh)
        return workspace_dir

    def write_file_and_push(
        self,
        repo_ref: GitRepoRef,
        settings: GitHubIntegrationSettings,
        *,
        workspace_relative_path: str,
        content: str,
        commit_message: str,
    ) -> str:
        normalized = normalize_github_repo_ref(repo_ref)
        if not normalized.branch:
            normalized = normalized.model_copy(update={"branch": self._detect_default_branch(normalized, settings)})

        workspace_dir = self.ensure_workspace(normalized, settings, refresh=False)
        relative_path = str(workspace_relative_path or "").strip().replace("\\", "/").strip("/")
        if not relative_path:
            raise RepoWorkspaceError("invalid_relative_path", "A repository-relative file path is required for writes.")

        target_path = (workspace_dir / relative_path).resolve(strict=False)
        try:
            target_path.relative_to(workspace_dir.resolve(strict=False))
        except ValueError as exc:
            raise RepoWorkspaceError("invalid_relative_path", "The requested write target escapes the repository workspace.") from exc

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")

        client = GitHubClient(settings, self.cache.cache_root)
        env = client.build_git_env()

        try:
            self.git_runner.run(["add", "--", relative_path], cwd=workspace_dir, env=env)
            status = self.git_runner.run(["status", "--short", "--", relative_path], cwd=workspace_dir, env=env)
            if not status.strip():
                logger.info("Skipped repo write commit because %s has no staged changes", relative_path)
                return ""

            self.git_runner.run(["commit", "-m", commit_message, "--", relative_path], cwd=workspace_dir, env=env)
            commit_hash = self.git_runner.run(["rev-parse", "HEAD"], cwd=workspace_dir, env=env).strip()
            self.git_runner.run(["push", "origin", f"HEAD:{normalized.branch}"], cwd=workspace_dir, env=env)
        except GitCommandError as exc:
            raise self._map_git_error(exc) from exc

        logger.info(
            "Pushed managed repo workspace update repo=%s branch=%s path=%s commit=%s",
            normalized.repoSlug,
            normalized.branch,
            relative_path,
            commit_hash,
        )
        return commit_hash

    def _detect_default_branch(self, repo_ref: GitRepoRef, settings: GitHubIntegrationSettings) -> str:
        client = GitHubClient(settings, self.cache.cache_root)
        try:
            output = self.git_runner.run(
                ["ls-remote", "--symref", repo_ref.repoUrl, "HEAD"],
                env=client.build_git_env(),
            )
        except GitCommandError as exc:
            raise RepoWorkspaceError("auth_failure", exc.stderr.strip() or exc.stdout.strip() or str(exc)) from exc

        for line in output.splitlines():
            if line.startswith("ref: ") and line.endswith("\tHEAD"):
                ref = line.split()[1]
                if ref.startswith("refs/heads/"):
                    return ref.rsplit("/", 1)[-1]
        raise RepoWorkspaceError("missing_branch", "Unable to determine the repository default branch.")

    def _clone_workspace(self, workspace_dir: Path, repo_ref: GitRepoRef, env: dict[str, str]) -> None:
        try:
            self.git_runner.run(
                [
                    "clone",
                    "--branch",
                    repo_ref.branch,
                    "--single-branch",
                    repo_ref.repoUrl,
                    str(workspace_dir),
                ],
                env=env,
            )
        except GitCommandError as exc:
            raise self._map_git_error(exc) from exc

    def _refresh_workspace(
        self,
        workspace_dir: Path,
        repo_ref: GitRepoRef,
        env: dict[str, str],
        *,
        hard_reset: bool,
    ) -> None:
        try:
            self.git_runner.run(["remote", "set-url", "origin", repo_ref.repoUrl], cwd=workspace_dir, env=env)
            self.git_runner.run(["fetch", "origin", "--prune"], cwd=workspace_dir, env=env)
            self.git_runner.run(["checkout", "-B", repo_ref.branch, f"origin/{repo_ref.branch}"], cwd=workspace_dir, env=env)
            if hard_reset:
                self.git_runner.run(["reset", "--hard", f"origin/{repo_ref.branch}"], cwd=workspace_dir, env=env)
        except GitCommandError as exc:
            raise self._map_git_error(exc) from exc

    def _map_git_error(self, exc: GitCommandError) -> RepoWorkspaceError:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        lowered = message.lower()
        if "authentication failed" in lowered or "could not read username" in lowered:
            return RepoWorkspaceError("auth_failure", message or "GitHub authentication failed.")
        if "permission to" in lowered and "denied" in lowered:
            return RepoWorkspaceError("write_not_allowed", message or "The configured GitHub credential cannot push to this repository.")
        if "remote branch" in lowered and "not found" in lowered:
            return RepoWorkspaceError("missing_branch", message or "The requested GitHub branch was not found.")
        if "repository not found" in lowered:
            return RepoWorkspaceError("invalid_github_url", message or "The GitHub repository could not be found.")
        return RepoWorkspaceError("clone_fetch_failure", message or "Unable to refresh the GitHub workspace.")
