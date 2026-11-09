"""把 data_raw/*.json 里采集到的原文片段，整理成 data/chunks.json 知识库。

对齐思路（按可信度从高到低）：
1) 模型有时会带出【参考内容N - 章节 - 小节】块头，块头到下一个块头之间就是该节完整原文，
   章节元数据直接来自块头，最可信；
2) 没有块头时，用接口 sources 的 120 字 excerpt 作锚点，在答案里找最长公共前缀起点，
   只有前缀连续命中 >=12 字才接受，否则不做猜测；
3) 对不齐或切得太碎的，退回 excerpt 原文，保证不产生错误章节归属。
"""
import json
import os
import re
import sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data_raw")
OUT = os.path.join(ROOT, "data", "chunks.json")

HDR = re.compile(r"【参考内容\s*\d+\s*[-－—]\s*([^】]*)】")


def norm(s):
    return re.sub(r"[\s\u3000]+", "", s or "")


def clean(t):
    t = re.sub(r"【片段\d+】", "", t)
    lines = [l.rstrip() for l in t.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


COMMENT = [r"^以上", r"^综上", r"^总结", r"^总之", r"^希望", r"^这段", r"^注：", r"^注:", r"^（",
           r"^原文中", r"^需要说明", r"^注\s"]


def strip_comment(t):
    segs = t.split("\n\n")
    keep = []
    for s in segs:
        if any(re.match(p, s.strip()) for p in COMMENT):
            break
        keep.append(s)
    return "\n\n".join(keep).strip()


def best_pos(ans_n, excerpt_n):
    """在去空白的答案里找 excerpt 的最可信起点，返回 (去空白下标, 命中前缀长度)。"""
    anchor = excerpt_n[:10]
    if len(anchor) < 6:
        return None, 0
    best, bp = -1, None
    start = 0
    while True:
        p = ans_n.find(anchor, start)
        if p < 0:
            break
        seg = ans_n[p:p + len(excerpt_n) + 20]
        c = 0
        for a, b in zip(seg, excerpt_n):
            if a == b:
                c += 1
            else:
                break
        if c > best:
            best, bp = c, p
        start = p + 1
    return bp, best


def dedup_para(t):
    segs = [s.strip() for s in re.split(r"\n{1,}", t) if s.strip()]
    seen, keep = set(), []
    for s in segs:
        k = norm(s)[:60]
        if len(k) >= 10 and k in seen:
            continue
        seen.add(k)
        keep.append(s)
    out = "\n".join(keep)
    # 起点若落在半句中间，切到第一个句号之后
    if out and out[0] in "）)」，,。、；：”’" and "。" in out[:40]:
        out = out[out.find("。") + 1:].lstrip()
    return out


def trim(t, limit=1200):
    if len(t) <= limit:
        return t
    cut = t.rfind("。", 0, limit)
    return t[:cut + 1] if cut > limit * 0.4 else t[:limit]


def add(chunks, chapter, section, text, excerpt=""):
    text = trim(dedup_para(strip_comment(clean(text))))
    if len(text) < 80 and excerpt and len(clean(excerpt)) > len(text):
        text = clean(excerpt)
    if len(text) < 12:
        return
    key = (chapter, section, norm(text)[:40])
    if key in chunks:
        if len(text) > len(chunks[key]["text"]):
            chunks[key]["text"] = text
        return
    chunks[key] = {"chapter": chapter, "section": section, "text": text}


def parse_headers(ans):
    """用【参考内容N - 章节 - 小节】块头切块，返回 [(chapter, section, body)]。"""
    ms = list(HDR.finditer(ans))
    out = []
    for i, m in enumerate(ms):
        parts = [p.strip() for p in re.split(r"\s*[-－—]\s*", m.group(1)) if p.strip()]
        if len(parts) < 2:
            continue
        chapter, section = parts[0], parts[-1]
        start = m.end()
        end = ms[i + 1].start() if i + 1 < len(ms) else len(ans)
        body = re.split(r"【片段\s*\d+】", ans[start:end])[0]
        out.append((chapter, section, body))
    return out


def main():
    files = sorted(f for f in os.listdir(RAW) if f.endswith(".json")) if os.path.isdir(RAW) else []
    chunks = OrderedDict()
    for name in files:
        d = json.load(open(os.path.join(RAW, name), encoding="utf-8"))
        ans = d.get("answer") or ""
        srcs = d.get("sources") or []
        if not ans or not srcs:
            continue

        # 1) 块头精确切分
        covered = set()
        by_sec = {}
        for s in srcs:
            by_sec.setdefault(norm(s.get("section", "")), s.get("excerpt", ""))
        for chapter, section, body in parse_headers(ans):
            if not section:
                continue
            add(chunks, chapter, section, body, by_sec.get(norm(section), ""))
            covered.add(norm(body)[:60])

        # 2) 无块头（或块头没覆盖到）的，用 excerpt 锚点对齐
        pos_list = [i for i, ch in enumerate(ans) if not re.match(r"[\s\u3000]", ch)]
        an_n = norm(ans)
        matched = []
        for s in srcs:
            pre = norm(s.get("excerpt", ""))
            if len(pre) < 12:
                continue
            p, c = best_pos(an_n, pre)
            if p is None or c < 12:
                continue          # 不作低置信度猜测
            matched.append((p, s))
        matched.sort(key=lambda x: x[0])
        for i, (p, s) in enumerate(matched):
            start = pos_list[p] if p < len(pos_list) else 0
            end = pos_list[matched[i + 1][0]] if i + 1 < len(matched) else len(ans)
            text = clean(ans[start:end])
            if norm(text)[:60] in covered:
                continue
            # 切得太碎就不采信，退回 excerpt
            if len(text) < max(80, len(s.get("excerpt", "")) * 0.6):
                text = s.get("excerpt", "")
            add(chunks, s.get("chapter", ""), s.get("section", ""), text, s.get("excerpt", ""))

        # 3) 完全没对齐的片段，用 excerpt 兜底
        have = {norm(c["text"])[:30] for c in chunks.values()}
        for s in srcs:
            pre = norm(s.get("excerpt", ""))[:30]
            if len(pre) < 20 or pre in have:
                continue
            add(chunks, s.get("chapter", ""), s.get("section", ""), s.get("excerpt", ""))
            have.add(pre)

    items = list(chunks.values())
    # 丢掉封面/版权这类无信息块
    items = [c for c in items if len(c["text"]) >= 20 and not re.match(r"^黄帝内针\s*和平的使者", c["text"])]
    # 按原书目录排序
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from sections import SECTIONS
        order = {s: i for i, s in enumerate(SECTIONS)}
        items.sort(key=lambda c: order.get(c["section"], 999))
    except Exception:
        pass
    # 跨块段落去重：同一段只保留一次，但绝不把某节删空
    seen, cleaned = set(), []
    for c in items:
        paras = [p.strip() for p in re.split(r"\n+", c["text"]) if p.strip()]
        keep = []
        for p in paras:
            k = norm(p)[:80]
            if len(k) >= 40 and k in seen:
                continue
            if len(k) >= 40:
                seen.add(k)
            keep.append(p)
        text = "\n".join(keep).strip()
        if len(text) < 60:
            text = c["text"]          # 去重会毁掉本节，保留原样
        if len(text) >= 20:
            c["text"] = text
            cleaned.append(c)
    items = cleaned
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(items, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("raw files:", len(files), "chunks:", len(items), "chars:", sum(len(c["text"]) for c in items))
    print("sections covered:", len({c["section"] for c in items}))


if __name__ == "__main__":
    main()
