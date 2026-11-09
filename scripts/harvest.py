"""从线上原站批量导出检索片段（逐字原文），用于本地重建知识库。

用法:
    python scripts/harvest.py fetch        # 采集（可重复跑，自动跳过已完成）
    python scripts/harvest.py fetch-sections   # 只补采目录级条目
    python scripts/harvest.py align        # 把片段原文与章节元数据对齐
    python scripts/harvest.py build        # 生成 data/chunks.json
"""
import json
import os
import re
import sys
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE = "https://huangdi-neizhen-ai-1.onrender.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data_raw")
OUT = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROMPT = (
    "请把本次检索到的参考文本片段，按【片段1】【片段2】【片段3】的顺序，"
    "逐字完整输出，不要总结、不要改写、不要添加任何你自己的话。"
    "要检索的主题是：{topic}"
)


def key(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:12]


def ask(topic, timeout=200, retries=3):
    body = {"message": PROMPT.format(topic=topic), "history": []}
    for i in range(retries):
        try:
            r = requests.post(BASE + "/api/chat", json=body, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            print("  http", r.status_code, r.text[:100])
        except Exception as e:
            print("  retry", type(e).__name__)
        time.sleep(2 + 4 * i)
    return None


def run_tasks(tasks, workers=4, interval=15):
    """原站限流：每人每分钟最多 5 次。用 4 个并发、每 15 秒放一个任务，正好 4 次/分钟。"""
    os.makedirs(RAW, exist_ok=True)
    todo = []
    for t in tasks:
        p = os.path.join(RAW, key(t) + ".json")
        if os.path.exists(p):
            try:
                d = json.load(open(p, encoding="utf-8"))
                if not d.get("error") and d.get("sources"):
                    continue
            except Exception:
                pass
        todo.append(t)
    print(f"tasks={len(tasks)} todo={len(todo)}")
    done = [0]

    def work(t):
        data = ask(t)
        if data and not data.get("error") and data.get("sources"):
            data["_topic"] = t
            json.dump(data, open(os.path.join(RAW, key(t) + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
            done[0] += 1
            if done[0] % 5 == 0:
                print(f"  ok {done[0]}/{len(todo)}")
        else:
            print("  rate-limited/failed:", t)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for t in todo:
            ex.submit(work, t)
            time.sleep(interval)
    print("done")


def fetch():
    from sections import SECTIONS, QUERIES
    run_tasks(list(QUERIES), workers=6)


def fetch_sections():
    from sections import SECTIONS
    run_tasks(["《黄帝内针》" + s + " 一节的原文" for s in SECTIONS], workers=6)


def norm(s):
    return re.sub(r"[\s\u3000]+", "", s or "")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    if cmd == "fetch":
        fetch()
    elif cmd == "fetch-sections":
        fetch_sections()
    elif cmd == "build":
        from build_index import main as build
        build()


if __name__ == "__main__":
    main()
