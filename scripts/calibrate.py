"""Prints the student's biggest losses in saved analyses, to tune thresholds.

Usage: python scripts/calibrate.py raw/<id>.json.gz [...]
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import analyze, evaluate, sgf  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
for name in sys.argv[1:]:
    raw = analyze.load_raw(Path(name))
    game = sgf.parse(raw["sgf"])
    color = raw["studentColor"]
    evals = evaluate.evaluate(game, raw["overview"]["responses"])
    mine = [e for e in evals if e.color == color]
    print(f"== {raw['gameId']}  student {color}  {len(game.moves)} moves  {game.result}")
    counts = Counter((evaluate.phase(e.number), e.severity) for e in mine)
    for ph in ("opening", "middle", "endgame"):
        print(f"  {ph:8}", {s: counts[(ph, s)] for s in ("inaccuracy", "mistake", "blunder")})
    print("  top losses (move, points, rank-aware, stdev, chance, source, peer prob):")
    for e in sorted(mine, key=lambda e: -e.weight)[:18]:
        print(
            f"   #{e.number:>3} {e.point or 'pass':4} best {e.best:3} loss {e.score_loss:5.1f}目 "
            f"{e.rank_loss * 100:5.1f}% σ={e.stdev:4.1f} p={e.chance_before:.2f} {e.source:6} "
            f"prior {e.played_prior:.2f}/{e.best_prior:.2f} {evaluate.SEVERITY_ZH.get(e.severity, '')}"
        )
