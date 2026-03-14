"""Tests for source adapters (unit tests with mocks — no network calls)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from src.normalize.schema import SOURCE_TYPE_DISCUSSION, SOURCE_TYPE_PAPER


# ── helper ─────────────────────────────────────────────────────────────────────
def _mock_response(json_data, status_code: int = 200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status.return_value = None
    return mock


# ── arXiv adapter ─────────────────────────────────────────────────────────────
class TestArxivAdapter(unittest.TestCase):
    def test_fetch_returns_normalized_items(self) -> None:
        from src.sources.arxiv import ArxivAdapter

        fake_entry = SimpleNamespace(
            id="https://arxiv.org/abs/2403.00001",
            title="Tool-Using Multi-Agent Planning",
            link="https://arxiv.org/abs/2403.00001",
            summary="A planning paper about multi-agent tool use.",
            published="2024-03-01T00:00:00Z",
            authors=[SimpleNamespace(name="Alice Zhang")],
            tags=[{"term": "cs.AI"}, {"term": "cs.LG"}],
        )
        fake_feed = SimpleNamespace(
            status=200,
            bozo=False,
            entries=[fake_entry],
        )

        topics = [
            {
                "id": "agents",
                "name": "AI Agents",
                "enabled": True,
                "priority": "high",
                "include_keywords": ["agent", "multi-agent"],
                "exclude_keywords": [],
                "arxiv_categories": ["cs.AI"],
            }
        ]

        with patch("src.sources.arxiv._feedparser.parse", return_value=fake_feed):
            adapter = ArxivAdapter({"max_results_per_topic": 10})
            items = adapter.fetch(topics)

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.source, "arxiv")
        self.assertEqual(item.source_type, SOURCE_TYPE_PAPER)
        self.assertEqual(item.title, "Tool-Using Multi-Agent Planning")
        self.assertIn("cs.AI", item.raw_tags)
        self.assertIn("2403.00001", item.paper_ids)

    def test_fetch_returns_empty_on_feed_error(self) -> None:
        from src.sources.arxiv import ArxivAdapter

        broken_feed = SimpleNamespace(
            status=503,
            bozo=False,
            entries=[],
        )
        topics = [
            {
                "id": "agents",
                "name": "AI Agents",
                "enabled": True,
                "include_keywords": ["agent"],
                "exclude_keywords": [],
                "arxiv_categories": ["cs.AI"],
            }
        ]
        with patch("src.sources.arxiv._feedparser.parse", return_value=broken_feed):
            adapter = ArxivAdapter()
            items = adapter.fetch(topics)
        # fetch() isolates errors → returns []
        self.assertEqual(items, [])


# ── HuggingFace adapter ────────────────────────────────────────────────────────
class TestHuggingFaceAdapter(unittest.TestCase):
    def _make_raw_hf_item(
        self,
        paper_id: str,
        title: str,
        upvotes: int = 10,
        keywords: list | None = None,
        summary: str = "A great paper about AI agents.",
    ) -> dict:
        return {
            "upvotes": upvotes,
            "numComments": 3,
            "paper": {
                "id": paper_id,
                "title": title,
                "summary": summary,
                "submittedOnDailyAt": "2024-03-01T09:00:00.000Z",
                "authors": [{"name": "Alice"}, {"name": "Bob"}],
                "aiKeywords": keywords if keywords is not None else ["agent", "planning"],
                "githubRepo": "user/awesome-repo",
                "githubRepoStars": 150,
            },
            "submittedBy": {"fullname": "OpenClaw"},
        }

    def test_fetch_filters_by_topics(self) -> None:
        from src.sources.huggingface import HuggingFaceAdapter

        raw = [
            self._make_raw_hf_item("2403.00001", "Agent Planning Framework", upvotes=42,
                                   keywords=["agent", "planning"]),
            self._make_raw_hf_item(
                "2403.00002", "Quantum Chemistry Benchmarks", upvotes=5,
                keywords=["chemistry", "benchmark"],
                summary="A new benchmark for quantum chemistry simulations.",
            ),
        ]
        topics = [
            {
                "id": "agents",
                "name": "AI Agents",
                "enabled": True,
                "priority": "high",
                "include_keywords": ["agent", "planning"],
                "exclude_keywords": [],
                "arxiv_categories": ["cs.AI"],
            }
        ]

        with patch.object(
            HuggingFaceAdapter, "_http_get", return_value=_mock_response(raw)
        ):
            adapter = HuggingFaceAdapter()
            items = adapter.fetch(topics)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].external_id, "2403.00001")
        self.assertEqual(items[0].engagement_metrics.upvotes, 42)
        self.assertIn("https://github.com/user/awesome-repo", items[0].repo_urls)

    def test_fetch_returns_all_when_no_topics(self) -> None:
        from src.sources.huggingface import HuggingFaceAdapter

        raw = [
            self._make_raw_hf_item("2403.00001", "Paper A"),
            self._make_raw_hf_item("2403.00002", "Paper B"),
        ]
        with patch.object(
            HuggingFaceAdapter, "_http_get", return_value=_mock_response(raw)
        ):
            adapter = HuggingFaceAdapter()
            items = adapter.fetch([])  # no topic filter
        self.assertEqual(len(items), 2)


# ── Reddit adapter ─────────────────────────────────────────────────────────────
class TestRedditAdapter(unittest.TestCase):
    def _make_raw_reddit(self, post_id: str, title: str, score: int = 50, url: str = "") -> dict:
        return {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": post_id,
                            "title": title,
                            "selftext": f"See {url} for details." if url else "",
                            "url": url or f"https://www.reddit.com/r/ML/{post_id}",
                            "score": score,
                            "num_comments": 12,
                            "author": "u_researcher",
                            "created_utc": 1709280000.0,
                            "subreddit": "MachineLearning",
                            "link_flair_text": "Research",
                        }
                    }
                ]
            }
        }

    def test_fetch_extracts_arxiv_ids(self) -> None:
        from src.sources.reddit import RedditAdapter

        arxiv_url = "https://arxiv.org/abs/2403.55555"
        raw = self._make_raw_reddit("post1", "Cool new paper", score=100, url=arxiv_url)

        with patch.object(RedditAdapter, "_http_get", return_value=_mock_response(raw)):
            adapter = RedditAdapter({"subreddits": ["MachineLearning"], "min_upvotes": 5})
            items = adapter.fetch([])

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source, "reddit")
        self.assertIn("2403.55555", items[0].paper_ids)
        self.assertEqual(items[0].source_type, SOURCE_TYPE_PAPER)

    def test_fetch_filters_low_upvote_posts(self) -> None:
        from src.sources.reddit import RedditAdapter

        raw = self._make_raw_reddit("post_low", "Boring post", score=2)
        with patch.object(RedditAdapter, "_http_get", return_value=_mock_response(raw)):
            adapter = RedditAdapter({"subreddits": ["MachineLearning"], "min_upvotes": 10})
            items = adapter.fetch([])
        self.assertEqual(items, [])


# ── Hacker News adapter ────────────────────────────────────────────────────────
class TestHackerNewsAdapter(unittest.TestCase):
    def test_fetch_extracts_arxiv_from_url(self) -> None:
        from src.sources.hackernews import HackerNewsAdapter

        raw_hits = {
            "hits": [
                {
                    "objectID": "12345",
                    "title": "Ask HN: What did you think of this arxiv paper?",
                    "url": "https://arxiv.org/abs/2403.77777",
                    "author": "hn_user",
                    "points": 200,
                    "num_comments": 45,
                    "created_at_i": 1709280000,
                    "_tags": ["story"],
                }
            ]
        }
        with patch.object(HackerNewsAdapter, "_http_get", return_value=_mock_response(raw_hits)):
            adapter = HackerNewsAdapter({"search_queries": ["arxiv"], "min_points": 5, "lookback_hours": 48})
            items = adapter.fetch([])

        self.assertEqual(len(items), 1)
        self.assertIn("2403.77777", items[0].paper_ids)
        self.assertEqual(items[0].engagement_metrics.upvotes, 200)


# ── backward compat: existing arXiv/HF tests still pass ───────────────────────
class TestLegacyBackwardCompat(unittest.TestCase):
    """Verify existing CandidateItem logic is unaffected by new layer."""

    def test_item_key_stable(self) -> None:
        import common

        item1 = common.CandidateItem(
            source="arXiv",
            title="Test",
            url="https://arxiv.org/abs/2403.00001",
            paper_id="2403.00001",
        )
        item2 = common.CandidateItem(
            source="Semantic Scholar",
            title="Test (extended)",
            url="https://api.semanticscholar.org/paper/alpha",
            paper_id="2403.00001v2",
        )
        self.assertEqual(common.item_key(item1), common.item_key(item2))

    def test_merge_candidates_deduplicates_by_paper_id(self) -> None:
        import common

        items = [
            common.CandidateItem(
                source="arXiv", title="Paper A",
                url="https://arxiv.org/abs/2403.00001", paper_id="2403.00001",
            ),
            common.CandidateItem(
                source="HF", title="Paper A",
                url="https://huggingface.co/papers/2403.00001", paper_id="2403.00001v1",
            ),
        ]
        merged = common.merge_candidates(items)
        self.assertEqual(len(merged), 1)
        self.assertIn("arXiv", merged[0].source)
        self.assertIn("HF", merged[0].source)


if __name__ == "__main__":
    unittest.main()
