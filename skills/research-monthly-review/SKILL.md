---
name: research-monthly-review
description: Generate a monthly academic review by aggregating all daily briefs in the target month, deduplicating papers, analyzing topic trends, and producing a Chinese Markdown report with LLM-powered narrative sections.
---

# Research Monthly Review

Production skill backed by `scripts/build_periodic_report.py`.

## Current scope

- Parse daily brief Markdown files from Obsidian vault (`01_Daily/`)
- Full-month paper deduplication and re-ranking (top 30)
- Topic trend analysis across the month
- Community hotspot aggregation across platforms
- LLM-generated Chinese overview and next-month recommendations
- Threshold checking (configurable minimum daily briefs)
- Output to `04_Monthly/YYYY-MM-academic-monthly.md` in Obsidian vault

## Workflow

1. Compute the date range for the target month.
2. Find and parse all daily briefs in the range from the Obsidian vault.
3. Check thresholds from `config/report-thresholds.example.yaml`.
4. Aggregate: deduplicate papers, compute topic counts and trends, merge hotspots.
5. Call LLM to generate overview and next-month recommendations (skippable with `--skip-llm`).
6. Render the monthly template and write to Obsidian.

## Single-command execution

```bash
python3 scripts/build_periodic_report.py --period monthly
python3 scripts/build_periodic_report.py --period monthly --date 2026-03-31
python3 scripts/build_periodic_report.py --period monthly --skip-llm
python3 scripts/build_periodic_report.py --period monthly --dry-run
```

## Resources

- `../../templates/monthly-template.md` — output template
- `../../config/report-thresholds.example.yaml` — threshold configuration
- `../../scripts/parse_daily_briefs.py` — daily brief parser module
- `../../scripts/aggregate_period.py` — aggregation logic module
