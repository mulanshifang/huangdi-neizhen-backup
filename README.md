---
title: Huangdi Neizhen AI Backup
emoji: 📖
colorFrom: gray
colorTo: green
sdk: docker
pinned: false
---

# 黄帝内针 AI · 本地/云端自托管复刻版

原站 `https://huangdi-neizhen-ai-1.onrender.com/` 的完整备份实现：同样的接口、同样的页面、同样的知识库组织方式，模型可自由替换（阿里百炼 / 任意 OpenAI 兼容接口 / 本地 Ollama / 纯检索离线模式）。

## 1. 目录结构

```
huangdi-neizhen-local/
├─ app.py                 # FastAPI 后端（兼容原站 4 个接口）
├─ static/
│  ├─ index.html          # 与原站一致的聊天页面
│  └─ cover.png           # 书籍封面
├─ data/
│  ├─ chunks.json         # 知识库（章节 + 原文片段）
│  └─ aliases.json        # 症状→部位/经络 检索扩展词表
├─ scripts/
│  ├─ harvest.py          # 从原站导出原文片段（限速 4 次/分钟）
│  ├─ build_index.py      # 把导出结果整理成 chunks.json
│  ├─ compare.py          # 与原站做同题对照评测
│  ├─ coverage.py         # 核对知识块覆盖率
│  └─ sections.py         # 原书目录与测试问题集
├─ requirements.txt
├─ 启动.bat               # Windows 一键启动
├─ Dockerfile / render.yaml
└─ .env.example
```

## 2. 本地启动（Windows）

```powershell
cd huangdi-neizhen-local
python -m pip install -r requirements.txt
copy .env.example .env      # 编辑 .env 填入模型配置
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 。也可直接双击 `启动.bat`。

## 3. 模型配置（.env）

| 方案 | 配置 | 说明 |
|---|---|---|
| 阿里百炼（最接近原站） | `HDNZ_PROVIDER=dashscope`、`HDNZ_API_KEY=sk-xxx`、`HDNZ_MODEL=qwen-plus`（或 `qwen-max`） | 原站就是用 DashScope 的通义千问，换成同名模型效果最接近 |
| 智谱 GLM（免费 · 当前在用） | `HDNZ_PROVIDER=openai`、`HDNZ_BASE_URL=https://open.bigmodel.cn/api/paas/v4`、`HDNZ_API_KEY=<BigModel 的 Key>`、`HDNZ_MODEL=glm-4.5-flash` | `glm-4.5-flash` / `glm-4-flash` 免费，无需充值；代码会自动关闭深度思考以提速 |
| 任意 OpenAI 兼容接口 | `HDNZ_PROVIDER=openai`、`HDNZ_BASE_URL=https://api.deepseek.com/v1`、`HDNZ_MODEL=deepseek-chat` | 硅基流动、DeepSeek、Moonshot 等都可 |
| 本地离线大模型 | `HDNZ_PROVIDER=ollama`、`HDNZ_MODEL=qwen2.5:7b` | 先装 Ollama 并 `ollama pull qwen2.5:7b`，断网也能用 |
| 不接模型 | `HDNZ_PROVIDER=none` | 只返回检索到的原文片段，零成本、零依赖，可离线 |

## 4. 接口（与原站一致，可直接替换前端）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 聊天页面 |
| GET | `/api/health` | `{status, initialized, chunks_count, active_users_in_last_minute}` |
| POST | `/api/init` | `{api_key}` → `{status, chunks_count}` |
| POST | `/api/chat` | `{message, history, api_key}` → `{answer, sources[], error}` |

`sources` 每项含 `chapter / section / excerpt`，与前端展示逻辑完全对接。

## 5. 免费云端托管

### 方案 A：Render（与原站相同）
1. 把本目录推到 GitHub（**private 仓库即可**）。
2. Render → New → Blueprint，选中仓库，`render.yaml` 会自动建服务。
3. 在 Environment 里填 `HDNZ_API_KEY`。
4. 免费实例约 15 分钟无访问会休眠，首次访问有 30~60 秒唤醒，属正常现象。

### 方案 B：Hugging Face Spaces（Docker，免费）
1. 新建 Space → SDK 选 Docker → Blank。
2. 上传本目录（`Dockerfile` 已按 `$PORT` 自适应，端口会指向 7860）。
3. Settings → Variables 增加 `HDNZ_PROVIDER / HDNZ_API_KEY / HDNZ_MODEL`。
4. 在 Space 根目录的 `README.md` 顶部补 front matter（HF 用它识别 Docker Space）：
   ```
   ---
   title: 黄帝内针 AI 备份
   sdk: docker
   app_port: 7860
   ---
   ```
   若不想改本仓库 README，可另建一个仅含 front matter 的同名文件推到 Space。
5. 访问 `https://<用户名>-<space名>.hf.space`。

### 方案 C：本机常开 + 内网穿透
`uvicorn` 常驻本机，需要外网时用 frp / cloudflared 暴露端口即可，数据和密钥都在自己手里。

## 6. 知识库与现状

原站 `/api/health` 自报 276 块，来源是《黄帝内针——和平的使者》正文 + 书中图表转写（`补录数据`）+ 自整理医案/速查表。

**本项目实际导出结果**：458 次成功采集 → **203 个知识块、113 个小节、约 7.6 万字**（`data/chunks.json`）。
按"原站曾返回过的块"统计，覆盖率 **113/118 = 95.8%**；未覆盖的 5 个是封面、版权页、章级标题等无信息块（用 `python scripts/coverage.py` 可随时复核）。

导出脚本以「限速 4 次/分钟」（低于原站每 IP 5 次/分钟的限制）把原站检索到的**原文片段**逐块取回：

```powershell
python scripts/harvest.py fetch            # 约 90 个典型问题
python scripts/harvest.py fetch-sections   # 目录级逐节补采
python scripts/build_index.py              # 生成 data/chunks.json
```

想继续扩充覆盖率，只要往 `scripts/sections.py` 的 `QUERIES` 里加问题，再跑一次 `fetch` 即可（已采过的会自动跳过）。

## 7. 评测

```powershell
python scripts/test_retrieval.py   # 离线检索自检（不调外部接口）
python scripts/compare.py          # 与原站同题对照（10 题）
python scripts/compare.py 全部      # 全部题目
python scripts/coverage.py         # 核对知识块覆盖率
```

输出会对比同一问题在原站与本地站命中的章节，以及两边回答，用来判断"检索是否对齐、回答是否同水平"。

## 8. 免责声明

本工具仅用于中医经典学习与文献检索，不构成诊疗建议。针刺属侵入性操作，务必由具备资质的医师执行；急危重症请立即就医。
