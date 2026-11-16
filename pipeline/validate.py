"""Cross-checks the chosen key points with a deeper search and with stronger human profiles.

Two questions a non-player cannot answer by looking, but the engine can:

1. Stability: at several times the deep pass's visits, is the move still a loss of about the same
   size, and is the recommended move still (close to) the best?
2. Human level: would players a little and a lot stronger than the student play the recommended
   move (HumanSL policy)? If even 5-dan players rarely find it, it may be too hard to teach; if
   players at the student's own level usually play it, the mistake was a slip.

Results are cached in raw/<id>.json.gz under "checks"; the report is printed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from . import analyze, build, evaluate, facts, sgf
from .config import Config

CHECK_VISITS = 10000
STRONG_PROFILES = ["rank_1d", "rank_5d"]
LOSS_KEEP = 0.6  # the deeper loss should keep at least this share of the deep-pass loss ...
LOSS_SLACK = 2.0  # ... unless the difference is this small (points)
REC_GAP = 1.5  # points the recommended move may trail the deeper search's best
HARD_RANK = 8  # 5-dan players' policy ranks the recommended move below this ...
HARD_PROB = 0.03  # ... and gives it less than this: hard to teach


@dataclass
class Verdict:
    keypoint: dict
    deep_loss: float | None
    check_loss: float | None
    best_same: bool
    rec_gap: float | None
    human: dict[str, tuple[float, int]]  # profile -> (probability, rank) of the recommended move
    issues: list[str]
    notes: list[str]

    @property
    def ok(self) -> bool:
        return not self.issues


def _slim(resp: dict) -> dict:
    """Keeps what the checks use, so the cache stays small."""
    return {
        "turnNumber": resp["turnNumber"],
        "rootInfo": {k: resp["rootInfo"].get(k) for k in ("scoreLead", "winrate", "visits", "humanScoreStdev")},
        "moveInfos": [
            {k: m.get(k) for k in ("move", "scoreLead", "winrate", "visits", "order", "pv")}
            for m in resp.get("moveInfos", [])
        ],
    }


def _query(engine, game: sgf.Game, query_id: str, turns: list[int], visits: int, profile: str, policy: bool):
    query = analyze.base_query(game, query_id)
    query.update(
        {
            "analyzeTurns": turns,
            "maxVisits": visits,
            "includePolicy": policy,
            "overrideSettings": {"humanSLProfile": profile},
        }
    )
    engine.send(query)
    return engine.responses(query_id, len(turns), timeout=3600.0)


def run_checks(engine, game: sgf.Game, raw: dict, turns: set[int], human_turns: set[int], log=print) -> bool:
    """Fills raw["checks"] for missing turns; returns True if anything new was analysed."""
    checks = raw.setdefault("checks", {"visits": CHECK_VISITS, "responses": {}, "human": {}})
    missing = sorted(t for t in turns if str(t) not in checks["responses"])
    profiles = [analyze.student_profile(game, raw["studentColor"])] + STRONG_PROFILES
    missing_human = {
        p: sorted(t for t in human_turns if str(t) not in checks["human"].get(p, {})) for p in profiles
    }
    if not missing and not any(missing_human.values()):
        return False
    if missing:
        log(f"  复核 {len(missing)} 个局面（每个 {CHECK_VISITS} visits）……")
        started = time.monotonic()
        for r in _query(engine.get(), game, "check", missing, CHECK_VISITS, profiles[0], False):
            checks["responses"][str(r["turnNumber"])] = _slim(r)
        log(f"  用时 {time.monotonic() - started:.0f} 秒")
    for profile, todo in missing_human.items():
        if todo:
            store = checks["human"].setdefault(profile, {})
            for r in _query(engine.get(), game, f"human-{profile}", todo, 1, profile, True):
                store[str(r["turnNumber"])] = [round(v, 5) for v in r["humanPolicy"]]
    return True


def _rank_of(policy: list[float], point: str, size: int) -> tuple[float, int]:
    p = evaluate.policy_at(policy, point, size)
    return p, 1 + sum(1 for v in policy if v > p)


def judge(game: sgf.Game, raw: dict, data: dict) -> list[Verdict]:
    color = raw["studentColor"]
    size = game.size
    checks = raw.get("checks", {"responses": {}, "human": {}})
    resp = {int(k): v for k, v in checks["responses"].items()}
    deep = analyze.deep_responses(raw)
    student_profile = analyze.student_profile(game, color)
    out = []
    for k in data["keyPoints"]:
        i = k["position"]["moveIndex"]
        issues, notes = [], []
        sign = 1.0 if color == "B" else -1.0
        deep_loss = check_loss = rec_gap = None
        best_same = True
        if i in resp and i + 1 in resp:
            chk = evaluate.evaluate_move(i, color, k["played"], resp[i], resp[i + 1], size)
            before = deep.get(i)
            if before is not None:
                best_same = evaluate.gtp_sgf(before["moveInfos"][0]["move"], size) == chk.best
            rec = k["recommended"]["move"]
            info = evaluate.find_move(resp[i], rec, size)
            if info is not None and info["visits"] >= 30:
                rec_gap = max(0.0, chk.best_lead - sign * info["scoreLead"])
            if k["kind"] == "good":
                # The move played must still be (nearly) the best.
                if chk.score_loss > 1.0:
                    issues.append(f"深算后这手不再是好棋（离最好的一手差 {chk.score_loss:.1f} 目）")
            else:
                deep_loss = next(f["scoreLoss"] for f in k["facts"] if f["type"] == "loss")
                check_loss = chk.score_loss
                if check_loss < LOSS_KEEP * deep_loss and deep_loss - check_loss >= LOSS_SLACK:
                    issues.append(f"深算后损失变小：{deep_loss} 目 → {check_loss:.1f} 目")
                if rec_gap is None:
                    issues.append("深算几乎不考虑推荐的 A 点")
                elif rec_gap > REC_GAP:
                    issues.append(f"深算后推荐的 A 点比最好的一手差 {rec_gap:.1f} 目")
            if not best_same:
                notes.append("深算的首选点变了")
        else:
            notes.append("还没有复核数据")

        human: dict[str, tuple[float, int]] = {}
        point = k["played"] if k["kind"] == "good" else k["recommended"]["move"]
        for profile, store in checks.get("human", {}).items():
            policy = store.get(str(i))
            if policy:
                human[profile] = _rank_of(policy, point, size)
        strong = human.get(STRONG_PROFILES[-1])
        if strong and strong[1] > HARD_RANK and strong[0] < HARD_PROB:
            notes.append("连业余 5 段也很少下这里，可能偏难")
        mine = human.get(student_profile)
        if mine and mine[0] >= facts.SLIP_MANY and k["kind"] != "good":
            notes.append("同水平的人多数会下对，这次是一时疏忽")
        out.append(Verdict(k, deep_loss, check_loss, best_same, rec_gap, human, issues, notes))
    return out


def validate(cfg: Config, game_id: str, engine, log=print) -> list[Verdict]:
    raw_path = cfg.raw_dir / f"{game_id}.json.gz"
    raw = analyze.load_raw(raw_path)
    game = sgf.parse(raw["sgf"])
    plan = build.plan(game, raw)
    data = build.game_data(game_id, game, raw, plan)
    turns = {t for k in data["keyPoints"] for t in (k["position"]["moveIndex"], k["position"]["moveIndex"] + 1)}
    human_turns = {k["position"]["moveIndex"] for k in data["keyPoints"]}
    if engine is not None and run_checks(engine, game, raw, turns, human_turns, log):
        analyze.write_raw(raw_path, raw)
    return judge(game, raw, data)


def report(game_id: str, verdicts: list[Verdict], profiles: list[str], log=print) -> None:
    bad = sum(not v.ok for v in verdicts)
    log(f"== {game_id}：{len(verdicts)} 个关键点，{len(verdicts) - bad} 个通过，{bad} 个有问题")
    for v in verdicts:
        k = v.keypoint
        loss = (f"损失 {v.deep_loss}→{v.check_loss:.1f} 目" if v.check_loss is not None else "")
        gap = f"A 差 {v.rec_gap:.1f} 目" if v.rec_gap is not None else ""
        human = " ".join(
            f"{p}:{v.human[p][0]:.0%}(第{v.human[p][1]})" for p in profiles if p in v.human
        )
        log(f"  {'✓' if v.ok else '✗'} 第{k['move']:>3}手 {k['kind']:13} {loss:18} {gap:12} {human}")
        for text in v.issues:
            log(f"      ✗ {text}")
        for text in v.notes:
            log(f"      · {text}")
