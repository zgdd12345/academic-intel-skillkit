"""Unified normalized schema for all source adapters.

Every source adapter outputs NormalizedItem objects.  The pipeline layer converts
these to the legacy CandidateItem when feeding the existing brief generator.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── constants ──────────────────────────────────────────────────────────────────
SOURCE_TYPE_PAPER = "paper"
SOURCE_TYPE_DISCUSSION = "discussion"
SOURCE_TYPE_REPO = "repo"
SOURCE_TYPE_MODEL = "model"
SOURCE_TYPE_TOPIC = "topic"


# ── engagement metrics ─────────────────────────────────────────────────────────
@dataclass
class EngagementMetrics:
    upvotes: int | None = None
    downvotes: int | None = None
    comments: int | None = None
    stars: int | None = None
    forks: int | None = None
    views: int | None = None
    citations: int | None = None
    shares: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EngagementMetrics:
        if not isinstance(data, dict):
            return cls()
        return cls(
            upvotes=_coerce_int(data.get("upvotes")),
            downvotes=_coerce_int(data.get("downvotes")),
            comments=_coerce_int(data.get("comments")),
            stars=_coerce_int(data.get("stars")),
            forks=_coerce_int(data.get("forks")),
            views=_coerce_int(data.get("views")),
            citations=_coerce_int(data.get("citations")),
            shares=_coerce_int(data.get("shares")),
        )

    @property
    def total_engagement(self) -> int:
        """Weighted sum for scoring purposes."""
        return (
            (self.upvotes or 0)
            + (self.comments or 0) * 2
            + (self.stars or 0)
            + (self.forks or 0) * 2
            + (self.citations or 0) * 3
        )


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ── normalized item ────────────────────────────────────────────────────────────
@dataclass
class NormalizedItem:
    """Unified output schema shared by all source adapters.

    Fields follow the spec in the project requirements:
        source, source_type, external_id, url, title, content, author,
        published_at, fetched_at, engagement_metrics, raw_tags, language,
        raw_payload (+ derived scoring / entity fields)
    """

    # Core identity
    source: str                             # adapter name: "arxiv", "reddit", …
    source_type: str                        # SOURCE_TYPE_* constant
    external_id: str                        # unique ID within the source
    url: str                                # canonical URL
    title: str
    content: str                            # body / abstract
    author: str                             # primary author or username
    published_at: str | None                # ISO 8601
    fetched_at: str                         # ISO 8601, set by adapter

    # Enrichment containers
    engagement_metrics: EngagementMetrics = field(default_factory=EngagementMetrics)
    raw_tags: list[str] = field(default_factory=list)
    language: str = "en"
    raw_payload: dict[str, Any] = field(default_factory=dict)

    # Scoring / topic matching (filled by scoring layer)
    topic_scores: dict[str, float] | None = None
    matched_topics: list[str] | None = None
    score: float = 0.0
    summary_zh: str = ""

    # Entity links extracted by entity resolver
    paper_ids: list[str] = field(default_factory=list)   # arXiv IDs
    repo_urls: list[str] = field(default_factory=list)    # GitHub repo URLs
    model_ids: list[str] = field(default_factory=list)    # HuggingFace model IDs

    # ── serialisation ──────────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_type": self.source_type,
            "external_id": self.external_id,
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "author": self.author,
            "published_at": self.published_at,
            "fetched_at": self.fetched_at,
            "engagement_metrics": self.engagement_metrics.to_dict(),
            "raw_tags": self.raw_tags,
            "language": self.language,
            "topic_scores": self.topic_scores,
            "matched_topics": self.matched_topics,
            "score": self.score,
            "summary_zh": self.summary_zh,
            "paper_ids": self.paper_ids,
            "repo_urls": self.repo_urls,
            "model_ids": self.model_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedItem:
        return cls(
            source=str(data.get("source", "unknown")),
            source_type=str(data.get("source_type", SOURCE_TYPE_PAPER)),
            external_id=str(data.get("external_id", "")),
            url=str(data.get("url", "")),
            title=str(data.get("title", "")),
            content=str(data.get("content", "")),
            author=str(data.get("author", "")),
            published_at=data.get("published_at"),
            fetched_at=str(data.get("fetched_at", "")),
            engagement_metrics=EngagementMetrics.from_dict(
                data.get("engagement_metrics") or {}
            ),
            raw_tags=list(data.get("raw_tags") or []),
            language=str(data.get("language", "en")),
            raw_payload=dict(data.get("raw_payload") or {}),
            topic_scores=data.get("topic_scores"),
            matched_topics=data.get("matched_topics"),
            score=float(data.get("score", 0.0)),
            summary_zh=str(data.get("summary_zh", "")),
            paper_ids=list(data.get("paper_ids") or []),
            repo_urls=list(data.get("repo_urls") or []),
            model_ids=list(data.get("model_ids") or []),
        )

    # ── backward-compat bridge ─────────────────────────────────────────────────
    def to_candidate_item(self) -> Any:
        """Convert to legacy CandidateItem for the existing brief generator."""
        _scripts = str(Path(__file__).resolve().parents[2] / "scripts")
        if _scripts not in sys.path:
            sys.path.insert(0, _scripts)
        from common import CandidateItem  # noqa: PLC0415

        return CandidateItem(
            source=self.source,
            title=self.title,
            url=self.url,
            summary=self.content,
            summary_zh=self.summary_zh,
            authors=[self.author] if self.author else None,
            published_at=self.published_at,
            topic_scores=self.topic_scores,
            score=self.score,
            matched_topics=self.matched_topics,
            categories=self.raw_tags or None,
        )
