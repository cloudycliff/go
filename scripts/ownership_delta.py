"""Shows how ownership changes around one move, to tune the group/area thresholds in facts.py.

Usage: python scripts/ownership_delta.py <id> <move number>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import analyze, board, sgf  # noqa: E402
from pipeline.coords import xy_to_sgf  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
root = Path(__file__).resolve().parent.parent
raw = analyze.load_raw(root / "raw" / f"{sys.argv[1]}.json.gz")
game = sgf.parse(raw["sgf"])
i = int(sys.argv[2]) - 1
color = raw["studentColor"]
sign = 1 if color == "B" else -1
deep = analyze.deep_responses(raw)
before = deep.get(i, raw["overview"]["responses"][i])
after = deep.get(i + 1, raw["overview"]["responses"][i + 1])
boards = board.positions(game)
b = boards[i + 1]
ob, oa = before["ownership"], after["ownership"]
print("move", game.moves[i], "deep", i in deep)
for c, stones, libs in b.groups():
    if len(stones) < 2:
        continue
    mb = sum(sign * ob[y * 19 + x] for x, y in stones) / len(stones)
    ma = sum(sign * oa[y * 19 + x] for x, y in stones) / len(stones)
    if abs(mb - ma) >= 0.25:
        print(f"  group {c} {len(stones):>2} stones libs {len(libs)} at {xy_to_sgf(min(stones))}: "
              f"student-side {mb:+.2f} -> {ma:+.2f}")
deltas = sorted(
    ((sign * (ob[y * 19 + x] - oa[y * 19 + x]), xy_to_sgf((x, y))) for x in range(19) for y in range(19)
     if (x, y) not in b.stones),
    reverse=True,
)
print("  empty points lost >= 0.5:", sum(d >= 0.5 for d, _ in deltas), " >= 1.0:", sum(d >= 1.0 for d, _ in deltas))
print("  top:", [(p, round(d, 2)) for d, p in deltas[:12]])
