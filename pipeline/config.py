"""Loads config.toml and resolves paths against the project folder."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class KataGoPaths:
    exe: Path
    model: Path
    human_model: Path
    config: Path


@dataclass(frozen=True)
class Config:
    fox_nickname: str
    katago: KataGoPaths
    overview_visits: int
    deep_visits: int
    peer_steps: int

    @property
    def raw_dir(self) -> Path:
        return ROOT / "raw"

    @property
    def local_raw_dir(self) -> Path:
        """Analyses kept on this computer only (git-ignored): not committed, not on the site."""
        return ROOT / "local" / "raw"

    @property
    def cache_dir(self) -> Path:
        return ROOT / ".cache"


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load(path: Path | None = None) -> Config:
    path = path or ROOT / "config.toml"
    if not path.exists():
        raise SystemExit(f"找不到配置文件 {path}，请从 config.example.toml 复制一份。")
    with path.open("rb") as f:
        data = tomllib.load(f)
    student = data.get("student", {})
    katago = data.get("katago", {})
    analysis = data.get("analysis", {})
    nickname = str(student.get("fox_nickname", "")).strip()
    if not nickname:
        raise SystemExit("config.toml 里缺少 [student] fox_nickname。")
    return Config(
        fox_nickname=nickname,
        katago=KataGoPaths(
            exe=_path(katago["exe"]),
            model=_path(katago["model"]),
            human_model=_path(katago["human_model"]),
            config=_path(katago.get("config", "katago/analysis.cfg")),
        ),
        overview_visits=int(analysis.get("overview_visits", 400)),
        deep_visits=int(analysis.get("deep_visits", 3000)),
        peer_steps=int(analysis.get("peer_steps", 2)),
    )
