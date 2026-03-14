"""Tests for entity extraction and entity resolver."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from src.normalize.entity_resolver import (
    EntityResolver,
    extract_arxiv_ids,
    extract_github_repos,
    extract_hf_models,
)
from src.normalize.schema import (
    EngagementMetrics,
    NormalizedItem,
    SOURCE_TYPE_DISCUSSION,
    SOURCE_TYPE_PAPER,
)


class TestExtractArxivIds(unittest.TestCase):
    def test_extract_from_url(self) -> None:
        text = "Check out https://arxiv.org/abs/2403.12345 for details."
        ids = extract_arxiv_ids(text)
        self.assertEqual(ids, ["2403.12345"])

    def test_extract_strips_version(self) -> None:
        text = "arxiv.org/abs/2403.12345v3"
        ids = extract_arxiv_ids(text)
        self.assertEqual(ids, ["2403.12345"])

    def test_extract_citation_style(self) -> None:
        text = "See arXiv:2403.99999 for the proof."
        ids = extract_arxiv_ids(text)
        self.assertIn("2403.99999", ids)

    def test_deduplication(self) -> None:
        text = "arxiv.org/abs/2403.11111 and https://arxiv.org/abs/2403.11111v2"
        ids = extract_arxiv_ids(text)
        self.assertEqual(ids.count("2403.11111"), 1)

    def test_no_false_positives_for_bare_numbers(self) -> None:
        text = "The model has 2403 parameters."
        ids = extract_arxiv_ids(text)
        self.assertEqual(ids, [])


class TestExtractGithubRepos(unittest.TestCase):
    def test_basic_repo_url(self) -> None:
        text = "Code at https://github.com/openai/gpt-4"
        repos = extract_github_repos(text)
        self.assertIn("https://github.com/openai/gpt-4", repos)

    def test_deduplication(self) -> None:
        text = "github.com/user/repo and github.com/user/repo again"
        repos = extract_github_repos(text)
        self.assertEqual(len(repos), 1)

    def test_multiple_repos(self) -> None:
        text = "github.com/user/repo1 and github.com/org/repo2"
        repos = extract_github_repos(text)
        self.assertEqual(len(repos), 2)


class TestExtractHfModels(unittest.TestCase):
    def test_basic_model_id(self) -> None:
        text = "Using huggingface.co/mistralai/Mistral-7B"
        models = extract_hf_models(text)
        self.assertIn("mistralai/Mistral-7B", models)


class TestEntityResolver(unittest.TestCase):
    def _make_item(self, source: str, external_id: str, paper_ids: list[str], **kwargs) -> NormalizedItem:
        return NormalizedItem(
            source=source,
            source_type=SOURCE_TYPE_PAPER,
            external_id=external_id,
            url=kwargs.get("url", f"https://example.com/{external_id}"),
            title=kwargs.get("title", "A Paper"),
            content=kwargs.get("content", ""),
            author=kwargs.get("author", ""),
            published_at=None,
            fetched_at="2024-03-01T00:00:00+00:00",
            paper_ids=paper_ids,
            engagement_metrics=kwargs.get("engagement_metrics", EngagementMetrics()),
        )

    def test_enrich_extracts_arxiv_ids_from_content(self) -> None:
        resolver = EntityResolver()
        item = self._make_item(
            "reddit", "post123",
            paper_ids=[],
            content="Check arxiv.org/abs/2403.55555 for details.",
        )
        resolver.enrich(item)
        self.assertIn("2403.55555", item.paper_ids)

    def test_group_by_entity_clusters_same_paper(self) -> None:
        resolver = EntityResolver()
        items = [
            self._make_item("arxiv", "2403.00001", ["2403.00001"]),
            self._make_item("reddit", "post_xyz", ["2403.00001"]),
            self._make_item("arxiv", "2403.00002", ["2403.00002"]),
        ]
        groups = resolver.group_by_entity(items)
        # First two share arxiv:2403.00001
        self.assertEqual(len(groups["arxiv:2403.00001"]), 2)
        self.assertEqual(len(groups["arxiv:2403.00002"]), 1)

    def test_merge_group_sums_engagement(self) -> None:
        resolver = EntityResolver()
        items = [
            self._make_item(
                "arxiv", "2403.00001", ["2403.00001"],
                engagement_metrics=EngagementMetrics(upvotes=10, comments=2),
            ),
            self._make_item(
                "reddit", "post_xyz", ["2403.00001"],
                engagement_metrics=EngagementMetrics(upvotes=150, comments=30),
            ),
        ]
        merged = resolver.merge_group(items)
        self.assertEqual(merged.engagement_metrics.upvotes, 160)
        self.assertEqual(merged.engagement_metrics.comments, 32)

    def test_merge_group_concatenates_sources(self) -> None:
        resolver = EntityResolver()
        items = [
            self._make_item("arxiv", "2403.00001", ["2403.00001"]),
            self._make_item("hackernews", "hn_999", ["2403.00001"]),
        ]
        merged = resolver.merge_group(items)
        self.assertIn("arxiv", merged.source)
        self.assertIn("hackernews", merged.source)
