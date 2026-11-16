"""Command line: `python -m pipeline <command>` (run from the go-review folder)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

from . import analyze, fox, sgf
from .config import Config, load
from .katago import KataGo, KataGoError


def _out(text: str = "") -> None:
    print(text, flush=True)


def _pad(text: str, width: int) -> str:
    """Left-aligns text in a terminal column where CJK characters take two cells."""
    cells = 0
    out = []
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if cells + w > width:
            break
        out.append(ch)
        cells += w
    return "".join(out) + " " * (width - cells)


def _flags(g: fox.FoxGame) -> str:
    flags = []
    if g.handicap == 1:
        flags.append("让先")
    elif g.handicap >= 2:
        flags.append(f"让{g.handicap}子")
    return " ".join(flags)


def _cached_list(cfg: Config) -> tuple[str, list[fox.FoxGame]]:
    """Only 19x19 games: the 11x11 games on Fox are a special mode that v1 does not review."""
    uid = fox.find_uid(cfg.fox_nickname)
    return uid, [g for g in fox.list_games(uid) if g.size == 19]


def cmd_list(cfg: Config, args: argparse.Namespace) -> int:
    uid, games = _cached_list(cfg)
    analyzed = {p.name.split(".")[0] for p in cfg.raw_dir.glob("*.json.gz")}
    _out(f"野狐昵称 {cfg.fox_nickname}（UID {uid}），最近 {min(args.limit, len(games))} 局 19 路对局：")
    _out()
    _out(" #  日期              执色 对手               段位   结果              手数  棋局 ID")
    for i, g in enumerate(games[: args.limit], 1):
        color = g.student_color(uid)
        opponent, opp_rank = (g.white, g.white_rank) if color == "B" else (g.black, g.black_rank)
        won = (g.winner == 1 and color == "B") or (g.winner == 2 and color == "W")
        mark = "✓" if g.chessid in analyzed else " "
        _out(
            f"{i:>2}{mark} {g.start:%Y-%m-%d %H:%M}  {'黑' if color == 'B' else '白'}   "
            f"{_pad(opponent, 18)} {_pad(opp_rank.label_zh(), 6)} "
            f"{'胜' if won else '负'} {_pad(g.result_text(), 14)} {g.moves:>4}  {g.chessid}  {_flags(g)}"
        )
    _out()
    _out("✓ = 已分析。用 `python -m pipeline analyze <序号或棋局 ID>` 分析一局。")
    return 0


def _resolve_game(cfg: Config, target: str) -> tuple[str, str, str]:
    """Returns (game id, SGF text, student color) for a list index, chessid or --sgf file."""
    uid, games = _cached_list(cfg)
    chosen = None
    if target.isdigit() and len(target) <= 3:
        index = int(target)
        if not 1 <= index <= len(games):
            raise SystemExit(f"序号 {index} 超出范围（1-{len(games)}）")
        chosen = games[index - 1]
    else:
        chosen = next((g for g in games if g.chessid == target), None)
    game_id = chosen.chessid if chosen else target
    color = chosen.student_color(uid) if chosen else None
    text = fox.fetch_sgf(game_id)
    if color is None:
        parsed = sgf.parse(text)
        color = "B" if parsed.black == cfg.fox_nickname else "W" if parsed.white == cfg.fox_nickname else None
    if color is None:
        raise SystemExit("无法判断孩子执黑还是执白，请用 --color B 或 --color W 指定。")
    return game_id, text, color


def cmd_analyze(cfg: Config, args: argparse.Namespace) -> int:
    if args.sgf:
        text = Path(args.sgf).read_text(encoding="utf-8")
        game_id = "sgf-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
        parsed = sgf.parse(text)
        color = args.color or (
            "B" if parsed.black == cfg.fox_nickname else "W" if parsed.white == cfg.fox_nickname else None
        )
        if color is None:
            raise SystemExit("无法判断孩子执黑还是执白，请用 --color B 或 --color W 指定。")
    else:
        if not args.target:
            raise SystemExit("请给出序号、棋局 ID，或用 --sgf 指定棋谱文件。")
        game_id, text, color = _resolve_game(cfg, args.target)
        color = args.color or color
    game = sgf.parse(text)
    if game.size != 19:
        _out(f"这是 {game.size} 路对局，目前只复盘 19 路对局。")
        return 1
    raw_path = cfg.raw_dir / f"{game_id}.json.gz"
    if raw_path.exists() and not args.force:
        _out(f"{raw_path.name} 已经分析过了；要重新分析请加 --force。")
        return 0

    rank = game.black_rank if color == "B" else game.white_rank
    _out(
        f"棋局 {game_id}：{game.black}（{game.black_rank.label_zh() if game.black_rank else '?'}）"
        f" 对 {game.white}（{game.white_rank.label_zh() if game.white_rank else '?'}），"
        f"{len(game.moves)} 手，{game.result}，贴目 {game.komi:g}，让子 {game.handicap}"
    )
    _out(f"孩子执{'黑' if color == 'B' else '白'}，段位 {rank.label_zh() if rank else '未知'}，"
         f"HumanSL 档位 {analyze.student_profile(game, color)}")
    _out("启动 KataGo……")
    try:
        with KataGo(cfg.katago) as engine:
            version = engine.version()
            _out(f"KataGo {version['version']} 已就绪，开始整盘分析（每个局面 {cfg.overview_visits} visits）")
            responses, params = analyze.overview(engine, game, color, cfg.overview_visits)
            for warning in engine.warnings():
                _out(f"  {warning}")
    except KataGoError as e:
        _out(f"分析失败：{e}")
        return 1
    analyze.save_raw(
        raw_path,
        game=game,
        game_id=game_id,
        student_color=color,
        model=cfg.katago.model.name,
        version=version,
        params=params,
        responses=responses,
    )
    _out(f"完成，用时 {params['seconds']:.0f} 秒，原始结果已保存到 raw/{raw_path.name}")
    _print_curve(responses, color)
    return 0


def _print_curve(responses: list[dict], color: str) -> None:
    """A rough text view of the student's score lead, to sanity-check an analysis."""
    sign = 1 if color == "B" else -1
    leads = [sign * r["rootInfo"]["scoreLead"] for r in responses]
    _out("孩子领先目数（每 20 手）：")
    _out("  " + "  ".join(f"{i}:{leads[i]:+.1f}" for i in range(0, len(leads), 20)))
    # Response i is the position before move i+1, so move i+1 changed leads[i] into leads[i+1].
    drops = sorted(((leads[i] - leads[i + 1], i + 1) for i in range(len(leads) - 1)), reverse=True)
    _out("孩子领先目数下降最多的 5 手：" + ", ".join(f"第{m}手({-d:+.1f})" for d, m in drops[:5]))


def cmd_show(cfg: Config, args: argparse.Namespace) -> int:
    path = cfg.raw_dir / f"{args.game_id}.json.gz"
    raw = analyze.load_raw(path)
    _out(json.dumps({k: v for k, v in raw.items() if k not in ("overview", "sgf")}, ensure_ascii=False, indent=2))
    _print_curve(raw["overview"]["responses"], raw["studentColor"])
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m pipeline", description="野狐对局复盘")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="列出最近的对局")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("analyze", help="分析一局")
    p.add_argument("target", nargs="?", help="list 里的序号，或棋局 ID")
    p.add_argument("--sgf", help="改用本地 SGF 文件")
    p.add_argument("--color", choices=["B", "W"], help="孩子执色（自动判断失败时用）")
    p.add_argument("--force", action="store_true", help="已分析过也重新分析")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("show", help="查看已保存的分析")
    p.add_argument("game_id")
    p.set_defaults(func=cmd_show)

    args = parser.parse_args(argv)
    try:
        return args.func(load(), args)
    except fox.FoxError as e:
        _out(str(e))
        return 1
