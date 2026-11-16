"""Minimal SGF reader for Fox game records: root properties plus the main line."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import ranks
from .coords import sgf_to_xy

_NAME = re.compile(r"[A-Za-z]+")


@dataclass
class Game:
    size: int
    komi: float
    rules: str  # "chinese" or "japanese"
    handicap: int
    setup_black: list[str] = field(default_factory=list)  # SGF points
    setup_white: list[str] = field(default_factory=list)
    moves: list[tuple[str, str]] = field(default_factory=list)  # ("B"|"W", sgf point; "" = pass)
    black: str = ""
    white: str = ""
    black_rank: ranks.Rank | None = None
    white_rank: ranks.Rank | None = None
    result: str = ""
    date: str = ""
    raw: str = ""


def _read_value(text: str, i: int) -> tuple[str, int]:
    i += 1  # past "["
    out = []
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            out.append(text[i + 1])
            i += 2
        elif c == "]":
            return "".join(out), i + 1
        else:
            out.append(c)
            i += 1
    raise ValueError("unterminated SGF value")


def main_line(text: str) -> list[dict[str, list[str]]]:
    """The nodes of the main line: at every fork, the first variation."""
    nodes: list[dict[str, list[str]]] = []
    # For each open "(" on the main line: has a child variation already been taken?
    taken: list[bool] = []
    skip = 0  # nesting depth inside a variation that is not on the main line
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "[":
            i = _read_value(text, i)[1]
        elif c == "(":
            if skip:
                skip += 1
            elif taken and taken[-1]:
                skip = 1
            else:
                if taken:
                    taken[-1] = True
                taken.append(False)
            i += 1
        elif c == ")":
            if skip:
                skip -= 1
            elif taken:
                taken.pop()
            i += 1
        elif c == ";" and not skip:
            i += 1
            node: dict[str, list[str]] = {}
            while i < n and text[i] not in ";()":
                if text[i].isspace() or text[i] == "\\":
                    i += 1
                    continue
                m = _NAME.match(text, i)
                if not m:
                    raise ValueError(f"bad SGF near position {i}")
                name, i = m.group(0), m.end()
                while i < n and text[i].isspace():
                    i += 1
                while i < n and text[i] == "[":
                    value, i = _read_value(text, i)
                    node.setdefault(name, []).append(value)
                    while i < n and text[i].isspace():
                        i += 1
            nodes.append(node)
        else:
            i += 1
    return nodes


def _first(node: dict[str, list[str]], name: str, default: str = "") -> str:
    values = node.get(name)
    return values[0].strip() if values else default


def _fox_komi(raw: str, chinese: bool) -> float:
    """Fox writes komi 7.5 as 375 (stones x 100 under Chinese rules) and 6.5 as 650."""
    try:
        komi = float(raw)
    except ValueError:
        return 7.5 if chinese else 6.5
    if abs(komi) >= 50:
        komi /= 100
        if chinese and -4 <= komi <= 4:
            komi *= 2
    return komi


def parse(text: str) -> Game:
    text = text.replace("﻿", "").strip()
    nodes = main_line(text)
    if not nodes:
        raise ValueError("SGF has no nodes")
    root = nodes[0]
    size = int(_first(root, "SZ", "19").split(":")[0])
    rules_text = _first(root, "RU", "Chinese").lower()
    chinese = "chin" in rules_text or rules_text in ("cn", "")
    game = Game(
        size=size,
        komi=_fox_komi(_first(root, "KM", "375"), chinese),
        rules="chinese" if chinese else "japanese",
        handicap=0,
        setup_black=[p for p in root.get("AB", []) if p],
        setup_white=[p for p in root.get("AW", []) if p],
        black=_first(root, "PB"),
        white=_first(root, "PW"),
        black_rank=ranks.parse(_first(root, "BR")),
        white_rank=ranks.parse(_first(root, "WR")),
        result=_first(root, "RE"),
        date=_first(root, "DT"),
        raw=text,
    )
    for node in nodes:
        for color in ("B", "W"):
            for value in node.get(color, []):
                point = value.strip()
                if point == "tt" and size <= 19:
                    point = ""
                sgf_to_xy(point, size)  # validates
                game.moves.append((color, point))

    # Fox records handicap stones as a leading run of Black moves instead of AB.
    run = 0
    for color, point in game.moves:
        if color != "B" or not point:
            break
        run += 1
    if run >= 2 and not game.setup_black:
        game.setup_black = [p for _, p in game.moves[:run]]
        game.moves = game.moves[run:]
    game.handicap = len(game.setup_black)
    if game.handicap >= 2:
        game.komi = 0.0 if chinese else 0.5
    return game
