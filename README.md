# Academic Intel SkillKit

## 文档分区 / Documentation Audience Map

### 面向人类阅读 / For Human Readers

- `README.md`
  - 项目定位、当前能力边界、快速开始、标准 CLI 路径
- `CONTRIBUTING.md`
  - 面向维护者和贡献者的仓库约定
- `examples/obsidian-layout.md`
  - 面向使用者的 Obsidian 目录建议
- `NEXT_PHASE_PLAN.md`
  - 面向项目负责人和维护者的开发路线与阶段计划

### 面向 AI Agent 与部署 / For AI Agents And Deployment

- `skills/*.SKILL.md`
  - 面向 OpenClaw、Claude Code、Codex、OpenCode 等 agent 的技能入口与执行约定
- `scripts/*.py`
  - 面向 agent / 调度器的确定性执行层；优先由 agent 直接调用
- `config/research-topics.local.yaml`
  - 面向部署环境的本地运行时配置
- `templates/*.md`
  - 面向生成链路的输出模板契约
- `examples/openclaw-cron-notes.md`
  - 面向 OpenClaw 定时调度与部署的入口说明
- `examples/launchd-setup.md`
  - 面向 macOS 本地定时部署（launchd/crontab）的配置指南
- `examples/skill-installation.md`
  - 面向各 AI agent 平台（Claude Code、Codex、OpenCode）的 skill 挂载说明

阅读建议：

- 人类初次了解项目时，先读 `README.md`
- 人类准备部署到 Obsidian / OpenClaw 时，再读 `examples/obsidian-layout.md` 与 `examples/openclaw-cron-notes.md`
- 人类准备在本机设置定时任务时，读 `examples/launchd-setup.md`
- 人类或 agent 需要在特定平台挂载 skills 时，读 `examples/skill-installation.md`
- AI agent 执行任务时，优先读取相关 `SKILL.md`、目标脚本和本地配置

## 中文版

开源研究情报技能库，当前包含一个可用的最小 MVP，以及为后续扩展预留的清晰脚手架。

这个仓库的目标是在 OpenClaw、Claude Code、Codex、OpenCode 以及类似的 ACP 风格运行器之间保持可移植性：

- skills 使用纯 Markdown
- templates 使用纯 Markdown
- 已实现的自动化层是一个小型 Python CLI

### 当前状态

#### 已实现

- `scripts/fetch_arxiv.py` 会根据配置中的 topic 抓取 arXiv 论文
- `scripts/fetch_huggingface.py` 会调用 Hugging Face Papers 官方热点接口，并按本地 topic 做可选过滤
- `scripts/run_multi_source.py` 多源采集管线，支持 Reddit、Hacker News、GitHub、Semantic Scholar、OpenAlex（通过 `src/sources/` 适配器）
- `scripts/enrich_summaries.py` 通过 OpenAI 兼容 API 将 top-N 英文摘要翻译为中文
- `scripts/generate_daily_brief.py` 会合并候选 JSON、去重、排序，并生成一份中文 Markdown 日报，同时保留论文元数据原文
- `scripts/run_daily_pipeline.py` 会把 arXiv 抓取、多源热点采集、LLM 摘要翻译与日报生成串成一条可被 OpenClaw/cron 直接调度的单命令链路
- `src/sources/` 7 个信息源适配器，内置限流、重试和故障隔离
- `src/normalize/` 跨源实体解析与去重
- `src/scoring/` 多维 hot_score 排序
- `src/storage/` 磁盘缓存
- topic 匹配、基础打分、以 arXiv 为核心的日报生成链路已经可用
- 日报目前包含中文概览、主题快照、社区热点、建议动作以及明确的数据边界说明
- `scripts/manage_topics.py` 支持列出、查看、校验，并预览实际生效的 arXiv 查询计划，不会修改配置

#### 当前仅脚手架

- `scripts/build_periodic_report.py`（周期报告生成占位）
- `scripts/manage_topics.py` 中超出只读查看、校验、查询预览之外的部分
- `skills/` 目录中的深度研读编排（`paper-deep-dive`）和周期性复盘自动化（`research-weekly-review`、`research-monthly-review`）

如果你是第一次评估这个仓库，请把下面的“arXiv 主链路 + 可选热点补充”视为当前标准路径。

### 标准 MVP 路径

请在仓库根目录执行以下命令。

这条路径的标准运行时文件如下：

- `config/research-topics.local.yaml`
- `templates/daily-brief-template.md`
- `output/arxiv.json`
- `output/daily-brief.md`

#### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p output
```

#### 2. 创建本地 topic 配置

```bash
cp config/research-topics.example.yaml config/research-topics.local.yaml
```

编辑 `config/research-topics.local.yaml`，设置你的 vault 路径，并只保留你想跟踪的 topic。当前已实现脚本默认就会读取这个本地运行时配置，因此标准 MVP 流程里可以省略 `--config`。

可选：在抓取前先查看、校验或预览实际生效的 arXiv 查询计划。

```bash
python3 scripts/manage_topics.py --list

python3 scripts/manage_topics.py --validate

python3 scripts/manage_topics.py --query-plan
```

可选：查看某一个 topic 的详细信息或做只读诊断。

```bash
python3 scripts/manage_topics.py --detail --topic agents

python3 scripts/manage_topics.py --diagnose
```

#### 3. 抓取 arXiv 候选论文

```bash
python3 scripts/fetch_arxiv.py
```

默认会写入 `output/arxiv.json`。

可选：把抓取限制到单个 topic id。

```bash
python3 scripts/fetch_arxiv.py --topic agents
```

#### 4. 生成日报

```bash
python3 scripts/generate_daily_brief.py
```

默认会读取 `output/arxiv.json` 并写入 `output/daily-brief.md`，内置模板也会自动使用。报告叙述部分使用中文，但标题、作者、机构、ID、URL 和 venue 名称保持原文。

如果你要给 OpenClaw 或 cron 做每日定时任务，推荐直接使用单命令包装脚本：

```bash
python3 scripts/run_daily_pipeline.py
```

当 `config/research-topics.local.yaml` 里设置了有效的 `obsidian.vault_path` 和 `obsidian.root_dir` 时，它会默认把日报写到：

```text
<vault_path>/<root_dir>/01_Daily/YYYY_MM_DD_Daily.md
```

#### 5. 之后可选地补社区热点并合并额外来源文件

当前仓库仍不会替你采集 Semantic Scholar 数据，但已经提供了最小可用的 Hugging Face Papers 热点采集器。如果其他工作流已经产出了规范化 JSON，日报生成器也可以直接消费这些文件。

```bash
python3 scripts/fetch_huggingface.py --out output/huggingface.json
```

```bash
python3 scripts/generate_daily_brief.py \
  --arxiv output/arxiv.json \
  --semantic-scholar output/semantic-scholar.json \
  --huggingface output/huggingface.json \
  --out output/daily-brief.md
```

### 仓库结构

- `skills/`：面向宿主的 skill 文档；其中 `research-daily-brief` 和 `research-topic-manager` 的只读部分，今天可以直接映射到仓库内已实现的自动化
- `scripts/`：确定性的 CLI 层；arXiv 抓取、多源采集、LLM 摘要翻译与日报生成
- `src/`：可复用 Python 模块层；信息源适配器、归一化、打分、缓存和采集管线
- `config/`：`config/research-topics.local.yaml` 的标准起始配置，以及一些面向未来工作的示例配置
- `configs/`：多信息源配置；`configs/sources.local.yaml` 控制各源的启用/限流/凭证
- `templates/`：标准日报模板，以及面向未来流程的脚手架模板
- `examples/`：宿主布局、定时调度、skill 挂载说明

### 内置 Skills

#### 已实现

- `research-daily-brief`
- `research-topic-manager` 的只读查看、校验与 arXiv 查询预览能力

#### 当前仅脚手架

- `paper-deep-dive`
- `research-topic-manager` 的配置修改辅助能力
- `research-weekly-review`
- `research-monthly-review`

### 说明

- `fetch_arxiv.py` 需要访问 arXiv API 的网络权限。
- `fetch_huggingface.py` 需要访问 Hugging Face 官方 `daily_papers` API 的网络权限。
- `run_daily_pipeline.py` 是当前最适合 OpenClaw/cron/launchd 定时调用的入口；多源采集或 LLM 翻译失败时会降级为只生成 arXiv 主链路日报。
- 文档约定：
  - `README.md`、`CONTRIBUTING.md`、`examples/obsidian-layout.md`、`NEXT_PHASE_PLAN.md` 主要服务人类阅读。
  - `skills/*.SKILL.md`、`scripts/*.py`、`config/research-topics.local.yaml`、`templates/*.md`、`examples/openclaw-cron-notes.md` 主要服务 AI agent 执行与部署。
- 缺失可选的 Semantic Scholar 或热点文件不会阻塞日报生成；脚本会给出警告后继续执行。
- `scripts/manage_topics.py --query-plan` 是当前无需联网即可确认哪些启用 topic 会真正转成 arXiv 查询的最快方式。
- `scripts/manage_topics.py --diagnose` 会展示每个 topic 的抓取范围、查询预览、关键词截断情况和显式配置风险。
- 当前排序逻辑是刻意保持简单和透明的，而不是按生产级效果调优。
- 如果合并后的条目里包含 `summary_zh`，日报会直接把它作为中文摘要输出；否则只会写中文阅读提示，不会伪装成自动翻译结果。
- `config/report-thresholds.example.yaml`、`config/scoring-rules.example.yaml` 以及非日报模板目前都只是脚手架示例，不会被 MVP 主链路读取。
- 如果想把输出写进 Obsidian，只需要把 `--out` 指向你的 vault 目录；当前仓库还不会自动处理 vault 索引或路由。

### 路线图

- 在清晰规范化规则下补充更多来源采集器
- 提供真正可用的周报和月报汇总，而不只是占位模板
- 增加可以安全修改本地配置文件的 topic 管理工具
- 加入更深入的论文分析工作流，同时避免把 skill 库绑定到单一宿主

### 许可证

MIT

## English

### Audience Map

#### For Human Readers

- `README.md`
  - project scope, capability boundaries, quick start, canonical CLI path
- `CONTRIBUTING.md`
  - repository contract for maintainers and contributors
- `examples/obsidian-layout.md`
  - suggested Obsidian structure for users
- `NEXT_PHASE_PLAN.md`
  - phase planning and roadmap for maintainers and project owners

#### For AI Agents And Deployment

- `skills/*.SKILL.md`
  - skill entrypoints and execution contracts for OpenClaw, Claude Code, Codex, OpenCode, and similar agents
- `scripts/*.py`
  - deterministic execution layer intended for direct agent/scheduler invocation
- `config/research-topics.local.yaml`
  - local runtime configuration for deployment
- `templates/*.md`
  - output template contract for generation flows
- `examples/openclaw-cron-notes.md`
  - OpenClaw scheduling and deployment notes
- `examples/launchd-setup.md`
  - macOS scheduled deployment guide (launchd/crontab)
- `examples/skill-installation.md`
  - skill mounting instructions for Claude Code, Codex, OpenCode

Recommended reading order:

- humans should start with `README.md`
- humans preparing deployment should then read `examples/obsidian-layout.md` and `examples/openclaw-cron-notes.md`
- humans setting up local scheduled runs should read `examples/launchd-setup.md`
- humans or agents mounting skills on a specific platform should read `examples/skill-installation.md`
- AI agents should read the relevant `SKILL.md`, target scripts, and local config before execution

Open-source research-intelligence skill library with a small implemented MVP and clearly labeled scaffolds for future expansion.

The repository is designed to stay portable across OpenClaw, Claude Code, Codex, OpenCode, and similar ACP-style harnesses:

- skills are plain Markdown
- templates are plain Markdown
- the implemented automation layer is a small Python CLI

### Current Status

#### Implemented

- `scripts/fetch_arxiv.py` fetches arXiv papers from config-defined topics
- `scripts/fetch_huggingface.py` calls the official Hugging Face Papers hotspot API and can optionally filter results with local topics
- `scripts/run_multi_source.py` multi-source collection pipeline for Reddit, Hacker News, GitHub, Semantic Scholar, OpenAlex (via `src/sources/` adapters)
- `scripts/enrich_summaries.py` translates top-N English abstracts to Chinese via OpenAI-compatible API
- `scripts/generate_daily_brief.py` merges candidate JSON, deduplicates papers, ranks them, and renders one Chinese Markdown daily brief while keeping paper metadata in the original language
- `scripts/run_daily_pipeline.py` chains arXiv fetch, multi-source hotspot collection, LLM summary enrichment, and brief generation into one command suitable for OpenClaw/cron scheduling
- `src/sources/` 7 source adapters with built-in rate limiting, retry, and failure isolation
- `src/normalize/` cross-source entity resolution and deduplication
- `src/scoring/` multi-dimensional hot_score ranking
- `src/storage/` disk cache for adapter-level HTTP response caching
- topic matching, scoring, and arXiv-first daily brief generation are working today
- the daily brief includes a Chinese overview, topic snapshot, community hotspots, suggested actions, and explicit data-boundary notes
- `scripts/manage_topics.py` can list, inspect, validate, and preview the effective arXiv query plan without mutating configs

#### Scaffold-Only Today

- `scripts/build_periodic_report.py` (periodic report generation placeholder)
- `scripts/manage_topics.py` beyond read-only inspection, validation, and query-plan preview
- deep-dive orchestration (`paper-deep-dive`) and periodic review automation (`research-weekly-review`, `research-monthly-review`) in `skills/`

If you are evaluating the repo for first-time use, treat the flow below as the canonical path: arXiv as the primary chain, with hotspots as an optional supplement.

### Canonical MVP Path

Run these commands from the repository root.

Canonical runtime files for this path:

- `config/research-topics.local.yaml`
- `templates/daily-brief-template.md`
- `output/arxiv.json`
- `output/daily-brief.md`

#### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p output
```

#### 2. Create a local topic config

```bash
cp config/research-topics.example.yaml config/research-topics.local.yaml
```

Edit `config/research-topics.local.yaml` to set your vault path and keep only the topics you want to track. The implemented scripts now default to this local runtime path, so the canonical MVP flow below can omit `--config`.

Optional: inspect, validate, or preview the effective arXiv query plan before fetching.

```bash
python3 scripts/manage_topics.py --list

python3 scripts/manage_topics.py --validate

python3 scripts/manage_topics.py --query-plan
```

Optional: inspect one topic in more detail or run read-only diagnostics.

```bash
python3 scripts/manage_topics.py --detail --topic agents

python3 scripts/manage_topics.py --diagnose
```

#### 3. Fetch arXiv candidates

```bash
python3 scripts/fetch_arxiv.py
```

This writes to `output/arxiv.json` by default.

Optional: restrict the fetch to one topic id.

```bash
python3 scripts/fetch_arxiv.py --topic agents
```

#### 4. Generate the daily brief

```bash
python3 scripts/generate_daily_brief.py
```

This reads `output/arxiv.json` and writes `output/daily-brief.md` by default. The bundled template is also the default. It renders the report narrative in Chinese while leaving titles, authors, institutions, ids, URLs, and venue names untouched.

If you are configuring OpenClaw or cron, prefer the single-command wrapper:

```bash
python3 scripts/run_daily_pipeline.py
```

When `config/research-topics.local.yaml` contains valid `obsidian.vault_path` and `obsidian.root_dir` values, the wrapper writes the final brief to:

```text
<vault_path>/<root_dir>/01_Daily/YYYY_MM_DD_Daily.md
```

#### 5. Optionally collect hotspots and merge extra source files later

The repo still does not collect Semantic Scholar data for you, but it now includes a minimal Hugging Face Papers hotspot collector. The daily brief generator can also consume normalized JSON payloads produced by other workflows.

```bash
python3 scripts/fetch_huggingface.py --out output/huggingface.json
```

```bash
python3 scripts/generate_daily_brief.py \
  --arxiv output/arxiv.json \
  --semantic-scholar output/semantic-scholar.json \
  --huggingface output/huggingface.json \
  --out output/daily-brief.md
```

### Repository Layout

- `skills/`: host-facing skill docs; `research-daily-brief` plus the read-only parts of `research-topic-manager` map directly to implemented repo automation today
- `scripts/`: deterministic CLI layer; arXiv fetch, multi-source collection, LLM summary enrichment, and daily brief generation
- `src/`: reusable Python modules; source adapters, normalization, scoring, caching, and collection pipeline
- `config/`: one canonical starter config for `config/research-topics.local.yaml` plus scaffold-only examples for future work
- `configs/`: multi-source config; `configs/sources.local.yaml` controls per-source enable/rate-limit/credentials
- `templates/`: one canonical daily brief template plus scaffold-only templates for future workflows
- `examples/`: host layout, scheduling, and skill installation guides

### Included Skills

#### Implemented

- `research-daily-brief`
- `research-topic-manager` for read-only inspection, validation, and arXiv query-plan preview

#### Scaffold-Only

- `paper-deep-dive`
- `research-topic-manager` mutation helpers
- `research-weekly-review`
- `research-monthly-review`

### Notes

- `fetch_arxiv.py` requires network access to the arXiv API.
- `fetch_huggingface.py` requires network access to the official Hugging Face `daily_papers` API.
- `run_daily_pipeline.py` is the preferred OpenClaw/cron/launchd scheduling entrypoint; if multi-source collection or LLM enrichment fails, it degrades to an arXiv-only brief instead of skipping the whole daily run.
- Documentation contract:
  - `README.md`, `CONTRIBUTING.md`, `examples/obsidian-layout.md`, and `NEXT_PHASE_PLAN.md` are primarily for human readers.
  - `skills/*.SKILL.md`, `scripts/*.py`, `config/research-topics.local.yaml`, `templates/*.md`, and `examples/openclaw-cron-notes.md` are primarily for AI-agent execution and deployment.
- Missing optional Semantic Scholar or hotspot files do not block brief generation; the script emits a warning and continues.
- `scripts/manage_topics.py --query-plan` is the quickest no-network way to confirm which enabled topics will actually turn into arXiv queries.
- `scripts/manage_topics.py --diagnose` shows per-topic fetch scope, query preview, keyword truncation, and explicit config risks.
- The current ranking is intentionally simple and transparent rather than tuned for production use.
- If a merged item contains `summary_zh`, the brief renders it as a Chinese abstract. Otherwise the report writes a Chinese reading note instead of pretending a translation exists.
- `config/report-thresholds.example.yaml`, `config/scoring-rules.example.yaml`, and the non-daily templates are scaffold-only examples and are not read by the MVP path.
- Writing into Obsidian is just a matter of choosing an `--out` path inside your vault; the repo does not currently manage vault indexing or routing automatically.

### Roadmap

- implement additional source collectors behind clear normalization rules
- add real weekly and monthly report synthesis instead of placeholder templates
- add topic-management helpers that safely edit local config files
- add deeper paper-analysis workflows without tying the skill library to one specific host

---

## 多信息源架构（Multi-Source Architecture）

> 本章节描述 `feature/new-sources` 分支中新增的可扩展信息源体系。
> 代码位于 `src/`，与现有 `scripts/` 层并行共存，不影响原有 arXiv/HF 日报链路。

### 新增信息源优先级

| 批次 | 信息源 | 类型 | 认证 | 状态 |
|------|--------|------|------|------|
| Tier 0 | arXiv | 学术论文 | 无需 | ✅ 已迁移到 adapter |
| Tier 0 | Hugging Face Papers | 学术热点 | 无需 | ✅ 已迁移到 adapter |
| Tier 1 | Reddit | 社区讨论 | 无需（只读 JSON API） | ✅ 实现 |
| Tier 1 | Hacker News | 社区讨论 | 无需（Algolia API） | ✅ 实现 |
| Tier 1 | GitHub Issues/Discussions | 开发讨论 | 可选（GITHUB_TOKEN） | ✅ 实现 |
| Tier 2 | Semantic Scholar | 论文元数据 | 可选（S2 API Key） | ✅ 实现 |
| Tier 2 | OpenAlex | 论文元数据 | 可选（email polite pool） | ✅ 实现 |

### 目录结构

```
src/
├── sources/           # 所有 source adapters
│   ├── base.py        # SourceAdapter ABC + RateLimiter + RetryConfig
│   ├── arxiv.py       # arXiv Atom feed adapter
│   ├── huggingface.py # HuggingFace daily_papers adapter
│   ├── reddit.py      # Reddit JSON API adapter
│   ├── hackernews.py  # HN Algolia Search API adapter
│   ├── github.py      # GitHub Search Issues/Repos API adapter
│   ├── semantic_scholar.py  # S2 Graph API adapter
│   └── openalex.py    # OpenAlex Works API adapter
├── normalize/
│   ├── schema.py      # NormalizedItem + EngagementMetrics
│   └── entity_resolver.py  # arXiv ID / GitHub / HF entity extraction & merge
├── scoring/
│   └── hot_score.py   # 多维 hot_score（freshness/engagement/depth/cross-platform/impl）
├── pipelines/
│   └── collect.py     # 多 source 编排 pipeline
└── storage/
    └── cache.py       # 文件级磁盘缓存（JSON + TTL）
configs/
└── sources.example.yaml  # 所有 source 的配置模板
scripts/
└── run_multi_source.py   # 多信息源 CLI 入口
```

### 统一 NormalizedItem 字段

每个 adapter 输出 `NormalizedItem`，包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | str | adapter 名称：arxiv / reddit / hackernews / github / … |
| `source_type` | str | paper / discussion / repo / model / topic |
| `external_id` | str | 源系统内唯一 ID |
| `url` | str | 规范 URL |
| `title` | str | 标题 |
| `content` | str | 摘要 / 正文 |
| `author` | str | 主要作者 / 用户名 |
| `published_at` | str | ISO 8601 发布时间 |
| `fetched_at` | str | ISO 8601 抓取时间 |
| `engagement_metrics` | EngagementMetrics | upvotes / comments / stars / forks / citations |
| `raw_tags` | list[str] | 原始 tag / category |
| `language` | str | en / zh 等 |
| `raw_payload` | dict | 原始 API 响应（供调试 / 未来扩展） |
| `paper_ids` | list[str] | 提取的 arXiv ID |
| `repo_urls` | list[str] | 提取的 GitHub repo URL |
| `model_ids` | list[str] | 提取的 HuggingFace model ID |
| `topic_scores` | dict | topic 匹配得分 |
| `score` | float | hot_score（0–10） |

### hot_score 计算公式

```
hot_score = 10 × Σ(weight_i × component_i)

component          weight   说明
freshness          0.30     指数衰减，半衰期 7 天
engagement         0.25     log(upvotes + 2×comments + stars + 2×forks + 3×citations)
discussion_depth   0.15     log(comments)，归一化到 [0,1]
cross_platform     0.15     每多一个平台 +0.3，上限 1.0
impl_signal        0.10     有 GitHub 链接 +0.5，有 demo 提及 +0.3
topic_match        0.05     最佳 topic score / 5.0
```

### 配置新信息源

```bash
# 1. 复制配置模板
cp configs/sources.example.yaml configs/sources.local.yaml

# 2. 按需启用 source（默认 Tier 1/2 均为 disabled）
#    编辑 configs/sources.local.yaml：
#      sources.reddit.enabled: true
#      sources.hackernews.enabled: true

# 3. 可选：设置 token（用于更高速率限制）
export GITHUB_TOKEN="your-token"
export SEMANTIC_SCHOLAR_API_KEY="your-key"
export OPENALEX_EMAIL="you@example.com"
```

### 运行多信息源 pipeline

```bash
# 运行所有已启用 source
python scripts/run_multi_source.py \
  --config config/research-topics.local.yaml \
  --sources-config configs/sources.local.yaml \
  --out output/multi-source.json

# 只跑特定 source
python scripts/run_multi_source.py \
  --sources reddit hackernews \
  --out output/social-signals.json

# 不使用缓存（每次全量抓取）
python scripts/run_multi_source.py --no-cache

# 调试模式
python scripts/run_multi_source.py --log-level DEBUG
```

### 限流策略

| 信息源 | 默认 rpm | 认证后 rpm | 备注 |
|--------|----------|-----------|------|
| arXiv | 3 | — | 官方要求礼貌访问 |
| HuggingFace | 10 | — | 公开 API |
| Reddit | 20 | — | 无需认证，公开 JSON API |
| HN Algolia | 30 | — | 无限制（合理使用） |
| GitHub | 10 | 30 | GITHUB_TOKEN 获取更高限额 |
| Semantic Scholar | 10 | 100 | API key 获取独立配额 |
| OpenAlex | 10 | 100 | email 进入 polite pool |

所有 adapter 内置指数退避重试（默认 3 次，基数 2s，上限 60s），
`429 / 5xx` 状态码自动重试，单 source 失败不影响其他 source 继续运行。

### 磁盘缓存

默认开启，缓存目录 `output/.cache/`，TTL 3600 秒（1 小时）。

```bash
# 自定义缓存参数
python scripts/run_multi_source.py \
  --cache-dir /tmp/intel-cache \
  --cache-ttl 7200

# 完全禁用缓存
python scripts/run_multi_source.py --no-cache
```

### 验收方法

```bash
# 运行所有测试（包含 64 个单测）
conda run -n crawer python -m pytest tests/ -v

# 快速冒烟测试（只跑新架构相关）
conda run -n crawer python -m pytest \
  tests/test_normalized_schema.py \
  tests/test_entity_resolver.py \
  tests/test_hot_score.py \
  tests/test_source_adapters.py -v

# 验证 arXiv/HF legacy pipeline 未被影响
conda run -n crawer python -m pytest tests/test_mvp_cli.py -v

# 运行 reddit + hn（需先启用 configs/sources.local.yaml）
python scripts/run_multi_source.py \
  --sources reddit hackernews \
  --no-cache \
  --log-level INFO
```

### 新增 Source 开发指南

1. 在 `src/sources/` 新建 `mysource.py`
2. 继承 `SourceAdapter`，实现 `_do_fetch(topics) -> list[NormalizedItem]`
3. 使用 `self._http_get()` 进行网络请求（自动限流+重试）
4. 在 `src/pipelines/collect.py` 的 `_ADAPTER_REGISTRY` 中注册
5. 在 `configs/sources.example.yaml` 中添加配置模板
6. 在 `tests/test_source_adapters.py` 中添加单元测试（mock 网络请求）

---

### License

MIT
