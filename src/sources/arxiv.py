"""arXiv source adapter.

Wraps the existing scripts/fetch_arxiv.py logic in the SourceAdapter
interface.  Uses feedparser to fetch the arXiv Atom API.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

_scripts = str(Path(__file__).resolve().parents[2] / "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from common import (  # noqa: E402
    build_arxiv_query_plan,
    enabled_topics,
    utc_now_iso,
)
from src.normalize.schema import NormalizedItem, SOURCE_TYPE_PAPER
from src.sources.base import SourceAdapter, SourceError

try:
    import feedparser as _feedparser
    _FEEDPARSER_AVAILABLE = True
except ImportError:
    _feedparser = None  # type: ignore[assignment]
    _FEEDPARSER_AVAILABLE = False

_ARXIV_BASE = (
    "https://export.arxiv.org/api/query?search_query={query}"
    "&start=0&max_results={n}&sortBy=submittedDate&sortOrder=descending"
)


class ArxivAdapter(SourceAdapter):
    name = "arxiv"
    source_type = SOURCE_TYPE_PAPER

    def _do_fetch(self, topics: list[dict[str, Any]]) -> list[NormalizedItem]:
        if not _FEEDPARSER_AVAILABLE:
            raise SourceError(
                "[arxiv] feedparser not installed; run: pip install feedparser"
            )
        max_results = int(self._cfg("max_results_per_topic", 25))
        # Build per-topic query plan (same logic as scripts/fetch_arxiv.py)
        # `topics` here is the full config dict OR a list of topic dicts
        if isinstance(topics, dict):
            query_plan = build_arxiv_query_plan(topics)
        else:
            # topics is a list of topic dicts — build a synthetic config
            query_plan = build_arxiv_query_plan({"topics": topics})

        fetched_at = utc_now_iso()
        items: list[NormalizedItem] = []

        for plan_entry in query_plan:
            url = _ARXIV_BASE.format(
                query=quote_plus(plan_entry["query"]),
                n=max_results,
            )
            feed = _feedparser.parse(url)
            status = getattr(feed, "status", None)
            if status is not None and int(status) >= 400:
                raise SourceError(f"[arxiv] HTTP {status} for topic {plan_entry['topic_id']!r}")
            entries = getattr(feed, "entries", [])
            if getattr(feed, "bozo", False) and not entries:
                exc = getattr(feed, "bozo_exception", None)
                raise SourceError(f"[arxiv] feed parse error: {exc}")

            for entry in entries:
                paper_id = getattr(entry, "id", "").rsplit("/", 1)[-1]
                item = NormalizedItem(
                    source=self.name,
                    source_type=SOURCE_TYPE_PAPER,
                    external_id=paper_id,
                    url=getattr(entry, "link", ""),
                    title=getattr(entry, "title", "").replace("\n", " ").strip(),
                    content=getattr(entry, "summary", "").replace("\n", " ").strip(),
                    author=_first_author(getattr(entry, "authors", [])),
                    published_at=getattr(entry, "published", None),
                    fetched_at=fetched_at,
                    raw_tags=[
                        t.get("term", "")
                        for t in getattr(entry, "tags", [])
                        if t.get("term")
                    ],
                    raw_payload={
                        "topic_id": plan_entry["topic_id"],
                        "query": plan_entry["query"],
                        "authors": [
                            a.name for a in getattr(entry, "authors", [])
                        ],
                    },
                    paper_ids=[paper_id] if paper_id else [],
                )
                items.append(item)

        return items


def _first_author(authors: list[Any]) -> str:
    for a in authors:
        name = getattr(a, "name", None)
        if name:
            return str(name)
    return ""
