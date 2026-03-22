"""aggregate_period.py — Aggregate parsed daily briefs into period-level summaries.

This module is imported by build_periodic_report.py, not run as a CLI.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from parse_daily_briefs import DailyBriefData, ParsedHotspot, ParsedPaper


@dataclass
class PeriodAggregate:
    period_type: str  # "weekly" or "monthly"
    period_id: str  # "2026-W12" or "2026-03"
    start_date: str
    end_date: str
    daily_briefs_found: int = 0
    total_candidates: int = 0
    total_high_signal: int = 0
    top_papers: list[ParsedPaper] = field(default_factory=list)
    topic_counts: dict[str, int] = field(default_factory=dict)
    topic_trend: dict[str, list[int]] = field(default_factory=dict)
    hotspot_highlights: list[ParsedHotspot] = field(default_factory=list)
    daily_overviews: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Date range helpers
# ---------------------------------------------------------------------------

def compute_period_id(target: date, period_type: str) -> str:
    if period_type == "weekly":
        iso = target.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    return target.strftime("%Y-%m")


def compute_date_range(target: date, period_type: str) -> tuple[date, date]:
    if period_type == "weekly":
        end = target
        start = end - timedelta(days=6)
        return start, end
    # Monthly: first to last day of the month
    start = target.replace(day=1)
    if target.month == 12:
        end = target.replace(year=target.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = target.replace(month=target.month + 1, day=1) - timedelta(days=1)
    return start, end


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _normalize_id(paper_id: str) -> str:
    """Strip version suffix: 2603.18718v1 -> 2603.18718."""
    return re.sub(r"v\d+$", "", paper_id.strip()) if paper_id else ""


def _dedup_key(paper: ParsedPaper) -> str:
    """Return a key for deduplication: prefer paper_id, then url."""
    nid = _normalize_id(paper.paper_id)
    if nid:
        return f"id:{nid}"
    if paper.url:
        return f"url:{paper.url}"
    return f"title:{paper.title.lower().strip()}"


def _dedup_papers(papers: list[ParsedPaper]) -> list[ParsedPaper]:
    """Deduplicate papers, keeping the entry with the highest score."""
    seen: dict[str, ParsedPaper] = {}
    for p in papers:
        key = _dedup_key(p)
        if key not in seen or p.score > seen[key].score:
            seen[key] = p
    return list(seen.values())


def _dedup_hotspots(items: list[ParsedHotspot]) -> list[ParsedHotspot]:
    """Deduplicate hotspots by URL, preferring richer summary."""
    seen: dict[str, ParsedHotspot] = {}
    for h in items:
        if h.url not in seen or (len(h.summary_zh) > len(seen[h.url].summary_zh)):
            seen[h.url] = h
    return list(seen.values())


# ---------------------------------------------------------------------------
# Core aggregation
# ---------------------------------------------------------------------------

def aggregate_briefs(
    briefs: list[DailyBriefData],
    period_type: str,
    period_id: str,
    start_date: date,
    end_date: date,
    top_n: int = 15,
) -> PeriodAggregate:
    """Aggregate multiple daily briefs into a period summary."""
    agg = PeriodAggregate(
        period_type=period_type,
        period_id=period_id,
        start_date=str(start_date),
        end_date=str(end_date),
        daily_briefs_found=len(briefs),
    )

    all_papers: list[ParsedPaper] = []
    all_hotspots: list[ParsedHotspot] = []
    topic_day_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for brief in briefs:
        agg.total_candidates += brief.candidates
        agg.total_high_signal += brief.high_signal
        if brief.overview:
            agg.daily_overviews.append(f"[{brief.date}] {brief.overview}")
        all_papers.extend(brief.papers)
        all_hotspots.extend(brief.hotspot_items)

        # Track topic counts per day
        for paper in brief.papers:
            for topic in paper.topics:
                topic_day_counts[topic][brief.date] += 1

    # Deduplicate and rank papers
    deduped = _dedup_papers(all_papers)
    deduped.sort(key=lambda p: p.score, reverse=True)
    if period_type == "monthly":
        top_n = max(top_n, 30)
    agg.top_papers = deduped[:top_n]

    # Topic counts
    for topic, day_map in topic_day_counts.items():
        agg.topic_counts[topic] = sum(day_map.values())

    # Topic trend: count per day across the range
    date_list = []
    d = start_date
    while d <= end_date:
        date_list.append(str(d))
        d += timedelta(days=1)
    for topic, day_map in topic_day_counts.items():
        agg.topic_trend[topic] = [day_map.get(ds, 0) for ds in date_list]

    # Deduplicate hotspots
    agg.hotspot_highlights = _dedup_hotspots(all_hotspots)

    return agg


# ---------------------------------------------------------------------------
# Threshold check
# ---------------------------------------------------------------------------

def check_thresholds(
    aggregate: PeriodAggregate,
    thresholds: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Check if the aggregate meets configured thresholds.

    Returns (passes, reasons).
    """
    period_key = "weekly" if aggregate.period_type == "weekly" else "monthly"
    cfg = thresholds.get(period_key, {})
    if not isinstance(cfg, dict):
        return True, []

    reasons: list[str] = []
    min_briefs = cfg.get("min_daily_briefs", 0)
    if aggregate.daily_briefs_found < min_briefs:
        reasons.append(
            f"日报数量不足：找到 {aggregate.daily_briefs_found} 份，"
            f"要求至少 {min_briefs} 份"
        )

    min_signal = cfg.get("min_high_signal_items", 0)
    if aggregate.total_high_signal < min_signal:
        reasons.append(
            f"高信号论文不足：共 {aggregate.total_high_signal} 篇，"
            f"要求至少 {min_signal} 篇"
        )

    return len(reasons) == 0, reasons
