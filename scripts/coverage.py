"""Cross-checks the chosen key points against the whole game, without needing to read Go.

For each game: how much of the student's total loss the key points cover, and whether the
student's biggest single losses fall inside a chosen segment (or which segment won instead).

Usage: python scripts/coverage.py [raw/<id>.json.gz ...]   (default: every game in raw/)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import analyze, build, sgf  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
root = Path(__file__).resolve().parent.parent
paths = [Path(p) for p in sys.argv[1:]] or sorted((root / "raw").glob("*.json.gz"))
for path in paths:
    raw = analyze.load_raw(path)
    game = sgf.parse(raw["sgf"])
    color = raw["studentColor"]
    plan = build.plan(game, raw)
    mine = [e for e in plan.evals if e.color == color]
    chosen = [s for s in plan.selection.keypoints if s.kind != "good"]
    covered = {t for s in chosen for t in range(s.span[0], s.span[1] + 1)}
    total_w = sum(e.weight for e in mine)
    cov_w = sum(e.weight for e in mine if e.index in covered)
    print(f"== {raw['gameId']}  student {color}  {game.result}  {len(chosen)} mistake key points")
    print(f"   rank-aware loss covered: {cov_w / total_w:.0%} of {total_w:.2f}  "
          f"(moves covered {len([e for e in mine if e.index in covered])}/{len(mine)})")
    for e in sorted(mine, key=lambda e: -e.weight)[:8]:
        seg = next((s for s in plan.segments if e.index in s.turns and s.kind != "good"), None)
        state = "IN key point" if e.index in covered else (
            f"not chosen (segment #{seg.index + 1} {seg.kind} prio {seg.priority * 100:.1f}%)" if seg else "no segment")
        print(f"   #{e.number:>3} loss {e.score_loss:4.1f}目 {e.weight * 100:5.1f}%  {state}")
