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


class HabitsTest(unittest.TestCase):
    def games(self):
        out = []
        for n in range(4):
            gid = f"g{n}"
            mine = [move(gid, 10, "mistake", loss=5 + n, tags={"slip"}),
                    move(gid, 12, "mistake", loss=1, tags={"missed_urgent"}), move(gid, 14)]
            theirs = [move(gid, 11, "mistake", tags={"missed_urgent"}), move(gid, 13, "mistake")]
            out.append(stats.GameStats(gid, f"2026-11-0{n + 1}", "B", 100, "B+R", mine, theirs, n < 2))
        return out

    def test_habit_needs_more_than_the_opponents(self):
        data = stats.habits(self.games(), {})
        keys = [x["key"] for x in data["habits"]]
        self.assertEqual(keys, ["slip"])  # missed_urgent: the opponents do it just as often

    def test_examples_only_from_published_pages_one_per_game(self):
        pages = {
            "g0": {"keyPoints": [{"id": "k1", "kind": "mistake", "moves": [10]},
                                  {"id": "k2", "kind": "mistake", "moves": [10, 12]}]},
            "g1": {"keyPoints": [{"id": "k1", "kind": "good", "moves": [10]},
                                  {"id": "k3", "kind": "mistake", "moves": [10]}]},
        }
        slip = stats.habits(self.games(), pages)["habits"][0]
        self.assertEqual([(e["game"], e["keyPoint"]) for e in slip["examples"]], [("g1", "k3"), ("g0", "k1")])
        self.assertEqual(slip["games"], 4)  # unpublished games still count


class PracticeTest(unittest.TestCase):
    def test_questions_newest_first_with_habits(self):
        games = HabitsTest().games()
        pages = {
            "g0": {"keyPoints": [{"id": "k1", "kind": "mistake", "move": 10, "title": "t", "moves": [10]}]},
            "g3": {"keyPoints": [{"id": "k2", "kind": "good", "move": 14, "title": "好", "moves": [14]}]},
        }
        qs = stats.practice(games, pages)["questions"]
        self.assertEqual([(q["game"], q["keyPoint"]) for q in qs], [("g3", "k2"), ("g0", "k1")])
        self.assertEqual(qs[1]["habits"], ["slip"])
        self.assertEqual(qs[0]["habits"], [])
