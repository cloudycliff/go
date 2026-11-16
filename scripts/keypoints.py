"""Prints the key points chosen from saved analyses (overview pass only), to tune thresholds.

Usage: python scripts/keypoints.py raw/<id>.json.gz [...]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import analyze, evaluate, keypoints, sgf  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
for name in sys.argv[1:]:
    raw = analyze.load_raw(Path(name))
    game = sgf.parse(raw["sgf"])
    color = raw["studentColor"]
    responses = raw["overview"]["responses"]
    evals = evaluate.evaluate(game, responses)
    cands = keypoints.candidates(evals, color, responses, game.size)
    segs = keypoints.segments(cands, evals, responses, color)
    sel = keypoints.select(segs, evals, color)
    small = "  (small game)" if sel.small_game else ""
    print(f"== {raw['gameId']} student {color} {game.result}  candidates {len(cands)} segments {len(segs)}{small}")
    for s in sorted(segs, key=lambda s: -s.weight)[:14]:
        mark = "*" if s in sel.keypoints else " "
        print(
            f" {mark} {s.kind:14} #{s.index + 1:>3} span {s.span[0] + 1}-{s.span[1] + 1} "
            f"turns {len(s.turns):>2} loss {s.score_loss:5.1f} w {s.weight * 100:5.1f}% {s.severity}"
        )
