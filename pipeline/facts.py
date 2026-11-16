"""Facts about one key point, all computed from KataGo data and replays on the board.

Facts are the only material the explanation may use. Points and groups that
facts talk about become board marks (A/B points, ▲/△ groups); text refers to marks, never to
coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .board import Board, distance, other
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
NEAR_LIBS = 3  # "A touches a group with only N liberties" is worth saying up to this many
FAR_AWAY = 6  # lines between ✕ and A before "you played elsewhere" is said
CLOSE_POINTS = 2.0  # moves within this many points of the best get a mark (C, D) and a table row
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
    candidates: list[dict] = field(default_factory=list)  # every rated point, for the page's table
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

    def mark_group(self, stones: set, student: bool) -> str | None:
        """The group's label (reused if it is already marked); None when the labels run out."""
        points = sorted(xy_to_sgf(p) for p in stones)
        for m in self.marks:
            if m["type"] == "group" and m["points"] == points:
                return m["label"]
        labels = STUDENT_LABELS if student else OPPONENT_LABELS
        used = {m["label"] for m in self.marks}
        label = next((lb for lb in labels if lb not in used), None)
        if label is None:
            return None
        self.marks.append({"label": label, "type": "group", "points": points, "owner": "student" if student else "opponent"})
        return label

    def group_fact(self, type_: str, stones: set, student: bool, **values) -> dict | None:
        """Adds a fact about a marked group; skipped when the group cannot get a label."""
        label = self.mark_group(stones, student)
        if label is None:
            return None
        return self.add(type_, mark=label, **values)


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


def near_group(k: KeyFacts, board: Board, point: str, student: str) -> None:
    """Why A matters, when the board shows it: A touches a group (2+ stones) short of liberties.

    Adds `rec_near_group` for the touching group with the fewest liberties (at most NEAR_LIBS).
    A group that A itself fills the last liberty of is a capture and is said elsewhere.
    """
    xy = sgf_to_xy(point, board.size) if point else None
    if xy is None or board.get(xy) is not None:
        return
    best = None
    for n in board.neighbors(xy):
        if board.get(n) is None:
            continue
        stones, libs = board.group(n)
        if len(stones) < 2 or len(libs) > NEAR_LIBS:
            continue
        if best is None or len(libs) < len(best[1]):
            best = (stones, libs, board.get(n))
    if best is None:
        return
    stones, libs, color = best
    k.group_fact(
        "rec_near_group", stones, color == student, pointMark="A",
        owner="student" if color == student else "opponent", liberties=len(libs), count=len(stones),
    )


def _touching(board: Board, xy) -> dict[str, list[tuple[set, set]]]:
    """Distinct groups touching an empty point, by color: (stones, liberties)."""
    out: dict[str, list[tuple[set, set]]] = {"B": [], "W": []}
    seen: set = set()
    for n in board.neighbors(xy):
        color = board.get(n)
        if color is None or n in seen:
            continue
        stones, libs = board.group(n)
        seen |= stones
        out[color].append((stones, libs))
    return out


def shape_facts(k: KeyFacts, board: Board, point: str, student: str, mark: str = "A") -> None:
    """What the move at `point` (A) does to the stones next to it, from the board alone.

    - `rec_connects`: A touches two of the student's groups, so it joins them;
    - `rec_cuts`: A touches two opponent groups (2+ stones each), so they can no longer join there;
    - `rec_atari` / `rec_presses`: after A an opponent group has 1 / 2 liberties (it had more).
    """
    xy = sgf_to_xy(point, board.size) if point else None
    if xy is None or board.get(xy) is not None:
        return
    opponent = other(student)
    near = _touching(board, xy)
    mine = sorted(near[student], key=lambda g: -len(g[0]))
    if len(mine) >= 2 and len(mine[0][0]) + len(mine[1][0]) >= 3:
        a = k.mark_group(mine[0][0], True)
        b = k.mark_group(mine[1][0], True)
        if a and b and a != b:
            k.add("rec_connects", mark=a, mark2=b, moveMark=mark)
    theirs = sorted((g for g in near[opponent] if len(g[0]) >= 2), key=lambda g: -len(g[0]))
    if len(theirs) >= 2:
        a = k.mark_group(theirs[0][0], False)
        b = k.mark_group(theirs[1][0], False)
        if a and b and a != b:
            k.add("rec_cuts", mark=a, mark2=b, moveMark=mark)
    after = board.copy()
    captured = after.play(student, xy)
    if captured:
        return  # a capture is told by best_capture
    squeezed = []
    for stones, libs in near[opponent]:
        if len(stones) < 2:
            continue
        left = after.group(next(iter(stones)))[1]
        if len(left) < len(libs) and len(left) <= 2:
            squeezed.append((len(left), -len(stones), stones))
    if squeezed:
        left, _, stones = min(squeezed, key=lambda s: (s[0], s[1]))
        if not any(f["type"] == "rec_near_group" and f["owner"] == "opponent" and f.get("liberties") == left
                   for f in k.facts):
            k.group_fact("rec_atari" if left == 1 else "rec_presses", stones, False, moveMark=mark, liberties=left)


def refute_squeeze(k: KeyFacts, before_board: Board, after_board: Board, reply: str, student: str) -> None:
    """After ✕, the opponent's best reply leaves one of the student's groups with 1-2 liberties."""
    xy = sgf_to_xy(reply, after_board.size) if reply else None
    if xy is None or after_board.get(xy) is not None:
        return
    board = after_board.copy()
    board.play(other(student), xy)
    worst = None
    for color, stones, libs in board.groups(student):
        shown = {p for p in stones if before_board.get(p) == student}
        if len(shown) < 2 or len(libs) > 2:
            continue
        had = after_board.group(next(iter(shown)))[1]
        if len(libs) >= len(had):
            continue
        if worst is None or (len(libs), -len(shown)) < (len(worst[1]), -len(worst[0])):
            worst = (shown, libs)
    if worst:
        k.group_fact("refute_squeeze", worst[0], True, liberties=len(worst[1]), count=len(worst[0]))


def where_facts(k: KeyFacts, after: dict, played: str, rec: str, size: int, prefix: str = "") -> None:
    """Where the move went compared with A, and whether A is where the opponent wants to play.

    For a good move the same questions are asked about the usual move B (prefix "common_"):
    B is far from A, and after B the opponent wants to play at A.
    """
    p, r = sgf_to_xy(played, size) if played else None, sgf_to_xy(rec, size) if rec else None
    if p and r and max(abs(p[0] - r[0]), abs(p[1] - r[1])) >= FAR_AWAY:
        played_region, rec_region = region([p])[0], region([r])[0]
        if played_region != rec_region:
            k.add(f"{prefix}far_away", playedMark="B" if prefix else "✕", playedRegion=played_region,
                  recRegion=rec_region, mark="A")
    if r and after and after.get("moveInfos"):
        reply = sgf_to_xy(gtp_sgf(after["moveInfos"][0]["move"], size), size)
        if reply and max(abs(reply[0] - r[0]), abs(reply[1] - r[1])) <= 1:
            k.add(f"{prefix}opponent_wants", mark="A", exact=reply == r, **({"commonMark": "B"} if prefix else {}))


@dataclass
class Recommend:
    best: str  # the engine's first choice (SGF)
    best_lead: float  # points ahead after it, from the student's side
    move: str  # what the page recommends
    source: str  # "ai" / "peer" / "urgent"
    peer: str  # the stronger players' usual move, "" when unknown
    peer_diff: float | None  # points between `best` and `peer`


def recommend(
    *, kind: str, played: str, before: dict, peer_policy: list[float] | None,
    urgent_point: str | None, size: int, student: str,
) -> Recommend:
    """Which move the page points at: the engine's choice, or the stronger players' when close."""
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
    return Recommend(best, best_lead, rec, source, peer, peer_diff)


def close_candidates(
    before: dict, k: KeyFacts, played: str, rec: str, best: str, size: int,
    student: str = "B", played_loss: float | None = None,
) -> list[dict]:
    """The rated points shown as a table: A, B, the move played ✕, and close alternatives C, D.

    `diff` is points behind the engine's first choice for the student, rounded to 0.1. Scores are
    Black's, so for White a higher score is worse and the subtraction is flipped. The move played
    uses `played_loss` (the loss the page text quotes) when given, since it is often searched
    too little in `before` to have a trustworthy score, or not at all. `first` marks the engine's
    first choice so the page can call only that row "最好".
    """
    sign = 1.0 if student == "B" else -1.0
    first = gtp_sgf(before["moveInfos"][0]["move"], size)
    top = before["moveInfos"][0]["scoreLead"]
    best_visits = before["moveInfos"][0]["visits"]
    rows: dict[str, float] = {}
    for info in before["moveInfos"][:10]:
        if info["visits"] < max(8, best_visits / 20):
            continue
        diff = round(max(0.0, sign * (top - info["scoreLead"])), 1)
        if diff <= CLOSE_POINTS:
            rows[gtp_sgf(info["move"], size)] = diff
    played_info = find_move(before, played, size)
    out: list[dict] = []
    shown = {rec, best, played}
    named = (
        ("A", rec, "recommended", "推荐"),
        ("B", best if rec != best else None, "ai_best", "AI 最喜欢"),
        ("✕", played, "played", "你下的"),
    )
    for label, point, role, note in named:
        if not point:
            continue
        if point == played and played_loss is not None:
            diff = round(max(0.0, played_loss), 1)
        elif point in rows:
            diff = rows[point]
        elif point == played and played_info:
            diff = round(max(0.0, sign * (top - played_info["scoreLead"])), 1)
        else:
            diff = None
        out.append({"label": label, "point": point, "diff": diff, "role": role, "note": note,
                    "first": point == first})
    extra = iter("CDE")
    for point, diff in sorted(rows.items(), key=lambda r: r[1]):
        if point in shown:
            continue
        label = next(extra, None)
        if label is None:
            break
        shown.add(point)
        k.mark_point(label, point, "alternative")
        out.append({"label": label, "point": point, "diff": diff, "role": "alternative", "note": "也可以",
                    "first": point == first})
    return out


def follow_up(
    k: KeyFacts, *, played: str, rec: str, after: dict, probe_a: dict | None, student: str, size: int
) -> None:
    """What the two moves are worth after one exchange: each with the opponent's best answer.

    `after` is the position after the move played, `probe_a` the position after the recommended
    move; each is worth the lead its own search reports (the same player is to move in both).
    """
    if not probe_a or not after.get("moveInfos") or not probe_a.get("moveInfos"):
        return
    sign = 1.0 if student == "B" else -1.0
    lead_a = sign * probe_a["rootInfo"]["scoreLead"]
    lead_x = sign * after["rootInfo"]["scoreLead"]
    reply_a = gtp_sgf(probe_a["moveInfos"][0]["move"], size)
    reply_x = gtp_sgf(after["moveInfos"][0]["move"], size)
    k.add(
        "follow_up", moveMark="A", playedMark="✕",
        leadAfterA=round(lead_a, 1), leadAfterPlayed=round(lead_x, 1), diff=round(lead_a - lead_x, 1),
        replyNearA=distance(sgf_to_xy(reply_a, size), sgf_to_xy(rec, size)) <= 2,
        replyNearPlayed=distance(sgf_to_xy(reply_x, size), sgf_to_xy(played, size)) <= 2,
    )


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
    probe_a: dict | None = None,  # the position after the recommended move, analysed
) -> KeyFacts:
    """Facts for a mistake, a missed punishment or a missed urgent point."""
    k = KeyFacts()
    opponent = other(student)
    k.mark_point("✕", played, "played")

    choice = recommend(
        kind=kind, played=played, before=before, peer_policy=peer_policy,
        urgent_point=urgent_point, size=size, student=student,
    )
    best, best_lead, rec, source = choice.best, choice.best_lead, choice.move, choice.source
    peer, peer_diff = choice.peer, choice.peer_diff
    k.mark_point("A", rec, "recommended")
    if rec != best and best != played:
        k.mark_point("B", best, "ai_best")
    k.recommended = {"move": rec, "source": source}
    k.candidates = close_candidates(before, k, played, rec, best, size, student=student, played_loss=move_loss)
    follow_up(k, played=played, rec=rec, after=after, probe_a=probe_a, student=student, size=size)

    k.add("played", mark="✕")
    k.add("recommended", mark="A", source=source)
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
            k.group_fact("atari_ignored", stones, True, count=len(stones))
            break
    if played_xy and not k.has("atari_ignored"):
        stones, libs = after_board.group(played_xy)
        shown = {p for p in stones if before_board.get(p) == student}
        if len(stones) >= 2 and len(libs) == 1 and shown and shown <= lost_mine:
            k.group_fact("self_atari", shown, True, count=len(stones))
    if lost_mine:
        fact = k.group_fact("refute_capture", lost_mine, True, count=len(lost_mine))
        saved = {p for p in lost_mine if rec_board.get(p) == student}
        if fact and saved == lost_mine and rec != played:
            k.add("best_save", mark=fact["mark"], count=len(saved), moveMark="A")
    taken = {p for p in rec_lost[opponent] if before_board.get(p) == opponent}
    if len(taken) >= MIN_CAPTURE:
        k.group_fact("best_capture", taken, False, count=len(taken), moveMark="A")

    own_before, own_after = before.get("ownership"), after.get("ownership")
    if own_before and own_after:
        dies, lives = flips(after_board, own_before, own_after, student, size)
        # Only stones already on the board in the position shown can carry a mark.
        for stones, _ in sorted(dies, key=lambda d: len(d[0]), reverse=True)[:1]:
            shown = {p for p in stones if before_board.get(p) == student}
            if len(shown) >= 2:
                k.group_fact("group_dies", shown, True, count=len(shown))
        for stones, _ in sorted(lives, key=lambda d: len(d[0]), reverse=True)[:1]:
            shown = {p for p in stones if before_board.get(p) == opponent}
            if len(shown) >= 2:
                k.group_fact("group_lives", shown, False, count=len(shown))
        area = area_change(after_board, own_before, own_after, student, size)
        if area:
            name, count = region(area)
            if count >= AREA_MIN:
                k.marks.append({"label": "", "type": "area", "points": sorted(xy_to_sgf(p) for p in area)})
                k.add("area_flip", count=count, region=name)
        k.category = category(after_board, own_before, own_after, number, move_loss, size)
    # Why A: what it does on the board, and where it is compared with ✕.
    near_group(k, before_board, rec, student)
    if rec != played:
        reply = refute_moves[1][1] if len(refute_moves) > 1 else ""
        refute_squeeze(k, before_board, after_board, reply, student)
        shape_facts(k, before_board, rec, student)
        where_facts(k, after, played, rec, size)
    if any(k.has(t) for t in ("group_dies", "group_lives", "refute_capture", "best_capture", "atari_ignored",
                              "rec_atari", "refute_squeeze")):
        k.category = "life_death"

    if peer and peer_diff is not None:
        if peer == rec:
            if source == "peer":
                k.add("peer_choice", mark="A", sameAsAi=False, diff=round(peer_diff), aiMark="B")
            else:
                k.add("peer_choice", mark="A", sameAsAi=True)
    # How often players at the student's own level find A: often means this was a slip.
    level = policy_at(level_policy, rec, size) if level_policy else 0.0
    if level >= SLIP_MANY and rec != played:
        k.add("slip", mark="A", share="most" if level >= SLIP_MOST else "many")
    k.add("phase", phase=phase(number), category=k.category, move=number)
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
    near_group(k, before_board, played, student)
    shape_facts(k, before_board, played, student)
    where_facts(k, probe, common, played, size, prefix="common_")

    taken = {p for p in good_lost[opponent] if before_board.get(p) == opponent}
    if len(taken) >= MIN_CAPTURE:
        k.group_fact("best_capture", taken, False, count=len(taken), moveMark="A")
    lost = {p for p in common_lost[student] if before_board.get(p) == student}
    if len(lost) >= MIN_CAPTURE:
        k.group_fact("common_capture", lost, True, count=len(lost), moveMark="B")
    if probe and before.get("ownership") and probe.get("ownership"):
        after_common = before_board.copy()
        after_common.play_sgf(student, common)
        dies, _ = flips(after_common, before["ownership"], probe["ownership"], student, size)
        for stones, _ in sorted(dies, key=lambda d: len(d[0]), reverse=True)[:1]:
            shown = {p for p in stones if before_board.get(p) == student}
            if len(shown) >= 2:
                k.group_fact("common_group_dies", shown, True, count=len(shown), moveMark="B")
        k.category = category(after_common, before["ownership"], probe["ownership"], number, common_loss, size)
    k.add("phase", phase=phase(number), category=k.category, move=number)
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
