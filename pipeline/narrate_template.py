"""Template explanation: always generated, and the fallback when the LLM's text fails checks."""

from __future__ import annotations

from .evaluate import SEVERITY_ZH

TIPS = {
    "missed_punish": "对方下完一手，先想一想：它有没有留下毛病，能不能马上抓住？",
    "missed_urgent": "每次落子前，先看看上一次的急所还在不在。",
    "life_death": "下之前先数一数双方棋子的气，看看谁的棋更危险。",
    "big_point": "布局时先抢最大的空地方，再考虑小地方。",
    "territory": "动手之前先比一比：哪里最大？哪块棋需要补？",
    "endgame": "收官时先找最大的地方。",
    "good": "这种好棋多看几遍，记住它的样子。",
    "slip": "落子前多停一秒：先看看有没有更急、更大的地方。",
}


def _f(facts: list[dict], type_: str) -> dict | None:
    return next((f for f in facts if f["type"] == type_), None)


def _points(n: int) -> str:
    return f"约 {n} 目" if n >= 1 else "不到 1 目"


def follow_up_text(f: dict) -> str:
    """What each move is worth after the opponent's best answer."""
    where_a = "就在 A 附近" if f.get("replyNearA") else "在别处"
    return (
        f"下 {f['moveMark']} 以后，对方最强的一手{where_a}，这时你"
        f"{'领先' if f['leadAfterA'] >= 0 else '落后'}约 {abs(round(f['leadAfterA']))} 目；"
        f"实战 {f['playedMark']} 后对方应一手，你{'领先' if f['leadAfterPlayed'] >= 0 else '落后'}"
        f"约 {abs(round(f['leadAfterPlayed']))} 目。"
    )


def near_group_text(f: dict) -> str:
    whose = "你的" if f["owner"] == "student" else "对方的"
    return f"{f['pointMark']} 紧挨着{whose} {f['mark']}，{f['mark']} 只剩 {f['liberties']} 口气。"


def why_text(f: dict) -> str:
    """Sentences for the "why" facts, shared by the template and the LLM's fact meanings."""
    t = f["type"]
    if t == "far_away":
        return f"你下在了{f['playedRegion']}，可这时{f['recRegion']}的 A 更要紧。"
    if t == "opponent_wants":
        where = "A" if f.get("exact") else "A 旁边"
        return f"你下了 ✕ 以后，对方最想下的就是 {where}：这里是双方都想要的地方。"
    if t == "refute_squeeze":
        return f"你下了 ✕ 以后，对方下一步就能让 {f['mark']} 只剩 {f['liberties']} 口气。"
    if t == "rec_connects":
        return f"下 {f['moveMark']} 能把 {f['mark']} 和 {f['mark2']} 连在一起。"
    if t == "rec_cuts":
        return f"下 {f['moveMark']} 能把对方的 {f['mark']} 和 {f['mark2']} 隔开。"
    if t == "rec_atari":
        return f"下 {f['moveMark']} 可以叫吃对方的 {f['mark']}。"
    if t == "rec_presses":
        return f"下 {f['moveMark']} 以后，对方的 {f['mark']} 只剩 {f['liberties']} 口气。"
    if t == "common_far_away":
        return f"大家常下的 B 在{f['playedRegion']}，可这时{f['recRegion']}的 A 更要紧。"
    if t == "common_opponent_wants":
        where = "A" if f.get("exact") else "A 旁边"
        return f"假如你下的是 B，对方下一步最想下的正是 {where}。你抢先下了 A。"
    if t == "follow_up":
        return follow_up_text(f)
    return ""


WHAT_HAPPENED = ("far_away", "opponent_wants", "refute_squeeze")
WHY_A = ("rec_connects", "rec_cuts", "rec_atari", "rec_presses", "common_far_away", "common_opponent_wants",
         "follow_up")


PHASE_ZH = {"opening": "布局", "middle": "中盘", "endgame": "官子"}
CATEGORY_LONG = {"life_death": "死活/对杀", "big_point": "大场", "territory": "实地", "endgame": "官子"}


def describe(f: dict) -> str:
    """What one fact means, in plain words; the LLM gets this next to the fact's fields."""
    t = f["type"]
    grade = SEVERITY_ZH.get(f.get("severity") or "", "")
    texts = {
        "played": "✕ 是你实战下的位置。",
        "recommended": {"peer": "A 是推荐的下法，比你强一点的人多数会下这里。",
                        "urgent": "A 是推荐的下法，也是这一段一直没下的急所。"}.get(f.get("source"), "A 是推荐的下法。"),
        "loss": f"这手亏了{_points(f.get('scoreLoss', 0))}" + (f"，等级是{grade}。" if grade else "。"),
        "segment_loss": f"这一片前后 {f.get('moves')} 手棋，一共亏了约 {f.get('scoreLoss')} 目" + (f"，等级是{grade}。" if grade else "。"),
        "opponent_mistake": f"对方上一手亏了{_points(f.get('scoreLoss', 0))}，你这手没有抓住机会。",
        "missed_urgent": f"A 是急所，这一段你有 {f.get('turns')} 次机会下在那里，都没有下。" + ("对方也没有发现。" if f.get("opponentMissed") else ""),
        "atari_ignored": f"{f.get('mark')} 已经被叫吃（只剩一口气），你这手没有逃。",
        "self_atari": f"你这手让 {f.get('mark')} 只剩一口气。",
        "refute_capture": f"实战后，对方接下来可以吃掉 {f.get('mark')} 这 {f.get('count')} 颗子。",
        "best_save": f"下 A 可以救出 {f.get('mark')} 这 {f.get('count')} 颗子。",
        "best_capture": f"下 {f.get('moveMark', 'A')} 可以吃掉 {f.get('mark')} 这 {f.get('count')} 颗子。",
        "group_dies": f"AI 认为你这手以后，{f.get('mark')} 这块棋（{f.get('count')} 颗子）很可能被吃掉。",
        "group_lives": f"对方 {f.get('mark')} 这块棋本来可以吃掉，你这手以后它很可能活了。",
        "area_flip": f"{f.get('region')}大约 {f.get('count')} 个点的地，变成了对方的。",
        "peer_choice": ("比你强一点的人多数也会下 A。" if f.get("sameAsAi")
                        else f"比你强一点的人多数会下 A；AI 最喜欢的是 B，两者只差{_points(f.get('diff', 0))}。"),
        "slip": "和你水平差不多的人，" + ("多数" if f.get("share") == "most" else "很多") + "会下 A，这次是一时疏忽。",
        "rec_near_group": near_group_text(f) if "pointMark" in f else "",
        "good_move": "你下了 A，这是 AI 最喜欢的一手。",
        "common_move": f"和你水平差不多的人多数会下 B，那样要亏{_points(f.get('scoreLoss', 0))}。",
        "common_capture": f"下 B 的话，对方可以吃掉 {f.get('mark')} 这 {f.get('count')} 颗子。",
        "common_group_dies": f"下 B 的话，{f.get('mark')} 这块棋就危险了。",
        "phase": f"第 {f.get('move')} 手，{PHASE_ZH.get(f.get('phase'), '')}阶段，类别：{CATEGORY_LONG.get(f.get('category'), '其他')}。",
    }
    if t == "follow_up":
        where_a = "就在 A 附近" if f.get("replyNearA") else "在别处"
        return (
            f"下 A 以后，对方最强的一手{where_a}，这时孩子"
            f"{'领先' if f['leadAfterA'] >= 0 else '落后'}约 {abs(round(f['leadAfterA']))} 目；"
            f"实战 ✕ 后对方应一手，孩子{'领先' if f['leadAfterPlayed'] >= 0 else '落后'}"
            f"约 {abs(round(f['leadAfterPlayed']))} 目，两者相差约 {abs(round(f['diff']))} 目。"
        )
    if t in WHAT_HAPPENED or t in WHY_A:
        return why_text(f)
    return texts.get(t, "")


def mistake(kind: str, facts: list[dict], recommended: dict) -> list[str]:
    out = ["你下了 ✕。"]
    loss = _f(facts, "loss")
    seg = _f(facts, "segment_loss")
    if loss:
        grade = "" if seg else SEVERITY_ZH.get(loss.get("severity") or "", "")
        out.append(f"这手亏了{_points(loss['scoreLoss'])}" + (f"，算是{grade}。" if grade else "。"))
    if seg:
        grade = SEVERITY_ZH.get(seg.get("severity") or "", "")
        out.append(
            f"这一片前后 {seg['moves']} 手棋，一共亏了约 {seg['scoreLoss']} 目" + (f"，算是{grade}。" if grade else "。")
        )
    opp = _f(facts, "opponent_mistake")
    if opp:
        out.append(f"对方上一手亏了{_points(opp['scoreLoss'])}，给了你机会，可惜这手没有抓住。")
    urgent = _f(facts, "missed_urgent")
    if urgent:
        text = f"A 是急所，这一段你有 {urgent['turns']} 次机会下在那里，都没有下。"
        if urgent.get("opponentMissed"):
            text += "对方也没有发现。"
        out.append(text)
    f = _f(facts, "atari_ignored")
    if f:
        out.append(f"{f['mark']} 已经被叫吃了，这手没有逃出来。")
    f = _f(facts, "self_atari")
    if f:
        out.append(f"这手让 {f['mark']} 只剩一口气了。")
    f = _f(facts, "refute_capture")
    if f:
        out.append(f"对方接下来可以吃掉 {f['mark']} 这 {f['count']} 颗子。")
    f = _f(facts, "group_dies")
    if f and not _f(facts, "refute_capture"):
        out.append(f"AI 认为 {f['mark']} 这块棋（{f['count']} 颗子）很可能被吃掉。")
    f = _f(facts, "group_lives")
    if f:
        out.append(f"对方 {f['mark']} 这块棋本来可以吃掉，现在它很可能活了。")
    f = _f(facts, "area_flip")
    if f:
        out.append(f"{f['region']}大约 {f['count']} 个点的地，变成了对方的。")
    out += [why_text(f) for f in facts if f["type"] in WHAT_HAPPENED]

    peer = _f(facts, "peer_choice")
    if recommended.get("source") == "peer" and peer:
        out.append(f"更好的是 A：比你强一点的人多数会下这里，和 AI 最喜欢的 B 只差{_points(round(peer['diff']))}。")
    elif recommended.get("source") == "urgent":
        out.append("更好的是先下 A。")
    else:
        out.append("更好的是 A。" + ("比你强一点的人也会这样下。" if peer and peer.get("sameAsAi") else ""))
    f = _f(facts, "best_save")
    if f:
        out.append(f"下 A 可以救出 {f['mark']} 这 {f['count']} 颗子。")
    f = _f(facts, "rec_near_group")
    if f:
        out.append(near_group_text(f))
    f = _f(facts, "best_capture")
    if f:
        out.append(f"下 A 的话，可以吃掉 {f['mark']} 这 {f['count']} 颗子。")
    out += [why_text(f) for f in facts if f["type"] in WHY_A]
    f = _f(facts, "slip")
    if f:
        who = "多数" if f["share"] == "most" else "很多"
        out.append(f"和你水平差不多的人，{who}会下 A。这次是一时疏忽，你本来能找到的！")
    return out


def good(facts: list[dict]) -> list[str]:
    out = ["你下了 A，这正是 AI 最喜欢的一手！"]
    common = _f(facts, "common_move")
    if common:
        out.append(f"和你水平差不多的人，多数会下 B，那样要亏{_points(common['scoreLoss'])}。")
    f = _f(facts, "common_capture")
    if f:
        out.append(f"下 B 的话，对方可以吃掉 {f['mark']} 这 {f['count']} 颗子。")
    f = _f(facts, "common_group_dies")
    if f and not _f(facts, "common_capture"):
        out.append(f"下 B 的话，{f['mark']} 这块棋就危险了。")
    f = _f(facts, "best_capture")
    if f:
        out.append(f"下 A 以后，可以吃掉 {f['mark']} 这 {f['count']} 颗子。")
    f = _f(facts, "rec_near_group")
    if f:
        out.append(near_group_text(f))
    out += [why_text(f) for f in facts if f["type"] in WHY_A]
    return out


def explain(
    kind: str, category: str, facts: list[dict], recommended: dict
) -> dict:
    if kind == "good":
        return {"template": good(facts), "tip": TIPS["good"]}
    tip = TIPS.get(kind) if kind in ("missed_punish", "missed_urgent") else None
    if _f(facts, "slip") and kind == "mistake":
        tip = TIPS["slip"]
    return {
        "template": mistake(kind, facts, recommended),
        "tip": tip or TIPS.get(category, TIPS["territory"]),
    }


CATEGORY_ZH = {"life_death": "死活", "big_point": "大场", "territory": "实地", "endgame": "官子"}
KIND_ZH = {"mistake": "错误", "missed_punish": "没惩罚对方", "missed_urgent": "漏掉急所", "good": "好棋"}


def summary(keypoints: list[dict], small_game: bool) -> str:
    """One line for the end of the page, e.g. "这盘有 2 处死活、1 处没惩罚对方"."""
    if small_game:
        return "这盘下得不错，有两处可以更好。"
    parts: dict[str, int] = {}
    for k in keypoints:
        if k["kind"] == "good":
            continue
        if k["kind"] in ("missed_punish", "missed_urgent"):
            label = KIND_ZH[k["kind"]]
        else:
            label = CATEGORY_ZH.get(k["category"], "其他")
        parts[label] = parts.get(label, 0) + 1
    text = "、".join(f"{n} 处{label}" for label, n in parts.items())
    goods = sum(k["kind"] == "good" for k in keypoints)
    if not text:
        return "这盘没有大问题。" + ("还下出了一手好棋！" if goods else "")
    return f"这盘要注意：{text}。" + ("另外还下出了一手好棋！" if goods else "")
