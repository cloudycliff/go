"""Key-point candidates, merged into segments (one per fight), then the 4 + 1 shown to the child.

Calibration on the child's games (8K, HumanSL score spread 20-35 points before the endgame):
single moves rarely lose 10% rank-aware winning chance, but a lost fight is usually a run of
5-8% slips in one area. So every slip (>= 缓手) is a candidate, slips in one fight are merged,
and a segment is shown when its *net* loss reaches 问题手.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .board import distance
from .coords import sgf_to_xy
from .evaluate import SEVERITY_ORDER, MoveEval, Thresholds, move_value, phase, rank_chance

MERGE_GAP = 6  # moves between candidates in the same fight
MERGE_DISTANCE = 4  # lines between their points
URGENT_DISTANCE = 2  # the same urgent point: first choices at most this far apart
URGENT_TURNS = 3  # student turns that left it
URGENT_GAP = 10  # moves between two of those turns
URGENT_MIN_LOSS = 3.0  # points each of those turns lost
GOOD_PRIOR = 0.15  # players at the student's rank rarely find it ...
GOOD_NEAR_BEST = 0.5  # points from the engine's first choice
GOOD_PEER_LOSS = 0.05  # ... and their usual move loses this much winning chance
MAX_PER_PHASE = 3  # design said 2; 3 keeps the big middle-game fights (calibrated M2)
MAX_MISTAKES = 4
MAX_URGENT = 2  # "a big point left alone" is one lesson; do not repeat it
SMALL_GAME_PICKS = 2
DECIDED_DISCOUNT = 0.6  # ranking weight of segments that start after the game is decided

# When one segment holds several kinds, the story told is the most specific one.
KIND_PRIORITY = ["missed_punish", "mistake"]


@dataclass
class Candidate:
    kind: str  # mistake / missed_punish / missed_urgent / good
    index: int  # representative student move (0-based)
    turns: list[int]  # student moves involved
    weight: float
    extra: dict = field(default_factory=dict)


@dataclass
class Segment:
    kind: str
    index: int  # representative move: the one shown on the board
    turns: list[int]
    weight: float  # rank-aware loss (points / 100 once the game is decided)
    score_loss: float  # points
    severity: str | None
    candidates: list[Candidate]
    decided: bool = False  # the game was already decided when the segment started

    @property
    def priority(self) -> float:
        """Ranking value: once a game is decided, its mistakes no longer change the result."""
        return self.weight * (DECIDED_DISCOUNT if self.decided else 1.0)

    @property
    def span(self) -> tuple[int, int]:
        return min(self.turns), max(self.turns)

    def extra(self, key: str, default=None):
        for c in self.candidates:
            if key in c.extra:
                return c.extra[key]
        return default


@dataclass
class Selection:
    keypoints: list[Segment]
    small_game: bool  # no segment reached 问题手: the two biggest slips are shown instead


def _xy(point: str):
    return sgf_to_xy(point, 19) if point else None


def grade(weight: float, t: Thresholds) -> str | None:
    """Severity of a (merged) loss expressed as a weight; see MoveEval.weight."""
    if weight >= t.blunder:
        return "blunder"
    if weight >= t.mistake:
        return "mistake"
    if weight >= t.inaccuracy:
        return "inaccuracy"
    return None


def _urgent(evals: list[MoveEval], color: str) -> list[Candidate]:
    """The same urgent point left alone for several student turns."""
    runs: list[list[MoveEval]] = []
    open_runs: list[list[MoveEval]] = []
    for e in (e for e in evals if e.color == color):
        if e.best and distance(_xy(e.point), _xy(e.best)) <= 1:
            # Played at (or next to) its first choice: runs anchored there are over.
            open_runs = [r for r in open_runs if distance(_xy(r[0].best), _xy(e.best)) > URGENT_DISTANCE]
            continue
        open_runs = [r for r in open_runs if e.index - r[-1].index <= URGENT_GAP]
        if not e.best or e.score_loss < URGENT_MIN_LOSS:
            continue
        run = next(
            (r for r in open_runs if distance(_xy(r[0].best), _xy(e.best)) <= URGENT_DISTANCE), None
        )
        if run is None:
            run = []
            open_runs.append(run)
            runs.append(run)
        run.append(e)
    out = []
    for run in runs:
        if len(run) < URGENT_TURNS:
            continue
        rep = max(run, key=lambda r: r.weight)
        opponent_missed = [
            o.index
            for o in evals
            if o.color != color
            and run[0].index < o.index < run[-1].index
            and o.best
            and distance(_xy(o.best), _xy(run[0].best)) <= URGENT_DISTANCE
            and distance(_xy(o.point), _xy(o.best)) > 1
        ]
        # Leaving the point again does not lose it again: weigh the run by its worst turn.
        weight = rep.weight * min(1.5, 1 + 0.1 * (len(run) - 1))
        out.append(
            Candidate(
                "missed_urgent",
                rep.index,
                [r.index for r in run],
                weight,
                {"point": run[0].best, "opponentMissed": opponent_missed},
            )
        )
    return out


def candidates(
    evals: list[MoveEval],
    color: str,
    responses: list[dict],
    size: int,
    common_value: Callable[[MoveEval], float | None] | None = None,
) -> list[Candidate]:
    """All four kinds of candidate for the student playing `color`."""
    out: list[Candidate] = []
    by_index = {e.index: e for e in evals}

    for e in (e for e in evals if e.color == color):
        prev = by_index.get(e.index - 1)
        if (
            prev is not None
            and prev.color != color
            and SEVERITY_ORDER[prev.severity] >= SEVERITY_ORDER["mistake"]
            and not e.is_best
            and e.score_loss >= 0.5 * prev.score_loss
        ):
            out.append(
                Candidate(
                    "missed_punish",
                    e.index,
                    [e.index],
                    e.weight,
                    {"opponent": prev.index, "opponentLoss": prev.score_loss},
                )
            )
        elif e.severity is not None:
            out.append(Candidate("mistake", e.index, [e.index], e.weight))

    out += _urgent(evals, color)

    # Good moves: (nearly) the engine's choice where players at the student's rank usually play
    # something else that loses. The usual move's value comes from the search, or from a probe
    # (the position after it, analysed in the deep pass); unknown values stay as "needs probe".
    for e in (e for e in evals if e.color == color):
        if e.decided or e.score_loss > GOOD_NEAR_BEST or e.played_prior >= GOOD_PRIOR:
            continue
        if not e.human_top or e.human_top == e.point:
            continue
        lead = common_value(e) if common_value else None
        if lead is None:
            lead = move_value(responses[e.index], e.human_top, color, size)
        if lead is None:
            out.append(Candidate("good", e.index, [e.index], 0.0, {"common": e.human_top, "needsProbe": True}))
            continue
        peer_loss = e.chance_before - rank_chance(lead, e.stdev)
        if peer_loss >= GOOD_PEER_LOSS:
            out.append(
                Candidate(
                    "good",
                    e.index,
                    [e.index],
                    peer_loss,
                    {"common": e.human_top, "commonLoss": max(0.0, e.best_lead - lead)},
                )
            )
    return out


def _points(c: Candidate, by_index: dict[int, MoveEval]) -> list:
    pts = []
    for t in c.turns:
        e = by_index[t]
        pts += [_xy(e.point), _xy(e.best)]
    return [p for p in pts if p]


def _net(turns: list[int], by_index: dict[int, MoveEval], responses: list[dict], color: str):
    """Points and weight lost from before the first move to after the last one."""
    first, last = by_index[min(turns)], by_index[max(turns)]
    sign = 1.0 if color == "B" else -1.0
    after = sign * responses[last.index + 1]["rootInfo"]["scoreLead"]
    points = max(0.0, first.best_lead - after)
    if first.decided:
        weight = points / (first.thresholds.decided_mistake / first.thresholds.mistake)
    else:
        weight = max(0.0, first.chance_before - rank_chance(after, first.stdev))
    return points, weight


def segments(
    cands: list[Candidate], evals: list[MoveEval], responses: list[dict], color: str
) -> list[Segment]:
    """Merges slips in the same fight; urgent-point runs and good moves stay on their own."""
    by_index = {e.index: e for e in evals}
    thresholds = evals[0].thresholds if evals else Thresholds()
    urgent = [c for c in cands if c.kind == "missed_urgent"]
    in_urgent = {t for c in urgent for t in c.turns}
    bad = sorted(
        (c for c in cands if c.kind in ("mistake", "missed_punish") and c.index not in in_urgent),
        key=lambda c: c.index,
    )
    groups: list[list[Candidate]] = []
    for c in bad:
        if groups:
            last = groups[-1]
            last_end = max(t for g in last for t in g.turns)
            near = any(
                distance(p, q) <= MERGE_DISTANCE
                for g in last
                for p in _points(g, by_index)
                for q in _points(c, by_index)
            )
            if c.index - last_end <= MERGE_GAP and near:
                last.append(c)
                continue
        groups.append([c])

    out = []
    for g in groups:
        turns = sorted({t for c in g for t in c.turns})
        kind = next(k for k in KIND_PRIORITY if any(c.kind == k for c in g))
        rep = max(turns, key=lambda t: by_index[t].weight)
        biggest = by_index[rep]
        points, weight = _net(turns, by_index, responses, color)
        points, weight = max(points, biggest.score_loss), max(weight, biggest.weight)
        out.append(Segment(kind, rep, turns, weight, points, grade(weight, thresholds), g, by_index[turns[0]].decided))
    for c in urgent:
        e = by_index[c.index]
        out.append(
            Segment(
                "missed_urgent", c.index, c.turns, c.weight, e.score_loss, grade(c.weight, thresholds), [c],
                by_index[c.turns[0]].decided,
            )
        )
    for c in cands:
        if c.kind == "good":
            out.append(Segment("good", c.index, [c.index], c.weight, 0.0, None, [c]))
    return out


def select(segs: list[Segment], evals: list[MoveEval], color: str) -> Selection:
    """Up to four mistakes (at most three per phase), then one good move."""
    bad = sorted(
        (s for s in segs if s.kind != "good" and SEVERITY_ORDER[s.severity] >= SEVERITY_ORDER["mistake"]),
        key=lambda s: -s.priority,
    )
    chosen: list[Segment] = []
    per_phase: dict[str, int] = {}
    # First pass keeps the phases varied; the second fills free places with what is left.
    for cap in (MAX_PER_PHASE, MAX_MISTAKES):
        for s in bad:
            if len(chosen) == MAX_MISTAKES:
                break
            ph = phase(s.index + 1)
            if s in chosen or per_phase.get(ph, 0) >= cap:
                continue
            if any(set(s.turns) & set(c.turns) for c in chosen):
                continue
            if s.kind == "missed_urgent" and sum(c.kind == s.kind for c in chosen) >= MAX_URGENT:
                continue
            chosen.append(s)
            per_phase[ph] = per_phase.get(ph, 0) + 1
    small = not chosen
    if small:
        rest = sorted((s for s in segs if s.kind != "good" and s.score_loss >= 1.0), key=lambda s: -s.priority)
        chosen = rest[:SMALL_GAME_PICKS]
    chosen.sort(key=lambda s: s.index)
    taken = {t for s in chosen for t in s.turns}
    goods = sorted(
        (s for s in segs if s.kind == "good" and s.index not in taken and not s.extra("needsProbe")),
        key=lambda s: -s.weight,
    )
    if goods:
        chosen.append(goods[0])
    return Selection(chosen, small)


def pool(segs: list[Segment], mistakes: int = 10, goods: int = 6) -> list[Segment]:
    """The wider set of segments worth a deep look before the final choice."""
    bad = sorted((s for s in segs if s.kind != "good"), key=lambda s: -s.priority)[:mistakes]
    good = sorted(
        (s for s in segs if s.kind == "good"), key=lambda s: (-s.weight, bool(s.extra("needsProbe")))
    )[:goods]
    return bad + good
