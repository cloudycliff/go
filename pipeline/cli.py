"""Command line: `python -m pipeline <command>` (run from the go-review folder)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from . import analyze, build, fox, sgf
from .config import ROOT, Config, load
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


def _ids(folder: Path) -> set[str]:
    return {p.name.split(".")[0] for p in folder.glob("*.json.gz")}


def cmd_list(cfg: Config, args: argparse.Namespace) -> int:
    uid, games = _cached_list(cfg)
    analyzed = _ids(cfg.raw_dir)
    local = _ids(cfg.local_raw_dir)
    _out(f"野狐昵称 {cfg.fox_nickname}（UID {uid}），最近 {min(args.limit, len(games))} 局 19 路对局：")
    _out()
    _out(" #  日期              执色 对手               段位   结果              手数  棋局 ID")
    for i, g in enumerate(games[: args.limit], 1):
        color = g.student_color(uid)
        opponent, opp_rank = (g.white, g.white_rank) if color == "B" else (g.black, g.black_rank)
        won = (g.winner == 1 and color == "B") or (g.winner == 2 and color == "W")
        mark = "✓" if g.chessid in analyzed else "○" if g.chessid in local else " "
        _out(
            f"{i:>2}{mark} {g.start:%Y-%m-%d %H:%M}  {'黑' if color == 'B' else '白'}   "
            f"{_pad(opponent, 18)} {_pad(opp_rank.label_zh(), 6)} "
            f"{'胜' if won else '负'} {_pad(g.result_text(), 14)} {g.moves:>4}  {g.chessid}  {_flags(g)}"
        )
    _out()
    _out("✓ = 已分析并发布；○ = 只在本机分析过（collect），analyze 它就会发布到网站。")
    _out("用 `python -m pipeline analyze <序号或棋局 ID>` 分析一局。")
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
    if args.latest:
        return _analyze_latest(cfg, args)
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
            raise SystemExit("请给出序号、棋局 ID，或用 --latest / --sgf。")
        game_id, text, color = _resolve_game(cfg, args.target)
        color = args.color or color
    code = _analyze_one(cfg, game_id, text, color, args.force)
    if code == 0 and args.publish:
        return _publish(f"review: {game_id}")
    return code


def _analyze_latest(cfg: Config, args: argparse.Namespace) -> int:
    """New games only; with none, stop before starting KataGo or touching git (for polling)."""
    from . import publish

    try:
        with publish.Lock(cfg.cache_dir / "update.lock"):
            uid, games = _cached_list(cfg)
            analyzed = {p.name.split(".")[0] for p in cfg.raw_dir.glob("*.json.gz")}
            fresh = publish.new_games(games, uid, analyzed, args.max)
            if not fresh:
                _out(f"{datetime.now():%Y-%m-%d %H:%M} 没有新对局，结束。")
                return 0
            _out(f"有 {len(fresh)} 局新对局：" + "、".join(f"{g.start:%m-%d %H:%M}（{g.chessid}）" for g in fresh))
            done = []
            for g in fresh:
                code = _analyze_one(cfg, g.chessid, fox.fetch_sgf(g.chessid), g.student_color(uid), False)
                if code != 0:
                    _out(f"棋局 {g.chessid} 分析失败，停止。")
                    break
                done.append(g)
            if done and args.publish:
                dates = "、".join(f"{g.start:%m-%d}" for g in done)
                code = _publish(f"review: {len(done)} new game(s) {dates}") or code
            return 0 if len(done) == len(fresh) else 1
    except publish.PublishError as e:
        _out(str(e))
        return 1


def _publish(message: str) -> int:
    from . import publish

    try:
        publish.publish(message, log=_out)
    except publish.PublishError as e:
        _out(f"发布失败：{e}")
        return 1
    return 0


def cmd_publish(cfg: Config, args: argparse.Namespace) -> int:
    return _publish(args.message or f"review: update {datetime.now():%Y-%m-%d %H:%M}")


def _analyze_one(cfg: Config, game_id: str, text: str, color: str | None, force: bool) -> int:
    """Whole-game analysis (unless already done), then the deep pass and the page data."""
    raw_path = cfg.raw_dir / f"{game_id}.json.gz"
    local_path = cfg.local_raw_dir / f"{game_id}.json.gz"
    if not raw_path.exists() and local_path.exists() and not force:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.replace(raw_path)
        _out(f"用本机已有的整盘分析（local/raw → raw/{raw_path.name}）。")
    if raw_path.exists() and not force:
        _out(f"{raw_path.name} 已有整盘分析（要重新分析请加 --force），直接生成复盘。")
        return _build(cfg, [game_id], use_engine=True)
    code = _overview(cfg, game_id, text, color, raw_path)
    return code or _build(cfg, [game_id], use_engine=True)


def _overview(cfg: Config, game_id: str, text: str, color: str | None, raw_path: Path,
              engine: KataGo | None = None) -> int:
    """The whole-game pass only, saved to `raw_path`. Uses `engine` when given, else starts one."""
    if color is None:
        _out(f"棋局 {game_id}：无法判断孩子执黑还是执白。")
        return 1
    game = sgf.parse(text)
    if game.size != 19:
        _out(f"这是 {game.size} 路对局，目前只复盘 19 路对局。")
        return 1

    rank = game.black_rank if color == "B" else game.white_rank
    _out(
        f"棋局 {game_id}：{game.black}（{game.black_rank.label_zh() if game.black_rank else '?'}）"
        f" 对 {game.white}（{game.white_rank.label_zh() if game.white_rank else '?'}），"
        f"{len(game.moves)} 手，{game.result}，贴目 {game.komi:g}，让子 {game.handicap}"
    )
    _out(f"孩子执{'黑' if color == 'B' else '白'}，段位 {rank.label_zh() if rank else '未知'}，"
         f"HumanSL 档位 {analyze.student_profile(game, color)}")
    own = engine is None
    try:
        if own:
            _out("启动 KataGo……")
            engine = KataGo(cfg.katago)
        version = engine.version()
        _out(f"KataGo {version['version']} 已就绪，开始整盘分析（每个局面 {cfg.overview_visits} visits）")
        responses, params = analyze.overview(engine, game, color, cfg.overview_visits)
        for warning in engine.warnings():
            _out(f"  {warning}")
    except KataGoError as e:
        _out(f"分析失败：{e}")
        return 1
    finally:
        if own and engine is not None:
            engine.close()
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
    _out(f"完成，用时 {params['seconds']:.0f} 秒，原始结果已保存到 {raw_path.relative_to(ROOT).as_posix()}")
    _print_curve(responses, color)
    return 0


def cmd_collect(cfg: Config, args: argparse.Namespace) -> int:
    """Whole-game analysis of recent games into local/raw/, for statistics across games.

    Nothing is committed or published; `analyze <id>` later moves a game to raw/ and builds its page.
    """
    from . import publish

    uid, games = _cached_list(cfg)
    done = _ids(cfg.raw_dir) | _ids(cfg.local_raw_dir)
    todo = [g for g in games[: args.limit]
            if g.chessid not in done and g.student_color(uid) and g.moves >= publish.MIN_MOVES]
    if not todo:
        _out("最近的对局都已分析过。")
        return 0
    _out(f"要在本机分析 {len(todo)} 局（只做整盘分析，不发布）。")
    failed = 0
    with KataGo(cfg.katago) as engine:
        for n, g in enumerate(todo, 1):
            _out(f"[{n}/{len(todo)}] {g.start:%Y-%m-%d %H:%M} {g.chessid}")
            try:
                text = fox.fetch_sgf(g.chessid)
            except fox.FoxError as e:
                _out(f"  下载棋谱失败：{e}")
                failed += 1
                continue
            path = cfg.local_raw_dir / f"{g.chessid}.json.gz"
            if _overview(cfg, g.chessid, text, g.student_color(uid), path, engine):
                failed += 1
            time.sleep(1)  # the Fox API is unofficial: keep requests slow
    _out(f"完成 {len(todo) - failed} 局" + (f"，{failed} 局失败" if failed else "") + "，保存在 local/raw/。")
    return 1 if failed else 0


def _build(cfg: Config, game_ids: list[str], use_engine: bool) -> int:
    engine = build.LazyEngine(cfg, _out) if use_engine else None
    try:
        for game_id in game_ids:
            _out(f"生成复盘 {game_id}")
            build.build(cfg, game_id, engine, _out)
    except KataGoError as e:
        _out(f"深度分析失败：{e}")
        return 1
    finally:
        if engine:
            engine.close()
    _out("本地预览：python -m pipeline serve，然后打开 http://localhost:8000/")
    return 0


def cmd_build(cfg: Config, args: argparse.Namespace) -> int:
    ids = args.game_ids or sorted(p.name.split(".")[0] for p in cfg.raw_dir.glob("*.json.gz"))
    if not ids:
        _out("raw/ 里还没有分析结果。")
        return 1
    return _build(cfg, ids, use_engine=not args.no_engine)


def cmd_stats(cfg: Config, args: argparse.Namespace) -> int:
    """Statistics across every analysed game, published or local, into local/report.md."""
    from . import stats

    games = stats.load_all([(cfg.raw_dir, True), (cfg.local_raw_dir, False)])
    if not games:
        _out("还没有分析过的对局。")
        return 1
    path = ROOT / "local" / "report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stats.report(games), encoding="utf-8")
    _out(f"已生成 {path.relative_to(ROOT).as_posix()}（{len(games)} 局）。这个文件只在本机，不会提交。")
    pages = {}
    for g in games:
        page = build.SITE / "data" / "games" / f"{g.id}.json"
        if g.published and page.exists():
            pages[g.id] = json.loads(page.read_text(encoding="utf-8"))
    data = stats.habits(games, pages)
    target = build.SITE / "data" / "habits.json" if args.site else ROOT / "local" / "habits.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    names = "、".join(h["title"] for h in data["habits"]) or "没有"
    if args.site:
        _out(f"已生成 {target.relative_to(ROOT).as_posix()}：{names}。下次 publish 会发布到网站。")
    else:
        _out(f"已生成 {target.relative_to(ROOT).as_posix()}：{names}。"
             "本机预览 serve 时可以看到“我的常见问题”页；要放到网站上，用 stats --site。")
    return 0


def cmd_serve(cfg: Config, args: argparse.Namespace) -> int:
    import functools
    import http.server

    class Handler(http.server.SimpleHTTPRequestHandler):
        # Windows' registry often maps .js to text/plain, which browsers refuse for module scripts.
        extensions_map = {
            **http.server.SimpleHTTPRequestHandler.extensions_map,
            ".js": "text/javascript",
            ".json": "application/json",
            ".css": "text/css",
            ".svg": "image/svg+xml",
        }

        def translate_path(self, path):
            # Preview the child's habits page from local/ until it is put on the site.
            local = ROOT / "local" / "habits.json"
            if path.split("?")[0] == "/data/habits.json" and not (build.SITE / "data" / "habits.json").exists()                     and local.exists():
                return str(local)
            return super().translate_path(path)

    handler = functools.partial(Handler, directory=str(build.SITE))
    with http.server.ThreadingHTTPServer((args.bind, args.port), handler) as server:
        _out(f"本地预览 http://localhost:{args.port}/ （iPad 预览请加 --bind 0.0.0.0 并用本机 IP 访问），Ctrl+C 结束")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


def cmd_validate(cfg: Config, args: argparse.Namespace) -> int:
    from . import validate

    ids = args.game_ids or sorted(p.name.split(".")[0] for p in cfg.raw_dir.glob("*.json.gz"))
    engine = None if args.no_engine else build.LazyEngine(cfg, _out)
    failed = 0
    try:
        for game_id in ids:
            raw = analyze.load_raw(cfg.raw_dir / f"{game_id}.json.gz")
            profiles = [analyze.student_profile(sgf.parse(raw["sgf"]), raw["studentColor"])]
            verdicts = validate.validate(cfg, game_id, engine, _out)
            validate.report(game_id, verdicts, profiles + validate.STRONG_PROFILES, _out)
            failed += sum(not v.ok for v in verdicts)
    except KataGoError as e:
        _out(f"复核失败：{e}")
        return 1
    finally:
        if engine:
            engine.close()
    _out(f"共 {failed} 个关键点没通过复核。" if failed else "全部关键点通过复核。")
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
    p.add_argument("--latest", action="store_true", help="只分析野狐上的新对局；没有就直接结束（适合定时运行）")
    p.add_argument("--max", type=int, default=3, help="--latest 一次最多分析几局（默认 3）")
    p.add_argument("--publish", action="store_true", help="完成后提交 site/ 和 raw/ 并推送（网站随之更新）")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("collect", help="在本机分析最近的对局（只做整盘分析，不发布），给多盘统计用")
    p.add_argument("--limit", type=int, default=20, help="看最近几局（默认 20）")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("stats", help="多盘统计：已发布和本机的全部对局 → local/report.md 和“我的常见问题”页的数据")
    p.add_argument("--site", action="store_true", help="把“我的常见问题”的数据写进 site/（之后 publish 就会上网站）")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("publish", help="提交 site/ 和 raw/ 并推送")
    p.add_argument("-m", "--message", help="提交说明")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("build", help="从已保存的分析生成复盘页面数据（需要时做深度分析）")
    p.add_argument("game_ids", nargs="*", help="棋局 ID；不写则处理 raw/ 里的全部对局")
    p.add_argument("--no-engine", action="store_true", help="不启动 KataGo，缺深度分析就用整盘数据")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("serve", help="在本机预览 site/")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--bind", default="127.0.0.1", help="用 0.0.0.0 让同一局域网的 iPad 访问")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("validate", help="用更深的搜索和更强的人类档位复核关键点")
    p.add_argument("game_ids", nargs="*", help="棋局 ID；不写则复核 raw/ 里的全部对局")
    p.add_argument("--no-engine", action="store_true", help="只用已缓存的复核结果")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("show", help="查看已保存的分析")
    p.add_argument("game_id")
    p.set_defaults(func=cmd_show)

    args = parser.parse_args(argv)
    try:
        return args.func(load(), args)
    except fox.FoxError as e:
        _out(str(e))
        return 1
