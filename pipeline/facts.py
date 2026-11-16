"""Facts about one key point, all computed from KataGo data and replays on the board.

Facts are the only material the explanation may use (template or LLM). Points and groups that
facts talk about become board marks (A/B points, ▲/△ groups); text refers to marks, never to
coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .board import Board, other
from .coords import sgf_to_xy, xy_to_sgf
from .evaluate import find_move, gtp_sgf, phase, policy_at, policy_top

PV_LIMIT = 12  # moves of a variation replayed and shown
# A group "flips" when its owner's side of the ownership ends at <= -0.5 after falling by >= 0.8.
# (Design said 0.6 -> -0.3; on the child's games groups in a fight often start near +0.4.)
FLIP_TO = -0.5
FLIP_DELTA = 0.8
SAVED_BY_BEST = 0.5  # the group's ownership under the best move: "probably safe"
AREA_DELTA = 0.8  # an empty point changes hands: ownership moves by at least this much
AREA_MIN = 5  # empty points before an area change is worth saying
PEER_CLOSE = 1.0  # points: recommend the stronger players' move when it is this close to the AI's
PEER_MIN_VISITS = 16
MIN_CAPTURE = 2  # single stones taken somewhere in a long variation are mostly noise
# Players at the student's own level play the recommended move this often: the mistake was a slip.
SLIP_MANY = 0.25
SLIP_MOST = 0.5

STUDENT_LABELS = ["▲", "■"]
OPPONENT_LABELS = ["△", "□"]

REGIONS = {
    (0, 0): "左上", (1, 0): "上边", (2, 0): "右上",
    (0, 1): "左边", (1, 1): "中腹", (2, 1): "右边",
    (0, 2): "左下", (1, 2): "下边", (2, 2): "右下",
}  # fmt: skip


@dataclass
class KeyFacts:
    facts: list[dict] = field(default_factory=list)
    marks: list[dict] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)
    recommended: dict | None = None
    category: str = "territory"
    title: str = ""

    def add(self, type_: str, **values) -> dict:
        fact = {"id": f"f{len(self.facts) + 1}", "type": type_, **values}
        self.facts.append(fact)
        return fact

    def has(self, type_: str) -> bool:
        return any(f["type"] == type_ for f in self.facts)

    def mark_point(self, label: str, point: str, role: str) -> None:
        if point and not any(m.get("point") == point for m in self.marks):
            self.marks.append({"label": label, "type": "point", "point": point, "role": role})

    def mark_group(self, stones: set, student: bool) -> str:
        points = sorted(xy_to_sgf(p) for p in stones)
        for m in self.marks:
            if m["type"] == "group" and m["points"] == points:
                return m["label"]
        labels = STUDENT_LABELS if student else OPPONENT_LABELS
        used = {m["label"] for m in self.marks}
        label = next((lb for lb in labels if lb not in used), labels[-1])
        self.marks.append({"label": label, "type": "group", "points": points, "owner": "student" if student else "opponent"})
        return label


def region(points: list) -> tuple[str, int]:
    """The board region (左上 ... 右下) holding most of the points, and how many it holds."""
    third = lambda v: 0 if v < 6 else 2 if v > 12 else 1  # noqa: E731
    counts: dict[str, int] = {}
    for x, y in points:
        name = REGIONS[(third(x), third(y))]
        counts[name] = counts.get(name, 0) + 1
    name = max(counts, key=counts.get)
    return name, counts[name]


def pv_moves(start_color: str, pv: list[str], size: int, limit: int = PV_LIMIT) -> list[tuple[str, str]]:
    out, color = [], start_color
    for move in pv[:limit]:
        out.append((color, gtp_sgf(move, size)))
        color = other(color)
    return out


def replay(board: Board, moves: list[tuple[str, str]]) -> tuple[Board, dict[str, set]]:
    """Plays a variation; returns the final board and the stones each color lost."""
    b = board.copy()
    lost: dict[str, set] = {"B": set(), "W": set()}
    for color, point in moves:
        try:
            captured = b.play_sgf(color, point)
        except ValueError:
            break
        lost[other(color)] |= captured
    return b, lost


def _own(ownership: list[float] | None, p, size: int, sign: float) -> float:
    if not ownership:
        return 0.0
    return sign * ownership[p[1] * size + p[0]]


def flips(board: Board, before: list[float], after: list[float], student: str, size: int):
    """Groups (2+ stones) on `board` that change hands from the student's point of view.

    Returns (student groups that die, opponent groups that come back to life), each as a list of
    (stones, student-side ownership before) pairs.
    """
    sign = 1.0 if student == "B" else -1.0
    dies, lives = [], []
    for color, stones, _ in board.groups():
        if len(stones) < 2:
            continue
        own_before = sum(_own(before, p, size, sign) for p in stones) / len(stones)
        own_after = sum(_own(after, p, size, sign) for p in stones) / len(stones)
        # From the student's side the rule is the same for both colors: a student group dies, or
        # an opponent group that could have been captured comes back to life.
        if own_after <= FLIP_TO and own_before - own_after >= FLIP_DELTA:
            (dies if color == student else lives).append((stones, own_before))
    return dies, lives


def area_change(board: Board, before: list[float], after: list[float], student: str, size: int):
    """Empty points whose ownership swings against the student; None if too few."""
    sign = 1.0 if student == "B" else -1.0
    points = [
        (x, y)
        for x in range(size)
        for y in range(size)
        if (x, y) not in board.stones
        and _own(before, (x, y), size, sign) - _own(after, (x, y), size, sign) >= AREA_DELTA
    ]
    return points if len(points) >= AREA_MIN else None


def category(board: Board, before, after, number: int, score_loss: float, size: int) -> str:
    """Where the ownership changed: on stones (life and death) or on empty points (territory)."""
    if not before or not after:
        return "territory"
    on_stones = on_empty = 0.0
    for x in range(size):
        for y in range(size):
            delta = abs(before[y * size + x] - after[y * size + x])
            if (x, y) in board.stones:
                on_stones += delta
            else:
                on_empty += delta
    ph = phase(number)
    if ph == "endgame" and score_loss < 10:
        return "endgame"
    if on_stones >= on_empty:
        return "life_death"
    return "big_point" if ph == "opening" else "territory"


def _atari_groups(board: Board, color: str) -> list[set]:
    return [stones for c, stones, libs in board.groups(color) if len(libs) == 1]


def mistake_facts(
    *,
    kind: str,
    student: str,
    size: int,
    number: int,
    played: str,
    move_loss: float,
    severity: str | None,
    segment_moves: int,
    segment_loss: float,
    segment_severity: str | None = None,
    before_board: Board,
    after_board: Board,
    before: dict,
    after: dict,
    peer_policy: list[float] | None,
    level_policy: list[float] | None = None,
    urgent_point: str | None = None,
    urgent_turns: int = 0,
    opponent_missed: bool = False,
    opponent_loss: float | None = None,
) -> KeyFacts:
    """Facts for a mistake, a missed punishment or a missed urgent point."""
    k = KeyFacts()
    opponent = other(student)
    k.mark_point("✕", played, "played")

    # What to recommend: the AI's choice, or the stronger players' choice when it is close.
    best = gtp_sgf(before["moveInfos"][0]["move"], size)
    sign = 1.0 if student == "B" else -1.0
    best_lead = sign * before["moveInfos"][0]["scoreLead"]
    rec, source = best, "ai"
    if kind == "missed_urgent" and urgent_point:
        rec = urgent_point if find_move(before, urgent_point, size) else best
        source = "urgent"
    peer = policy_top(peer_policy, size)
    peer_info = find_move(before, peer, size) if peer else None
    peer_diff = None
    if peer_info is not None and peer_info["visits"] >= PEER_MIN_VISITS:
        peer_diff = max(0.0, best_lead - sign * peer_info["scoreLead"])
    if source == "ai" and peer and peer != best and peer != played and peer_diff is not None and peer_diff <= PEER_CLOSE:
        rec, source = peer, "peer"
    k.mark_point("A", rec, "recommended")
    if rec != best and best != played:
        k.mark_point("B", best, "ai_best")
    k.recommended = {"move": rec, "source": source}

    k.add("loss", scoreLoss=round(move_loss), severity=severity)
    if segment_moves > 1 and round(segment_loss) > round(move_loss):
        k.add("segment_loss", moves=segment_moves, scoreLoss=round(segment_loss), severity=segment_severity)
    if kind == "missed_punish" and opponent_loss is not None:
        k.add("opponent_mistake", scoreLoss=round(opponent_loss))
    if kind == "missed_urgent":
        k.add("missed_urgent", mark="A", turns=urgent_turns, opponentMissed=opponent_missed)

    # The opponent's best answer to the move played.
    refute = after["moveInfos"][0].get("pv", []) if after.get("moveInfos") else []
    refute_moves = [(student, played)] + pv_moves(opponent, refute, size)
    _, refute_lost = replay(after_board, refute_moves[1:])
    lost_mine = {p for p in refute_lost[student] if before_board.get(p) == student}
    if len(lost_mine) < MIN_CAPTURE:
        lost_mine = set()
    k.lines.append({"name": "实战后对方的应法", "moves": [p for _, p in refute_moves]})

    # The recommended line.
    rec_info = find_move(before, rec, size)
    rec_pv = rec_info.get("pv", [rec]) if rec_info else [rec]
    rec_moves = pv_moves(student, rec_pv, size)
    rec_board, rec_lost = replay(before_board, rec_moves)
    k.lines.append({"name": "推荐下法", "moves": [p for _, p in rec_moves]})

    played_xy = sgf_to_xy(played, size)
    for stones in _atari_groups(before_board, student):
        still = after_board.group(next(iter(stones)))
        if still[0] and len(still[1]) == 1 and stones & lost_mine:
            label = k.mark_group(stones, True)
            k.add("atari_ignored", mark=label, count=len(stones))
            break
    if played_xy and not k.has("atari_ignored"):
        stones, libs = after_board.group(played_xy)
        shown = {p for p in stones if before_board.get(p) == student}
        if len(stones) >= 2 and len(libs) == 1 and shown and shown <= lost_mine:
            label = k.mark_group(shown, True)
            k.add("self_atari", mark=label, count=len(stones))
    if lost_mine:
        label = k.mark_group(lost_mine, True)
        k.add("refute_capture", mark=label, count=len(lost_mine))
        saved = {p for p in lost_mine if rec_board.get(p) == student}
        if saved == lost_mine and rec != played:
            k.add("best_save", mark=label, count=len(saved), moveMark="A")
    taken = {p for p in rec_lost[opponent] if before_board.get(p) == opponent}
    if len(taken) >= MIN_CAPTURE:
        label = k.mark_group(taken, False)
        k.add("best_capture", mark=label, count=len(taken), moveMark="A")

    own_before, own_after = before.get("ownership"), after.get("ownership")
    if own_before and own_after:
        dies, lives = flips(after_board, own_before, own_after, student, size)
        # Only stones already on the board in the position shown can carry a mark.
        for stones, _ in sorted(dies, key=lambda d: len(d[0]), reverse=True)[:1]:
            shown = {p for p in stones if before_board.get(p) == student}
            if len(shown) >= 2:
                label = k.mark_group(shown, True)
                k.add("group_dies", mark=label, count=len(shown))
        for stones, _ in sorted(lives, key=lambda d: len(d[0]), reverse=True)[:1]:
            shown = {p for p in stones if before_board.get(p) == opponent}
            if len(shown) >= 2:
                label = k.mark_group(shown, False)
                k.add("group_lives", mark=label, count=len(shown))
        area = area_change(after_board, own_before, own_after, student, size)
        if area:
            name, count = region(area)
            if count >= AREA_MIN:
                k.marks.append({"label": "", "type": "area", "points": sorted(xy_to_sgf(p) for p in area)})
                k.add("area_flip", count=count, region=name)
        k.category = category(after_board, own_before, own_after, number, move_loss, size)
    if any(k.has(t) for t in ("group_dies", "group_lives", "refute_capture", "best_capture", "atari_ignored")):
        k.category = "life_death"

    if peer and peer_diff is not None:
        if peer == rec:
            if source == "peer":
                k.add("peer_choice", mark="A", sameAsAi=False, diff=round(peer_diff, 1), aiMark="B")
            else:
                k.add("peer_choice", mark="A", sameAsAi=True)
    # How often players at the student's own level find A: often means this was a slip.
    level = policy_at(level_policy, rec, size) if level_policy else 0.0
    if level >= SLIP_MANY and rec != played:
        k.add("slip", mark="A", share="most" if level >= SLIP_MOST else "many")
    k.add("phase", phase=phase(number), category=k.category)
    k.title = title(kind, k)
    return k


def good_facts(
    *,
    student: str,
    size: int,
    number: int,
    played: str,
    common: str,
    common_loss: float,
    before_board: Board,
    before: dict,
    probe: dict | None,
) -> KeyFacts:
    """Facts for a good move: the engine's choice that players at the student's rank rarely find."""
    k = KeyFacts()
    opponent = other(student)
    k.mark_point("A", played, "played_good")
    k.mark_point("B", common, "common")
    k.recommended = {"move": played, "source": "played"}
    k.add("good_move", mark="A")
    k.add("common_move", mark="B", scoreLoss=round(common_loss))

    info = find_move(before, played, size)
    good_pv = info.get("pv", [played]) if info else [played]
    good_moves = pv_moves(student, good_pv, size)
    _, good_lost = replay(before_board, good_moves)
    k.lines.append({"name": "实战（好棋）", "moves": [p for _, p in good_moves]})
    common_moves = [(student, common)]
    if probe and probe.get("moveInfos"):
        common_moves += pv_moves(opponent, probe["moveInfos"][0].get("pv", []), size)
    common_board, common_lost = replay(before_board, common_moves)
    k.lines.append({"name": "常见下法", "moves": [p for _, p in common_moves]})

    taken = {p for p in good_lost[opponent] if before_board.get(p) == opponent}
    if len(taken) >= MIN_CAPTURE:
        label = k.mark_group(taken, False)
        k.add("best_capture", mark=label, count=len(taken), moveMark="A")
    lost = {p for p in common_lost[student] if before_board.get(p) == student}
    if len(lost) >= MIN_CAPTURE:
        label = k.mark_group(lost, True)
        k.add("common_capture", mark=label, count=len(lost), moveMark="B")
    if probe and before.get("ownership") and probe.get("ownership"):
        after_common = before_board.copy()
        after_common.play_sgf(student, common)
        dies, _ = flips(after_common, before["ownership"], probe["ownership"], student, size)
        for stones, _ in sorted(dies, key=lambda d: len(d[0]), reverse=True)[:1]:
            shown = {p for p in stones if before_board.get(p) == student}
            if len(shown) >= 2:
                label = k.mark_group(shown, True)
                k.add("common_group_dies", mark=label, count=len(shown), moveMark="B")
        k.category = category(after_common, before["ownership"], probe["ownership"], number, common_loss, size)
    k.add("phase", phase=phase(number), category=k.category)
    k.title = "这手下得好"
    return k


def title(kind: str, k: KeyFacts) -> str:
    """Card title, shown with the question: it must not mention marks (they appear with the answer)."""
    if kind == "missed_urgent":
        return "这里有一个急所"
    if kind == "missed_punish":
        return "对方给了你机会"
    if k.has("group_dies") or k.has("refute_capture") or k.has("atari_ignored"):
        return "有一块棋危险了"
    if k.has("group_lives") or k.has("best_capture"):
        return "本来可以吃掉对方的棋"
    if k.has("area_flip"):
        region_ = next(f["region"] for f in k.facts if f["type"] == "area_flip")
        return f"{region_}的地很大"
    return "有更好的下法"
