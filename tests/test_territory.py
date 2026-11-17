"""The territory view: ownership packed into letters, and the variations it is computed for."""

import unittest

from pipeline import analyze, build


class TerritoryTest(unittest.TestCase):
    def test_letters(self):
        self.assertEqual(build.territory_text([-1.0, -0.56, 0.0, 0.04, 0.56, 1.0, 1.7]), "aejjoss")
        self.assertIsNone(build.territory_text(None))

    def test_line_key(self):
        self.assertEqual(analyze.line_key(12, "B", ["pd", "", "dp"]), "12:B:pd pass dp")

    def test_variations_get_territory_from_the_students_side(self):
        data = {
            "game": {"moves": [["B", "pd"], ["W", "dp"], ["B", "pp"]]},
            "keyPoints": [{"position": {"moveIndex": 1}, "lines": [{"moves": ["dp", "qf"]}, {"moves": ["dd"]}]}],
        }
        self.assertEqual(build.wanted_lines(data), [(1, "W", ["dp", "qf"]), (1, "W", ["dd"])])
        raw = {
            "studentColor": "W",
            "overview": {"responses": [{"ownership": [1.0] * 4}, {}]},
            "lines": {"1:W:dp qf": {"scoreLead": [2.0, -1.5], "ownership": [[-1.0] * 4, [0.0] * 4]}},
        }
        build.add_territory(data, raw)
        self.assertEqual(data["territory"], ["ssss", None])
        first, missing = data["keyPoints"][0]["territory"]
        self.assertEqual(first["lead"], [-2.0, 1.5])  # Black's lead turned into White's
        self.assertEqual(first["own"], ["aaaa", "jjjj"])
        self.assertIsNone(missing)


if __name__ == "__main__":
    unittest.main()
