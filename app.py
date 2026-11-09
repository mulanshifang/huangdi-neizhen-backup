"""
黄帝内针 AI —— 本地/云端可自托管复刻版
兼容原站接口：GET /、GET /api/health、POST /api/init、POST /api/chat

模型可插拔：
  HDNZ_PROVIDER = dashscope | openai | ollama | none
  HDNZ_BASE_URL / HDNZ_API_KEY / HDNZ_MODEL
"""
import json
import math
import os
import re
import time
import threading
from collections import Counter, defaultdict
from typing import List, Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
STATIC = os.path.join(ROOT, "static")


def _load_env():
    p = os.path.join(ROOT, ".env")
    if not os.path.exists(p):
        return
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env()

PROVIDER = os.getenv("HDNZ_PROVIDER", "none").lower()
BASE_URL = os.getenv("HDNZ_BASE_URL", "")
API_KEY = os.getenv("HDNZ_API_KEY", "")
MODEL = os.getenv("HDNZ_MODEL", "qwen-plus")

app = FastAPI(title="黄帝内针AI查询（本地复刻版）", version="1.0.0")

SYSTEM_PROMPT = """你是「黄帝内针 AI」，一位精通杨真海先生《黄帝内针——和平的使者》的临床顾问。
你的任务：依据给定的《黄帝内针》原文片段，用内针的法理回答提问，让学人能照着做。

回答要求：
1. 只用内针体系的语言：三才（三焦）、阴阳（六经）、同气相求、四总则、三二一（定三焦→定经络→定阴阳→定阿是）、肘膝以下取穴、导引。
2. 先给结论，再讲法理，最后给可执行的取穴路径（部位→经络→左右上下→阿是）。
3. 能引用原文时引用原文（可注明出自哪一章哪一节）；原文片段中没有的内容不要编造，穴位位置不确定时明说要查证。
4. 不堆术语，段落叙述，不用表格、不用 emoji、不用加粗符号；总长一般 300~800 字。
5. 遇到危急重症、出血、感染、孕妇、儿童、不明原因剧痛，先提示及时就医，内针只作辅助。
6. 三焦归属必须先定参照、再下结论，焦位说错比不说更糟：
   - 病在四肢：以「一条胳膊」「一条腿」为参照——肩、胯为下焦；肘、膝为中焦；腕、踝、手、足、指、趾为上焦；上臂、大腿属下至中焦；前臂、小腿属上至中焦。
   - 只有病在躯干本身（胸、腹、背、腰）时才用躯干参照：膈以上为上焦，膈至脐间为中焦，脐以下为下焦。
   - 固定对应：肩↔胯，肘↔膝，腕↔踝。
   - 头颈（头面、颈项）不在三焦框架内，不要给头颈定上中下焦：直接按头颈手足同气求对侧——头对应手与足，颈项对应腕、踝一带；躯干焦位（膈脐分界）也不得套到头上。
   - 自检红线：不得出现「肩属上焦」「膝（盖）属下焦」「小腿属下焦」「踝、手、腕属下焦」「头部属某焦」「头痛（含偏头痛）属某焦」这类说法；把握不准就只写取穴路径，不硬判焦位。
7. 结尾用一句简短口诀收束，便于记忆。
"""

# ---------------- 检索 ----------------------------
def _norm(s: str) -> str:
    return re.sub(r"[\s\u3000]+", "", s or "")


def _tokens(s: str) -> List[str]:
    s = _norm(s)
    toks = []
    for i, ch in enumerate(s):
        if "\u4e00" <= ch <= "\u9fff":
            toks.append(ch)
            if i + 1 < len(s) and "\u4e00" <= s[i + 1] <= "\u9fff":
                toks.append(ch + s[i + 1])
        elif ch.isalnum():
            toks.append(ch.lower())
    return toks


class KB:
    def __init__(self, path: str):
        with open(path, encoding="utf-8") as f:
            self.chunks = json.load(f)
        # 标题重复三次，让"章节标题命中"在打分中占更大权重
        self.docs = []
        for c in self.chunks:
            title = _norm(c.get("section", "") + c.get("chapter", ""))
            self.docs.append(title + " " + title + " " + title + " " + _norm(c["text"]))
        self.tf = [Counter(_tokens(d)) for d in self.docs]
        self.dl = [sum(t.values()) or 1 for t in self.tf]
        self.avgdl = sum(self.dl) / len(self.dl)
        df = defaultdict(int)
        for t in self.tf:
            for w in set(t):
                df[w] += 1
        n = len(self.tf)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}
        self.aliases = {}
        ap = os.path.join(DATA, "aliases.json")
        if os.path.exists(ap):
            self.aliases = json.load(open(ap, encoding="utf-8"))

    def expand(self, q: str) -> str:
        extra = []
        for k, v in self.aliases.items():
            if k in q:
                extra += v
        return q + " " + " ".join(extra)

    def alias_tokens(self, q: str) -> set:
        toks = set()
        for k, v in self.aliases.items():
            if k in q:
                toks.update(v)
        return toks

    def primary_tokens(self, q: str) -> set:
        """每个症状的首个词才是"部位/主题"词，用它做标题命中。"""
        toks = set()
        for k, v in self.aliases.items():
            if k in q and v:
                toks.add(v[0])
        return toks

    def search(self, q: str, k: int = 3):
        # 标题命中词只从用户原话里取，避免扩展词（如"肘""膝"）把无关小节判成命中
        ptoks = {t for t in self.primary_tokens(q) if len(t) >= 1}
        q = self.expand(q)
        qt = Counter(_tokens(q))
        atoks = self.alias_tokens(q)
        best = []
        k1, b = 1.5, 0.75
        for i, tf in enumerate(self.tf):
            score = 0.0
            dl = self.dl[i]
            for w, qf in qt.items():
                f = tf.get(w)
                if not f:
                    continue
                idf = self.idf.get(w, 0.3)
                score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / self.avgdl)) * (1 + 0.6 * (qf > 1))
            # 标题命中优先：症状词落在小节标题上，基本就是该查的那一节
            title = _norm(self.chunks[i].get("section", ""))
            hit_title = 1 if any(t in title for t in ptoks) else 0
            score = (200.0 if hit_title else 0.0) + score / max(1, len(qt)) * 8.0
            # 过短的块（如一句禁令）信息量不足：除非正是本节，否则不进候选
            if len(self.chunks[i].get("text", "")) < 60 and not hit_title:
                continue
            if score > 0:
                best.append((score, i))
        best.sort(reverse=True)
        out = []
        used = set()
        for s, i in best:
            key = (self.chunks[i].get("section"), self.chunks[i].get("text", "")[:30])
            if key in used:
                continue
            used.add(key)
            out.append((s, i))
            if len(out) >= k * 3:
                break
        # 同一节最多取 2 块，保证多样性
        picked, cnt = [], defaultdict(int)
        for s, i in out:
            sec = self.chunks[i].get("section")
            if cnt[sec] >= 2:
                continue
            cnt[sec] += 1
            picked.append((s, i))
            if len(picked) >= k:
                break
        return [self.chunks[i] for _, i in picked]


KB_PATH = os.path.join(DATA, "chunks.json")
kb = KB(KB_PATH) if os.path.exists(KB_PATH) else None

STATE = {"initialized": kb is not None, "hits": defaultdict(list)}
LOCK = threading.Lock()


def llm_chat(messages, api_key: Optional[str] = None, max_tokens: int = 1400) -> str:
    key = api_key or API_KEY
    provider = PROVIDER
    if provider == "none":
        # 未配置模型时，退化为原文检索式回答，保证离线可用
        ctx = messages[-1]["content"]
        return ("（当前为本地检索模式，未接入大模型；配置 .env 中的模型后即为完整问答）\n\n"
                + ctx.split("可参考原文片段：", 1)[-1].strip()
                + "\n\n以上为《黄帝内针》原文片段，可据此对照取穴。")
    if provider == "ollama":
        url = (BASE_URL or "http://localhost:11434") + "/api/chat"
        # 纯 CPU 推理较慢：限制输出长度并放宽超时，保证能出完整回答
        r = requests.post(url, json={"model": MODEL, "messages": messages, "stream": False,
                                     "keep_alive": "30m",
                                     "options": {"temperature": 0.4, "num_predict": min(max_tokens, 500),
                                                 "num_ctx": 4096}}, timeout=900)
        r.raise_for_status()
        return r.json()["message"]["content"]
    base = BASE_URL or ("https://dashscope.aliyuncs.com/compatible-mode/v1" if provider == "dashscope" else "https://api.openai.com/v1")
    payload = {"model": MODEL, "messages": messages, "temperature": 0.4, "max_tokens": max_tokens}
    # 智谱 GLM-4.5 系列默认开深度思考，会多耗一倍 token 并显著拖慢；问答场景关掉更快
    if "bigmodel.cn" in base:
        payload["thinking"] = {"type": "disabled"}
    r = requests.post(base.rstrip("/") + "/chat/completions",
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json=payload, timeout=300)
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=f"模型调用失败: {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"]


def build_messages(message: str, history: Optional[list], hits) -> list:
    ctx = "\n\n".join(f"【片段{i+1}】{c.get('chapter','')}·{c.get('section','')}\n{c['text'][:1200]}"
                      for i, c in enumerate(hits))
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in (history or [])[-6:]:
        if h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str):
            msgs.append({"role": h["role"], "content": h["content"][:2000]})
    msgs.append({"role": "user", "content": f"问题：{message}\n\n可参考原文片段：\n{ctx}"})
    return msgs


class ChatRequest(BaseModel):
    message: str
    history: Optional[list] = None
    api_key: Optional[str] = None


class InitRequest(BaseModel):
    api_key: str = ""


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/cover.png")
def cover():
    return FileResponse(os.path.join(STATIC, "cover.png"))


@app.get("/api/health")
def health():
    now = time.time()
    with LOCK:
        act = sum(1 for t in STATE["hits"]["global"] if now - t < 60)
    return {"status": "ok", "initialized": STATE["initialized"],
            "chunks_count": len(kb.chunks) if kb else 0,
            "active_users_in_last_minute": act,
            "total_requests_tracked": len(STATE["hits"]["global"])}


@app.post("/api/init")
def init_engine(req: InitRequest):
    global kb
    if req.api_key:
        STATE["user_key"] = req.api_key
    kb = KB(KB_PATH)
    STATE["initialized"] = True
    return {"status": "ok", "chunks_count": len(kb.chunks)}


@app.post("/api/chat")
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=422, detail="消息不能为空")
    with LOCK:
        STATE["hits"]["global"].append(time.time())
    hits = kb.search(req.message, k=3) if kb else []
    try:
        answer = llm_chat(build_messages(req.message, req.history, hits), req.api_key)
    except HTTPException:
        raise
    except Exception as e:
        answer = f"模型连接失败：{e}"
        return JSONResponse({"answer": answer, "sources": [], "error": True})
    sources = [{"chapter": c.get("chapter", ""), "section": c.get("section", ""),
                "excerpt": c.get("text", "")[:120]} for c in hits]
    return {"answer": answer, "sources": sources, "error": False}
