# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Open-source research-intelligence skill library for academic paper tracking and reporting. Designed to run across multiple AI agent platforms (OpenClaw, Claude Code, Codex, OpenCode). Core capability: deterministic arXiv daily brief generation with Obsidian vault integration.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p output
cp config/research-topics.example.yaml config/research-topics.local.yaml
# Edit config/research-topics.local.yaml with your topics and vault path
```

## Common Commands

```bash
# Validate configuration
python3 scripts/manage_topics.py --validate
python3 scripts/manage_topics.py --list
python3 scripts/manage_topics.py --query-plan

# Full daily pipeline (recommended)
python3 scripts/run_daily_pipeline.py

# Individual steps
python3 scripts/fetch_arxiv.py
python3 scripts/fetch_huggingface.py --out output/huggingface.json
python3 scripts/generate_daily_brief.py \
  --arxiv output/arxiv.json \
  --huggingface output/huggingface.json \
  --out output/daily-brief.md

# Run tests
python3 -m pytest tests/test_mvp_cli.py
```

## Architecture

**Three-layer design:**

1. **Skill Layer** (`skills/`) — Pure Markdown agent execution contracts. `*.SKILL.md` files define what each skill does, its inputs/outputs, and how to invoke the underlying scripts. These are read by AI agents, not executed directly.

2. **Script Layer** (`scripts/`) — Deterministic Python CLIs:
   - `common.py` — Shared data models (`CandidateItem`), YAML config loading, topic matching, scoring, deduplication (SHA256)
   - `fetch_arxiv.py` — arXiv Atom feed via feedparser → `output/arxiv.json`
   - `fetch_huggingface.py` — HF `daily_papers` API → `output/huggingface.json`
   - `generate_daily_brief.py` — Merges/deduplicates/scores candidates → Markdown report
   - `run_daily_pipeline.py` — Orchestrates the full chain; suitable for cron/OpenClaw
   - `manage_topics.py` — Read-only topic inspection (no mutation)

3. **Template & Config Layer** — YAML configs + Markdown templates. `config/research-topics.local.yaml` is the runtime config (gitignored). `templates/daily-brief-template.md` is the canonical output template.

**Data flow:**
```
run_daily_pipeline.py
  ├─ fetch_arxiv.py         → output/arxiv.json
  ├─ fetch_huggingface.py   → output/huggingface.json
  └─ generate_daily_brief.py → output/daily-brief.md (or Obsidian vault)
```

**arXiv query building:** Combines `include_keywords`, `exclude_keywords`, and `arxiv_categories` per topic (up to 6 keywords each). Example: `(all:agent OR all:planning) AND cat:cs.AI ANDNOT (all:game)`.

**Output:** Chinese-language Markdown reports. When `obsidian.vault_path` is configured, writes to `<vault>/<root_dir>/01_Daily/YYYY-MM-DD-研究情报日报.md`.

## Implementation Status

- **Production-ready:** arXiv fetch, HuggingFace fetch, deduplication/scoring, daily brief generation, topic validation, Obsidian integration
- **Scaffold only (no logic):** Semantic Scholar, topic mutation, weekly/monthly reports, paper deep-dive

## Key Config

`config/research-topics.local.yaml` (gitignored, must be created from `.example.yaml`):
- `obsidian.vault_path` — Obsidian vault root
- `reporting.daily_top_n` — Number of recommendations in brief
- `sources.arxiv.lookback_days` — Days to look back
- `topics[]` — List of topics with `include_keywords`, `exclude_keywords`, `arxiv_categories`

Default output paths are resolved relative to the repo root (hardcoded in `common.py`).
