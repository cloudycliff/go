"""Template explanation: always generated, and the fallback when the LLM's text fails checks."""

from __future__ import annotations

from .evaluate import SEVERITY_ZH

TIPS = {
    "missed_punish": "对方下完一手，先想一想：它有没有留下毛病，能不能马上抓住？",
    "missed_urgent": "每次落子前，先看看上一次的急所还在不在。",
    "life_death": "下之前先数一数双方棋子的气，看看谁的棋更危险。",
    "big_point": "布局时先抢最大的空地方，再考虑小地方。",
    "territory": "动手之前先比一比：哪里最大？哪块棋需要补？",
    "endgame": "收官时先找最大的地方，能先手的先下。",
    "good": "这种好棋多看几遍，记住它的样子。",
    "slip": "落子前多停一秒：先看看有没有更急、更大的地方。",
}


def _f(facts: list[dict], type_: str) -> dict | None:
    return next((f for f in facts if f["type"] == type_), None)


def _points(n: int) -> str:
    return f"约 {n} 目" if n >= 1 else "不到 1 目"


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
    f = _f(facts, "best_capture")
    if f:
        out.append(f"下 A 的话，可以吃掉 {f['mark']} 这 {f['count']} 颗子。")
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
    return out


def explain(kind: str, category: str, facts: list[dict], recommended: dict) -> dict:
    if kind == "good":
        return {"template": good(facts), "tip": TIPS["good"]}
    tip = TIPS.get(kind) if kind in ("missed_punish", "missed_urgent") else None
    if _f(facts, "slip") and kind == "mistake":
        tip = TIPS["slip"]
    return {"template": mistake(kind, facts, recommended), "tip": tip or TIPS.get(category, TIPS["territory"])}


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
