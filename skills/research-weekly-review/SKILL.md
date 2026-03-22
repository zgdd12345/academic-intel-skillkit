---
name: research-weekly-review
description: Generate a weekly academic review by aggregating the past 7 days of daily briefs, deduplicating papers, analyzing topic trends, and producing a Chinese Markdown report with LLM-powered narrative sections.
---

# Research Weekly Review

Production skill backed by `scripts/build_periodic_report.py`.

## Current scope

- Parse daily brief Markdown files from Obsidian vault (`01_Daily/<YYYY-MM>/`)
- Cross-day paper deduplication and re-ranking by score
- Topic distribution analysis with daily trend visualization
- Community hotspot aggregation across platforms
- LLM-generated Chinese overview and next-week watchlist
- Threshold checking (configurable minimum daily briefs)
- Output to `03_Weekly/YYYY-MM-WNN-academic-weekly.md` in Obsidian vault (e.g. `2026-03-W13`)
- Automatically triggered by `run_daily_pipeline.py` on Sundays (can also run standalone)

## Workflow

1. Compute the 7-day date range ending on the target date.
2. Find and parse all daily briefs in the range from the Obsidian vault.
3. Check thresholds from `config/report-thresholds.example.yaml`.
4. Aggregate: deduplicate papers, compute topic counts and trends, merge hotspots.
5. Call LLM to generate overview and watchlist paragraphs (skippable with `--skip-llm`).
6. Render the weekly template and write to Obsidian.

## Single-command execution

```bash
python3 scripts/build_periodic_report.py --period weekly
python3 scripts/build_periodic_report.py --period weekly --date 2026-03-22
python3 scripts/build_periodic_report.py --period weekly --skip-llm
python3 scripts/build_periodic_report.py --period weekly --dry-run
```

## Resources

- `../../templates/weekly-template.md` — output template
- `../../config/report-thresholds.example.yaml` — threshold configuration
- `../../scripts/parse_daily_briefs.py` — daily brief parser module
- `../../scripts/aggregate_period.py` — aggregation logic module
