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


def student_rank(game: Game, student_color: str) -> ranks.Rank:
    rank = game.black_rank if student_color == "B" else game.white_rank
    return rank if rank is not None else ranks.Rank("K", 8)


def student_profile(game: Game, student_color: str, steps_up: int = 0) -> str:
    return ranks.profile_for(student_rank(game, student_color), steps_up)


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


def deep(
    engine: KataGo,
    game: Game,
    student_color: str,
    turns: list[int],
    visits: int,
    peer_steps: int,
    query_id: str = "deep",
) -> tuple[list[dict], dict]:
    """Analyses selected positions deeply, for long variations and more exact losses.

    The HumanSL profile is the stronger "peer" one, so `humanPolicy` here shows what players a
    little stronger than the student would play.
    """
    profile = student_profile(game, student_color, peer_steps)
    query = base_query(game, query_id)
    query.update(
        {
            "analyzeTurns": sorted(turns),
            "maxVisits": visits,
            "includeOwnership": True,
            "includePolicy": True,
            "overrideSettings": {"humanSLProfile": profile},
        }
    )
    started = time.monotonic()
    engine.send(query)
    responses = engine.responses(
        query_id, len(turns), timeout=1800.0, on_each=lambda d, t: _progress(d, t, started)
    )
    params = {
        "visits": visits,
        "humanSLProfile": profile,
        "seconds": round(time.monotonic() - started, 1),
    }
    return responses, params


def add_deep(raw: dict, responses: list[dict], params: dict) -> None:
    """Merges deep results into a raw analysis, keyed by turn number."""
    store = raw.setdefault("deep", {"params": params, "responses": {}})
    store["params"] = params
    for r in responses:
        store["responses"][str(r["turnNumber"])] = r


def probe(
    engine: KataGo,
    game: Game,
    student_color: str,
    probes: list[tuple[int, str]],
    visits: int,
) -> dict[str, dict]:
    """Analyses the position after a move that was not played: (move index, SGF point) pairs.

    Used for good moves, to know how much the move players at the student's rank usually play
    would have lost. Keys are "<index>:<point>".
    """
    profile = student_profile(game, student_color)
    out: dict[str, dict] = {}
    started = time.monotonic()
    for n, (index, point) in enumerate(probes, 1):
        query_id = f"probe-{index}-{point}"
        query = base_query(game, query_id)
        color = game.moves[index][0]
        query["moves"] = query["moves"][:index] + [[color, sgf_to_gtp(point, game.size)]]
        query.update(
            {
                "analyzeTurns": [index + 1],
                "maxVisits": visits,
                "includeOwnership": True,
                "overrideSettings": {"humanSLProfile": profile},
            }
        )
        engine.send(query)
        out[f"{index}:{point}"] = engine.responses(query_id, 1, timeout=600.0)[0]
        _progress(n, len(probes), started)
    return out


def deep_responses(raw: dict) -> dict[int, dict]:
    return {int(k): v for k, v in raw.get("deep", {}).get("responses", {}).items()}


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
    write_raw(path, payload)


def write_raw(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)


def load_raw(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)
