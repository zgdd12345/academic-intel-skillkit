"""Hacker News source adapter.

Uses the HN Algolia Search API (https://hn.algolia.com/api) which supports
full-text search and date filtering — no credentials required.

Config keys (under sources.hackernews in YAML):
  enabled:              bool   (default true)
  search_queries:       list   (default: see _DEFAULT_QUERIES)
  limit:                int    max stories to return per query (default 30)
  min_points:           int    filter stories below this score (default 5)
  lookback_hours:       int    only fetch stories from last N hours (default 48)
  requests_per_minute:  float  (default 30)
  max_retries:          int    (default 3)
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from src.normalize.schema import (
    EngagementMetrics,
    NormalizedItem,
    SOURCE_TYPE_DISCUSSION,
    SOURCE_TYPE_PAPER,
)
from src.sources.base import SourceAdapter, SourceError

from common import match_topics, utc_now_iso  # noqa: E402

_ALGOLIA_SEARCH = "https://hn.algolia.com/api/v1/search"
_DEFAULT_QUERIES = ["arxiv machine learning", "large language model", "deep learning paper"]


class HackerNewsAdapter(SourceAdapter):
    name = "hackernews"
    source_type = SOURCE_TYPE_DISCUSSION

    def _do_fetch(self, topics: list[dict[str, Any]]) -> list[NormalizedItem]:
        queries: list[str] = self._cfg("search_queries", _DEFAULT_QUERIES)
        limit: int = int(self._cfg("limit", 30))
        min_points: int = int(self._cfg("min_points", 5))
        lookback_hours: int = int(self._cfg("lookback_hours", 48))

        cutoff_ts = int(
            (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).timestamp()
        )
        fetched_at = utc_now_iso()
        seen_ids: set[str] = set()
        items: list[NormalizedItem] = []

        for query in queries:
            params = {
                "query": query,
                "tags": "story",
                "numericFilters": f"created_at_i>{cutoff_ts},points>{min_points}",
                "hitsPerPage": limit,
            }
            try:
                resp = self._http_get(_ALGOLIA_SEARCH, params=params)
            except SourceError as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "[hackernews] query %r failed: %s", query, exc
                )
                continue

            try:
                data = resp.json()
            except ValueError:
                continue

            hits = data.get("hits", []) if isinstance(data, dict) else []
            for hit in hits:
                if not isinstance(hit, dict):
                    continue
                story_id = _s(hit.get("objectID") or "")
                if story_id in seen_ids:
                    continue
                seen_ids.add(story_id)
                item = _normalize_hit(hit, fetched_at, topics)
                if item is not None:
                    items.append(item)

        return items


def _normalize_hit(
    hit: dict[str, Any],
    fetched_at: str,
    topics: list[dict[str, Any]],
) -> NormalizedItem | None:
    title = _s(hit.get("title") or "")
    if not title:
        return None

    story_id = _s(hit.get("objectID") or "")
    url = _s(hit.get("url") or "") or f"https://news.ycombinator.com/item?id={story_id}"
    text = _s(hit.get("story_text") or hit.get("comment_text") or "")
    author = _s(hit.get("author") or "")
    points = hit.get("points") or 0
    num_comments = hit.get("num_comments") or 0

    created_ts = hit.get("created_at_i")
    published_at: str | None = None
    if created_ts:
        published_at = datetime.fromtimestamp(
            float(created_ts), tz=timezone.utc
        ).isoformat()

    combined = f"{title} {text} {url}"

    from src.normalize.entity_resolver import (
        extract_arxiv_ids,
        extract_github_repos,
        extract_hf_models,
    )
    arxiv_ids = extract_arxiv_ids(combined)
    stype = SOURCE_TYPE_PAPER if arxiv_ids else SOURCE_TYPE_DISCUSSION

    if topics:
        import sys
        from pathlib import Path
        _scripts = str(Path(__file__).resolve().parents[2] / "scripts")
        if _scripts not in sys.path:
            sys.path.insert(0, _scripts)
        from common import CandidateItem as _CI  # noqa: PLC0415
        proxy = _CI(source="hackernews", title=title, url=url, summary=text)
        ts = match_topics(proxy, topics)
        if not ts and not arxiv_ids:
            return None
    else:
        ts = {}

    tags = [_s(t) for t in (hit.get("_tags") or []) if _s(t)]

    return NormalizedItem(
        source="hackernews",
        source_type=stype,
        external_id=story_id,
        url=url,
        title=title,
        content=text,
        author=author,
        published_at=published_at,
        fetched_at=fetched_at,
        engagement_metrics=EngagementMetrics(
            upvotes=int(points),
            comments=int(num_comments),
        ),
        raw_tags=tags,
        raw_payload={"hn_id": story_id, "points": points},
        topic_scores=ts if ts else None,
        matched_topics=list(ts) if ts else None,
        paper_ids=arxiv_ids,
        repo_urls=extract_github_repos(combined),
        model_ids=extract_hf_models(combined),
    )


def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""
