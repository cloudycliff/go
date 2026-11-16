"""Publishing: commit the review data (site/ and raw/ only) and push; Cloudflare Pages deploys it.

Also the pieces `analyze --latest` needs for unattended runs: which Fox games are new, and a lock
so two scheduled runs never overlap.
"""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from .config import ROOT

PUBLISHED = ["site", "raw"]  # never config.toml, models/, logs/ or keys
MIN_MOVES = 40  # shorter games (an early resignation) have nothing to review
MAX_NEW = 3  # games per run; the rest wait for the next run
LOCK_STALE = 3 * 3600  # seconds; a lock older than this is from a crashed run


class PublishError(RuntimeError):
    pass


def new_games(games: list, uid: str, analyzed: set[str], limit: int = MAX_NEW) -> list:
    """Games newer than the newest analysed one, oldest first.

    With nothing analysed yet, only the newest game counts (a first run must not analyse 100).
    """
    mine = [g for g in games if g.size == 19 and g.student_color(uid)]
    done = [g.start for g in mine if g.chessid in analyzed]
    if done:
        newest: datetime = max(done)
        fresh = [g for g in mine if g.start > newest and g.chessid not in analyzed]
    else:
        fresh = sorted(mine, key=lambda g: g.start)[-1:]
    fresh = [g for g in fresh if g.moves >= MIN_MOVES]
    return sorted(fresh, key=lambda g: g.start)[:limit]


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if check and proc.returncode != 0:
        raise PublishError(f"git {' '.join(args)} 失败：{(proc.stderr or proc.stdout).strip()}")
    return proc


def publish(message: str, repo: Path = ROOT, branch: str = "main", remote: str = "origin", log=print) -> bool:
    """Commits site/ and raw/ and pushes. Returns False when there was nothing to publish."""
    current = _git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip()
    if current != branch:
        raise PublishError(f"当前分支是 {current}，发布只在 {branch} 分支上进行。")
    paths = [p for p in PUBLISHED if (repo / p).exists()]
    _git(repo, "add", "--", *paths)
    if _git(repo, "diff", "--cached", "--quiet", "--", *paths, check=False).returncode == 0:
        log("没有需要发布的变化。")
        return False
    # Only these paths go into the commit, even if something else happens to be staged.
    _git(repo, "commit", "-m", message, "--", *paths)
    log(f"已提交：{message}")
    _git(repo, "push", remote, branch)
    log(f"已推送到 {remote}/{branch}，Cloudflare Pages 会在一两分钟内更新网站。")
    return True


class Lock:
    """An exclusive lock file; a lock left by a crashed run expires after LOCK_STALE seconds."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.held = False

    def __enter__(self) -> "Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age > LOCK_STALE:
                    self.path.unlink(missing_ok=True)
                    continue
                raise PublishError(f"上一次运行还没结束（{self.path} 存在）。")
            with os.fdopen(fd, "w") as f:
                f.write(f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n")
            self.held = True
            return self
        raise PublishError(f"无法获得锁 {self.path}")

    def __exit__(self, *exc) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)
