"""Prints the key points of a built review in plain text. Usage: python scripts/show_review.py <id>"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
root = Path(__file__).resolve().parent.parent
data = json.loads((root / "site" / "data" / "games" / f"{sys.argv[1]}.json").read_text(encoding="utf-8"))
print(data["summary"], "| small game" if data["smallGame"] else "")
for k in data["keyPoints"]:
    print(f"\n[{k['id']}] {k['kind']} 第{k['move']}手 {k['title']}  span {k['span']} {k['severity']} "
          f"{k['scoreLoss']}目 w={k['rankAwareLoss']} {k['category']} deep={k['deep']}")
    print("  played", k["played"], "rec", k["recommended"])
    print("  marks", [(m["label"], m["type"], m.get("point") or len(m.get("points", []))) for m in k["marks"]])
    print("  lines", [(ln["name"], len(ln["moves"])) for ln in k["lines"]])
    for f in k["facts"]:
        print("   ", f)
    for s in k["explain"]["template"]:
        print("  >", s)
    print("  tip:", k["explain"]["tip"])
