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

阅读建议：

- 人类初次了解项目时，先读 `README.md`
- 人类准备部署到 Obsidian / OpenClaw 时，再读 `examples/obsidian-layout.md` 与 `examples/openclaw-cron-notes.md`
- AI agent 执行任务时，优先读取相关 `SKILL.md`、目标脚本和本地配置

## 中文版

开源研究情报技能库，当前包含一个可用的最小 MVP，以及为后续扩展预留的清晰脚手架。

这个仓库的目标是在 OpenClaw、Claude Code、Codex、OpenCode 以及类似的 ACP 风格运行器之间保持可移植性：

- skills 使用纯 Markdown
- templates 使用纯 Markdown
- 已实现的自动化层是一个小型 Python CLI

### 当前状态

#### 已实现的 MVP

- `scripts/fetch_arxiv.py` 会根据配置中的 topic 抓取 arXiv 论文
- `scripts/fetch_huggingface.py` 会调用 Hugging Face Papers 官方热点接口，并按本地 topic 做可选过滤
- `scripts/generate_daily_brief.py` 会合并候选 JSON、去重、排序，并生成一份中文 Markdown 日报，同时保留论文元数据原文
- `scripts/run_daily_pipeline.py` 会把 arXiv 抓取、可选热点抓取与日报生成串成一条可被 OpenClaw/cron 直接调度的单命令链路
- topic 匹配、基础打分、以 arXiv 为核心的日报生成链路已经可用
- 日报目前包含中文概览、主题快照、建议动作以及明确的数据边界说明
- 当前标准 CLI 路径默认使用 `config/research-topics.local.yaml`、`output/arxiv.json` 和 `output/daily-brief.md`
- `scripts/manage_topics.py` 支持列出、查看、校验，并预览实际生效的 arXiv 查询计划，不会修改配置
- 如果你在仓库外部已经拿到了其他来源的规范化 JSON，日报生成器也可以选择性合并

#### 当前仅脚手架

- `scripts/fetch_semantic_scholar.py`
- `scripts/build_periodic_report.py`
- `scripts/manage_topics.py` 中超出只读查看、校验、查询预览之外的部分
- `skills/` 目录中的深度研读编排和周期性复盘自动化

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
<vault_path>/<root_dir>/01_Daily/YYYY-MM-DD-研究情报日报.md
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
- `scripts/`：确定性的 CLI 层；当前 MVP 主要是 arXiv 抓取与日报生成
- `config/`：`config/research-topics.local.yaml` 的标准起始配置，以及一些面向未来工作的示例配置
- `templates/`：标准日报模板，以及面向未来流程的脚手架模板
- `examples/`：可选的宿主布局与调度说明，不是 MVP 的必需部分

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
- `run_daily_pipeline.py` 是当前最适合 OpenClaw 定时调用的入口；热点抓取失败时会降级为只生成 arXiv 主链路日报。
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

Recommended reading order:

- humans should start with `README.md`
- humans preparing deployment should then read `examples/obsidian-layout.md` and `examples/openclaw-cron-notes.md`
- AI agents should read the relevant `SKILL.md`, target scripts, and local config before execution

Open-source research-intelligence skill library with a small implemented MVP and clearly labeled scaffolds for future expansion.

The repository is designed to stay portable across OpenClaw, Claude Code, Codex, OpenCode, and similar ACP-style harnesses:

- skills are plain Markdown
- templates are plain Markdown
- the implemented automation layer is a small Python CLI

### Current Status

#### Implemented MVP

- `scripts/fetch_arxiv.py` fetches arXiv papers from config-defined topics
- `scripts/fetch_huggingface.py` calls the official Hugging Face Papers hotspot API and can optionally filter results with local topics
- `scripts/generate_daily_brief.py` merges candidate JSON, deduplicates papers, ranks them, and renders one Chinese Markdown daily brief while keeping paper metadata in the original language
- `scripts/run_daily_pipeline.py` chains arXiv fetch, optional hotspot fetch, and brief generation into one command suitable for OpenClaw/cron scheduling
- topic matching, simple scoring, and arXiv-first daily brief generation are working today
- the daily brief now includes a Chinese overview, topic snapshot, suggested actions, and explicit data-boundary notes
- the canonical CLI path now defaults to `config/research-topics.local.yaml`, `output/arxiv.json`, and `output/daily-brief.md`
- `scripts/manage_topics.py` can list, inspect, validate, and preview the effective arXiv query plan without mutating configs
- the brief generator can optionally merge pre-normalized JSON from other sources if you collected it outside this repo

#### Scaffold-Only Today

- `scripts/fetch_semantic_scholar.py`
- `scripts/build_periodic_report.py`
- `scripts/manage_topics.py` beyond read-only inspection, validation, and query-plan preview
- deep-dive orchestration and periodic review automation in `skills/`

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
<vault_path>/<root_dir>/01_Daily/YYYY-MM-DD-研究情报日报.md
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
- `scripts/`: deterministic CLI layer; arXiv fetch plus daily brief generation are the current MVP
- `config/`: one canonical starter config for `config/research-topics.local.yaml` plus scaffold-only examples for future work
- `templates/`: one canonical daily brief template plus scaffold-only templates for future workflows
- `examples/`: optional host-layout and scheduling notes, not required for the MVP

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
- `run_daily_pipeline.py` is the preferred OpenClaw scheduling entrypoint; if hotspot collection fails, it degrades to an arXiv-only brief instead of skipping the whole daily run.
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

### License

MIT
