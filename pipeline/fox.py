"""Fox (野狐) public game records through the unofficial H5 endpoints LizzieYzy Next uses.

These endpoints are not a public API and may stop working; `review analyze --sgf` is the fallback.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from . import ranks

_H5 = "https://h5.foxwq.com/yehuDiamond/chessbook_local"
_USER = "https://newframe.foxwq.com/cgi/QueryUserInfoPanel"
_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


class FoxError(RuntimeError):
    pass


def _get_json(url: str, retries: int = 3) -> dict:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": _UA, "Accept": "application/json,text/plain,*/*"}
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (OSError, ValueError) as e:
            last = e
            time.sleep(0.4 * attempt)
    raise FoxError(f"野狐接口请求失败：{last}。可以改用 --sgf 手动导入棋谱。")


@dataclass(frozen=True)
class FoxGame:
    chessid: str
    start: datetime
    black: str
    white: str
    black_uid: str
    white_uid: str
    black_rank: ranks.Rank
    white_rank: ranks.Rank
    winner: int  # 1 black, 2 white, other: draw / unknown
    point: int
    moves: int
    size: int
    handicap: int

    def student_color(self, uid: str) -> str | None:
        if self.black_uid == uid:
            return "B"
        if self.white_uid == uid:
            return "W"
        return None

    def result_text(self) -> str:
        if self.winner not in (1, 2):
            return "和棋/其他"
        side = "黑" if self.winner == 1 else "白"
        if self.point == -1:
            return f"{side}中盘胜"
        if self.point == -2:
            return f"{side}超时胜"
        if self.point < 0:
            return f"{side}胜"
        return f"{side}胜{self.point / 100:g}子"


def find_uid(nickname: str) -> str:
    """Resolves a nickname (even an all-digit one) to the numeric Fox UID."""
    data = _get_json(f"{_USER}?srcuid=0&username={urllib.parse.quote(nickname)}")
    uid = str(data.get("uid", "")).strip()
    if uid in ("", "0"):
        raise FoxError(f"找不到野狐昵称为「{nickname}」的账号。")
    if data.get("result", data.get("errcode", -1)) != 0:
        raise FoxError(str(data.get("resultstr") or data.get("errmsg") or data))
    return uid


def list_games(uid: str) -> list[FoxGame]:
    """The account's most recent public games (Fox returns up to 100), newest first."""
    url = (
        f"{_H5}/YHWQFetchChessList?srcuid=0&dstuid={urllib.parse.quote(uid)}"
        f"&type=1&lastcode=0&searchkey=&uin={urllib.parse.quote(uid)}"
    )
    data = _get_json(url)
    if data.get("result") != 0:
        raise FoxError(f"获取棋谱列表失败：{data.get('resultstr') or data}")
    games = []
    for item in data.get("chesslist") or []:
        games.append(
            FoxGame(
                chessid=str(item["chessid"]),
                start=datetime.strptime(item["starttime"], "%Y-%m-%d %H:%M:%S"),
                black=item.get("blacknick") or item.get("blackenname") or "",
                white=item.get("whitenick") or item.get("whiteenname") or "",
                black_uid=str(item.get("blackuid", "")),
                white_uid=str(item.get("whiteuid", "")),
                black_rank=ranks.from_fox_dan(int(item.get("blackdan", 0))),
                white_rank=ranks.from_fox_dan(int(item.get("whitedan", 0))),
                winner=int(item.get("winner", 0)),
                point=int(item.get("point", 0)),
                moves=int(item.get("movenum", 0)),
                size=int(item.get("boardsize", 19)),
                handicap=int(item.get("handicap", 0)),
            )
        )
    return games


def fetch_sgf(chessid: str) -> str:
    data = _get_json(f"{_H5}/YHWQFetchChess?chessid={urllib.parse.quote(chessid)}")
    sgf = (data.get("chess") or "").strip()
    if data.get("result") != 0 or not sgf:
        raise FoxError(f"下载棋谱 {chessid} 失败：{data.get('resultstr') or '内容为空'}")
    return sgf
