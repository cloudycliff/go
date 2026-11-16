"""Prints which fields a saved raw analysis contains. Usage: python scripts/inspect_raw.py <raw.json.gz>"""

import gzip
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
with gzip.open(sys.argv[1], "rt", encoding="utf-8") as f:
    raw = json.load(f)
responses = raw["overview"]["responses"]
print("engine:", raw["engine"], "params:", raw["overview"]["params"])
first = responses[40]
print("response keys:", sorted(first))
print("rootInfo:", json.dumps(first["rootInfo"], ensure_ascii=False))
print("moveInfos[0] keys:", sorted(first["moveInfos"][0]))
print("moveInfos[0]:", {k: v for k, v in first["moveInfos"][0].items() if k not in ("pv", "ownership")})
print("pv len:", len(first["moveInfos"][0].get("pv", [])))
for key in ("ownership", "policy", "humanPolicy"):
    value = first.get(key)
    print(key, "len:", None if value is None else len(value))
stdevs = [r["rootInfo"].get("humanScoreStdev") for r in responses]
print("humanScoreStdev every 20:", [round(s, 1) if s is not None else None for s in stdevs[::20]])
print("scoreStdev every 20:", [round(r["rootInfo"].get("scoreStdev", float("nan")), 1) for r in responses[::20]])
