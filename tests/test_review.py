import unittest

from pipeline import board, evaluate, facts, keypoints, narrate_template
from pipeline.coords import sgf_to_gtp, sgf_to_xy


def resp(moves, root_lead, stdev=20.0, human=None, ownership=None, current="B"):
    """A fake KataGo response; moves = [(sgf point, scoreLead (Black), visits, pv)]."""
    return {
        "rootInfo": {"scoreLead": root_lead, "humanScoreStdev": stdev, "currentPlayer": current},
        "moveInfos": [
            {"move": sgf_to_gtp(p, 19), "scoreLead": lead, "visits": visits, "pv": [sgf_to_gtp(q, 19) for q in pv]}
            for p, lead, visits, pv in moves
        ],
        "humanPolicy": human,
        "ownership": ownership,
    }


class BoardTest(unittest.TestCase):
    def test_capture_and_liberties(self):
        b = board.Board(19)
        for color, p in [("B", "ba"), ("W", "aa")]:
            b.play_sgf(color, p)
        captured = b.play_sgf("B", "ab")
        self.assertEqual(captured, {(0, 0)})
        self.assertIsNone(b.get((0, 0)))
        stones, libs = b.group(sgf_to_xy("ba", 19))
        self.assertEqual(len(stones), 1)
        self.assertEqual(len(libs), 3)

    def test_suicide_removes_group(self):
        b = board.Board(19)
        for p in ["ba", "ab"]:
            b.play_sgf("W", p)
        b.play_sgf("B", "aa")
        self.assertIsNone(b.get((0, 0)))

    def test_positions_count(self):
        class G:
            size, setup_black, setup_white = 19, ["dd"], []
            moves = [("W", "pp"), ("B", "")]

        self.assertEqual(len(board.positions(G)), 3)


class EvaluateTest(unittest.TestCase):
    def test_rank_chance(self):
        self.assertAlmostEqual(evaluate.rank_chance(0, 20), 0.5)
        self.assertGreater(evaluate.rank_chance(10, 20), 0.68)
        self.assertAlmostEqual(evaluate.rank_chance(12, None), evaluate.rank_chance(12, 12))

    def test_loss_from_search_and_from_next_position(self):
        before = resp([("pd", 5.0, 200, []), ("dd", -3.0, 50, [])], 5.0)
        e = evaluate.evaluate_move(0, "B", "dd", before, resp([], -2.0), 19)
        self.assertEqual(e.source, "search")
        self.assertAlmostEqual(e.score_loss, 8.0)
        e = evaluate.evaluate_move(0, "B", "qq", before, resp([], -2.0), 19)
        self.assertEqual(e.source, "next")
        self.assertAlmostEqual(e.score_loss, 7.0)

    def test_white_view(self):
        before = resp([("pd", -5.0, 200, [])], -5.0, current="W")
        e = evaluate.evaluate_move(1, "W", "qq", before, resp([], 1.0), 19)
        self.assertAlmostEqual(e.best_lead, 5.0)
        self.assertAlmostEqual(e.score_loss, 6.0)

    def test_decided_game_uses_points(self):
        before = resp([("pd", 60.0, 200, [])], 60.0, stdev=10)
        e = evaluate.evaluate_move(0, "B", "qq", before, resp([], 48.0), 19)
        self.assertTrue(e.decided)
        self.assertEqual(e.severity, "mistake")

    def test_policy_index(self):
        policy = [0.0] * 362
        policy[3 * 19 + 15] = 0.7  # "pd": x 15, y 3
        self.assertAlmostEqual(evaluate.policy_at(policy, "pd", 19), 0.7)
        self.assertEqual(evaluate.policy_top(policy, 19), "pd")


def _eval(index, color, point, best, loss, stdev=20.0, lead=0.0):
    sign = 1 if color == "B" else -1
    before = resp([(best, sign * lead, 300, []), (point, sign * (lead - loss), 100, [])], sign * lead, stdev)
    return evaluate.evaluate_move(index, color, point, before, resp([], sign * (lead - loss)), 19)


class KeypointsTest(unittest.TestCase):
    def _game(self, losses):
        """Alternating B/W moves; losses maps index -> (point, best, points lost)."""
        evals, responses = [], []
        for i in range(60):
            color = "B" if i % 2 == 0 else "W"
            point, best, loss = losses.get(i, (f"a{chr(97 + i % 19)}", f"a{chr(97 + i % 19)}", 0.0))
            evals.append(_eval(i, color, point, best, loss))
            responses.append(resp([(best, 0.0, 300, [])], 0.0))
        responses.append(resp([], 0.0))
        return evals, responses

    def test_slips_in_one_fight_merge(self):
        evals, responses = self._game({10: ("dd", "de", 4.0), 14: ("df", "dg", 4.0), 40: ("pp", "qq", 4.0)})
        cands = keypoints.candidates(evals, "B", responses, 19)
        segs = [s for s in keypoints.segments(cands, evals, responses, "B") if s.kind != "good"]
        spans = sorted(s.span for s in segs)
        self.assertEqual(spans, [(10, 14), (40, 40)])

    def test_missed_punish(self):
        evals, responses = self._game({11: ("pp", "qq", 12.0), 12: ("aa", "qq", 10.0)})
        cands = keypoints.candidates(evals, "B", responses, 19)
        self.assertIn("missed_punish", [c.kind for c in cands])

    def test_missed_urgent(self):
        evals, responses = self._game({i: ("aa", "jj", 4.0) for i in (20, 22, 24)})
        cands = keypoints.candidates(evals, "B", responses, 19)
        urgent = [c for c in cands if c.kind == "missed_urgent"]
        self.assertEqual(len(urgent), 1)
        self.assertEqual(urgent[0].turns, [20, 22, 24])
        self.assertEqual(urgent[0].extra["point"], "jj")

    def test_selection_caps(self):
        losses = {i: ("aa" if i % 4 else "ss", "jj" if i % 4 else "kk", 12.0) for i in range(0, 60, 14)}
        evals, responses = self._game(losses)
        cands = keypoints.candidates(evals, "B", responses, 19)
        sel = keypoints.select(keypoints.segments(cands, evals, responses, "B"), evals, "B")
        self.assertLessEqual(len([s for s in sel.keypoints if s.kind != "good"]), keypoints.MAX_MISTAKES)
        self.assertFalse(sel.small_game)


class FactsTest(unittest.TestCase):
    def test_refute_capture_and_save(self):
        # Two black stones in atari at the edge; Black plays elsewhere and White captures them.
        b = board.Board(19)
        for color, p in [("B", "ab"), ("B", "ac"), ("W", "aa"), ("W", "bb"), ("W", "bc"), ("W", "cs")]:
            b.play_sgf(color, p)
        before_board = b.copy()
        after_board = b.copy()
        after_board.play_sgf("B", "pp")
        before = resp([("ad", 2.0, 400, ["ad"]), ("pp", -3.0, 100, [])], 2.0)
        after = resp([("ad", -3.0, 400, ["ad"])], -3.0, current="W")
        k = facts.mistake_facts(
            kind="mistake", student="B", size=19, number=80, played="pp", move_loss=5.0, severity="mistake",
            segment_moves=1, segment_loss=5.0, before_board=before_board, after_board=after_board,
            before=before, after=after, peer_policy=None,
        )
        types = [f["type"] for f in k.facts]
        self.assertIn("refute_capture", types)
        self.assertIn("atari_ignored", types)
        self.assertIn("best_save", types)
        self.assertEqual(k.recommended, {"move": "ad", "source": "ai"})
        self.assertEqual(k.category, "life_death")
        labels = {m["label"] for m in k.marks}
        self.assertTrue({"✕", "A", "▲"} <= labels)
        text = " ".join(narrate_template.explain("mistake", k.category, k.facts, k.recommended)["template"])
        self.assertIn("▲", text)
        self.assertNotRegex(text, r"[A-T]\d")

    def test_peer_choice_close_to_ai(self):
        b = board.Board(19)
        human = [0.0] * 362
        human[15 * 19 + 15] = 0.6  # "pp"
        before = resp([("dd", 3.0, 400, ["dd"]), ("pp", 2.5, 300, ["pp"])], 3.0)
        after = resp([("qq", -1.0, 400, [])], -1.0, current="W")
        after_board = b.copy()
        after_board.play_sgf("B", "jj")
        k = facts.mistake_facts(
            kind="mistake", student="B", size=19, number=30, played="jj", move_loss=4.0, severity="mistake",
            segment_moves=1, segment_loss=4.0, before_board=b, after_board=after_board,
            before=before, after=after, peer_policy=human,
        )
        self.assertEqual(k.recommended, {"move": "pp", "source": "peer"})
        self.assertEqual({m["label"]: m["point"] for m in k.marks if m["type"] == "point"}, {"✕": "jj", "A": "pp", "B": "dd"})


class SummaryTest(unittest.TestCase):
    def test_summary(self):
        kps = [{"kind": "mistake", "category": "life_death"}, {"kind": "mistake", "category": "life_death"},
               {"kind": "missed_punish", "category": "territory"}, {"kind": "good", "category": "territory"}]
        text = narrate_template.summary(kps, False)
        self.assertIn("2 处死活", text)
        self.assertIn("1 处没惩罚对方", text)
        self.assertIn("好棋", text)


if __name__ == "__main__":
    unittest.main()
