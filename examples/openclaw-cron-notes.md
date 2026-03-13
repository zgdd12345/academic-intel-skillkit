# Suggested Scheduler Notes

Audience: AI-agent operators and deployment owners. This file is written for OpenClaw scheduling and similar host-level automation, not for general project onboarding.

These notes are written with OpenClaw in mind, but the same structure can be adapted to Claude Code, Codex, OpenCode, or another runner. Only the daily brief job below is backed by implemented repo scripts today.

## Implemented today

- Schedule: every day at 09:00 local time
- Command flow: `scripts/run_daily_pipeline.py`
- Output: one Chinese daily note in `Research_Intel/01_Daily/` when `config/research-topics.local.yaml` contains a valid `obsidian.vault_path` and `obsidian.root_dir`

With the current canonical CLI defaults, OpenClaw only needs to schedule one command:

```bash
python3 scripts/run_daily_pipeline.py
```

What that wrapper does today:

- fetches arXiv candidates
- optionally fetches Hugging Face Papers hotspots
- generates the daily brief
- writes the final note into Obsidian if the config includes a valid vault path

Recommended OpenClaw job shape:

- trigger: daily, 09:00 local time
- runner: Codex by default
- working directory: repository root
- command:

```bash
conda run -n news python scripts/run_daily_pipeline.py
```

If you want to limit the daily run to selected topics:

```bash
conda run -n news python scripts/run_daily_pipeline.py --topic agents --topic multimodal
```

## Scaffold-only ideas

- Weekly review: reasonable future cadence is Sunday 20:00 local time, but generation is not implemented in this repo yet
- Monthly review: reasonable future cadence is the first day of month at 09:30 local time, but generation is not implemented in this repo yet
- Deep dive requests: still a host-level workflow idea, not a repo-backed automation path
