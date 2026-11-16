"""Names the shape a move makes (跳, 扳, 断, 点三三 ...), from the stones on the board alone.

Only shapes the stones settle are named; any other move gets None rather than a guess. The rules
follow LizzieYzy's teacher/MoveShapes (ideas only, rewritten): tactical moves first (capture,
atari, connection, wedge, cut), then moves touching stones (hane, attachment, extension), then
distant ones (corner moves, side extensions, jumps and knight's moves, invasions).
"""

from __future__ import annotations

from .board import Board, Point, other
from .coords import sgf_to_xy

CORNER_BOX = 5  # a corner is the 6x6 box (0-based edge distance <= 5)
DIAGONALS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
# (a, b) offsets from an own stone, tried in this order.
RELATIONS = ((1, 1, "尖"), (2, 0, "跳"), (1, 2, "小飞"), (3, 0, "大跳"), (1, 3, "大飞"))
SIDE_GAPS = "一二三四"  # 拆一 .. 拆四: one to four empty points to the own stone along the side


def describe(board: Board, point: str, color: str) -> str | None:
    """The shape name of `color` playing `point` on `board`, or None."""
    xy = sgf_to_xy(point, board.size) if point else None
    if xy is None or board.get(xy) is not None:
        return None
    named = _tactical(board, xy, color)
    if named is not None:
        return named or None
    touches = any(board.get(n) for n in board.neighbors(xy))
    return _contact(board, xy, color) if touches else _distant(board, xy, color)


def _at(board: Board, x: int, y: int) -> str | None:
    """The stone at (x, y); "off" off the board."""
    if not (0 <= x < board.size and 0 <= y < board.size):
        return "off"
    return board.get((x, y))


def _neighbors(board: Board, xy: Point, color: str) -> list[Point]:
    return [n for n in board.neighbors(xy) if board.get(n) == color]


def _groups(board: Board, xy: Point, color: str) -> list[set[Point]]:
    out: list[set[Point]] = []
    for n in _neighbors(board, xy, color):
        if not any(n in g for g in out):
            out.append(board.group(n)[0])
    return out


def _tactical(board: Board, xy: Point, color: str) -> str | None:
    """None: not tactical, look further; "": tactical but without a name."""
    opponent = other(color)
    theirs = _groups(board, xy, opponent)
    after = board.copy()
    after.stones[xy] = color  # no captures yet: count what is left of each group
    libs = [len(after.group(next(iter(g)))[1]) for g in theirs]
    if 0 in libs:
        return "提子"
    if 1 in libs:
        return "打吃"
    if len(_groups(board, xy, color)) >= 2:
        return "粘"
    if len(theirs) >= 2:
        touched = _neighbors(board, xy, opponent)
        for i, a in enumerate(touched):
            for b in touched[i + 1:]:
                if b in board.group(a)[0]:
                    continue
                if a[0] + b[0] == 2 * xy[0] and a[1] + b[1] == 2 * xy[1]:
                    return "挖"  # between two stones on a straight line
                across = (a[0] + b[0] - xy[0], a[1] + b[1] - xy[1])
                if a[0] != b[0] and a[1] != b[1] and _at(board, *across) == color:
                    return "断"  # across a diagonal, with our own stone on the far corner
        return ""
    return None


def _contact(board: Board, xy: Point, color: str) -> str | None:
    opponent = other(color)
    theirs = _neighbors(board, xy, opponent)
    mine = _neighbors(board, xy, color)
    if not theirs:
        for s in mine:
            for t in _neighbors(board, s, opponent):
                # Alongside the opponent stone it touches; straight back from it is a retreat.
                if (xy[0] - s[0]) * (t[0] - s[0]) + (xy[1] - s[1]) * (t[1] - s[1]) == 0:
                    return "长"
        return None
    if mine:
        return None  # touching both colours: a block or a push, not told apart here
    for t in theirs:
        for dx, dy in DIAGONALS:
            s = (xy[0] + dx, xy[1] + dy)
            if board.get(s) == color and abs(s[0] - t[0]) + abs(s[1] - t[1]) == 1:
                return "扳"
    return "靠"


def _distant(board: Board, xy: Point, color: str) -> str | None:
    if board.size >= 13:
        named = _corner(board, xy, color) or _side_extension(board, xy, color)
        if named:
            return named
    return _relation(board, xy, color) or _invasion(board, xy, color)


def _edge(v: int, far: bool, size: int) -> int:
    return size - 1 - v if far else v


def _corner(board: Board, xy: Point, color: str) -> str | None:
    size = board.size
    sides = []
    for v in xy:
        if v <= CORNER_BOX:
            sides.append(False)
        elif v >= size - 1 - CORNER_BOX:
            sides.append(True)
        else:
            return None
    far_x, far_y = sides
    mine, theirs = [], []
    for p, c in board.stones.items():
        if _edge(p[0], far_x, size) <= CORNER_BOX and _edge(p[1], far_y, size) <= CORNER_BOX:
            (mine if c == color else theirs).append(p)
    x, y = _edge(xy[0], far_x, size), _edge(xy[1], far_y, size)
    if not mine and not theirs:
        return "占角" if 2 <= x <= 4 and 2 <= y <= 4 else None
    if not mine and len(theirs) == 1:
        s = theirs[0]
        sx, sy = _edge(s[0], far_x, size), _edge(s[1], far_y, size)
        if (x, y) == (2, 2) and (sx, sy) == (3, 3):
            return "点三三"
        if 2 <= sx <= 4 and 2 <= sy <= 4 and x >= 2 and y >= 2 and _cheb(xy, s) >= 2:
            return "挂角"
    if not theirs and len(mine) == 1:
        s = mine[0]
        sx, sy = _edge(s[0], far_x, size), _edge(s[1], far_y, size)
        if 2 <= sx <= 4 and 2 <= sy <= 4 and x >= 2 and y >= 2 and _cheb(xy, s) <= 3:
            return "守角"
    return None


def _side_extension(board: Board, xy: Point, color: str) -> str | None:
    size = board.size
    for along in ((0, 1), (1, 0)):
        across = xy[0] if along == (0, 1) else xy[1]
        if not 2 <= min(across, size - 1 - across) <= 3:
            continue  # only from the third and fourth lines
        for direction in (1, -1):
            for gap in range(1, 6):
                stone = _at(board, xy[0] + along[0] * direction * gap, xy[1] + along[1] * direction * gap)
                if stone == "off" or stone == other(color):
                    break
                if stone == color:
                    if gap >= 2:
                        return "拆" + SIDE_GAPS[gap - 2]
                    break
    return None


def _relation(board: Board, xy: Point, color: str) -> str | None:
    for a, b, name in RELATIONS:
        offsets = {(a, b), (-a, b), (a, -b), (-a, -b), (b, a), (-b, a), (b, -a), (-b, -a)}
        for dx, dy in sorted(offsets):
            x, y = xy[0] + dx, xy[1] + dy
            if _at(board, x, y) == color and _open_between(board, xy, (x, y)):
                return name
    return None


def _open_between(board: Board, a: Point, b: Point) -> bool:
    """Whether the points strictly between the ends of a straight jump are empty."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx and dy:
        return True
    steps = max(abs(dx), abs(dy))
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    return all(_at(board, a[0] + sx * i, a[1] + sy * i) is None for i in range(1, steps))


def _invasion(board: Board, xy: Point, color: str) -> str | None:
    size = board.size
    if min(xy[0], xy[1], size - 1 - xy[0], size - 1 - xy[1]) < 2:
        return None
    mine = theirs = 0
    for x in range(xy[0] - 4, xy[0] + 5):
        for y in range(xy[1] - 4, xy[1] + 5):
            c = _at(board, x, y)
            if c == color:
                mine += 1
            elif c == other(color):
                theirs += 1
    return "打入" if mine == 0 and theirs >= 3 else None


def _cheb(a: Point, b: Point) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
