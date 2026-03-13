---
name: research-topic-manager
description: Partially implemented workflow for managing research tracking topics. Use when inspecting or validating tracked themes and arXiv query coverage; note that automated topic mutation is still not implemented.
---

# Research Topic Manager

Read-only topic-management skill with scaffolded mutation guidance. The current repo still expects manual YAML edits for topic changes.

## Current scope

- Implemented here: config shape example plus `scripts/manage_topics.py --list`, `--detail`, `--validate`, `--query-plan`, and `--print`
- Not implemented here: add/remove/update automation, history tracking, or safe config mutation helpers

## Workflow

1. Inspect the current topic set and validate the config.
2. Preview the effective arXiv query plan before fetching, especially when narrowing to one topic.
3. If a change is needed, update the YAML config manually.
4. Preserve existing fields unless the user asks to replace them.
5. Record the change in a topic-history note if the host workflow supports it.
6. Confirm the final state back to the user.

## Planned manual change types

- add topic
- remove topic
- enable or disable topic
- add or remove include keywords
- add or remove exclude keywords
- add or remove arXiv categories
- change priority
- include or exclude from weekly/monthly review
