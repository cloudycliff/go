"""Why A is better: the candidate table, the one-exchange follow-up, and template sentences that leave the table's numbers to it."""

import unittest

from pipeline import facts, narrate_template
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


class TableDuplicationTest(unittest.TestCase):
    FACTS = [{"type": "loss", "scoreLoss": 7, "severity": "mistake"},
             {"type": "peer_choice", "sameAsAi": False, "diff": 1.4}]
    REC = {"move": "qf", "source": "peer"}

    def test_without_table_numbers_are_in_the_text(self):
        text = "".join(narrate_template.mistake("mistake", self.FACTS, self.REC, table=False))
        self.assertIn("亏了约 7 目", text)
        self.assertIn("只差约 1 目", text)

    def test_with_table_numbers_are_left_to_it(self):
        lines = narrate_template.mistake("mistake", self.FACTS, self.REC, table=True)
        text = "".join(lines)
        self.assertNotIn("目", text)
        self.assertNotIn("你下了 ✕。", lines)
        self.assertIn("问题手", text)

    def test_table_shown_matches_the_page(self):
        self.assertFalse(narrate_template.table_shown([{"label": "A", "diff": 0.0}, {"label": "✕", "diff": None}]))
        self.assertTrue(narrate_template.table_shown([{"label": "A", "diff": 0.0}, {"label": "✕", "diff": 5.0}]))
