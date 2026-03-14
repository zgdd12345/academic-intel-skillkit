"""Entity resolution: extract and normalise paper/repo/model references.

The resolver scans `title + content + url` of each NormalizedItem to find:
  - arXiv IDs  (canonical form: YYMM.NNNNN, version suffix stripped)
  - GitHub repo slugs (owner/repo)
  - HuggingFace model / dataset IDs (owner/name)

Items that share the same paper_id (or, failing that, the same URL) are
considered the same entity across platforms and can be merged downstream.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from src.normalize.schema import NormalizedItem

# ── regex patterns ──────────────────────────────────────────────────────────────
_ARXIV_URL = re.compile(
    r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(?:v\d+)?",
    re.IGNORECASE,
)
_ARXIV_BARE = re.compile(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b")

_GITHUB_REPO = re.compile(
    r"github\.com/([a-zA-Z0-9](?:[a-zA-Z0-9._-]*/[a-zA-Z0-9._-]+))",
    re.IGNORECASE,
)

_HF_MODEL = re.compile(
    r"huggingface\.co/(?:models?/)?([a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+)",
    re.IGNORECASE,
)

# Papers are sometimes referenced as "arXiv:2403.00001" or "arXiv 2403.00001"
_ARXIV_CITE = re.compile(r"arXiv[:\s]+(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)


# ── extraction helpers ──────────────────────────────────────────────────────────
def extract_arxiv_ids(text: str) -> list[str]:
    """Return de-duplicated, version-stripped arXiv IDs found in *text*."""
    found: list[str] = []
    for pattern in (_ARXIV_URL, _ARXIV_CITE, _ARXIV_BARE):
        for match in pattern.findall(text):
            aid = match.strip().lower()
            if aid and aid not in found:
                found.append(aid)
    return found


def extract_github_repos(text: str) -> list[str]:
    """Return de-duplicated GitHub repo URLs found in *text*."""
    repos: list[str] = []
    for slug in _GITHUB_REPO.findall(text):
        # Strip trailing .git or punctuation
        slug = slug.rstrip("./,)")
        url = f"https://github.com/{slug}"
        if url not in repos:
            repos.append(url)
    return repos


def extract_hf_models(text: str) -> list[str]:
    """Return de-duplicated HuggingFace model/dataset IDs found in *text*."""
    models: list[str] = []
    for m in _HF_MODEL.findall(text):
        mid = m.rstrip("./,)")
        if mid and mid not in models:
            models.append(mid)
    return models


# ── entity resolver ─────────────────────────────────────────────────────────────
class EntityResolver:
    """Enrich items with entity links and group cross-platform items."""

    def enrich(self, item: NormalizedItem) -> NormalizedItem:
        """Scan item text for entity references and populate link fields."""
        combined = f"{item.title} {item.content} {item.url}"
        new_paper_ids = extract_arxiv_ids(combined)
        new_repo_urls = extract_github_repos(combined)
        new_model_ids = extract_hf_models(combined)

        # Merge with any already-set values (adapter may have set them directly)
        item.paper_ids = _merge_unique(item.paper_ids, new_paper_ids)
        item.repo_urls = _merge_unique(item.repo_urls, new_repo_urls)
        item.model_ids = _merge_unique(item.model_ids, new_model_ids)
        return item

    def enrich_all(self, items: list[NormalizedItem]) -> list[NormalizedItem]:
        return [self.enrich(item) for item in items]

    # ── grouping ──────────────────────────────────────────────────────────────
    def group_by_entity(
        self, items: list[NormalizedItem]
    ) -> dict[str, list[NormalizedItem]]:
        """Return {entity_key: [item, …]} grouping cross-platform duplicates.

        Key priority:
          1. arxiv:<paper_id>  — most stable identifier
          2. <source>:<external_id>
          3. url:<url>
        """
        groups: dict[str, list[NormalizedItem]] = defaultdict(list)
        for item in items:
            key = _entity_key(item)
            groups[key].append(item)
        return dict(groups)

    def merge_group(self, group: list[NormalizedItem]) -> NormalizedItem:
        """Merge a group of cross-platform items into a single canonical item.

        Keeps the richest fields; sums engagement metrics.
        """
        if len(group) == 1:
            return group[0]

        # Prefer arXiv item as base (most metadata)
        base = _pick_base(group)

        merged_upvotes = _sum_metric(group, "upvotes")
        merged_comments = _sum_metric(group, "comments")
        merged_stars = _sum_metric(group, "stars")

        from src.normalize.schema import EngagementMetrics
        base.engagement_metrics = EngagementMetrics(
            upvotes=merged_upvotes,
            comments=merged_comments,
            stars=merged_stars,
            forks=base.engagement_metrics.forks,
            citations=base.engagement_metrics.citations,
        )

        # Merge source names
        seen_sources = [base.source]
        for item in group:
            if item.source not in seen_sources:
                seen_sources.append(item.source)
        base.source = " + ".join(seen_sources)

        # Merge entity links
        for item in group:
            base.paper_ids = _merge_unique(base.paper_ids, item.paper_ids)
            base.repo_urls = _merge_unique(base.repo_urls, item.repo_urls)
            base.model_ids = _merge_unique(base.model_ids, item.model_ids)

        # Prefer longest content / summary
        contents = [item.content for item in group if item.content]
        if contents:
            base.content = max(contents, key=len)
        summaries_zh = [item.summary_zh for item in group if item.summary_zh]
        if summaries_zh:
            base.summary_zh = max(summaries_zh, key=len)

        return base


# ── internal helpers ────────────────────────────────────────────────────────────
def _entity_key(item: NormalizedItem) -> str:
    if item.paper_ids:
        return f"arxiv:{item.paper_ids[0]}"
    if item.external_id:
        return f"{item.source}:{item.external_id}"
    return f"url:{item.url}"


def _pick_base(group: list[NormalizedItem]) -> NormalizedItem:
    priority = {"arxiv": 0, "semantic_scholar": 1, "openalex": 2}
    return sorted(group, key=lambda i: priority.get(i.source.lower(), 99))[0]


def _sum_metric(group: list[NormalizedItem], attr: str) -> int | None:
    vals = [getattr(item.engagement_metrics, attr) for item in group]
    non_none = [v for v in vals if v is not None]
    return sum(non_none) if non_none else None


def _merge_unique(existing: list[str], new: list[str]) -> list[str]:
    result = list(existing)
    for val in new:
        if val not in result:
            result.append(val)
    return result
