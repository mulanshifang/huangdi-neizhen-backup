"""对照评测：同一批问题，分别问线上原站与本地复刻站，比较检索命中与回答。

用法：
    python scripts/compare.py            # 默认 10 题
    python scripts/compare.py 全部       # 全部题目
"""
import json
import sys
import time

import requests

ONLINE = "https://huangdi-neizhen-ai-1.onrender.com"
LOCAL = "http://127.0.0.1:8000"

QUESTIONS = [
    "什么是同气相求？",
    "黄帝内针的四总则是什么？分别怎么用？",
    "三焦怎么定位？上焦中焦下焦各管哪些部位？",
    "头痛怎么治？",
    "肩痛怎么治？",
    "腰痛怎么治？",
    "膝盖痛怎么治？",
    "牙痛怎么治？",
    "失眠怎么治？",
    "内针的用针禁忌有哪些？",
    "什么是阿是穴？怎么找阿是穴？",
    "踝关节扭伤怎么治？",
    "颈椎不舒服怎么治？",
    "胃胀胃痛怎么治？",
    "痛经怎么治？",
]


def ask(base, q, timeout=240):
    try:
        r = requests.post(base + "/api/chat", json={"message": q, "history": []}, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"answer": f"<失败: {e}>", "sources": []}


def secs(d):
    return {s.get("section", "") for s in d.get("sources", []) if s.get("section")}


def main():
    n = len(QUESTIONS) if len(sys.argv) > 1 and sys.argv[1] == "全部" else 10
    hit = 0
    for q in QUESTIONS[:n]:
        o = ask(ONLINE, q)
        time.sleep(13)  # 原站限流 5 次/分钟
        l = ask(LOCAL, q)
        os_, ls = secs(o), secs(l)
        inter = os_ & ls
        score = 1 if inter else 0
        hit += score
        print("=" * 60)
        print("Q:", q)
        print("  线上章节:", " | ".join(sorted(os_)))
        print("  本地章节:", " | ".join(sorted(ls)))
        print("  检索重合:", len(inter), "/", len(os_))
        print("  线上答案:", (o.get("answer") or "")[:180].replace("\n", " "))
        print("  本地答案:", (l.get("answer") or "")[:180].replace("\n", " "))
    print(f"\n章节命中率: {hit}/{n}")


if __name__ == "__main__":
    main()
