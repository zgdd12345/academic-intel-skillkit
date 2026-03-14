<!-- Canonical template for the daily brief.
Used by scripts/generate_daily_brief.py by default.
Optimized for Obsidian rendering with YAML frontmatter and callout blocks. -->
---
date: {{date}}
tags:
  - research-intel
  - daily-brief
candidates: {{candidate_count}}
high_signal: {{high_signal_count}}
hotspots: {{hotspot_count}}
recommended: {{recommended_count}}
---

# 研究情报日报 · {{date}}

> [!abstract] 今日概览
> {{overview}}

---

## 最新工作

{{latest_work}}

---

## 社区热点

{{hotspots}}

---

## 建议关注的热点

{{hotspot_analysis}}

---

> [!note]- 数据说明
{{source_notes}}
