---
name: paper-deep-dive
description: Scaffold workflow for a deep paper analysis. Use as a host-level checklist when the user asks to deeply analyze a paper, but note that this repo does not yet implement paper resolution, retrieval, or report assembly automation.
---

# Paper Deep Dive

Scaffold skill only. This repository currently ships a template and routing guidance, not a deterministic deep-dive pipeline.

## Current scope

- Implemented here: `templates/deep-dive-template.md`
- Not implemented here: paper lookup, metadata retrieval, PDF parsing, Claude/Codex orchestration, or automated report writing

## Routing

- Default academic reading path: Claude Code
- Optional code/repro path: Codex
- Final report assembly: OpenClaw

## Workflow

1. Resolve the paper identity from title, id, DOI, or URL.
2. Gather metadata and abstract.
3. Ask Claude Code for academic analysis when deep reading is requested.
4. Ask Codex for code/repro analysis only when explicitly requested or clearly useful.
5. Merge outputs into one final report.
6. Write the report into Obsidian.

## Output sections

- metadata
- academic summary
- strengths and limitations
- relation to tracked topics
- code / reproducibility notes
- recommendation

## Resources

- Use `../../templates/deep-dive-template.md`.
