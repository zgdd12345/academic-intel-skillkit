"""OpenAlex source adapter.

Uses the OpenAlex REST API to fetch works (papers) matching topic keywords.
OpenAlex provides rich open-access metadata: concepts, institutions, citations,
open-access URLs, and author affiliations.

Config keys (under sources.openalex in YAML):
  enabled:               bool
  email:                 str   for the polite pool (higher rate limit)
  max_results_per_topic: int   (default 20; max 200 per page)
  lookback_days:         int   filter by from_publication_date (default 30)
  requests_per_minute:   float (default 60 with email, 10 without)
  max_retries:           int   (default 3)

Rate limits:
  No email:  10 req/sec (best effort)
  With email: 100 req/sec (polite pool)

Docs: https://docs.openalex.org
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from src.normalize.schema import (
    EngagementMetrics,
    NormalizedItem,
    SOURCE_TYPE_PAPER,
)
from src.sources.base import SourceAdapter, SourceError

from common import match_topics, utc_now_iso  # noqa: E402

_OPENALEX_WORKS = "https://api.openalex.org/works"


class OpenAlexAdapter(SourceAdapter):
    name = "openalex"
    source_type = SOURCE_TYPE_PAPER

    def _do_fetch(self, topics: list[dict[str, Any]]) -> list[NormalizedItem]:
        email = _s(self._cfg("email")) or os.environ.get("OPENALEX_EMAIL", "")
        limit: int = min(int(self._cfg("max_results_per_topic", 20)), 200)
        lookback_days: int = int(self._cfg("lookback_days", 30))

        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=lookback_days)
        ).strftime("%Y-%m-%d")

        # Polite pool uses mailto= parameter
        mailto_param = f"&mailto={email}" if email else ""
        fetched_at = utc_now_iso()
        seen_ids: set[str] = set()
        items: list[NormalizedItem] = []

        for topic in (topics if isinstance(topics, list) else []):
            kws = [_s(k) for k in (topic.get("include_keywords") or []) if _s(k)]
            if not kws:
                continue
            search_query = " ".join(kws[:4])

            params = {
                "search": search_query,
                "filter": f"from_publication_date:{cutoff}",
                "per-page": limit,
                "select": (
                    "id,doi,title,abstract_inverted_index,authorships,"
                    "publication_date,primary_location,open_access,"
                    "cited_by_count,concepts,keywords,type"
                ),
                "sort": "cited_by_count:desc",
            }
            if email:
                params["mailto"] = email

            try:
                resp = self._http_get(_OPENALEX_WORKS, params=params)
            except SourceError as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "[openalex] topic %r failed: %s", topic.get("id", "?"), exc
                )
                continue

            try:
                data = resp.json()
            except ValueError:
                continue

            results = data.get("results", []) if isinstance(data, dict) else []
            for work in results:
                if not isinstance(work, dict):
                    continue
                work_id = _s(work.get("id") or "")
                if not work_id or work_id in seen_ids:
                    continue
                seen_ids.add(work_id)
                item = _normalize_work(work, topic, fetched_at)
                if item is not None:
                    items.append(item)

        return items


def _normalize_work(
    work: dict[str, Any],
    topic: dict[str, Any],
    fetched_at: str,
) -> NormalizedItem | None:
    work_id = _s(work.get("id") or "")  # OpenAlex URL like https://openalex.org/W1234
    title = _s(work.get("title") or "")
    if not title:
        return None

    # Reconstruct abstract from inverted index
    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
    doi = _s(work.get("doi") or "")

    # Best URL: OA PDF > DOI > OpenAlex page
    oa = work.get("open_access") or {}
    oa_url = _s(oa.get("oa_url") or "")
    primary = work.get("primary_location") or {}
    landing_page = _s(primary.get("landing_page_url") or "")
    url = oa_url or (f"https://doi.org/{doi}" if doi else "") or landing_page or work_id

    # arXiv ID from DOI or landing page
    arxiv_id = ""
    if doi and "arxiv" in doi.lower():
        arxiv_id = doi.split("arxiv.")[-1].strip("/")
    elif "arxiv.org" in landing_page:
        from src.normalize.entity_resolver import extract_arxiv_ids
        ids = extract_arxiv_ids(landing_page)
        arxiv_id = ids[0] if ids else ""

    # Authors
    authorships = work.get("authorships") or []
    authors = []
    for a in authorships[:5]:  # cap at 5
        if not isinstance(a, dict):
            continue
        author_info = a.get("author") or {}
        name = _s(author_info.get("display_name") or "")
        if name:
            authors.append(name)
    first_author = authors[0] if authors else ""

    # Concepts / keywords as tags
    concepts = [
        _s(c.get("display_name") or "")
        for c in (work.get("concepts") or [])
        if isinstance(c, dict) and _s(c.get("display_name"))
    ]
    kws = [
        _s(k.get("keyword") or k if isinstance(k, dict) else k)
        for k in (work.get("keywords") or [])
        if k
    ]
    tags = list(dict.fromkeys(concepts[:5] + kws[:5]))  # de-dup, cap

    pub_date = _s(work.get("publication_date") or "")
    citations = int(work.get("cited_by_count") or 0)

    # Topic matching
    import sys
    from pathlib import Path
    _scripts = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)
    from common import CandidateItem as _CI, match_topics  # noqa: PLC0415
    proxy = _CI(source="openalex", title=title, url=url, summary=abstract)
    ts = match_topics(proxy, [topic])

    return NormalizedItem(
        source="openalex",
        source_type=SOURCE_TYPE_PAPER,
        external_id=work_id,
        url=url,
        title=title,
        content=abstract,
        author=first_author,
        published_at=pub_date or None,
        fetched_at=fetched_at,
        engagement_metrics=EngagementMetrics(citations=citations),
        raw_tags=tags,
        raw_payload={
            "openalex_id": work_id,
            "doi": doi,
            "arxiv_id": arxiv_id,
            "authors": authors,
            "cited_by_count": citations,
            "open_access": oa,
            "type": _s(work.get("type") or ""),
        },
        topic_scores=ts if ts else None,
        matched_topics=list(ts) if ts else None,
        paper_ids=[arxiv_id] if arxiv_id else [],
    )


def _reconstruct_abstract(inverted_index: Any) -> str:
    """Reconstruct plain text from OpenAlex's inverted-index abstract format."""
    if not isinstance(inverted_index, dict):
        return ""
    positions: dict[int, str] = {}
    for word, pos_list in inverted_index.items():
        if isinstance(pos_list, list):
            for pos in pos_list:
                positions[int(pos)] = str(word)
    if not positions:
        return ""
    return " ".join(positions[k] for k in sorted(positions))


def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""
