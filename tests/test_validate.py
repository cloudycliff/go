import unittest

from pipeline import sgf, validate
from pipeline.coords import sgf_to_gtp


def resp(turn, moves, root):
    return {
        "turnNumber": turn,
        "rootInfo": {"scoreLead": root, "humanScoreStdev": 20.0},
        "moveInfos": [{"move": sgf_to_gtp(p, 19), "scoreLead": lead, "visits": v, "pv": []} for p, lead, v in moves],
    }


GAME = sgf.parse("(;SZ[19]KM[375]RU[Chinese]BR[8级]WR[8级];B[pd];W[dp];B[pp];W[dd])")


def keypoint(kind="mistake", loss=8, rec="qq", played="pp"):
    return {
        "kind": kind, "move": 3, "position": {"moveIndex": 2}, "played": played,
        "recommended": {"move": rec, "source": "ai"},
        "facts": [{"id": "f1", "type": "loss", "scoreLoss": loss}],
    }


def raw_with(before, after, human=None):
    return {
        "studentColor": "B",
        "deep": {"responses": {"2": before}},
        "checks": {"responses": {"2": before, "3": after}, "human": human or {}},
    }


class ValidateTest(unittest.TestCase):
    def test_stable_point_passes(self):
        before = resp(2, [("qq", 5.0, 5000), ("pp", -3.0, 200)], 5.0)
        after = resp(3, [], -3.0)
        (v,) = validate.judge(GAME, raw_with(before, after), {"keyPoints": [keypoint()]})
        self.assertTrue(v.ok, v.issues)
        self.assertAlmostEqual(v.check_loss, 8.0)

    def test_loss_shrinks_on_deeper_search(self):
        before = resp(2, [("qq", 5.0, 5000), ("pp", 3.5, 2000)], 5.0)
        after = resp(3, [], 3.5)
        (v,) = validate.judge(GAME, raw_with(before, after), {"keyPoints": [keypoint(loss=8)]})
        self.assertFalse(v.ok)
        self.assertIn("损失变小", v.issues[0])

    def test_recommended_move_no_longer_good(self):
        before = resp(2, [("rr", 6.0, 5000), ("qq", 2.0, 300), ("pp", -3.0, 200)], 6.0)
        after = resp(3, [], -3.0)
        (v,) = validate.judge(GAME, raw_with(before, after), {"keyPoints": [keypoint()]})
        self.assertTrue(any("推荐的 A 点" in t for t in v.issues))

    def test_hard_for_strong_players(self):
        before = resp(2, [("qq", 5.0, 5000), ("pp", -3.0, 200)], 5.0)
        after = resp(3, [], -3.0)
        policy = [0.0] * 362
        for i in range(20):
            policy[i] = 0.04  # twenty points ahead of the recommended one (which is 0)
        human = {"rank_5d": {"2": policy}}
        (v,) = validate.judge(GAME, raw_with(before, after, human), {"keyPoints": [keypoint()]})
        self.assertTrue(v.ok)
        self.assertTrue(any("偏难" in t for t in v.notes))


if __name__ == "__main__":
    unittest.main()
