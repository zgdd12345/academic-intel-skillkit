---
name: research-daily-brief
description: Generate the implemented arXiv-first daily academic brief. Use when tracking new papers by configured topics, ranking them by relevance and recency, and writing one Chinese Markdown daily brief. Optional extra JSON inputs can be merged if another workflow collected them.
---

# Research Daily Brief

Implemented skill backed by the repo's current MVP scripts.

## Current scope

- Implemented: arXiv collection, normalization, deduplication, scoring, and Chinese Markdown brief rendering
- Optional: merge pre-normalized JSON from other sources if another tool already produced it
- Not implemented here: non-arXiv collectors, automatic vault/index updates, weekly/monthly report generation

## Workflow

1. Read the local topic config.
2. Optionally inspect the current topic plan with `scripts/manage_topics.py --query-plan`.
3. Collect arXiv candidates with `scripts/fetch_arxiv.py`.
4. Normalize and deduplicate candidate metadata.
5. Score against enabled topics.
6. Render a Chinese brief with detailed top items, a short remaining shortlist, topic observations, and explicit data-boundary notes.
7. Write the output Markdown to the requested path.

## Outputs

Write:
- one daily brief note
- optional host-managed follow-up actions outside this repo
- paper metadata fields remain in the original language

## Resources

- Use `../../config/research-topics.example.yaml` as the config shape reference and make a local runtime copy such as `config/research-topics.local.yaml`.
- Use `../../templates/daily-brief-template.md` as the default output template.
- The canonical implemented runtime path defaults to `config/research-topics.local.yaml`, `output/arxiv.json`, and `output/daily-brief.md`.
- Use scripts in `../../scripts/` when deterministic collection or formatting is needed.
