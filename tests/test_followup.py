"""Why A is better: the candidate table (shown on the page, not in the template), the one-exchange follow-up, and no repeated sentences."""

import unittest

from pipeline import facts, narrate_template, verify
from tests.test_review import resp


def key():
    return facts.KeyFacts()


class CandidatesTest(unittest.TestCase):
    def test_table_lists_a_b_played_and_close_alternatives(self):
        before = resp(
            [("pd", 5.0, 400, []), ("qf", 4.6, 200, []), ("dp", 3.5, 80, []), ("cc", -9.0, 30, []), ("jj", 4.0, 3, [])],
            5.0,
        )
        k = key()
        rows = facts.close_candidates(before, k, played="cc", rec="qf", best="pd", size=19)
        by_label = {r["label"]: r for r in rows}
        self.assertEqual(by_label["A"]["point"], "qf")
        self.assertEqual(by_label["B"]["point"], "pd")
        self.assertEqual(by_label["✕"]["diff"], 14.0)
        self.assertEqual(by_label["C"]["point"], "dp")  # within 2 points, enough visits
        self.assertNotIn("jj", [r["point"] for r in rows])  # too few visits to trust
        self.assertIn("C", {m["label"] for m in k.marks})
        self.assertEqual([r["label"] for r in rows if r["first"]], ["B"])

    def test_white_diff_is_measured_from_whites_side(self):
        # Scores are Black's: for White the first choice has the lowest score.
        before = resp([("pd", -5.0, 400, []), ("qf", -3.8, 200, []), ("dp", -6.0, 150, [])], -5.0, current="W")
        rows = facts.close_candidates(before, key(), played="cc", rec="qf", best="pd", size=19,
                                      student="W", played_loss=9.4)
        by_label = {r["label"]: r for r in rows}
        self.assertEqual(by_label["A"]["diff"], 1.2)
        self.assertEqual(by_label["✕"]["diff"], 9.4)  # the evaluated loss, not a thin search
        self.assertEqual(by_label["C"]["diff"], 0.0)  # better for White than the first choice: clamp


class FollowUpTest(unittest.TestCase):
    def test_compares_both_moves_after_the_best_reply(self):
        k = key()
        after_played = resp([("qd", -4.0, 300, [])], -4.0, current="W")
        after_a = resp([("qe", 3.0, 300, [])], 3.0, current="W")  # reply right next to A
        facts.follow_up(k, played="cc", rec="qf", after=after_played, probe_a=after_a, student="B", size=19)
        f = next(f for f in k.facts if f["type"] == "follow_up")
        self.assertEqual((f["leadAfterA"], f["leadAfterPlayed"], f["diff"]), (3.0, -4.0, 7.0))
        self.assertTrue(f["replyNearA"])
        text = narrate_template.follow_up_text(f)
        self.assertIn("领先约 3 目", text)
        self.assertIn("落后约 4 目", text)

    def test_white_student_sign(self):
        k = key()
        facts.follow_up(
            k, played="cc", rec="qf", after=resp([("qd", 4.0, 300, [])], 4.0),
            probe_a=resp([("aa", -3.0, 300, [])], -3.0), student="W", size=19,
        )
        f = k.facts[-1]
        self.assertEqual((f["leadAfterA"], f["leadAfterPlayed"]), (3.0, -4.0))
        self.assertFalse(f["replyNearA"])

    def test_missing_probe_adds_nothing(self):
        k = key()
        facts.follow_up(k, played="cc", rec="qf", after=resp([("qd", 1.0, 1, [])], 1.0), probe_a=None,
                        student="B", size=19)
        self.assertEqual(k.facts, [])


class DuplicateTest(unittest.TestCase):
    MARKS = [{"label": "A", "type": "point", "point": "qf", "role": "recommended"}]
    FACTS = [{"id": "f1", "type": "loss", "scoreLoss": 7}, {"id": "f2", "type": "recommended", "mark": "A"}]

    def check(self, *texts):
        o = {"sentences": [{"text": t, "refs": ["f1", "f2"]} for t in texts],
             "tip": {"text": "下之前先看看A。", "refs": ["f2"]}}
        return verify.verify(o, self.FACTS, self.MARKS)

    def test_repeated_sentence_is_rejected(self):
        problems = self.check("这手亏了约7目。", "更好的是A。", "这一手亏了约7目。")
        self.assertTrue(any("重复" in p for p in problems), problems)

    def test_different_sentences_pass(self):
        self.assertEqual(self.check("这手亏了约7目。", "更好的是A。"), [])
