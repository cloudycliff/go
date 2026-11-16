"""A plain Go board for replaying games and variations: captures, groups and liberties."""

from __future__ import annotations

from collections.abc import Iterable

from .coords import sgf_to_xy

Point = tuple[int, int]


def other(color: str) -> str:
    return "W" if color == "B" else "B"


class Board:
    def __init__(self, size: int = 19) -> None:
        self.size = size
        self.stones: dict[Point, str] = {}

    def copy(self) -> "Board":
        b = Board(self.size)
        b.stones = dict(self.stones)
        return b

    def get(self, p: Point) -> str | None:
        return self.stones.get(p)

    def neighbors(self, p: Point) -> list[Point]:
        x, y = p
        out = []
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < self.size and 0 <= ny < self.size:
                out.append((nx, ny))
        return out

    def group(self, p: Point) -> tuple[set[Point], set[Point]]:
        """The stones connected to p and their liberties (both empty when p is empty)."""
        color = self.stones.get(p)
        if color is None:
            return set(), set()
        stones, libs, todo = {p}, set(), [p]
        while todo:
            q = todo.pop()
            for n in self.neighbors(q):
                c = self.stones.get(n)
                if c is None:
                    libs.add(n)
                elif c == color and n not in stones:
                    stones.add(n)
                    todo.append(n)
        return stones, libs

    def groups(self, color: str | None = None) -> list[tuple[str, set[Point], set[Point]]]:
        seen: set[Point] = set()
        out = []
        for p, c in sorted(self.stones.items()):
            if p in seen or (color and c != color):
                continue
            stones, libs = self.group(p)
            seen |= stones
            out.append((c, stones, libs))
        return out

    def play(self, color: str, p: Point | None) -> set[Point]:
        """Plays a move (None = pass) and returns the captured stones. Suicide removes the group."""
        if p is None:
            return set()
        if p in self.stones:
            raise ValueError(f"point {p} is occupied")
        self.stones[p] = color
        captured: set[Point] = set()
        for n in self.neighbors(p):
            if self.stones.get(n) == other(color):
                stones, libs = self.group(n)
                if not libs:
                    captured |= stones
        for q in captured:
            del self.stones[q]
        if not captured:
            stones, libs = self.group(p)
            if not libs:
                for q in stones:
                    del self.stones[q]
        return captured

    def play_sgf(self, color: str, point: str) -> set[Point]:
        return self.play(color, sgf_to_xy(point, self.size))


def setup(size: int, black: Iterable[str], white: Iterable[str]) -> Board:
    b = Board(size)
    for p in black:
        xy = sgf_to_xy(p, size)
        if xy:
            b.stones[xy] = "B"
    for p in white:
        xy = sgf_to_xy(p, size)
        if xy:
            b.stones[xy] = "W"
    return b


def positions(game) -> list[Board]:
    """The board before every move and after the last one: len(game.moves) + 1 boards."""
    b = setup(game.size, game.setup_black, game.setup_white)
    out = [b.copy()]
    for color, point in game.moves:
        b.play_sgf(color, point)
        out.append(b.copy())
    return out


def distance(a: Point | None, b: Point | None) -> int:
    """Chebyshev distance on the board; passes are far from everything."""
    if a is None or b is None:
        return 99
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
