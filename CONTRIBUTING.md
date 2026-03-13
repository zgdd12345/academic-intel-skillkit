# Contributing

Issues and pull requests are welcome.

## Documentation audience contract

Keep the repo documentation split explicit:

- human-facing docs:
  - `README.md`
  - `CONTRIBUTING.md`
  - `examples/obsidian-layout.md`
  - `NEXT_PHASE_PLAN.md`
- agent/deployment-facing docs:
  - `skills/*.SKILL.md`
  - `scripts/*.py`
  - `config/research-topics.local.yaml`
  - `templates/*.md`
  - `examples/openclaw-cron-notes.md`

When adding or editing docs, preserve that distinction instead of mixing onboarding prose with agent execution instructions.

## Current repo contract

- keep `README.md` aligned with the implemented arXiv-only daily brief MVP
- treat `config/research-topics.example.yaml` and `templates/daily-brief-template.md` as the canonical first-run path
- if a script, skill, template, or config file is scaffold-only, label it directly instead of implying automation exists
- prefer host-agnostic docs that work with OpenClaw, Claude Code, Codex, OpenCode, and similar setups

## Suggested contribution areas

- new source adapters
- scoring improvements
- topic clustering and trend detection
- Obsidian output polish
- OpenClaw cron examples
- Claude Code / Codex prompt routing improvements

## Basic standards

- keep skill frontmatter concise and accurate
- prefer small, composable scripts
- keep templates portable
- avoid hard-coding personal paths or secrets
