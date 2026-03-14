"""Multi-dimensional hot_score for NormalizedItem.

Formula (final score is in [0, 10]):

  hot_score = 10 × Σ(weight_i × component_i)

Components (each in [0, 1]):
  freshness        w=0.30  — exponential decay; 2d→1.0, 7d→0.67, 30d→0.33
  engagement       w=0.25  — log-scaled total engagement
  discussion_depth w=0.15  — log-scaled comment count
  cross_platform   w=0.15  — bonus for appearing on multiple platforms
  impl_signal      w=0.10  — has GitHub link (+0.5) or demo page (+0.3)
  topic_match      w=0.05  — best topic score normalised to [0,1]
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from src.normalize.schema import EngagementMetrics, NormalizedItem

# ── weights ────────────────────────────────────────────────────────────────────
WEIGHTS: dict[str, float] = {
    "freshness": 0.30,
    "engagement": 0.25,
    "discussion_depth": 0.15,
    "cross_platform": 0.15,
    "impl_signal": 0.10,
    "topic_match": 0.05,
}

# Normalisation constants
_ENGAGEMENT_NORM = math.log1p(1000)   # ~log(1001) ≈ 6.9
_DEPTH_NORM = math.log1p(100)         # ~log(101)  ≈ 4.6


# ── individual components ───────────────────────────────────────────────────────
def freshness_score(published_at: str | None, now: datetime | None = None) -> float:
    """Score in [0, 1] based on age.

    Uses exponential decay with half-life of ~7 days so items lose relevance
    gradually rather than dropping off a cliff.
    """
    if not published_at:
        return 0.0
    ts = _parse_dt(published_at)
    if ts is None:
        return 0.0
    ref = now or datetime.now(timezone.utc)
    age_days = max(0.0, (ref - ts).total_seconds() / 86_400.0)
    # half-life = 7 days → decay factor = ln(2)/7
    return math.exp(-math.log(2) / 7.0 * age_days)


def engagement_score(metrics: EngagementMetrics) -> float:
    """Log-scaled total engagement, normalised to [0, 1]."""
    total = (
        (metrics.upvotes or 0)
        + (metrics.comments or 0) * 2
        + (metrics.stars or 0)
        + (metrics.forks or 0) * 2
        + (metrics.citations or 0) * 3
    )
    return min(1.0, math.log1p(max(0, total)) / _ENGAGEMENT_NORM)


def discussion_depth_score(metrics: EngagementMetrics) -> float:
    """Log-scaled comment depth, normalised to [0, 1]."""
    comments = metrics.comments or 0
    return min(1.0, math.log1p(max(0, comments)) / _DEPTH_NORM)


def cross_platform_score(source_count: int) -> float:
    """Bonus for appearing on N platforms: each additional platform adds 0.3, capped at 1.0."""
    return min(1.0, max(0, source_count - 1) * 0.3)


def impl_signal_score(item: NormalizedItem) -> float:
    """Heuristic: presence of GitHub links or demo pages signals real implementation."""
    score = 0.0
    if item.repo_urls:
        score += 0.5
    content_lower = (item.content + item.url + item.title).lower()
    if any(kw in content_lower for kw in ("demo", "project page", "try it", "colab")):
        score += 0.3
    # Extra boost for stars (indicates active repo)
    stars = item.engagement_metrics.stars or 0
    if stars > 100:
        score += 0.2
    return min(1.0, score)


def topic_match_score(item: NormalizedItem) -> float:
    """Best topic score normalised to [0, 1] (topic scores typically in [0, 8])."""
    best = max((item.topic_scores or {}).values(), default=0.0)
    return min(1.0, best / 5.0)


# ── composite scorer ────────────────────────────────────────────────────────────
def compute_hot_score(
    item: NormalizedItem,
    source_count: int = 1,
    now: datetime | None = None,
) -> float:
    """Return hot_score in [0, 10] for a single NormalizedItem.

    Args:
        item:         The item to score.
        source_count: Number of distinct platforms this item appears on (for
                      cross-platform bonus).  Defaults to 1 (no bonus).
        now:          Reference datetime for freshness; defaults to UTC now.
    """
    components = {
        "freshness": freshness_score(item.published_at, now),
        "engagement": engagement_score(item.engagement_metrics),
        "discussion_depth": discussion_depth_score(item.engagement_metrics),
        "cross_platform": cross_platform_score(source_count),
        "impl_signal": impl_signal_score(item),
        "topic_match": topic_match_score(item),
    }
    raw = sum(WEIGHTS[k] * v for k, v in components.items())
    return round(raw * 10.0, 3)


def score_items(
    items: list[NormalizedItem],
    topics: list[dict[str, Any]],
    now: datetime | None = None,
) -> list[NormalizedItem]:
    """Score and sort a list of NormalizedItems.

    Fills `topic_scores`, `matched_topics`, and `score` on each item in-place,
    then returns them sorted by score descending.
    """
    # Import topic matching from the legacy common module
    import sys
    from pathlib import Path

    _scripts = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)
    from common import match_topics, merge_topic_scores, CandidateItem  # noqa: PLC0415

    scored: list[NormalizedItem] = []
    for item in items:
        # Reuse existing keyword-match logic via a throwaway CandidateItem
        proxy = CandidateItem(
            source=item.source,
            title=item.title,
            url=item.url,
            summary=item.content,
            categories=item.raw_tags or None,
        )
        discovered = match_topics(proxy, topics)
        item.topic_scores = merge_topic_scores(item.topic_scores, discovered) or None
        item.matched_topics = list(item.topic_scores) if item.topic_scores else None
        item.score = compute_hot_score(item, now=now)
        scored.append(item)

    return sorted(scored, key=lambda i: -i.score)


# ── internal ────────────────────────────────────────────────────────────────────
def _parse_dt(value: str) -> datetime | None:
    """Parse ISO 8601 string to UTC datetime."""
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None
