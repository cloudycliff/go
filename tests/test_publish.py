import os
import subprocess
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from pipeline import fox, publish, ranks


def game(chessid, day, hour=12, moves=200, size=19, black="1", white="2"):
    return fox.FoxGame(
        chessid=chessid, start=datetime(2026, 11, day, hour), black="b", white="w",
        black_uid=black, white_uid=white,
        black_rank=ranks.Rank("K", 8), white_rank=ranks.Rank("K", 8),
        winner=1, point=-1, moves=moves, size=size, handicap=0,
    )


class NewGamesTest(unittest.TestCase):
    GAMES = [game("g5", 15), game("g4", 14, moves=30), game("g3", 13), game("g2", 12, size=13), game("g1", 11)]

    def test_only_games_after_the_newest_analysed(self):
        fresh = publish.new_games(self.GAMES, "1", {"g1", "g3"})
        self.assertEqual([g.chessid for g in fresh], ["g5"])  # g4 too short, g2 not 19x19

    def test_nothing_new(self):
        self.assertEqual(publish.new_games(self.GAMES, "1", {"g5"}), [])

    def test_first_run_takes_only_the_newest(self):
        self.assertEqual([g.chessid for g in publish.new_games(self.GAMES, "1", set())], ["g5"])

    def test_oldest_first_and_limited(self):
        games = [game(f"n{d}", d) for d in range(20, 10, -1)]
        fresh = publish.new_games(games, "1", {"n11"}, limit=3)
        self.assertEqual([g.chessid for g in fresh], ["n12", "n13", "n14"])

    def test_other_players_games_ignored(self):
        self.assertEqual(publish.new_games([game("x", 20, black="9", white="8")], "1", {"g5"}), [])

    def test_student_as_white(self):
        fresh = publish.new_games(self.GAMES + [game("w1", 20, black="9", white="1")], "1", {"g5"})
        self.assertEqual([g.chessid for g in fresh], ["w1"])


class LockTest(unittest.TestCase):
    def test_exclusive_and_stale(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "update.lock"
            with publish.Lock(path):
                with self.assertRaises(publish.PublishError):
                    with publish.Lock(path):
                        pass
            self.assertFalse(path.exists())
            path.write_text("old")
            old = time.time() - publish.LOCK_STALE - 10
            os.utime(path, (old, old))
            with publish.Lock(path):
                pass


class PublishTest(unittest.TestCase):
    def test_commits_only_site_and_raw(self):
        with tempfile.TemporaryDirectory() as d:
            repo, remote = Path(d) / "repo", Path(d) / "remote.git"

            def run(*args, cwd=None):
                return subprocess.run(args, cwd=cwd, check=True, capture_output=True)

            run("git", "init", "--bare", "-b", "main", str(remote))
            run("git", "init", "-b", "main", str(repo))
            run("git", "config", "user.email", "t@example.com", cwd=repo)
            run("git", "config", "user.name", "t", cwd=repo)
            run("git", "config", "commit.gpgsign", "false", cwd=repo)
            run("git", "remote", "add", "origin", str(remote), cwd=repo)
            (repo / "site").mkdir()
            (repo / "site" / "a.json").write_text("1")
            (repo / "notes.txt").write_text("keep me out")
            run("git", "add", "notes.txt", cwd=repo)  # staged, but not part of a publish
            self.assertTrue(publish.publish("review: test", repo=repo, log=lambda *_: None))
            files = run("git", "show", "--name-only", "--format=", "HEAD", cwd=repo).stdout.decode().split()
            self.assertEqual(files, ["site/a.json"])
            self.assertFalse(publish.publish("again", repo=repo, log=lambda *_: None))
            pushed = run("git", "--git-dir", str(remote), "log", "--oneline", "main").stdout.decode()
            self.assertIn("review: test", pushed)


if __name__ == "__main__":
    unittest.main()
