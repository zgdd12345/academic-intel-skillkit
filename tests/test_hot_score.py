"""Tests for hot_score computation."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from src.normalize.schema import EngagementMetrics, NormalizedItem, SOURCE_TYPE_PAPER
from src.scoring.hot_score import (
    compute_hot_score,
    cross_platform_score,
    discussion_depth_score,
    engagement_score,
    freshness_score,
    impl_signal_score,
)


_NOW = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _make_item(**kwargs) -> NormalizedItem:
    defaults = dict(
        source="arxiv",
        source_type=SOURCE_TYPE_PAPER,
        external_id="2403.00001",
        url="https://arxiv.org/abs/2403.00001",
        title="Test",
        content="",
        author="Alice",
        published_at=_iso(_NOW - timedelta(days=1)),
        fetched_at=_iso(_NOW),
    )
    defaults.update(kwargs)
    return NormalizedItem(**defaults)


class TestFreshnessScore(unittest.TestCase):
    def test_very_fresh_near_1(self) -> None:
        s = freshness_score(_iso(_NOW - timedelta(hours=6)), now=_NOW)
        self.assertGreater(s, 0.9)

    def test_week_old_around_half(self) -> None:
        s = freshness_score(_iso(_NOW - timedelta(days=7)), now=_NOW)
        self.assertAlmostEqual(s, 0.5, delta=0.05)

    def test_month_old_low(self) -> None:
        s = freshness_score(_iso(_NOW - timedelta(days=30)), now=_NOW)
        self.assertLess(s, 0.1)

    def test_missing_published_at_returns_zero(self) -> None:
        self.assertEqual(freshness_score(None, now=_NOW), 0.0)

    def test_invalid_date_returns_zero(self) -> None:
        self.assertEqual(freshness_score("not-a-date", now=_NOW), 0.0)


class TestEngagementScore(unittest.TestCase):
    def test_zero_engagement(self) -> None:
        self.assertEqual(engagement_score(EngagementMetrics()), 0.0)

    def test_high_engagement_below_1(self) -> None:
        s = engagement_score(EngagementMetrics(upvotes=500, comments=100, stars=200))
        self.assertLessEqual(s, 1.0)
        self.assertGreater(s, 0.8)

    def test_moderate_engagement_in_range(self) -> None:
        s = engagement_score(EngagementMetrics(upvotes=50, comments=10))
        self.assertGreater(s, 0.0)
        self.assertLess(s, 1.0)


class TestDiscussionDepthScore(unittest.TestCase):
    def test_no_comments_returns_zero(self) -> None:
        self.assertEqual(discussion_depth_score(EngagementMetrics()), 0.0)

    def test_100_comments_near_1(self) -> None:
        s = discussion_depth_score(EngagementMetrics(comments=100))
        self.assertAlmostEqual(s, 1.0, delta=0.05)

    def test_monotone_with_more_comments(self) -> None:
        s1 = discussion_depth_score(EngagementMetrics(comments=5))
        s2 = discussion_depth_score(EngagementMetrics(comments=50))
        self.assertLess(s1, s2)


class TestCrossPlatformScore(unittest.TestCase):
    def test_single_source_no_bonus(self) -> None:
        self.assertEqual(cross_platform_score(1), 0.0)

    def test_two_sources_gives_bonus(self) -> None:
        self.assertAlmostEqual(cross_platform_score(2), 0.3)

    def test_capped_at_1(self) -> None:
        self.assertEqual(cross_platform_score(10), 1.0)


class TestImplSignalScore(unittest.TestCase):
    def test_no_repo_no_signal(self) -> None:
        item = _make_item()
        self.assertEqual(impl_signal_score(item), 0.0)

    def test_with_github_repo_has_signal(self) -> None:
        item = _make_item(repo_urls=["https://github.com/user/repo"])
        self.assertGreater(impl_signal_score(item), 0.0)

    def test_demo_mention_adds_bonus(self) -> None:
        item = _make_item(content="See our demo at example.com")
        self.assertGreater(impl_signal_score(item), 0.0)


class TestComputeHotScore(unittest.TestCase):
    def test_score_in_range(self) -> None:
        item = _make_item(
            engagement_metrics=EngagementMetrics(upvotes=50, comments=10),
            topic_scores={"agents": 3.0},
        )
        score = compute_hot_score(item, now=_NOW)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 10.0)

    def test_fresh_high_engagement_scores_higher(self) -> None:
        fresh = _make_item(
            published_at=_iso(_NOW - timedelta(hours=6)),
            engagement_metrics=EngagementMetrics(upvotes=200, comments=50),
        )
        stale = _make_item(
            published_at=_iso(_NOW - timedelta(days=60)),
            engagement_metrics=EngagementMetrics(upvotes=5, comments=1),
        )
        self.assertGreater(
            compute_hot_score(fresh, now=_NOW),
            compute_hot_score(stale, now=_NOW),
        )

    def test_cross_platform_bonus_raises_score(self) -> None:
        item = _make_item()
        score_single = compute_hot_score(item, source_count=1, now=_NOW)
        score_multi = compute_hot_score(item, source_count=3, now=_NOW)
        self.assertGreater(score_multi, score_single)

    def test_score_is_deterministic(self) -> None:
        item = _make_item(
            engagement_metrics=EngagementMetrics(upvotes=42, comments=7),
        )
        s1 = compute_hot_score(item, now=_NOW)
        s2 = compute_hot_score(item, now=_NOW)
        self.assertEqual(s1, s2)
