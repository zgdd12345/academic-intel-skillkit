---
name: research-daily-brief
description: Generate a multi-source daily academic brief. Collects papers from arXiv, social hotspots from Reddit/HN/GitHub/HuggingFace, and academic metadata from Semantic Scholar/OpenAlex; enriches top-N abstracts with LLM Chinese translation; renders one Chinese Markdown daily brief into Obsidian.
---

# Research Daily Brief

Production skill backed by the repo's pipeline scripts.

## Current scope

- arXiv paper collection via Atom feed
- Multi-source hotspot collection: Reddit, Hacker News, GitHub, HuggingFace, Semantic Scholar, OpenAlex (via `src/sources/` adapters)
- Cross-source entity resolution and deduplication
- Hot-score ranking across all sources
- LLM-powered English → Chinese abstract translation (`enrich_summaries.py`)
- Chinese Markdown daily brief rendering with Obsidian vault integration

## Workflow

1. Read the local topic config (`config/research-topics.local.yaml`).
2. Optionally inspect the current topic plan with `scripts/manage_topics.py --query-plan`.
3. Collect arXiv candidates with `scripts/fetch_arxiv.py`.
4. Collect multi-source hotspots with `scripts/run_multi_source.py` (Reddit, HN, GitHub, S2, OpenAlex; requires `configs/sources.local.yaml`).
5. Enrich top-N candidates with Chinese summaries via `scripts/enrich_summaries.py` (requires LLM API config).
6. Merge, deduplicate, and score all candidates.
7. Render a Chinese brief with top paper details, community hotspots by platform, topic observations, and data-boundary notes.
8. Write the output Markdown to the requested path (or Obsidian vault).

## Single-command execution

The entire workflow is orchestrated by one command:

```bash
python3 scripts/run_daily_pipeline.py
```

Optional flags: `--skip-hotspots`, `--skip-enrich`, `--topic <name>`.

## Outputs

Write:
- one daily brief note (Chinese Markdown)
- intermediate JSON: `output/arxiv.json`, `output/multi-source.json`
- paper metadata fields remain in the original language

## Resources

- `../../config/research-topics.example.yaml` — config shape reference
- `../../configs/sources.example.yaml` — per-source enable/rate-limit config
- `../../templates/daily-brief-template.md` — output template
- Scripts in `../../scripts/` for deterministic collection and formatting
