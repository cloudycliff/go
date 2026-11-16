"""Checks an LLM explanation against the facts it was given (design 6.3).

The LLM may only retell facts. Every sentence must cite facts, may only use marks those facts
use, may not contain coordinates, percentages or numbers the cited facts do not hold, and may not
use Go terms the facts cannot back up. Anything else is a violation and the page falls back to
the template text.
"""

from __future__ import annotations

import re

MARK_CHARS = "▲△■□✕"
MAX_SENTENCES = 5
MIN_SENTENCES = 2
MAX_CHARS = 32  # per sentence, spaces not counted (design: about 30 characters)

COORD = re.compile(r"(?<![A-Za-z])[A-HJ-Ta-hj-t](?:1[0-9]|[1-9])(?![0-9])")
SGF_COORD = re.compile(r"(?<![A-Za-z])[a-s]{2}(?![A-Za-z])")
LETTER_MARK = re.compile(r"(?<![A-Za-z])[A-Z](?![A-Za-z0-9])")
DIGITS = re.compile(r"\d+(?:\.\d+)?")
CN_NUM = re.compile(r"([一二两三四五六七八九十]+)\s*(?=颗|目|次|个点)")
CN_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

CAPTURE_FACTS = {
    "refute_capture", "best_capture", "best_save", "atari_ignored", "self_atari",
    "group_dies", "group_lives", "common_capture", "common_group_dies", "rec_near_group",
}  # fmt: skip
# "死/活/吃" are claims about stones; they need a fact that is about stones.
STONE_WORDS = re.compile(r"[死活吃]")
# v1 computes nothing about these, so the text may not mention them.
BANNED = [
    (re.compile(r"劫"), "劫"),
    (re.compile(r"征"), "征子"),
    (re.compile(r"定式"), "定式"),
    (re.compile(r"先手|后手"), "先手/后手"),
    (re.compile(r"双活"), "双活"),
    (re.compile(r"(?<!一)(?<!两)眼(?!睛|光|前)|两眼|做眼|眼位"), "眼"),
    (re.compile(r"胜率|赢的机会|概率"), "胜率"),
    (re.compile(r"坐标|[一二三四五六七八九十]+路"), "坐标"),
    # Claims about what happened later in the game, or about the child's state of mind: no fact
    # holds them (found in real DeepSeek output that passed every other check).
    (re.compile(r"来得及|还有机会|还能补|补上|以后还能|后来"), "推测后面的棋"),
    (re.compile(r"太急|有点急|着急|急躁|粗心|马虎|大意|紧张"), "猜测心态"),
]


def _cn_to_int(text: str) -> int | None:
    if text == "十":
        return 10
    if "十" in text:
        tens, _, ones = text.partition("十")
        return CN_DIGITS.get(tens, 1) * 10 + CN_DIGITS.get(ones, 0) if tens in CN_DIGITS or not tens else None
    if len(text) == 1:
        return CN_DIGITS.get(text)
    return None


def _numbers(value) -> set[float]:
    out: set[float] = set()
    if isinstance(value, bool):
        return out
    if isinstance(value, (int, float)):
        out.add(float(value))
    elif isinstance(value, dict):
        for v in value.values():
            out |= _numbers(v)
    elif isinstance(value, list):
        for v in value:
            out |= _numbers(v)
    return out


def _marks_in(value) -> set[str]:
    out: set[str] = set()
    if isinstance(value, str):
        if value in MARK_CHARS or re.fullmatch(r"[A-Z]", value):
            out.add(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k in ("mark", "moveMark", "aiMark", "commonMark") or isinstance(v, (dict, list)):
                out |= _marks_in(v)
    elif isinstance(value, list):
        for v in value:
            out |= _marks_in(v)
    return out


def _number_ok(n: float, allowed: set[float]) -> bool:
    return any(abs(n - a) < 0.51 for a in allowed)


def check_sentence(text: str, refs: list, facts: dict[str, dict], marks: set[str], where: str) -> list[str]:
    problems = []
    if not isinstance(text, str) or not text.strip():
        return [f"{where}：内容为空"]
    if not isinstance(refs, list) or not refs:
        problems.append(f"{where}：没有引用事实（refs 为空）")
        refs = []
    unknown = [r for r in refs if r not in facts]
    if unknown:
        problems.append(f"{where}：引用了不存在的事实 {', '.join(map(str, unknown))}")
    cited = [facts[r] for r in refs if r in facts]

    length = len(re.sub(r"\s", "", text))
    if length > MAX_CHARS:
        problems.append(f"{where}：太长（{length} 字，最多 {MAX_CHARS} 字）")
    if "%" in text or "％" in text or "百分" in text:
        problems.append(f"{where}：不能出现百分比")
    if COORD.search(text) or SGF_COORD.search(text):
        problems.append(f"{where}：出现了坐标")

    used = {c for c in text if c in MARK_CHARS} | set(LETTER_MARK.findall(text))
    stray = sorted(used - marks)
    if stray:
        problems.append(f"{where}：用了棋盘上没有的标记 {' '.join(stray)}")
    # ✕ (the move played) and A (the recommended / good move) mean the same thing on every card,
    # so a sentence may name them without citing; what it says about them is still checked
    # (numbers, 死/活/吃). Other marks must come with a fact about them.
    always = {"✕", "A"} & marks
    cited_marks = _marks_in(cited) | always
    uncited = sorted((used & marks) - cited_marks)
    if uncited:
        problems.append(f"{where}：提到 {' '.join(uncited)}，但没有引用讲到它的事实")

    allowed = _numbers(cited)
    for m in DIGITS.findall(text):
        if not _number_ok(float(m), allowed):
            problems.append(f"{where}：数字 {m} 不在所引用的事实里")
    for m in CN_NUM.findall(text):
        n = _cn_to_int(m)
        if n is not None and not _number_ok(n, allowed):
            problems.append(f"{where}：数字「{m}」不在所引用的事实里")

    if STONE_WORDS.search(text) and not any(f.get("type") in CAPTURE_FACTS for f in cited):
        problems.append(f"{where}：说了死/活/吃，但没有引用提子或棋块死活的事实")
    for pattern, name in BANNED:
        if pattern.search(text):
            problems.append(f"{where}：不能使用「{name}」")
    return problems


def verify(output, facts: list[dict], marks: list[dict]) -> list[str]:
    """Returns the violations; an empty list means the explanation may be shown."""
    if not isinstance(output, dict):
        return ["输出不是 JSON 对象"]
    by_id = {f["id"]: f for f in facts}
    labels = {m["label"] for m in marks if m.get("label")}
    sentences = output.get("sentences")
    problems = []
    if not isinstance(sentences, list):
        return ["缺少 sentences 列表"]
    if not MIN_SENTENCES <= len(sentences) <= MAX_SENTENCES:
        problems.append(f"句数 {len(sentences)}，应为 {MIN_SENTENCES}～{MAX_SENTENCES} 句")
    for n, s in enumerate(sentences, 1):
        if not isinstance(s, dict):
            problems.append(f"第 {n} 句格式不对")
            continue
        problems += check_sentence(s.get("text"), s.get("refs"), by_id, labels, f"第 {n} 句")
    tip = output.get("tip")
    if not isinstance(tip, dict):
        problems.append("缺少 tip")
    else:
        problems += check_sentence(tip.get("text"), tip.get("refs"), by_id, labels, "提示")
    return problems
