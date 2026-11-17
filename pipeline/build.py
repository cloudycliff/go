"""From a raw analysis to the review page data: evaluation, key points, deep pass, facts, text.

    raw/<id>.json.gz  ->  site/data/games/<id>.json  and  site/data/index.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from . import analyze, board, evaluate, facts, keypoints, narrate_template, sgf
from .config import ROOT, Config
from .katago import KataGo

SITE = ROOT / "site"
SCHEMA_VERSION = 1
DEEP_ROUNDS = 3  # deep pass, re-select, deep pass again for newly chosen positions ...
# Territory on the page: each point's owner (Black positive) as one letter, -1..1 in 2*OWN_STEPS+1 steps.
OWN_STEPS = 9
OWN_LETTERS = "abcdefghijklmnopqrs"  # "a" = surely White's, "j" = nobody's, "s" = surely Black's


class LazyEngine:
    """Starts KataGo only when the deep pass actually needs it."""

    def __init__(self, cfg: Config, log=print) -> None:
        self.cfg, self.log, self.engine = cfg, log, None

    def get(self) -> KataGo:
        if self.engine is None:
            self.log("启动 KataGo……")
            self.engine = KataGo(self.cfg.katago)
            self.engine.version()
        return self.engine

    def close(self) -> None:
        if self.engine is not None:
            self.engine.close()


@dataclass
class Plan:
    evals: list[evaluate.MoveEval]
    responses: list[dict]  # best available response per position (deep, else overview)
    segments: list[keypoints.Segment]
    selection: keypoints.Selection
    turns: set[int]  # positions the deep pass should cover
    probes: set[tuple[int, str]]  # (move index, point) of moves not played that the facts look at


def _sign(color: str) -> float:
    return 1.0 if color == "B" else -1.0


def evaluations(game: sgf.Game, raw: dict) -> tuple[list[evaluate.MoveEval], list[dict]]:
    """Per-move evaluations, using the deep pass wherever it covers both positions.

    The score spread and how often players play a move always come from the overview pass,
    which used the student's own HumanSL profile (the deep pass uses the stronger peer profile).
    """
    overview = raw["overview"]["responses"]
    deep = analyze.deep_responses(raw)
    out = []
    for e in evaluate.evaluate(game, overview):
        i = e.index
        if i in deep and i + 1 in deep:
            d = evaluate.evaluate_move(i, e.color, e.point, deep[i], deep[i + 1], game.size)
            e = replace(
                d,
                stdev=e.stdev,
                chance_before=evaluate.rank_chance(d.best_lead, e.stdev),
                chance_after=evaluate.rank_chance(d.played_lead, e.stdev),
                played_prior=e.played_prior,
                best_prior=e.best_prior,
                human_top=e.human_top,
            )
        out.append(e)
    responses = [deep.get(i, r) for i, r in enumerate(overview)]
    return out, responses


def plan(game: sgf.Game, raw: dict) -> Plan:
    color = raw["studentColor"]
    evals, responses = evaluations(game, raw)
    probes = raw.get("probes", {})

    def common_value(e: evaluate.MoveEval) -> float | None:
        r = probes.get(f"{e.index}:{e.human_top}")
        return _sign(e.color) * r["rootInfo"]["scoreLead"] if r else None

    cands = keypoints.candidates(evals, color, responses, game.size, common_value)
    segs = keypoints.segments(cands, evals, responses, color)
    selection = keypoints.select(segs, evals, color)
    turns: set[int] = set()
    wanted: set[tuple[int, str]] = set()
    by_index = {e.index: e for e in evals}
    urgent = {c.index: c.extra.get("point") for c in cands if c.kind == "missed_urgent"}
    for s in keypoints.pool(segs) + selection.keypoints:
        turns |= {s.index, s.index + 1}
        if s.kind == "good":
            wanted.add((s.index, s.extra("common")))
            continue
        # The position after the recommended move, to compare it with the move played.
        e = by_index[s.index]
        choice = facts.recommend(
            kind=s.kind, played=e.point, before=responses[s.index],
            peer_policy=raw.get("deep", {}).get("responses", {}).get(str(s.index), {}).get("humanPolicy"),
            urgent_point=urgent.get(s.index), size=game.size, student=color,
        )
        if choice.move and choice.move != e.point:
            wanted.add((s.index, choice.move))
    return Plan(evals, responses, segs, selection, turns, wanted)


def ensure_deep(cfg: Config, game: sgf.Game, raw: dict, raw_path: Path, engine: LazyEngine | None, log=print) -> Plan:
    """Runs the deep pass (and probes) until every chosen key point is covered."""
    current = plan(game, raw)
    for _ in range(DEEP_ROUNDS):
        done = analyze.deep_responses(raw)
        turns = sorted(t for t in current.turns if t not in done and t <= len(game.moves))
        probes = sorted(p for p in current.probes if f"{p[0]}:{p[1]}" not in raw.get("probes", {}))
        if not turns and not probes:
            break
        if engine is None:
            log(f"  还有 {len(turns)} 个局面没有深度分析（未启动 KataGo），先用整盘分析的数据。")
            break
        if turns:
            log(f"深度分析 {len(turns)} 个关键局面（每个 {cfg.deep_visits} visits）")
            responses, params = analyze.deep(
                engine.get(), game, raw["studentColor"], turns, cfg.deep_visits, cfg.peer_steps
            )
            analyze.add_deep(raw, responses, params)
        if probes:
            log(f"试下 {len(probes)} 个局面（推荐点和常见下法）")
            # Same depth as the deep pass: the comparison needs the two searches to be as exact.
            raw.setdefault("probes", {}).update(
                analyze.probe(engine.get(), game, raw["studentColor"], probes, max(800, cfg.deep_visits))
            )
        analyze.write_raw(raw_path, raw)
        current = plan(game, raw)
    return current


def _rank(r) -> str:
    return r.label_zh() if r else ""


def _result(game: sgf.Game, color: str) -> str:
    re = game.result.strip().upper()
    if re.startswith(("B+", "W+")):
        return "win" if re[0] == color else "lose"
    return "draw" if re.startswith(("0", "DRAW", "JIGO")) else "unknown"


def keypoint_data(n: int, seg: keypoints.Segment, game: sgf.Game, raw: dict, p: Plan, boards) -> dict:
    color = raw["studentColor"]
    i = seg.index
    by_index = {e.index: e for e in p.evals}
    e = by_index[i]
    deep = analyze.deep_responses(raw)
    before, after = p.responses[i], p.responses[i + 1]
    number = i + 1
    point = game.moves[i][1]
    if seg.kind == "good":
        common = seg.extra("common")
        k = facts.good_facts(
            student=color,
            size=game.size,
            number=number,
            played=point,
            common=common,
            common_loss=seg.extra("commonLoss", 0.0),
            before_board=boards[i],
            before=before,
            probe=raw.get("probes", {}).get(f"{i}:{common}"),
        )
    else:
        opponent = seg.extra("opponent")
        peer_policy = deep[i].get("humanPolicy") if i in deep else None
        choice = facts.recommend(
            kind=seg.kind, played=point, before=before, peer_policy=peer_policy,
            urgent_point=seg.extra("point"), size=game.size, student=color,
        )
        k = facts.mistake_facts(
            kind=seg.kind,
            student=color,
            size=game.size,
            number=number,
            played=point,
            move_loss=e.score_loss,
            # An urgent-point run is graded as a whole, like a merged segment.
            severity=seg.severity if seg.kind == "missed_urgent" else e.severity,
            segment_moves=len(seg.turns),
            segment_loss=seg.score_loss,
            segment_severity=seg.severity,
            before_board=boards[i],
            after_board=boards[i + 1],
            before=before,
            after=after,
            peer_policy=peer_policy,
            # The overview pass used the student's own HumanSL profile.
            level_policy=raw["overview"]["responses"][i].get("humanPolicy"),
            urgent_point=seg.extra("point"),
            urgent_turns=len(seg.turns),
            opponent_missed=bool(seg.extra("opponentMissed")),
            opponent_loss=by_index[opponent].score_loss if opponent is not None else None,
            probe_a=raw.get("probes", {}).get(f"{i}:{choice.move}"),
        )
    explain = narrate_template.explain(seg.kind, k.category, k.facts, k.recommended or {}, k.candidates)
    return {
        "id": f"k{n}",
        "kind": seg.kind,
        "title": k.title,
        "move": number,
        "span": [seg.span[0] + 1, seg.span[1] + 1],
        "moves": [t + 1 for t in seg.turns],
        "phase": evaluate.phase(number),
        "category": k.category,
        "severity": seg.severity,
        "scoreLoss": round(seg.score_loss, 1),
        "rankAwareLoss": round(seg.weight, 3),
        "deep": i in deep and i + 1 in deep,
        "position": {"moveIndex": i},
        "marks": k.marks,
        "candidates": k.candidates,
        "played": point,
        "recommended": k.recommended,
        "lines": k.lines,
        "facts": k.facts,
        "explain": {"template": explain["template"], "tip": explain["tip"]},
    }


def game_data(game_id: str, game: sgf.Game, raw: dict, p: Plan) -> dict:
    color = raw["studentColor"]
    boards = board.positions(game)
    overview = raw["overview"]
    sign = _sign(color)
    kps = [keypoint_data(n, s, game, raw, p, boards) for n, s in enumerate(p.selection.keypoints, 1)]
    me, opp = {"name": "我"}, None
    players = {
        "B": {"name": game.black, "rank": _rank(game.black_rank)},
        "W": {"name": game.white, "rank": _rank(game.white_rank)},
    }
    # The child's own nickname stays out of the public site.
    players[color] = {**me, "rank": players[color]["rank"]}
    opp = players["W" if color == "B" else "B"]
    deep = raw.get("deep", {}).get("params", {})
    return {
        "schemaVersion": SCHEMA_VERSION,
        "game": {
            "id": game_id,
            "date": game.date,
            "board": game.size,
            "komi": game.komi,
            "rules": game.rules,
            "handicap": game.handicap,
            "setup": {"B": game.setup_black, "W": game.setup_white},
            "black": players["B"],
            "white": players["W"],
            "opponent": opp,
            "studentColor": color,
            "result": game.result,
            "outcome": _result(game, color),
            "moves": [[c, pt] for c, pt in game.moves],
        },
        "analysis": {
            "katago": raw["engine"].get("version"),
            "model": raw["engine"].get("model"),
            "humanProfile": overview["params"].get("humanSLProfile"),
            "peerProfile": deep.get("humanSLProfile"),
            "visits": [overview["params"].get("visits"), deep.get("visits")],
            "analyzedAt": raw.get("analyzedAt"),
        },
        "curve": [
            {"move": i, "scoreLead": round(sign * r["rootInfo"]["scoreLead"], 1)}
            for i, r in enumerate(overview["responses"])
        ],
        "smallGame": p.selection.small_game,
        "summary": narrate_template.summary(kps, p.selection.small_game),
        "keyPoints": kps,
    }


def index_entry(data: dict) -> dict:
    g = data["game"]
    return {
        "id": g["id"],
        "date": g["date"],
        "opponent": g["opponent"]["name"],
        "opponentRank": g["opponent"]["rank"],
        "color": g["studentColor"],
        "result": g["outcome"],
        "resultText": g["result"],
        "moveCount": len(g["moves"]),
        "keyPointCount": len(data["keyPoints"]),
        "summary": data["summary"],
    }


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def write_site(data: dict, site: Path = SITE) -> Path:
    path = site / "data" / "games" / f"{data['game']['id']}.json"
    _write_json(path, data)
    index_path = site / "data" / "index.json"
    entries = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    entries = [e for e in entries if e["id"] != data["game"]["id"]] + [index_entry(data)]
    entries.sort(key=lambda e: (e["date"], e["id"]), reverse=True)
    _write_json(index_path, entries)
    return path


def territory_text(ownership: list[float] | None) -> str | None:
    """One letter per point, row by row from the top: who owns it and how surely."""
    if not ownership:
        return None
    return "".join(OWN_LETTERS[round(max(-1.0, min(1.0, v)) * OWN_STEPS) + OWN_STEPS] for v in ownership)


def wanted_lines(data: dict) -> list[tuple[int, str, list[str]]]:
    """The variations the page shows: (move index, colour of the first move, SGF moves)."""
    moves = data["game"]["moves"]
    out = []
    for k in data["keyPoints"]:
        i = k["position"]["moveIndex"]
        for line in k["lines"]:
            if line["moves"]:
                out.append((i, moves[i][0], line["moves"]))
    return out


def ensure_lines(cfg: Config, game: sgf.Game, raw: dict, raw_path: Path, data: dict,
                 engine: LazyEngine | None, log=print) -> None:
    """Analyses every step of the variations shown, for the territory view (cached in raw["lines"])."""
    have = raw.get("lines", {})
    missing = [w for w in wanted_lines(data) if analyze.line_key(*w) not in have]
    missing = list({analyze.line_key(*w): w for w in missing}.values())
    if not missing:
        return
    if engine is None:
        log(f"  还有 {len(missing)} 个变化没有形势数据（未启动 KataGo），这些变化不显示形势。")
        return
    log(f"分析 {len(missing)} 个变化的每一步，用于形势显示（每步 {cfg.overview_visits} visits）")
    got = analyze.lines(engine.get(), game, raw["studentColor"], missing, cfg.overview_visits, log)
    raw.setdefault("lines", {}).update(got)
    analyze.write_raw(raw_path, raw)


def add_territory(data: dict, raw: dict) -> None:
    """Territory for every position of the game and every step of each variation shown.

    Leads are from the student's side, like the curve; a variation without data gets null.
    """
    data["territory"] = [territory_text(r.get("ownership")) for r in raw["overview"]["responses"]]
    for k in data["keyPoints"]:
        k["territory"] = line_territory(k, data["game"]["moves"], raw)


def line_territory(k: dict, moves: list, raw: dict) -> list[dict | None]:
    """Lead (student's side) and territory after each step of each variation of a key point."""
    sign = _sign(raw["studentColor"])
    lines = raw.get("lines", {})
    i = k["position"]["moveIndex"]
    out = []
    for line in k["lines"]:
        got = lines.get(analyze.line_key(i, moves[i][0], line["moves"])) if line["moves"] else None
        out.append(None if not got else {
            "lead": [round(sign * v, 1) for v in got["scoreLead"]],
            "own": [territory_text(o) for o in got["ownership"]],
        })
    return out


def build(cfg: Config, game_id: str, engine: LazyEngine | None, log=print) -> dict:
    raw_path = cfg.raw_dir / f"{game_id}.json.gz"
    raw = analyze.load_raw(raw_path)
    game = sgf.parse(raw["sgf"])
    p = ensure_deep(cfg, game, raw, raw_path, engine, log)
    data = game_data(game_id, game, raw, p)
    ensure_lines(cfg, game, raw, raw_path, data, engine, log)
    add_territory(data, raw)
    path = write_site(data)
    log(f"已生成 {path.relative_to(ROOT)}：{len(data['keyPoints'])} 个关键点。{data['summary']}")
    return data
