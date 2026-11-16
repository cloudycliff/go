import unittest

from pipeline import coords, ranks, sgf


class SgfTest(unittest.TestCase):
    def test_fox_even_game(self):
        g = sgf.parse(
            "(;GM[1]FF[4]SZ[19]PB[a]PW[b]BR[8级]WR[7级]KM[375]HA[0]RU[Chinese]RE[B+R]"
            ";B[pd];W[dp];B[tt];W[dd])"
        )
        self.assertEqual(g.komi, 7.5)
        self.assertEqual(g.rules, "chinese")
        self.assertEqual(g.handicap, 0)
        self.assertEqual(g.moves, [("B", "pd"), ("W", "dp"), ("B", ""), ("W", "dd")])
        self.assertEqual(g.black_rank, ranks.Rank("K", 8))
        self.assertEqual(g.white_rank, ranks.Rank("K", 7))

    def test_fox_handicap_as_leading_black_moves(self):
        g = sgf.parse("(;SZ[19]KM[0]HA[2]RU[Chinese];B[pd];B[dp];W[dd];B[pp])")
        self.assertEqual(g.setup_black, ["pd", "dp"])
        self.assertEqual(g.handicap, 2)
        self.assertEqual(g.moves, [("W", "dd"), ("B", "pp")])
        self.assertEqual(g.komi, 0.0)

    def test_fox_take_first_keeps_zero_komi(self):
        g = sgf.parse("(;SZ[19]KM[0]HA[1]RU[Chinese];B[qd];W[dd])")
        self.assertEqual(g.handicap, 0)
        self.assertEqual(g.komi, 0.0)
        self.assertEqual(len(g.moves), 2)

    def test_main_line_skips_later_variations(self):
        g = sgf.parse("(;SZ[19];B[pd](;W[dp];B[pp])(;W[dd];B[cc]))")
        self.assertEqual(g.moves, [("B", "pd"), ("W", "dp"), ("B", "pp")])

    def test_escaped_bracket_in_comment(self):
        g = sgf.parse("(;SZ[19]C[a \\] b];B[pd]C[x(y);z];W[dp])")
        self.assertEqual(g.moves, [("B", "pd"), ("W", "dp")])


class CoordsTest(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(coords.sgf_to_gtp("pd", 19), "Q16")
        self.assertEqual(coords.gtp_to_sgf("Q16", 19), "pd")
        self.assertEqual(coords.sgf_to_gtp("aa", 19), "A19")
        self.assertEqual(coords.sgf_to_gtp("ss", 19), "T1")
        self.assertEqual(coords.sgf_to_gtp("", 19), "pass")


class RanksTest(unittest.TestCase):
    def test_fox_numeric(self):
        self.assertEqual(ranks.from_fox_dan(10), ranks.Rank("K", 8))
        self.assertEqual(ranks.from_fox_dan(17), ranks.Rank("K", 1))
        self.assertEqual(ranks.from_fox_dan(18), ranks.Rank("D", 1))
        self.assertEqual(ranks.from_fox_dan(100), ranks.Rank("P", 1))

    def test_profiles(self):
        self.assertEqual(ranks.profile_for(ranks.Rank("K", 8)), "preaz_11k")
        self.assertEqual(ranks.profile_for(ranks.Rank("K", 8), 2), "preaz_9k")
        self.assertEqual(ranks.profile_for(ranks.Rank("K", 25)), "preaz_20k")
        self.assertEqual(ranks.profile_for(ranks.Rank("D", 3)), "rank_3k")


if __name__ == "__main__":
    unittest.main()
