"""M3 acceptance: deliberately bad LLM outputs are all rejected; faithful ones pass."""

import json
import unittest

from pipeline import narrate_llm, narrate_template, verify

FACTS = [
    {"id": "f1", "type": "played", "mark": "✕"},
    {"id": "f2", "type": "recommended", "mark": "A", "source": "ai"},
    {"id": "f3", "type": "loss", "scoreLoss": 12, "severity": "blunder"},
    {"id": "f4", "type": "refute_capture", "mark": "▲", "count": 4},
    {"id": "f5", "type": "best_save", "mark": "▲", "count": 4, "moveMark": "A"},
    {"id": "f6", "type": "area_flip", "count": 15, "region": "右下"},
    {"id": "f7", "type": "phase", "phase": "middle", "category": "life_death", "move": 87},
]
MARKS = [
    {"label": "✕", "type": "point", "point": "rd", "role": "played"},
    {"label": "A", "type": "point", "point": "rf", "role": "recommended"},
    {"label": "▲", "type": "group", "points": ["qd", "qe", "re", "rc"], "owner": "student"},
]


def out(*sentences, tip=("下之前先数一数▲有几口气。", ["f4"])):
    return {
        "sentences": [{"text": t, "refs": r} for t, r in sentences],
        "tip": {"text": tip[0], "refs": tip[1]},
    }


GOOD = out(
    ("你下了✕以后，对方可以吃掉▲这4颗子。", ["f1", "f4"]),
    ("这手亏了大约12目，是一个恶手。", ["f3"]),
    ("更好的是下在A，可以把▲救出来。", ["f2", "f5"]),
)

BAD = {
    "坐标 GTP": out(("你下在Q16以后，对方可以吃掉▲这4颗子。", ["f4"]), ("这手亏了约12目。", ["f3"])),
    "坐标 SGF": out(("你下在rd以后，▲很危险。", ["f4"]), ("这手亏了约12目。", ["f3"])),
    "第几路": out(("A在三路，是急所。", ["f2"]), ("这手亏了约12目。", ["f3"])),
    "错误数字": out(("对方可以吃掉▲这5颗子。", ["f4"]), ("这手亏了约12目。", ["f3"])),
    "错误中文数字": out(("对方可以吃掉▲这五颗子。", ["f4"]), ("这手亏了约12目。", ["f3"])),
    "数字没引用": out(("对方可以吃掉▲这4颗子。", ["f1"]), ("这手亏了约12目。", ["f3"])),
    "百分号": out(("这手让你的胜率掉了30%。", ["f3"]), ("这手亏了约12目。", ["f3"])),
    "胜率": out(("这手让胜率下降很多。", ["f3"]), ("这手亏了约12目。", ["f3"])),
    "不存在的标记": out(("C点也很重要。", ["f2"]), ("这手亏了约12目。", ["f3"])),
    "不存在的标记△": out(("△这块棋很厚。", ["f2"]), ("这手亏了约12目。", ["f3"])),
    "标记没引用": out(("▲这块棋要小心。", ["f3"]), ("这手亏了约12目。", ["f3"])),
    "A 的数字没依据": out(("下A可以多拿5目。", ["f3"]), ("这手亏了约12目。", ["f3"])),
    "吃没有依据": out(("下A可以吃掉对方。", ["f2"]), ("这手亏了约12目。", ["f3"])),
    "死没有依据": out(("右下的棋死了。", ["f6"]), ("这手亏了约12目。", ["f3"])),
    "禁用词 劫": out(("这里可以打劫。", ["f4"]), ("这手亏了约12目。", ["f3"])),
    "禁用词 征子": out(("对方可以征子吃掉▲。", ["f4"]), ("这手亏了约12目。", ["f3"])),
    "禁用词 先手": out(("A是先手，要先下。", ["f2"]), ("这手亏了约12目。", ["f3"])),
    "禁用词 定式": out(("这是定式的下法。", ["f2"]), ("这手亏了约12目。", ["f3"])),
    "禁用词 眼": out(("▲这块棋没有眼了。", ["f4"]), ("这手亏了约12目。", ["f3"])),
    "禁用词 双活": out(("这里会变成双活。", ["f4"]), ("这手亏了约12目。", ["f3"])),
    "推测后面的棋": out(("对方也没发现，现在补上还来得及。", ["f4"]), ("这手亏了约12目。", ["f3"])),
    "猜测心态": out(("你这手✕下得有点急。", ["f1"]), ("这手亏了约12目。", ["f3"])),
    "refs 为空": out(("这手不太好。", []), ("这手亏了约12目。", ["f3"])),
    "refs 不存在": out(("这手不太好。", ["f9"]), ("这手亏了约12目。", ["f3"])),
    "句子太长": out(("你下了✕以后对方马上就可以把你的▲这一整块一共4颗子全部都吃掉了真可惜呀", ["f1", "f4"]),
                   ("这手亏了约12目。", ["f3"])),
    "句子太多": out(*[("这手亏了约12目。", ["f3"])] * 6),
    "只有一句": out(("这手亏了约12目。", ["f3"])),
    "tip 没有 refs": out(("这手亏了约12目。", ["f3"]), ("更好的是A。", ["f2"]), tip=("下次多想想。", [])),
    "tip 有坐标": out(("这手亏了约12目。", ["f3"]), ("更好的是A。", ["f2"]), tip=("下次先看R6。", ["f2"])),
    "缺 tip": {"sentences": GOOD["sentences"]},
    "不是对象": ["你下错了"],
}


class VerifyTest(unittest.TestCase):
    def test_faithful_output_passes(self):
        self.assertEqual(verify.verify(GOOD, FACTS, MARKS), [])

    def test_every_bad_output_is_rejected(self):
        passed = [name for name, o in BAD.items() if not verify.verify(o, FACTS, MARKS)]
        self.assertEqual(passed, [], f"these violations got through: {passed}")

    def test_natural_phrases_are_not_flagged(self):
        ok = out(
            ("多看一眼，就能发现这里很危险。", ["f4"]),
            ("第87手的时候，A是更好的选择。", ["f7", "f2"]),
            ("AI认为这手亏了不到12目。", ["f3"]),
        )
        self.assertEqual(verify.verify(ok, FACTS, MARKS), [])
        # Comparing with A while citing another fact is fine (the case DeepSeek hit).
        compare = out(("下✕亏了约12目，不如A。", ["f3"]), ("这手亏了约12目。", ["f3"]))
        self.assertEqual(verify.verify(compare, FACTS, MARKS), [])

    def test_template_text_would_pass_its_own_checks(self):
        # Every template sentence, cited with all facts, must satisfy the same rules.
        for text in narrate_template.mistake("mistake", FACTS, {"move": "rf", "source": "ai"}):
            problems = verify.check_sentence(text, [f["id"] for f in FACTS], {f["id"]: f for f in FACTS},
                                             {"✕", "A", "▲"}, text)
            self.assertEqual([p for p in problems if "太长" not in p], [], text)


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []
        self.cfg = type("C", (), {"model": "fake"})()

    def chat(self, msgs):
        self.sent.append(msgs)
        return self.replies.pop(0)


KP = {"kind": "mistake", "move": 87, "facts": FACTS, "marks": MARKS}


class ExplainTest(unittest.TestCase):
    def test_retry_after_violation(self):
        bad = json.dumps(BAD["坐标 GTP"], ensure_ascii=False)
        client = FakeClient([bad, json.dumps(GOOD, ensure_ascii=False)])
        result = narrate_llm.explain(client, KP, 10, "8级")
        self.assertTrue(result["verified"])
        self.assertEqual(result["attempts"], 2)
        self.assertIn("坐标", client.sent[1][-1]["content"])

    def test_gives_up_after_two_failures(self):
        bad = json.dumps(BAD["百分号"], ensure_ascii=False)
        result = narrate_llm.explain(FakeClient([bad, "not json"]), KP, 10, "8级")
        self.assertFalse(result["verified"])
        self.assertEqual(len(result["rejected"]), 2)

    def test_prompt_has_no_coordinates(self):
        msgs = narrate_llm.messages(KP, 10, "8级")
        text = msgs[1]["content"]
        for point in ("rd", "rf", "qd"):
            self.assertNotIn(f'"{point}"', text)
        self.assertIn("json", msgs[0]["content"])
        self.assertNotIn('"phase"', text)

    def test_hidden_fact_cannot_be_cited(self):
        cites_phase = out(("这是中盘的一手。", ["f7"]), ("这手亏了约12目。", ["f3"]))
        result = narrate_llm.explain(FakeClient([json.dumps(cites_phase, ensure_ascii=False)] * 2), KP, 10, "8级")
        self.assertFalse(result["verified"])


if __name__ == "__main__":
    unittest.main()
