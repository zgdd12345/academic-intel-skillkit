"""Tests for NormalizedItem schema and EngagementMetrics."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from src.normalize.schema import (
    EngagementMetrics,
    NormalizedItem,
    SOURCE_TYPE_DISCUSSION,
    SOURCE_TYPE_PAPER,
)


class TestEngagementMetrics(unittest.TestCase):
    def test_to_dict_excludes_none_fields(self) -> None:
        em = EngagementMetrics(upvotes=42, comments=5)
        d = em.to_dict()
        self.assertEqual(d["upvotes"], 42)
        self.assertEqual(d["comments"], 5)
        self.assertNotIn("stars", d)
        self.assertNotIn("forks", d)

    def test_from_dict_round_trip(self) -> None:
        em = EngagementMetrics(upvotes=10, comments=3, stars=100, citations=7)
        em2 = EngagementMetrics.from_dict(em.to_dict())
        self.assertEqual(em2.upvotes, 10)
        self.assertEqual(em2.stars, 100)
        self.assertEqual(em2.citations, 7)

    def test_total_engagement_weighted_sum(self) -> None:
        em = EngagementMetrics(upvotes=10, comments=5, stars=2, forks=1, citations=3)
        # 10 + 5*2 + 2 + 1*2 + 3*3 = 10 + 10 + 2 + 2 + 9 = 33
        self.assertEqual(em.total_engagement, 33)

    def test_from_dict_handles_non_dict(self) -> None:
        em = EngagementMetrics.from_dict(None)  # type: ignore[arg-type]
        self.assertIsNone(em.upvotes)


class TestNormalizedItem(unittest.TestCase):
    def _make_item(self, **kwargs) -> NormalizedItem:
        defaults = dict(
            source="arxiv",
            source_type=SOURCE_TYPE_PAPER,
            external_id="2403.00001",
            url="https://arxiv.org/abs/2403.00001",
            title="Test Paper",
            content="Abstract text.",
            author="Alice",
            published_at="2024-03-01T00:00:00+00:00",
            fetched_at="2024-03-02T00:00:00+00:00",
        )
        defaults.update(kwargs)
        return NormalizedItem(**defaults)

    def test_to_dict_contains_required_fields(self) -> None:
        item = self._make_item()
        d = item.to_dict()
        for field in (
            "source", "source_type", "external_id", "url", "title",
            "content", "author", "published_at", "fetched_at",
            "engagement_metrics", "raw_tags", "language", "paper_ids",
        ):
            self.assertIn(field, d, f"Missing field: {field}")

    def test_from_dict_round_trip(self) -> None:
        item = self._make_item(
            topic_scores={"agents": 2.5},
            matched_topics=["agents"],
            score=7.3,
            paper_ids=["2403.00001"],
            repo_urls=["https://github.com/user/repo"],
        )
        d = item.to_dict()
        item2 = NormalizedItem.from_dict(d)
        self.assertEqual(item2.source, "arxiv")
        self.assertEqual(item2.topic_scores, {"agents": 2.5})
        self.assertEqual(item2.paper_ids, ["2403.00001"])
        self.assertEqual(item2.repo_urls, ["https://github.com/user/repo"])

    def test_to_candidate_item_backward_compat(self) -> None:
        item = self._make_item(
            content="Abstract text.",
            summary_zh="摘要文本",
            topic_scores={"agents": 3.0},
            score=6.5,
            matched_topics=["agents"],
        )
        ci = item.to_candidate_item()
        self.assertEqual(ci.source, "arxiv")
        self.assertEqual(ci.title, "Test Paper")
        self.assertEqual(ci.summary, "Abstract text.")
        self.assertEqual(ci.summary_zh, "摘要文本")
        self.assertAlmostEqual(ci.score, 6.5)

    def test_from_dict_tolerates_missing_optional_fields(self) -> None:
        minimal = {
            "source": "reddit",
            "source_type": SOURCE_TYPE_DISCUSSION,
            "external_id": "abc123",
            "url": "https://reddit.com/r/ML/abc",
            "title": "Cool paper",
            "content": "",
            "author": "u/user",
            "published_at": None,
            "fetched_at": "2024-03-01T00:00:00+00:00",
        }
        item = NormalizedItem.from_dict(minimal)
        self.assertEqual(item.source, "reddit")
        self.assertEqual(item.paper_ids, [])
        self.assertEqual(item.language, "en")
