"""Prints the cached LLM explanations of saved games and how they fared in verification.

Usage: python scripts/llm_report.py [<id> ...]   (default: every game in raw/)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import analyze  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
root = Path(__file__).resolve().parent.parent
ids = sys.argv[1:] or sorted(p.name.split(".")[0] for p in (root / "raw").glob("*.json.gz"))
total = first = final = 0
for game_id in ids:
    raw = analyze.load_raw(root / "raw" / f"{game_id}.json.gz")
    site = json.loads((root / "site" / "data" / "games" / f"{game_id}.json").read_text(encoding="utf-8"))
    print(f"== {game_id}")
    for k in site["keyPoints"]:
        total += 1
        llm = k["explain"].get("llm")
        # Find this key point's cache entry: the verified one on the page, or a rejected one.
        entry = next((e for e in raw.get("llm", {}).values()
                      if llm and e.get("verified") and e["sentences"] == llm["sentences"]), None)
        if entry is None:
            entry = next((e for e in raw.get("llm", {}).values() if not e.get("verified")
                          and any(f'"move": {k["move"]}' in json.dumps(a, ensure_ascii=False) for a in e["rejected"])), None)
        print(f"  第{k['move']}手 {k['kind']}：", end="")
        if llm:
            final += 1
            attempts = entry["attempts"] if entry else "?"
            first += attempts == 1
            print(f"通过（第 {attempts} 次）")
            for s in llm["sentences"]:
                print(f"     {s['text']}   {s['refs']}")
            print(f"     tip: {llm['tip']['text']}   {llm['tip']['refs']}")
        else:
            print("未通过")
        if entry and entry.get("rejected") or (entry and entry.get("attempts", 1) > 1):
            pass
    for e in raw.get("llm", {}).values():
        for a in e.get("rejected", []):
            print("   被拒：", a["problems"])
print(f"\n共 {total} 个关键点：第一次就通过 {first}，最终通过 {final}（{final / total:.0%}）")
