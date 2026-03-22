# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Open-source research-intelligence skill library for academic paper tracking and reporting. Designed to run across multiple AI agent platforms (OpenClaw, Claude Code, Codex, OpenCode). Core capability: deterministic arXiv daily brief generation with Obsidian vault integration.

## Runtime Environment

This project runs in the **`crawer`** conda environment:

```bash
conda activate crawer
```

All commands, script executions, and test runs must use this environment.

## Setup

```bash
conda activate crawer
pip install -r requirements.txt
mkdir -p output
cp config/research-topics.example.yaml config/research-topics.local.yaml
# Edit config/research-topics.local.yaml with your topics and vault path
cp configs/sources.example.yaml configs/sources.local.yaml
# Edit configs/sources.local.yaml to enable/configure social sources
```

## Common Commands

```bash
# Validate configuration
python3 scripts/manage_topics.py --validate
python3 scripts/manage_topics.py --list
python3 scripts/manage_topics.py --query-plan

# Full daily pipeline — parallel fetch + enrich (default)
python3 scripts/run_daily_pipeline.py
# Serial mode (for debugging)
python3 scripts/run_daily_pipeline.py --no-parallel

# Multi-source pipeline — adds Reddit, HN, GitHub, S2, OpenAlex
python3 scripts/run_multi_source.py \
  --sources-config configs/sources.local.yaml \
  --out output/multi-source.json
# Output feeds into generate_daily_brief.py via --huggingface

# Enrich top-N abstracts with LLM Chinese translation
python3 scripts/enrich_summaries.py \
  --arxiv output/arxiv.json \
  --top-n 8
# Enrich only arXiv or only HF hotspots (used by parallel pipeline)
python3 scripts/enrich_summaries.py \
  --arxiv output/arxiv.json --enrich-target arxiv
python3 scripts/enrich_summaries.py \
  --arxiv output/arxiv.json --huggingface output/huggingface.json \
  --enrich-target huggingface
# Requires LLM_BASE_URL / LLM_API_KEY / LLM_MODEL env vars (or llm: block in YAML config)

# Individual steps
python3 scripts/fetch_arxiv.py
python3 scripts/fetch_huggingface.py --out output/huggingface.json
python3 scripts/generate_daily_brief.py \
  --arxiv output/arxiv.json \
  --huggingface output/huggingface.json \
  --out output/daily-brief.md

# Weekly report (past 7 days)
python3 scripts/build_periodic_report.py --period weekly
# Monthly report (current month)
python3 scripts/build_periodic_report.py --period monthly
# Dry run / skip LLM
python3 scripts/build_periodic_report.py --period weekly --dry-run
python3 scripts/build_periodic_report.py --period weekly --skip-llm

# Run tests (use crawer env)
conda run -n crawer python -m pytest tests/test_mvp_cli.py
```

## Architecture

**Four-layer design:**

1. **Skill Layer** (`skills/`) — Pure Markdown agent execution contracts. `*.SKILL.md` files define what each skill does, its inputs/outputs, and how to invoke the underlying scripts. These are read by AI agents, not executed directly.

2. **Script Layer** (`scripts/`) — Deterministic Python CLIs:
   - `common.py` — Shared data models (`CandidateItem`), YAML config loading, topic matching, scoring, deduplication (SHA256)
   - `fetch_arxiv.py` — arXiv Atom feed via feedparser → `output/arxiv.json`
   - `fetch_huggingface.py` — HF `daily_papers` API → `output/huggingface.json`
   - `generate_daily_brief.py` — Merges/deduplicates/scores candidates → Markdown report
   - `run_daily_pipeline.py` — Orchestrates arXiv + HF chain; suitable for cron/OpenClaw
   - `run_multi_source.py` — Multi-source pipeline (Reddit, HN, GitHub, S2, OpenAlex); output feeds into `generate_daily_brief.py`
   - `enrich_summaries.py` — LLM-translates top-N English abstracts → `summary_zh` via OpenAI-compatible API
   - `manage_topics.py` — Read-only topic inspection (no mutation)
   - `build_periodic_report.py` — Weekly/monthly report generator; parses daily briefs, aggregates, calls LLM for narrative
   - `parse_daily_briefs.py` — Module: parses daily brief Markdown back into structured data
   - `aggregate_period.py` — Module: cross-day deduplication, topic trends, threshold checking

3. **Library Layer** (`src/`) — Reusable Python modules backing the multi-source pipeline:
   - `src/sources/` — Source adapters (arxiv, huggingface, reddit, hackernews, github, semantic_scholar, openalex); all subclass `SourceAdapter` with built-in rate limiting, retry, and failure isolation
   - `src/normalize/` — `NormalizedItem` schema + `EntityResolver` for cross-source deduplication
   - `src/scoring/` — `hot_score` ranking function
   - `src/storage/` — `DiskCache` for adapter-level HTTP response caching
   - `src/pipelines/collect.py` — `CollectPipeline`: orchestrates adapters → entity resolution → scoring → ranked `NormalizedItem` list

4. **Template & Config Layer** — YAML configs + Markdown templates:
   - `config/research-topics.local.yaml` — runtime topic config (gitignored)
   - `configs/sources.local.yaml` — per-source enable/rate-limit/credential config (copy from `configs/sources.example.yaml`)
   - `templates/daily-brief-template.md` — canonical output template

**Data flow:**
```
run_daily_pipeline.py (arXiv + HF only)
  ├─ fetch_arxiv.py         → output/arxiv.json
  ├─ fetch_huggingface.py   → output/huggingface.json
  └─ generate_daily_brief.py → output/daily-brief.md (or Obsidian vault)

run_multi_source.py (social + academic sources)
  └─ CollectPipeline
       ├─ RedditAdapter / HNAdapter / GitHubAdapter / S2Adapter / OpenAlexAdapter
       └─ → output/multi-source.json → generate_daily_brief.py --huggingface
```

**arXiv query building:** Combines `include_keywords`, `exclude_keywords`, and `arxiv_categories` per topic (up to 6 keywords each). Example: `(all:agent OR all:planning) AND cat:cs.AI ANDNOT (all:game)`.

**Output:** Chinese-language Markdown reports. When `obsidian.vault_path` is configured, writes to `<vault>/<root_dir>/01_Daily/YYYY-MM-DD-研究情报日报.md`.

## Implementation Status

- **Production-ready:** arXiv fetch, HuggingFace fetch, Reddit/HN/GitHub/OpenAlex/Semantic Scholar adapters (`src/sources/`), multi-source pipeline (`run_multi_source.py`), LLM summary enrichment (`enrich_summaries.py`), deduplication/scoring, daily brief generation, weekly/monthly report generation (`build_periodic_report.py`), topic validation, Obsidian integration
- **Scaffold only (no logic):** topic mutation, paper deep-dive

## Key Config

`config/research-topics.local.yaml` (gitignored, must be created from `.example.yaml`):
- `obsidian.vault_path` — Obsidian vault root
- `reporting.daily_top_n` — Number of recommendations in brief
- `sources.arxiv.lookback_days` — Days to look back
- `topics[]` — List of topics with `include_keywords`, `exclude_keywords`, `arxiv_categories`
- `llm.base_url` / `llm.api_key` / `llm.model` — Optional; used by `enrich_summaries.py` (can also use env vars `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`)

`configs/sources.local.yaml` (gitignored, must be created from `configs/sources.example.yaml`):
- Per-source `enabled`, `requests_per_minute`, `max_retries`, and source-specific keys
- Sources: `huggingface`, `reddit`, `hackernews`, `github`, `semantic_scholar`, `openalex`

Default output paths are resolved relative to the repo root (hardcoded in `common.py`).
