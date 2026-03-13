<!-- Canonical template for the current arXiv-only daily brief MVP.
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

## 优先阅读

{{top_detailed}}

---

## 快速扫描

{{top_brief}}

---

## 主题分布

{{topic_snapshot}}

---

## 社区热点

{{hotspots}}

---

## 建议动作

{{suggested_actions}}

---

> [!note]- 数据说明
{{source_notes}}
