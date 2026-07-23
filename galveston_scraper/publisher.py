"""Publish data/dashboard.html to a GitHub Pages branch.

Uses git plumbing (`hash-object` / `mktree` / `commit-tree`) to build a single
orphan commit containing just `index.html` and force-push it to the Pages
branch. This never touches the working tree, the index, or `main`, and each
publish replaces the previous commit so the branch never accumulates history.

Enable via config `publish.enabled` (or `GALV_PUBLISH=1`). Failures are logged
and swallowed so publishing never breaks a poll.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import Config


def _git(args: list[str], cwd: Path, stdin: bytes | None = None) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return res.stdout.decode().strip()


def _repo_root(start: Path) -> Path | None:
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return Path(top.stdout.decode().strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def publish_dashboard(cfg: Config) -> bool:
    """Force-push the current dashboard to the Pages branch. Returns success."""
    if not cfg.publish.enabled:
        return False

    dash = cfg.dashboard_file
    if not dash.exists():
        print("  ! publish skipped: no dashboard.html yet")
        return False

    repo = _repo_root(dash.resolve().parent) or Path.cwd()
    branch = cfg.publish.branch or "gh-pages"
    remote = cfg.publish.remote or "origin"

    try:
        # Blob for the dashboard, plus a copy named index.html (Pages entrypoint).
        blob = _git(["hash-object", "-w", str(dash.resolve())], repo)
        tree_spec = (
            f"100644 blob {blob}\tindex.html\n"
            f"100644 blob {blob}\tdashboard.html\n"
        ).encode()
        tree = _git(["mktree"], repo, stdin=tree_spec)
        commit = _git(["commit-tree", tree, "-m", "Update case dashboard"], repo)
        _git(["push", "-f", remote, f"{commit}:refs/heads/{branch}"], repo)
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        err = (exc.stderr or b"").decode().strip()
        print(f"  ! dashboard publish failed: {err or exc}")
        return False
    except FileNotFoundError:  # git not on PATH
        print("  ! dashboard publish failed: git not found")
        return False

    print(f"  ↑ dashboard published to {remote}/{branch}")
    return True
