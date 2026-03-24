# Suggested Scheduler Notes

Audience: AI-agent operators and deployment owners. This file is written for OpenClaw scheduling and similar host-level automation, not for general project onboarding.

These notes are written with OpenClaw in mind, but the same structure can be adapted to Claude Code, Codex, OpenCode, or another runner. Only the daily brief job below is backed by implemented repo scripts today.

## Implemented today

- Schedule: every day at 09:00 local time
- Command flow: `scripts/run_daily_pipeline_with_sync.sh`
- Full chain: Obsidian repo pre-pull → arXiv fetch → multi-source hotspots (Reddit, HN, GitHub, S2, OpenAlex) → LLM abstract enrichment → daily brief generation → Obsidian repo add/commit/push
- Output: one Chinese daily note in `Research_Intel/01_Daily/<YYYY-MM>/` when `config/research-topics.local.yaml` contains a valid `obsidian.vault_path` and `obsidian.root_dir`
- On Sundays, also generates a weekly report to `03_Weekly/YYYY-MM-WNN-academic-weekly.md`
- On the last day of each month, also generates a monthly report to `04_Monthly/YYYY-MM-academic-monthly.md`

With the current canonical CLI defaults, OpenClaw only needs to schedule one command:

```bash
bash scripts/run_daily_pipeline_with_sync.sh
```

What that wrapper does today:

- checks that the Obsidian git repo exists
- aborts early if the Obsidian repo already has uncommitted or untracked changes
- pulls the latest Obsidian repo state with `git pull --rebase --autostash`
- runs the academic daily pipeline
- stages resulting Obsidian changes with `git add -A`
- commits them with an automatic timestamped message
- pushes them back to origin

Recommended OpenClaw job shape:

- trigger: daily, 09:00 local time
- runner: Codex by default
- working directory: repository root
- command:

```bash
bash scripts/run_daily_pipeline_with_sync.sh
```

If you want to limit the daily run to selected topics:

```bash
bash scripts/run_daily_pipeline_with_sync.sh --topic agents --topic multimodal
```

## Additional options

Weekly and monthly reports are auto-triggered by the daily pipeline. To skip them:

```bash
conda run -n crawer python scripts/run_daily_pipeline.py --skip-periodic
```

To run weekly or monthly reports standalone:

```bash
conda run -n crawer python scripts/build_periodic_report.py --period weekly
conda run -n crawer python scripts/build_periodic_report.py --period monthly
```

## Scaffold-only ideas

- Deep dive requests: still a host-level workflow idea, not a repo-backed automation path
