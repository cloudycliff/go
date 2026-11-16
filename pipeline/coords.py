"""Board coordinates: SGF ("pd"), GTP ("Q16") and (x, y) with y counted from the top."""

from __future__ import annotations

GTP_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
PASS = "pass"


def sgf_to_xy(sgf: str | None, size: int) -> tuple[int, int] | None:
    """None for a pass ("" or "tt" on boards up to 19)."""
    if not sgf or (sgf == "tt" and size <= 19):
        return None
    if len(sgf) != 2:
        raise ValueError(f"bad SGF point {sgf!r}")
    x, y = ord(sgf[0]) - ord("a"), ord(sgf[1]) - ord("a")
    if not (0 <= x < size and 0 <= y < size):
        raise ValueError(f"SGF point {sgf!r} is off a {size}x{size} board")
    return x, y


def xy_to_sgf(xy: tuple[int, int] | None) -> str:
    if xy is None:
        return ""
    return chr(ord("a") + xy[0]) + chr(ord("a") + xy[1])


def xy_to_gtp(xy: tuple[int, int] | None, size: int) -> str:
    if xy is None:
        return PASS
    return f"{GTP_LETTERS[xy[0]]}{size - xy[1]}"


def gtp_to_xy(gtp: str, size: int) -> tuple[int, int] | None:
    text = gtp.strip().upper()
    if text == "PASS":
        return None
    x = GTP_LETTERS.index(text[0])
    y = size - int(text[1:])
    if not (0 <= x < size and 0 <= y < size):
        raise ValueError(f"GTP point {gtp!r} is off a {size}x{size} board")
    return x, y


def sgf_to_gtp(sgf: str | None, size: int) -> str:
    return xy_to_gtp(sgf_to_xy(sgf, size), size)


def gtp_to_sgf(gtp: str, size: int) -> str:
    return xy_to_sgf(gtp_to_xy(gtp, size))
