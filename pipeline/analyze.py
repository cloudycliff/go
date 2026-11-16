"""Whole-game analysis: one KataGo query for every position, saved raw to raw/<id>.json.gz."""

from __future__ import annotations

import gzip
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import ranks
from .coords import sgf_to_gtp
from .katago import KataGo
from .sgf import Game

SCHEMA_VERSION = 1


def base_query(game: Game, query_id: str) -> dict:
    query = {
        "id": query_id,
        "rules": game.rules,
        "komi": game.komi,
        "boardXSize": game.size,
        "boardYSize": game.size,
        "moves": [[color, sgf_to_gtp(point, game.size)] for color, point in game.moves],
    }
    stones = [["B", sgf_to_gtp(p, game.size)] for p in game.setup_black]
    stones += [["W", sgf_to_gtp(p, game.size)] for p in game.setup_white]
    if stones:
        query["initialStones"] = stones
        query["initialPlayer"] = "W" if game.handicap >= 2 else "B"
    return query


def student_profile(game: Game, student_color: str) -> str:
    rank = game.black_rank if student_color == "B" else game.white_rank
    if rank is None:
        rank = ranks.Rank("K", 8)
    return ranks.profile_for(rank)


def _progress(done: int, total: int, started: float) -> None:
    elapsed = time.monotonic() - started
    eta = elapsed / done * (total - done) if done else 0
    sys.stdout.write(f"\r  已分析 {done}/{total} 个局面，用时 {elapsed:.0f}s，预计还要 {eta:.0f}s   ")
    sys.stdout.flush()
    if done == total:
        sys.stdout.write("\n")


def overview(
    engine: KataGo, game: Game, student_color: str, visits: int, query_id: str = "overview"
) -> tuple[list[dict], dict]:
    """Analyses the position before every move and the final position."""
    profile = student_profile(game, student_color)
    turns = list(range(len(game.moves) + 1))
    query = base_query(game, query_id)
    query.update(
        {
            "analyzeTurns": turns,
            "maxVisits": visits,
            "includeOwnership": True,
            "includePolicy": True,
            "overrideSettings": {"humanSLProfile": profile},
        }
    )
    started = time.monotonic()
    engine.send(query)
    responses = engine.responses(
        query_id, len(turns), on_each=lambda d, t: _progress(d, t, started)
    )
    params = {
        "visits": visits,
        "humanSLProfile": profile,
        "seconds": round(time.monotonic() - started, 1),
    }
    return responses, params


def save_raw(
    path: Path,
    *,
    game: Game,
    game_id: str,
    student_color: str,
    model: str,
    version: dict,
    params: dict,
    responses: list[dict],
) -> None:
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "gameId": game_id,
        "studentColor": student_color,
        "analyzedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": {**version, "model": model},
        "overview": {"params": params, "responses": responses},
        "sgf": game.raw,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)


def load_raw(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)
