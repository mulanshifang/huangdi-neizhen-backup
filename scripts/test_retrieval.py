"""离线检查检索命中情况（不调用任何外部接口）。"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
from app import KB, KB_PATH

kb = KB(KB_PATH)
qs = [
    "什么是同气相求？", "黄帝内针的四总则是什么？", "三焦怎么定位？",
    "头痛怎么治？", "肩痛怎么治？", "腰痛怎么治？", "膝盖痛怎么治？",
    "牙痛怎么治？", "失眠怎么治？", "内针的用针禁忌有哪些？",
    "踝关节扭伤怎么治？", "颈椎不舒服怎么治？", "胃胀胃痛怎么治？",
    "痛经怎么治？", "什么是阿是穴？",
]
for q in qs:
    hits = kb.search(q, 3)
    print(f"Q: {q}")
    for h in hits:
        print(f"    - {h['chapter']} | {h['section']} | {len(h['text'])}字")
