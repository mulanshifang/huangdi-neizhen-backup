"""核对本地知识库对原站可见块的覆盖情况。

用法：python scripts/coverage.py
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data_raw")
chunks = json.load(open(os.path.join(ROOT, "data", "chunks.json"), encoding="utf-8"))


def n(s):
    return "".join((s or "").split())


seen = {}
for p in glob.glob(os.path.join(RAW, "*.json")):
    d = json.load(open(p, encoding="utf-8"))
    for s in d.get("sources") or []:
        if s.get("section"):
            seen.setdefault(n(s["section"]), s.get("excerpt", ""))

have = {}
for c in chunks:
    k = n(c["section"])
    have[k] = have.get(k, 0) + len(c["text"])

covered = [k for k in seen if k in have]
print("原站曾返回的块（去重）:", len(seen))
print("本地已建块（去重）:", len(have), "总字数:", sum(have.values()))
print(f"按块覆盖率: {len(covered)}/{len(seen)} = {len(covered) / len(seen) * 100:.1f}%")
print("\n未覆盖:")
for k in seen:
    if k not in have:
        print("  -", k, "|", seen[k][:40].replace("\n", " "))
short = sorted(((v, k) for k, v in have.items() if v < 120))[:15]
print("\n本地过短的块(<120字):", len(short))
for v, k in short:
    print("  ", v, k)
