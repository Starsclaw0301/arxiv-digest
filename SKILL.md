---
name: arxiv-digest
description: >
  每日 cs.RO 论文日报技能。三步流水线：RSS 抓取 → 并行子 Agent 相关性判断 → 生成带评星的 Markdown 日报并同步 Zotero。
  关注具身智能方向：VLA、灵巧手、数据采集、人形机器人。
  当 cron 任务触发每日日报，或用户要求生成今日日报时使用。
---

# arXiv Daily Digest Skill

所有路径相对于本 skill 根目录（`skills/arxiv-digest/`）。

## 快速参考

| 项目 | 值 |
|------|-----|
| **抓取类别** | `cs.RO` |
| **公告类型** | `new` 和 `cross`（忽略 `replace`） |
| **Zotero 文库** | 个人文库 → `arxiv-digest`（不存在则自动创建） |
| **凭证** | `.secret/zotero.env`（`ZOTERO_API_KEY`、`ZOTERO_USER_ID`） |
| **日报输出** | `digests/YYYY-MM-DD.md` |
| **中间数据** | `data/papers.json`、`data/relevance.json` |

---

## 调用协议（三步）

### Step 1 — 抓取论文

```bash
source .venv/bin/activate
python src/fetcher.py
```

从 arXiv RSS Atom feed 抓取 `cs.RO` 当日新论文，调用 arXiv Search API 补充摘要和作者信息，过滤掉 `replace` 类型，写入 `data/papers.json`。

### Step 2 — 相关性判断（并行子 Agent）

读取 `data/papers.json`。对**每一篇**论文，根据标题和摘要判断是否与以下研究方向相关，写入 `data/relevance.json`。

**必须使用并行子 Agent 执行判断。** 不得使用关键词匹配或规则过滤。每批 ≤ 30 篇，多批并行，每个子 Agent 返回一个 JSON 数组。

#### `data/relevance.json` 格式

```json
[
  {
    "arxiv_id": "2603.01234",
    "is_relevant": true,
    "theme": "vla",
    "stars": 3,
    "reason": "一句话说明为什么相关，以及核心贡献"
  },
  {
    "arxiv_id": "2603.01235",
    "is_relevant": false,
    "theme": null,
    "stars": 0,
    "reason": ""
  }
]
```

文件必须包含 `data/papers.json` 中**每一篇**论文的条目（包括不相关的）。

#### 研究方向

**VLA / 模仿学习** (`theme: "vla"`)
视觉语言动作模型、模仿学习策略（Diffusion Policy、Flow Matching）、多模态融合、实机部署、跨具身迁移。

**灵巧手 / 触觉感知** (`theme: "dexterous"`)
多指灵巧手操控、触觉/力觉传感、hand-object interaction、in-hand manipulation、精密装配。

**数据采集 / 遥操作** (`theme: "data"`)
遥操作系统、便携采集接口（UMI/wrist camera）、人类示教采集、大规模机器人数据集、自视角数据。

**人形机器人 / 全身控制** (`theme: "humanoid"`)
人形机器人运动控制、全身协调、双臂操作、步态规划、sim-to-real。

#### 评星标准

- ⭐⭐⭐（`stars: 3`）**必读**：方法新颖、有实机验证、对领域有明显推进、或开源
- ⭐⭐（`stars: 2`）**值得关注**：方向相关、有一定创新点
- ⭐（`stars: 1`）**了解即可**：弱相关或纯理论

#### 过滤准则

- 一篇论文必须明确针对上述方向之一才标记为相关
- 泛泛的 LLM 推理（无机器人应用）、通用压缩（无边缘/机器人背景）标记为不相关
- 基于**标题和摘要**判断

### Step 3 — 处理、生成日报、同步 Zotero

```bash
source .venv/bin/activate
python src/processor.py
# 跳过 Zotero 同步（测试用）：
python src/processor.py --dry-run
```

此命令：
1. 加载 `data/papers.json` 和 `data/relevance.json`
2. 检测每篇相关论文的 **venue**（ICRA/IROS/CoRL/NeurIPS 等）
3. 从摘要中提取 **project page URL**
4. 生成带评星、分主题、末尾附"今日必读"的 Markdown 日报，写入 `digests/YYYY-MM-DD.md`
5. 将相关论文同步到 Zotero（按 arXiv ID 去重，附 PDF）

完成后，将 `digests/YYYY-MM-DD.md` 的内容直接发给用户。

---

## 输出格式

```
# cs.RO 日报 · YYYY-MM-DD

## 🤖 VLA / 模仿学习

**论文标题** `CoRL` ⭐⭐⭐
一句话核心贡献，说明方法和关键 insight
https://arxiv.org/abs/<id> · [项目页](https://...)

---
**今日必读** ⭐⭐⭐
- 论文标题1
- 论文标题2
```

---

## 环境准备

```bash
cd skills/arxiv-digest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -i https://mirrors.ustc.edu.cn/pypi/web/simple
```

确保 `.secret/zotero.env` 包含：

```
ZOTERO_API_KEY=<your key>
ZOTERO_USER_ID=<your user id>
```

---

## 调度说明

- arXiv RSS feed 每日在**北京时间 13:00 左右**更新（EDT 季节为 12:00）
- **周六、周日无更新**；周一的 feed 包含周五提交的论文
- 建议在北京时间 **13:30 后**调用，确保当天 feed 已更新
- 当前 cron 任务设置为每天 **08:00**，需改为 **14:00** 以匹配 feed 更新时间

---

## Attribution

感谢 arXiv 提供开放获取互操作性接口。
