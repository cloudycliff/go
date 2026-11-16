"""Shape names, the liberty facts around ✕ and A, and close alternatives to A."""

import unittest

from pipeline import facts, narrate_template
from pipeline.board import setup
from pipeline.shapes import describe


def board(black=(), white=()):
    return setup(19, black, white)


class ShapeNamesTest(unittest.TestCase):
    def check(self, name, point, black=(), white=(), color="B"):
        self.assertEqual(describe(board(black, white), point, color), name)

    def test_tactical(self):
        self.check("打吃", "jk", black=["ij", "kj"], white=["jj"])
        self.check("提子", "ji", black=["ij", "kj", "jk"], white=["jj"])
        self.check("粘", "jj", black=["ji", "jk"])
        self.check("挖", "jj", white=["ij", "kj"])
        self.check("断", "jj", black=["ki"], white=["ji", "kj"])

    def test_contact(self):
        self.check("扳", "jj", black=["ik"], white=["jk"])
        self.check("靠", "jk", white=["jj"])
        self.check("长", "jj", black=["jk"], white=["kk"])
        self.check(None, "ik", black=["jk"], white=["kk"])  # straight back from the contact

    def test_distant(self):
        self.check("尖", "kk", black=["jj"])
        self.check("跳", "jl", black=["jj"])
        self.check("小飞", "kl", black=["jj"])
        self.check("大跳", "jm", black=["jj"])
        self.check(None, "jm", black=["jj"], white=["jk"])  # a stone in between: no jump
        self.check("打入", "jj", white=["jg", "gj", "mj"])
        self.check(None, "jj")

    def test_corner_and_side(self):
        self.check("占角", "dd")
        self.check("点三三", "cc", white=["dd"])
        self.check("挂角", "fc", white=["dd"])
        self.check("守角", "ff", black=["dd"])
        self.check("拆二", "cm", black=["cj"])
        self.check(None, "cm", black=["cj"], white=["ck"])  # the opponent stands in between

    def test_occupied_or_pass(self):
        self.check(None, "jj", black=["jj"])
        self.check(None, "")


class LibertyFactsTest(unittest.TestCase):
    def test_played_short(self):
        before = board(black=["jj"], white=["ij", "ki", "lj", "kk"])
        after = before.copy()
        after.play_sgf("B", "kj")
        k = facts.KeyFacts()
        facts.played_short(k, before, after, "kj", "B")
        f = next(f for f in k.facts if f["type"] == "played_short")
        self.assertEqual(f["liberties"], 2)
        self.assertIn("2 口气", narrate_template.mistake("mistake", k.facts, {"source": "ai"})[-2])

    def test_no_played_short_when_liberties_do_not_drop(self):
        before = board(black=["jj"])
        after = before.copy()
        after.play_sgf("B", "kj")
        k = facts.KeyFacts()
        facts.played_short(k, before, after, "kj", "B")
        self.assertFalse(k.has("played_short"))

    def test_near_group_says_liberties_after_a(self):
        k = facts.KeyFacts()
        facts.near_group(k, board(black=["jj", "jk"], white=["ij", "ik", "kj", "ji"]), "kk", "B")
        f = next(f for f in k.facts if f["type"] == "rec_near_group")
        self.assertEqual((f["liberties"], f["libertiesAfter"]), (2, 3))
        self.assertIn("长到 3 口气", narrate_template.near_group_text(f))


class CloseAlternativesTest(unittest.TestCase):
    def key(self, rows):
        k = facts.KeyFacts()
        k.candidates = [{"label": lb, "diff": d} for lb, d in rows]
        return k

    def test_close_rows_count(self):
        k = self.key([("A", 0.0), ("B", 0.3), ("✕", 6.0), ("C", 0.4), ("D", 1.2)])
        facts.close_alternatives(k, "ai")
        f = next(f for f in k.facts if f["type"] == "close_alternatives")
        self.assertEqual(f["marks"], ["B", "C"])
        self.assertIn("都差不多一样好", narrate_template.close_alternatives_text(f))

    def test_peer_source_leaves_b_out(self):
        k = self.key([("A", 0.4), ("B", 0.0), ("✕", 6.0), ("C", 1.5)])
        facts.close_alternatives(k, "peer")
        self.assertFalse(k.has("close_alternatives"))

    def test_one_alternative_text(self):
        text = narrate_template.close_alternatives_text({"mark": "A", "marks": ["C"]})
        self.assertEqual(text, "C 和 A 差不多一样好，下 A 或 C 都可以。")


class ShapeTextTest(unittest.TestCase):
    def test_names_both_moves(self):
        fs = [{"type": "shape", "mark": "✕", "shape": "扳"}, {"type": "shape", "mark": "A", "shape": "跳"}]
        self.assertEqual(narrate_template.shape_text(fs, "✕", "A", ""), "你下的 ✕ 是扳，A 是跳。")

    def test_same_name_is_said_once(self):
        fs = [{"type": "shape", "mark": "✕", "shape": "粘"}, {"type": "shape", "mark": "A", "shape": "粘"}]
        self.assertEqual(narrate_template.shape_text(fs, "✕", "A", ""), "✕ 和 A 都是粘，但地方不一样。")

    def test_skips_a_name_another_sentence_gives(self):
        fs = [{"type": "shape", "mark": "A", "shape": "粘"},
              {"type": "rec_connects", "mark": "▲", "mark2": "■", "moveMark": "A"}]
        self.assertIsNone(narrate_template.shape_text(fs, "✕", "A", ""))

    def test_good_move_names_common_move(self):
        fs = [{"type": "shape", "mark": "B", "shape": "靠"}]
        self.assertEqual(narrate_template.shape_text(fs, "A", "B", "大家常下的 "), "大家常下的 B 是靠。")


if __name__ == "__main__":
    unittest.main()
