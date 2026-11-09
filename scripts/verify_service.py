"""本地服务端到端问答验证：打印每题的引用章节、回答长度与开头。

用法：python scripts/verify_service.py
"""
import json
import os
import sys
import time

import requests

BASE = os.environ.get("HDNZ_BASE", "http://127.0.0.1:8000")

QUESTIONS = [
    "肩周炎胳膊抬不起来，针哪里？",
    "腰痛怎么取穴？",
    "落枕脖子转不动怎么办？",
    "膝盖内侧痛取什么穴？",
    "偏头痛怎么扎？",
    "失眠多梦怎么取穴？",
    "用针有哪些禁忌？",
    "胃胀胃痛怎么处理？",
    "脚踝扭伤肿痛怎么取穴？",
    "内针的四总则是什么？",
    "什么是同气相求？",
    "痛经怎么取穴？",
]

for _ in range(40):
    try:
        h = requests.get(BASE + "/api/health", timeout=3).json()
        break
    except Exception:
        time.sleep(1)
else:
    sys.exit("服务未启动")

print("health:", json.dumps(h, ensure_ascii=False))
print("=" * 70)
ok = 0
for q in QUESTIONS:
    r = requests.post(BASE + "/api/chat",
                      json={"message": q, "history": [], "api_key": ""},
                      timeout=120).json()
    srcs = r.get("sources") or []
    ans = r.get("answer") or ""
    print(f"\nQ: {q}")
    print(f"   引用: {len(srcs)} 块 / 回答 {len(ans)} 字")
    for s in srcs:
        print(f"   - [{s.get('chapter','')}] {s.get('section','')}")
    print("   开头:", ans[:120].replace("\n", " "))
    if srcs:
        ok += 1
print("\n" + "=" * 70)
print(f"有引用返回: {ok}/{len(QUESTIONS)}")
