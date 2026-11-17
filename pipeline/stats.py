"""Statistics across games: where the student loses points, and which problems come back.

Every move is counted, not only the key points a page shows, so the selection rules cannot bias
the picture. All numbers come from the whole-game pass (400 visits), which every game has. The
opponents' moves are counted the same way, as a baseline for players of about the same rank.

    raw/*.json.gz + local/raw/*.json.gz  ->  local/report.md
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import analyze, board, evaluate, facts, keypoints, sgf, shapes
from .board import distance, other
from .coords import sgf_to_xy
from .evaluate import SEVERITY_ORDER, gtp_sgf, policy_at

BAD = SEVERITY_ORDER["mistake"]  # features are collected for 问题手 and 恶手
NEAR = 2  # lines: next to the opponent's last move
FAR = 6  # lines: somewhere else
MIN_GAMES = 3  # a problem seen in fewer games is not called a habit
MIN_SHAPE = 10  # moves of a shape before it gets a row
PHASES = ("opening", "middle", "endgame")
PHASE_ZH = {"opening": "布局（1-59 手）", "middle": "中盘（60-180 手）", "endgame": "官子（181 手起）"}

# Feature -> what it means, in the report.
TAGS = {
    "group_dies": "自己的棋块（2 子以上）因此被判死",
    "refute_capture": "对方接下来能吃掉自己 2 子以上",
    "refute_squeeze": "对方下一手就让自己的棋块只剩 1-2 口气",
    "played_short": "这手让自己的棋块只剩 1-2 口气",
    "rec_near_group": "AI 首选紧挨着一块气紧的棋（救自己或攻对方）",
    "rec_connects": "AI 首选是把自己两块棋连起来",
    "rec_cuts": "AI 首选是把对方两块棋分断",
    "rec_atari_or_press": "AI 首选能叫吃或紧对方的气",
    "followed": "跟着对方下在它旁边，AI 首选却在别处",
    "tenuki": "对方上一手需要应，却下到了别处",
    "opponent_wants": "AI 首选正是对方下一手最想下的地方",
    "missed_punish": "对方上一手是问题手，这手没有抓住",
    "missed_urgent": "同一个急所连续几次没下",
    "slip": "同级别的人多数能找到 AI 首选（一时疏忽）",
}


@dataclass
class Move:
    game: str
    date: str
    number: int
    phase: str
    severity: str | None
    decided: bool
    loss: float
    best_match: bool
    shape: str | None = None
    tags: set[str] = field(default_factory=set)

    @property
    def bad(self) -> bool:
        return SEVERITY_ORDER[self.severity] >= BAD


@dataclass
class GameStats:
    id: str
    date: str
    color: str
    moves: int
    result: str
    student: list[Move]
    opponent: list[Move]
    published: bool


def _tags(e, game, boards, responses, evals, urgent: set[int]) -> set[str]:
    """What the board and the search say about a bad move (the same facts as the review pages)."""
    i, color, size = e.index, e.color, game.size
    before_board, after_board = boards[i], boards[i + 1]
    before, after = responses[i], responses[i + 1]
    k = facts.KeyFacts()
    tags: set[str] = set()
    reply = ""
    if after.get("moveInfos"):
        reply = gtp_sgf(after["moveInfos"][0]["move"], size)
        pv = facts.pv_moves(other(color), after["moveInfos"][0].get("pv", []), size)
        _, lost = facts.replay(after_board, pv)
        if len({p for p in lost[color] if before_board.get(p) == color}) >= facts.MIN_CAPTURE:
            tags.add("refute_capture")
    facts.refute_squeeze(k, before_board, after_board, reply, color)
    facts.played_short(k, before_board, after_board, e.point, color)
    facts.near_group(k, before_board, e.best, color)
    facts.shape_facts(k, before_board, e.best, color)
    facts.where_facts(k, after, e.point, e.best, size)
    for f in k.facts:
        t = f["type"]
        tags.add("rec_atari_or_press" if t in ("rec_atari", "rec_presses") else t)
    tags.discard("far_away")  # followed / tenuki say it better: they look at the opponent's move too
    own_before, own_after = before.get("ownership"), after.get("ownership")
    if own_before and own_after:
        dies, _ = facts.flips(after_board, own_before, own_after, color, size)
        if any(len({p for p in s if before_board.get(p) == color}) >= 2 for s, _ in dies):
            tags.add("group_dies")
    prev = evals[i - 1] if i > 0 else None
    if prev is not None and prev.color != color and prev.point:
        p, b, last = sgf_to_xy(e.point, size), sgf_to_xy(e.best, size), sgf_to_xy(prev.point, size)
        if distance(p, last) <= NEAR and distance(b, last) >= FAR and distance(b, p) >= FAR:
            tags.add("followed")
        if distance(b, last) <= NEAR and distance(p, last) >= FAR:
            tags.add("tenuki")
        if SEVERITY_ORDER[prev.severity] >= BAD and e.score_loss >= 0.5 * prev.score_loss:
            tags.add("missed_punish")
    if i in urgent:
        tags.add("missed_urgent")
    if policy_at(before.get("humanPolicy"), e.best, size) >= facts.SLIP_MANY:
        tags.add("slip")
    return tags


def game_stats(game_id: str, raw: dict, published: bool) -> GameStats:
    game = sgf.parse(raw["sgf"])
    student = raw["studentColor"]
    responses = raw["overview"]["responses"]
    evals = evaluate.evaluate(game, responses)
    boards = board.positions(game)
    sides: dict[str, list[Move]] = {"B": [], "W": []}
    for color in ("B", "W"):
        urgent = {t for c in keypoints._urgent(evals, color) for t in c.turns}
        for e in evals:
            if e.color != color or not e.point:
                continue
            m = Move(game_id, game.date, e.number, evaluate.phase(e.number), e.severity, e.decided,
                     e.score_loss, e.is_best, shape=shapes.describe(boards[e.index], e.point, color))
            if m.bad and not m.decided:
                m.tags = _tags(e, game, boards, responses, evals, urgent)
            sides[color].append(m)
    return GameStats(game_id, game.date, student, len(game.moves), game.result,
                     sides[student], sides[other(student)], published)


def load_all(folders: list[tuple[Path, bool]]) -> list[GameStats]:
    """(folder, published) pairs -> one GameStats per analysed game, oldest first."""
    out = []
    for folder, published in folders:
        for path in sorted(folder.glob("*.json.gz")):
            out.append(game_stats(path.name.split(".")[0], analyze.load_raw(path), published))
    return sorted(out, key=lambda g: (g.date, g.id))


# ---- Report ------------------------------------------------------------------------------


def _live(moves: list[Move]) -> list[Move]:
    """Moves played while the game was still open (decided games are played loosely)."""
    return [m for m in moves if not m.decided]


def _rate(moves: list[Move]) -> float:
    return 100.0 * sum(m.bad for m in moves) / len(moves) if moves else 0.0


def _avg(moves: list[Move]) -> float:
    return sum(m.loss for m in moves) / len(moves) if moves else 0.0


def _match(moves: list[Move]) -> float:
    return 100.0 * sum(m.best_match for m in moves) / len(moves) if moves else 0.0


def _pct(n: int, total: int) -> str:
    return f"{100.0 * n / total:.0f}%" if total else "-"


def tag_rows(games: list[GameStats]) -> list[dict]:
    """Per feature: the student's bad moves with it, in how many games, and the opponents' share."""
    bad_mine = [m for g in games for m in _live(g.student) if m.bad]
    bad_theirs = [m for g in games for m in _live(g.opponent) if m.bad]
    rows = []
    for tag, text in TAGS.items():
        hit = [m for m in bad_mine if tag in m.tags]
        if hit:
            rows.append({
                "tag": tag, "text": text, "moves": hit, "games": len({m.game for m in hit}),
                "share": len(hit) / len(bad_mine), "loss": sum(m.loss for m in hit),
                "opponentShare": sum(tag in m.tags for m in bad_theirs) / max(1, len(bad_theirs)),
            })
    return sorted(rows, key=lambda r: -len(r["moves"]))


def report(games: list[GameStats]) -> str:
    mine = [m for g in games for m in g.student]
    theirs = [m for g in games for m in g.opponent]
    bad_mine = [m for m in _live(mine) if m.bad]
    bad_theirs = [m for m in _live(theirs) if m.bad]
    out: list[str] = []
    w = out.append
    n_pub = sum(g.published for g in games)
    w("# 多盘统计")
    w("")
    w(f"{len(games)} 局（{games[0].date} 至 {games[-1].date}；已发布 {n_pub} 局，只在本机 "
      f"{len(games) - n_pub} 局），孩子共 {len(mine)} 手。")
    w("")
    w("- 数据都来自整盘分析（每个局面 400 visits），每一手都算，不只是页面上的关键点。")
    w("- 对手和孩子段位相近，用同样的方法统计，作为参照。")
    w("- “问题手”包括问题手和恶手（按段位折算胜率掉 10% 以上）。"
      "胜负已定以后的手双方都下得随意，单独列出，不计入比率。")
    w("")

    w("## 一、各阶段")
    w("")
    w("| 阶段 | 孩子手数 | 问题手 / 100 手 | 平均每手亏 | 下在 AI 首选 | 对手：问题手 / 100 手 | 对手：平均每手亏 |")
    w("|---|---|---|---|---|---|---|")
    for ph in PHASES:
        a = _live([m for m in mine if m.phase == ph])
        b = _live([m for m in theirs if m.phase == ph])
        w(f"| {PHASE_ZH[ph]} | {len(a)} | {_rate(a):.1f} | {_avg(a):.1f} 目 | {_match(a):.0f}% | "
          f"{_rate(b):.1f} | {_avg(b):.1f} 目 |")
    a, b = _live(mine), _live(theirs)
    w(f"| 合计 | {len(a)} | {_rate(a):.1f} | {_avg(a):.1f} 目 | {_match(a):.0f}% | "
      f"{_rate(b):.1f} | {_avg(b):.1f} 目 |")
    decided = [m for m in mine if m.decided]
    w("")
    w(f"胜负已定以后孩子下了 {len(decided)} 手，其中问题手 {sum(m.bad for m in decided)} 手，未计入上表。")
    w("")

    w("## 二、反复出现的问题")
    w("")
    w(f"孩子的问题手共 {len(bad_mine)} 手（对手 {len(bad_theirs)} 手）。一手可以有几个特征。"
      f"“几局”是出现过的对局数，少于 {MIN_GAMES} 局的标“少”，不算习惯。")
    w("")
    w("| 特征 | 孩子：手数 | 占问题手 | 几局 | 共亏 | 对手：占问题手 |")
    w("|---|---|---|---|---|---|")
    rows = tag_rows(games)
    for r in rows:
        few = "" if r["games"] >= MIN_GAMES else "（少）"
        w(f"| {r['text']} | {len(r['moves'])} | {r['share'] * 100:.0f}% | {r['games']}{few} | "
          f"{r['loss']:.0f} 目 | {r['opponentShare'] * 100:.0f}% |")
    w("")
    w("注意：前三行常常是同一件事：一个大地方（往往是一块棋的死活）留在盘上，双方都好几手没去下。")
    w("")
    w("## 三、棋形")
    w("")
    w(f"每种棋形下了多少手、其中多少是问题手（只算胜负未定时，至少 {MIN_SHAPE} 手才列出）。认不出棋形的手不在表里。")
    w("")
    w("| 棋形 | 孩子下了 | 其中问题手 | 比例 | 对手比例 |")
    w("|---|---|---|---|---|")
    by_shape: dict[str, list[Move]] = defaultdict(list)
    opp_shape: dict[str, list[Move]] = defaultdict(list)
    for m in _live(mine):
        if m.shape:
            by_shape[m.shape].append(m)
    for m in _live(theirs):
        if m.shape:
            opp_shape[m.shape].append(m)
    overall = _rate(_live(mine))
    for name, ms in sorted(by_shape.items(), key=lambda kv: -len(kv[1])):
        if len(ms) < MIN_SHAPE:
            continue
        rate, opp = _rate(ms), _rate(opp_shape.get(name, []))
        flag = " ⚠" if len(ms) >= 20 and rate >= overall * 1.5 and rate >= opp * 1.5 else ""
        w(f"| {name} | {len(ms)} | {sum(m.bad for m in ms)} | {rate:.0f}%{flag} | {opp:.0f}% |")
    w("")
    w(f"全部手的问题手比例是 {overall:.0f}%；⚠ = 至少 20 手，比例达到这个数和对手同一棋形的 1.5 倍。"
      "手数少的棋形，一两手就能改变比例。")
    w("")

    w("## 四、按时间")
    w("")
    w("| 日期 | 棋局 | 执色 | 结果 | 孩子手数（未定） | 问题手 / 100 手 | 平均每手亏 | 下在 AI 首选 |")
    w("|---|---|---|---|---|---|---|---|")
    for g in games:
        a = _live(g.student)
        where = "" if g.published else "（本机）"
        w(f"| {g.date} | {g.id}{where} | {'黑' if g.color == 'B' else '白'} | {g.result} | {len(a)} | "
          f"{_rate(a):.1f} | {_avg(a):.1f} 目 | {_match(a):.0f}% |")
    half = len(games) // 2
    early = [m for g in games[:half] for m in _live(g.student)]
    late = [m for g in games[half:] for m in _live(g.student)]
    w("")
    w(f"前 {half} 局：问题手 {_rate(early):.1f} / 100 手，平均每手亏 {_avg(early):.1f} 目；"
      f"后 {len(games) - half} 局：{_rate(late):.1f} / 100 手，{_avg(late):.1f} 目。"
      "局数少，对手和棋局长短也不同，差别不大时不要当成进步或退步。")
    w("")

    w("## 五、例子（常见特征里亏得最多的 3 手）")
    w("")
    for r in rows[:6]:
        examples = sorted(r["moves"], key=lambda m: -m.loss)[:3]
        w(f"- {r['text']}：" + "；".join(f"{m.date} {m.game} 第 {m.number} 手（亏约 {m.loss:.0f} 目）" for m in examples))
    w("")
    return "\n".join(out)


# ---- The page for the child ---------------------------------------------------------------

# Habits the child page can name: features grouped into one lesson each, in a child's words.
HABITS = [
    {
        "key": "safety",
        "tags": {"group_dies", "refute_squeeze", "played_short", "refute_capture"},
        "title": "先照顾好自己气紧的棋",
        "text": "亏得多的棋里，常常是自己的一块棋气变少了，被对方吃掉或者变得很危险。",
        "tip": "落子前先数一数：自己哪块棋只剩两三口气？有的话先补一手。",
    },
    {
        "key": "slip",
        "tags": {"slip"},
        "title": "有些好棋，你本来能找到",
        "text": "这些地方，和你水平差不多的人多数都能下对。不是不会，是没有停下来想一想。",
        "tip": "落子前停一秒，问问自己：有没有更急、更大的地方？",
    },
    {
        "key": "connect",
        "tags": {"rec_connects"},
        "title": "该连的时候先连上",
        "text": "AI 最想下的是把你的两块棋连在一起，你下了别处，后来两块棋都变弱了。",
        "tip": "看到自己的两块棋快要被分开，先想想要不要连上。",
    },
    {
        "key": "punish",
        "tags": {"missed_punish"},
        "title": "对方下错了，要抓住机会",
        "text": "对方刚下了一手不好的棋，你没有马上抓住它的毛病。",
        "tip": "对方下完一手，先看看它有没有留下毛病，能不能马上抓住。",
    },
    {
        "key": "urgent",
        "tags": {"missed_urgent"},
        "title": "急所不要一直放着",
        "text": "同一个要紧的地方，好几手都没有去下。",
        "tip": "每次落子前，先看看上一次的急所还在不在。",
    },
    {
        "key": "followed",
        "tags": {"followed"},
        "title": "不要总跟着对方下",
        "text": "对方下在哪里，你就应在它旁边，可这时别处更要紧。",
        "tip": "对方下完，先想想：一定要应吗？有没有更大的地方？",
    },
]
MAX_HABITS = 3
HABIT_RATIO = 1.3  # the child's share must be this many times the opponents' to count as a habit
MAX_EXAMPLES = 2


def habits(games: list[GameStats], pages: dict[str, dict]) -> dict:
    """Data for the child's page: counts only, and examples from key points already published.

    `pages` maps a published game id to its site data (site/data/games/<id>.json). Unpublished
    games add to the counts but never to the examples, so their boards stay on this computer.
    """
    live_mine = [m for g in games for m in _live(g.student)]
    live_theirs = [m for g in games for m in _live(g.opponent)]
    bad_mine = [m for m in live_mine if m.bad]
    bad_theirs = [m for m in live_theirs if m.bad]
    found = []
    shown: set[tuple[str, str]] = set()  # a key point illustrates one habit only
    for h in HABITS:
        hit = [m for m in bad_mine if m.tags & h["tags"]]
        opp = sum(bool(m.tags & h["tags"]) for m in bad_theirs)
        share = len(hit) / max(1, len(bad_mine))
        opp_share = opp / max(1, len(bad_theirs))
        n_games = len({m.game for m in hit})
        if n_games < MIN_GAMES or share < HABIT_RATIO * opp_share:
            continue
        found.append({
            "key": h["key"], "title": h["title"], "text": h["text"], "tip": h["tip"],
            "games": n_games, "share": round(share, 2), "opponentShare": round(opp_share, 2),
            "examples": _examples(h["tags"], games, pages, shown),
            "_gap": share - opp_share,
        })
    found.sort(key=lambda r: -r["_gap"])
    for r in found:
        del r["_gap"]
    phases = []
    for ph in PHASES:
        a = [m for m in live_mine if m.phase == ph]
        b = [m for m in live_theirs if m.phase == ph]
        phases.append({"phase": ph, "rate": round(_rate(a), 1), "opponentRate": round(_rate(b), 1)})
    return {
        "games": len(games),
        "from": games[0].date if games else "",
        "to": games[-1].date if games else "",
        "rate": round(_rate(live_mine), 1),
        "opponentRate": round(_rate(live_theirs), 1),
        "phases": phases,
        "habits": found[:MAX_HABITS],
    }


def _examples(tags: set[str], games: list[GameStats], pages: dict[str, dict], shown: set) -> list[dict]:
    """Published key points whose moves include a bad move with one of `tags`: the biggest first.

    Key points already in `shown` (used for another habit) are skipped; the ones chosen are added.
    """
    scored = []
    for g in games:
        page = pages.get(g.id)
        if not page:
            continue
        by_number = {m.number: m for m in g.student}
        for k in page["keyPoints"]:
            if k["kind"] == "good":
                continue
            hit = [by_number[n] for n in k["moves"] if n in by_number]
            hit = [m for m in hit if m.bad and not m.decided and m.tags & tags]
            if hit and (g.id, k["id"]) not in shown:
                scored.append((max(m.loss for m in hit), g.id, k["id"], g.date))
    out, used = [], set()
    for loss, gid, kid, date in sorted(scored, key=lambda r: (-r[0], r[1], r[2])):
        if gid in used:
            continue  # one example per game
        used.add(gid)
        shown.add((gid, kid))
        out.append({"game": gid, "keyPoint": kid, "date": date})
        if len(out) == MAX_EXAMPLES:
            break
    return out


def practice(games: list[GameStats], pages: dict[str, dict]) -> dict:
    """Every published key point as a question, newest first, with the habits its moves show.

    The practice page filters by these habit keys; the good-move page takes kind == "good".
    """
    questions = []
    for g in sorted(games, key=lambda g: (g.date, g.id), reverse=True):
        page = pages.get(g.id)
        if not page:
            continue
        by_number = {m.number: m for m in g.student}
        for k in page["keyPoints"]:
            moves = [by_number[n] for n in k["moves"] if n in by_number]
            tags = set().union(*(m.tags for m in moves if m.bad and not m.decided)) if moves else set()
            questions.append({
                "game": g.id, "keyPoint": k["id"], "date": g.date, "move": k["move"], "kind": k["kind"],
                "title": k["title"], "habits": [h["key"] for h in HABITS if tags & h["tags"]],
            })
    return {"habits": [{"key": h["key"], "title": h["title"]} for h in HABITS], "questions": questions}
