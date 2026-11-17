"""Statistics across games: rates skip decided positions, features are counted per game."""

import unittest

from pipeline import stats


def move(game, number, severity=None, decided=False, loss=0.0, tags=(), shape=None):
    return stats.Move(game, "2026-11-01", number, "middle", severity, decided, loss, False,
                      shape=shape, tags=set(tags))


def game(gid, student, opponent=()):
    return stats.GameStats(gid, "2026-11-01", "B", 100, "B+R", list(student), list(opponent), True)


class StatsTest(unittest.TestCase):
    def test_decided_moves_are_left_out_of_rates(self):
        moves = [move("g", 1, "mistake"), move("g", 2), move("g", 3, "blunder", decided=True)]
        live = stats._live(moves)
        self.assertEqual(len(live), 2)
        self.assertEqual(stats._rate(live), 50.0)

    def test_inaccuracies_are_not_bad(self):
        self.assertFalse(move("g", 1, "inaccuracy").bad)
        self.assertTrue(move("g", 1, "mistake").bad)

    def test_tag_rows_count_games_and_opponents(self):
        games = [
            game("g1", [move("g1", 1, "mistake", loss=5, tags={"slip"}), move("g1", 2, "mistake")],
                 [move("g1", 3, "mistake", tags={"slip"})]),
            game("g2", [move("g2", 1, "blunder", loss=20, tags={"slip", "followed"})]),
        ]
        rows = {r["tag"]: r for r in stats.tag_rows(games)}
        self.assertEqual(len(rows["slip"]["moves"]), 2)
        self.assertEqual(rows["slip"]["games"], 2)
        self.assertAlmostEqual(rows["slip"]["share"], 2 / 3)
        self.assertEqual(rows["slip"]["loss"], 25)
        self.assertEqual(rows["slip"]["opponentShare"], 1.0)
        self.assertEqual(rows["followed"]["games"], 1)

    def test_report_renders(self):
        text = stats.report([game("g1", [move("g1", 1, "mistake", tags={"slip"}, shape="跳")], [move("g1", 2)])])
        self.assertIn("# 多盘统计", text)
        self.assertIn("一时疏忽", text)


if __name__ == "__main__":
    unittest.main()
