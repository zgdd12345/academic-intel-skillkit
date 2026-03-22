# Academic Intel SkillKit

开源研究情报技能库，支持学术论文追踪、多源信息采集与自动化报告生成。设计目标是在 OpenClaw、Claude Code、Codex、OpenCode 等 AI agent 平台间保持可移植性，同时支持本地定时部署。

- skills 使用纯 Markdown
- templates 使用纯 Markdown
- 自动化层是确定性的 Python CLI

## 当前状态

### 已实现

- **日报生成**：arXiv 论文抓取 → 多源热点采集（Reddit、HN、GitHub、HuggingFace、Semantic Scholar、OpenAlex）→ LLM 摘要翻译 → 中文 Markdown 日报 → Obsidian 写入
- **周报/月报生成**：解析日报 Markdown → 跨日去重聚合 → 主题趋势分析 → LLM 综述生成 → Obsidian 写入
- **7 个信息源适配器**（`src/sources/`）：内置限流、指数退避重试、故障隔离
- **跨源实体解析**（`src/normalize/`）：基于 arXiv ID / GitHub URL / HF model ID 去重
- **多维 hot_score 排序**（`src/scoring/`）：freshness、engagement、discussion depth、cross-platform、impl signal
- **Topic 管理**：列出、校验、查询预览（只读）

### 当前仅脚手架

- `paper-deep-dive`（深度论文研读编排）
- `manage_topics.py` 的配置修改辅助能力

## 快速开始

```bash
conda activate crawer
pip install -r requirements.txt
mkdir -p output

# 创建本地配置
cp config/research-topics.example.yaml config/research-topics.local.yaml
cp configs/sources.example.yaml configs/sources.local.yaml
# 编辑两个 local.yaml，设置 vault 路径、topic、信息源开关
```

### 日报（推荐使用单命令）

```bash
python3 scripts/run_daily_pipeline.py
```

这条命令会串联执行：arXiv 抓取 → 多源热点采集 → LLM 摘要翻译 → 日报生成 → Obsidian 写入。任何可选步骤失败时会自动降级，不会阻断整体链路。

当 `config/research-topics.local.yaml` 配置了有效的 `obsidian.vault_path` 时，日报会写入：

```text
<vault_path>/<root_dir>/01_Daily/YYYY_MM_DD_Daily.md
```

### 周报和月报

```bash
# 周报（过去 7 天）
python3 scripts/build_periodic_report.py --period weekly

# 月报（当前月）
python3 scripts/build_periodic_report.py --period monthly

# 预览（不写文件）
python3 scripts/build_periodic_report.py --period weekly --dry-run

# 不调用 LLM（纯数据报告）
python3 scripts/build_periodic_report.py --period weekly --skip-llm
```

周报写入 `03_Weekly/YYYY-Www-academic-weekly.md`，月报写入 `04_Monthly/YYYY-MM-academic-monthly.md`。

### 分步执行

```bash
# Topic 校验与查询预览
python3 scripts/manage_topics.py --validate
python3 scripts/manage_topics.py --query-plan

# 单独抓取
python3 scripts/fetch_arxiv.py
python3 scripts/fetch_huggingface.py --out output/huggingface.json

# 多源采集
python3 scripts/run_multi_source.py \
  --sources-config configs/sources.local.yaml \
  --out output/multi-source.json

# LLM 摘要翻译
python3 scripts/enrich_summaries.py --arxiv output/arxiv.json --top-n 8

# 日报生成
python3 scripts/generate_daily_brief.py \
  --arxiv output/arxiv.json \
  --huggingface output/huggingface.json \
  --out output/daily-brief.md
```

## 仓库结构

```
skills/                  # Markdown 技能契约（供 AI agent 读取）
  ├── research-daily-brief/
  ├── research-weekly-review/
  ├── research-monthly-review/
  ├── research-topic-manager/
  └── paper-deep-dive/         # 脚手架

scripts/                 # 确定性 Python CLI
  ├── run_daily_pipeline.py    # 日报全链路编排
  ├── build_periodic_report.py # 周报/月报生成
  ├── fetch_arxiv.py           # arXiv 抓取
  ├── fetch_huggingface.py     # HuggingFace 热点
  ├── run_multi_source.py      # 多源采集管线
  ├── enrich_summaries.py      # LLM 摘要翻译
  ├── generate_daily_brief.py  # 日报渲染
  ├── manage_topics.py         # Topic 只读管理
  ├── parse_daily_briefs.py    # 日报 Markdown 解析模块
  ├── aggregate_period.py      # 周期聚合模块
  └── common.py                # 共享数据模型与工具

src/                     # 可复用 Python 模块
  ├── sources/                 # 7 个信息源适配器
  ├── normalize/               # NormalizedItem + EntityResolver
  ├── scoring/                 # hot_score 排序
  ├── pipelines/               # CollectPipeline 编排
  └── storage/                 # 磁盘缓存

config/                  # Topic 配置（*.local.yaml 已 gitignore）
configs/                 # 多信息源配置（*.local.yaml 已 gitignore）
templates/               # 输出模板（日报/周报/月报）
examples/                # 部署说明与参考
  ├── launchd-setup.md         # macOS 定时部署（launchd/crontab）
  ├── openclaw-cron-notes.md   # OpenClaw 调度说明
  ├── skill-installation.md    # 各 AI agent 平台 skill 挂载指南
  └── obsidian-layout.md       # Obsidian 目录建议
```

## 信息源

| 批次 | 信息源 | 类型 | 认证 | 默认 rpm |
|------|--------|------|------|----------|
| Tier 0 | arXiv | 学术论文 | 无需 | 3 |
| Tier 0 | HuggingFace Papers | 学术热点 | 无需 | 10 |
| Tier 1 | Reddit | 社区讨论 | 无需 | 20 |
| Tier 1 | Hacker News | 社区讨论 | 无需 | 30 |
| Tier 1 | GitHub | 开发讨论 | 可选（GITHUB_TOKEN） | 10 |
| Tier 2 | Semantic Scholar | 论文元数据 | 可选（API Key） | 10 |
| Tier 2 | OpenAlex | 论文元数据 | 可选（email） | 10 |

所有适配器内置指数退避重试（默认 3 次），`429 / 5xx` 自动重试，单源失败不影响其他源。

## 定时部署

### macOS（推荐 launchd）

参见 `examples/launchd-setup.md`，提供了完整的 plist 配置和 crontab 替代方案。

### OpenClaw / Codex

参见 `examples/openclaw-cron-notes.md`。推荐命令：

```bash
conda run -n crawer python scripts/run_daily_pipeline.py
```

## 配置说明

`config/research-topics.local.yaml`（从 `.example.yaml` 复制）：

- `obsidian.vault_path` — Obsidian vault 根目录
- `reporting.daily_top_n` — 日报推荐论文数
- `sources.arxiv.lookback_days` — arXiv 回溯天数
- `topics[]` — 追踪主题列表（include_keywords / exclude_keywords / arxiv_categories）
- `llm.base_url` / `llm.api_key` / `llm.model` — LLM 配置（也可用环境变量 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`）

`configs/sources.local.yaml`（从 `sources.example.yaml` 复制）：

- 每个信息源的 `enabled`、`requests_per_minute`、`max_retries` 及源特有参数

`config/report-thresholds.example.yaml`：

- 周报/月报生成的最低数据量阈值

## 新增信息源开发指南

1. 在 `src/sources/` 新建 `mysource.py`，继承 `SourceAdapter`
2. 实现 `_do_fetch(topics) -> list[NormalizedItem]`
3. 使用 `self._http_get()` 进行网络请求（自动限流+重试）
4. 在 `src/pipelines/collect.py` 的 `_ADAPTER_REGISTRY` 中注册
5. 在 `configs/sources.example.yaml` 中添加配置模板
6. 在 `tests/test_source_adapters.py` 中添加单元测试

## 测试

```bash
# 全部测试
conda run -n crawer python -m pytest tests/ -v

# 多源架构测试
conda run -n crawer python -m pytest \
  tests/test_normalized_schema.py \
  tests/test_entity_resolver.py \
  tests/test_hot_score.py \
  tests/test_source_adapters.py -v

# 原有日报链路测试
conda run -n crawer python -m pytest tests/test_mvp_cli.py -v
```

## 路线图

- 增加可安全修改本地配置的 topic 管理工具
- 加入深度论文研读工作流
- 持续优化排序与评分策略

## 许可证

MIT
