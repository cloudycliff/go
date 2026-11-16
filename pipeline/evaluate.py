"""How much every move lost, in points and in the winning chance of players at the student's rank.

All values here are from the side that played the move. KataGo reports Black's view
(`reportAnalysisWinratesAs = BLACK`), so White's values are negated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .coords import gtp_to_xy, sgf_to_xy, xy_to_sgf

FALLBACK_STDEV = 12.0  # used when the HumanSL model reports no score spread
MIN_STDEV = 1.0  # below this the spread is noise
DECIDED = 0.05  # rank-aware chance below 5% or above 95%: judge by points instead


@dataclass(frozen=True)
class Thresholds:
    """Rank-aware winning-chance loss for each grade, and point loss once the game is decided."""

    inaccuracy: float = 0.05
    mistake: float = 0.10
    blunder: float = 0.20
    decided_inaccuracy: float = 5.0
    decided_mistake: float = 10.0
    decided_blunder: float = 20.0


SEVERITY_ORDER = {None: 0, "inaccuracy": 1, "mistake": 2, "blunder": 3}
SEVERITY_ZH = {"inaccuracy": "缓手", "mistake": "问题手", "blunder": "恶手"}


@dataclass
class MoveEval:
    index: int  # 0-based; the move is played in position `index` and leads to `index + 1`
    color: str
    point: str  # SGF, "" for a pass
    best: str  # SGF of the engine's first choice
    best_lead: float  # points ahead after the best move
    played_lead: float  # points ahead after the move played
    source: str  # "search": the played move's own search; "next": the next position's root
    stdev: float
    chance_before: float  # rank-aware winning chance with the best move
    chance_after: float  # ... with the move played
    played_prior: float  # how often players at the profile's rank play this move
    best_prior: float
    human_top: str  # the move players at the profile's rank play most often
    thresholds: Thresholds

    @property
    def number(self) -> int:
        return self.index + 1

    @property
    def score_loss(self) -> float:
        return max(0.0, self.best_lead - self.played_lead)

    @property
    def rank_loss(self) -> float:
        return max(0.0, self.chance_before - self.chance_after)

    @property
    def decided(self) -> bool:
        return self.chance_before < DECIDED or self.chance_before > 1 - DECIDED

    @property
    def is_best(self) -> bool:
        return self.point == self.best

    @property
    def severity(self) -> str | None:
        t = self.thresholds
        if self.decided:
            if self.score_loss >= t.decided_blunder:
                return "blunder"
            if self.score_loss >= t.decided_mistake:
                return "mistake"
            if self.score_loss >= t.decided_inaccuracy:
                return "inaccuracy"
            return None
        if self.rank_loss >= t.blunder:
            return "blunder"
        if self.rank_loss >= t.mistake:
            return "mistake"
        if self.rank_loss >= t.inaccuracy:
            return "inaccuracy"
        return None

    @property
    def weight(self) -> float:
        """A single number to rank mistakes by: the rank-aware loss, or points once decided."""
        if self.decided:
            return self.score_loss / (self.thresholds.decided_mistake / self.thresholds.mistake)
        return self.rank_loss


def rank_chance(lead: float, stdev: float | None) -> float:
    """The chance a player at the profile's rank goes on to win when leading by `lead` points."""
    s = stdev if stdev and math.isfinite(stdev) and stdev > 0 else FALLBACK_STDEV
    s = max(MIN_STDEV, s)
    return 0.5 * (1.0 + math.erf(lead / s / math.sqrt(2.0)))


def gtp_sgf(move: str, size: int) -> str:
    return xy_to_sgf(gtp_to_xy(move, size))


def policy_at(policy: list[float] | None, point: str, size: int) -> float:
    """The probability of an SGF move in a KataGo policy array (row-major from the top; pass last)."""
    if not policy:
        return 0.0
    xy = sgf_to_xy(point, size)
    i = size * size if xy is None else xy[1] * size + xy[0]
    return max(0.0, policy[i]) if i < len(policy) else 0.0


def policy_top(policy: list[float] | None, size: int) -> str:
    if not policy:
        return ""
    i = max(range(len(policy)), key=lambda k: policy[k])
    if i >= size * size:
        return ""
    return xy_to_sgf((i % size, i // size))


def find_move(response: dict, point: str, size: int) -> dict | None:
    for info in response.get("moveInfos", []):
        if gtp_sgf(info["move"], size) == point:
            return info
    return None


def evaluate_move(
    index: int,
    color: str,
    point: str,
    before: dict,
    after: dict,
    size: int,
    thresholds: Thresholds = Thresholds(),
) -> MoveEval:
    sign = 1.0 if color == "B" else -1.0
    best = before["moveInfos"][0]
    best_point = gtp_sgf(best["move"], size)
    played = find_move(before, point, size)
    if played is not None and played["visits"] >= max(16, best["visits"] / 20):
        played_lead, source = sign * played["scoreLead"], "search"
    else:
        played_lead, source = sign * after["rootInfo"]["scoreLead"], "next"
    best_lead = sign * best["scoreLead"]
    if point == best_point:
        played_lead = best_lead
    stdev = before["rootInfo"].get("humanScoreStdev")
    human = before.get("humanPolicy")
    return MoveEval(
        index=index,
        color=color,
        point=point,
        best=best_point,
        best_lead=best_lead,
        played_lead=played_lead,
        source=source,
        stdev=stdev if stdev else FALLBACK_STDEV,
        chance_before=rank_chance(best_lead, stdev),
        chance_after=rank_chance(played_lead, stdev),
        played_prior=policy_at(human, point, size),
        best_prior=policy_at(human, best_point, size),
        human_top=policy_top(human, size),
        thresholds=thresholds,
    )


def evaluate(game, responses: list[dict], thresholds: Thresholds = Thresholds()) -> list[MoveEval]:
    """One evaluation per move; responses[i] is the position before move i + 1."""
    return [
        evaluate_move(i, color, point, responses[i], responses[i + 1], game.size, thresholds)
        for i, (color, point) in enumerate(game.moves)
        if i + 1 < len(responses)
    ]


def move_value(response: dict, point: str, color: str, size: int, min_visits: int = 8) -> float | None:
    """Points ahead for `color` after playing `point`, when the search looked at it enough."""
    info = find_move(response, point, size)
    if info is None or info["visits"] < min_visits:
        return None
    return (1.0 if color == "B" else -1.0) * info["scoreLead"]


def phase(number: int) -> str:
    """Move number (1-based) to opening / middle / endgame."""
    if number < 60:
        return "opening"
    if number > 180:
        return "endgame"
    return "middle"
