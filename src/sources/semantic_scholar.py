"""Semantic Scholar source adapter.

Uses the Semantic Scholar Graph API v1 to search for papers matching topics.
Provides rich academic metadata: citations, influential citations, venue,
fields of study, authors with affiliations.

Config keys (under sources.semantic_scholar in YAML):
  enabled:               bool
  api_key:               str    (or SEMANTIC_SCHOLAR_API_KEY env var)
  max_results_per_topic: int    (default 20; max 100 per request)
  lookback_days:         int    filter by year; approximate only (default 30)
  fields:                list   S2 fields to request (default: see below)
  requests_per_minute:   float  (default 10 without key, 100 with key)
  max_retries:           int    (default 3)

Rate limits:
  Unauthenticated: ~100 req per 5 min
  API key:         up to 1 req/sec
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

_S2_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"

_DEFAULT_FIELDS = (
    "paperId,externalIds,title,abstract,authors,year,publicationDate,"
    "venue,publicationVenue,citationCount,influentialCitationCount,"
    "fieldsOfStudy,openAccessPdf,externalIds"
)


class SemanticScholarAdapter(SourceAdapter):
    name = "semantic_scholar"
    source_type = SOURCE_TYPE_PAPER

    def _do_fetch(self, topics: list[dict[str, Any]]) -> list[NormalizedItem]:
        api_key = (
            _s(self._cfg("api_key"))
            or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        )
        limit: int = min(int(self._cfg("max_results_per_topic", 20)), 100)
        fields: str = self._cfg("fields", _DEFAULT_FIELDS)

        headers: dict[str, str] = {}
        if api_key:
            headers["x-api-key"] = api_key

        fetched_at = utc_now_iso()
        seen_ids: set[str] = set()
        items: list[NormalizedItem] = []

        # Build search query from topic include_keywords
        for topic in (topics if isinstance(topics, list) else []):
            kws = [_s(k) for k in (topic.get("include_keywords") or []) if _s(k)]
            if not kws:
                continue
            query = " ".join(kws[:4])  # S2 works better with fewer keywords
            params = {
                "query": query,
                "fields": fields,
                "limit": limit,
            }
            try:
                resp = self._http_get(
                    _S2_SEARCH, params=params, headers=headers
                )
            except SourceError as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "[semantic_scholar] topic %r failed: %s",
                    topic.get("id", "?"),
                    exc,
                )
                continue

            try:
                data = resp.json()
            except ValueError:
                continue

            papers = data.get("data", []) if isinstance(data, dict) else []
            for paper in papers:
                if not isinstance(paper, dict):
                    continue
                paper_id = _s(paper.get("paperId") or "")
                if not paper_id or paper_id in seen_ids:
                    continue
                seen_ids.add(paper_id)
                item = _normalize_paper(paper, topic, fetched_at)
                if item is not None:
                    items.append(item)

        return items


def _normalize_paper(
    paper: dict[str, Any],
    topic: dict[str, Any],
    fetched_at: str,
) -> NormalizedItem | None:
    paper_id = _s(paper.get("paperId") or "")
    title = _s(paper.get("title") or "")
    if not title:
        return None

    abstract = _s(paper.get("abstract") or "")
    external_ids = paper.get("externalIds") or {}
    arxiv_id = _s(external_ids.get("ArXiv") or "")
    doi = _s(external_ids.get("DOI") or "")

    # Build canonical URL
    if arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
    elif doi:
        url = f"https://doi.org/{doi}"
    else:
        url = f"https://www.semanticscholar.org/paper/{paper_id}"

    # Authors
    authors_raw = paper.get("authors") or []
    authors = [_s(a.get("name") or "") for a in authors_raw if isinstance(a, dict)]
    first_author = next((a for a in authors if a), "")

    # Publication date
    pub_date = _s(paper.get("publicationDate") or "")
    pub_year = paper.get("year")
    published_at = pub_date or (f"{pub_year}-01-01" if pub_year else None)

    # Venue
    venue_raw = paper.get("publicationVenue") or paper.get("venue") or {}
    venue = _s(
        (venue_raw.get("name") if isinstance(venue_raw, dict) else venue_raw) or ""
    )

    # Fields of study
    fields = [_s(f.get("category") or "") for f in (paper.get("fieldsOfStudy") or []) if isinstance(f, dict)]

    citations = int(paper.get("citationCount") or 0)
    influential = int(paper.get("influentialCitationCount") or 0)

    # Topic matching via existing keyword logic
    import sys
    from pathlib import Path
    _scripts = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)
    from common import CandidateItem as _CI, match_topics  # noqa: PLC0415
    proxy = _CI(source="semantic_scholar", title=title, url=url, summary=abstract)
    ts = match_topics(proxy, [topic])

    pdf_url = _s((paper.get("openAccessPdf") or {}).get("url") or "")

    return NormalizedItem(
        source="semantic_scholar",
        source_type=SOURCE_TYPE_PAPER,
        external_id=paper_id,
        url=url,
        title=title,
        content=abstract,
        author=first_author,
        published_at=published_at,
        fetched_at=fetched_at,
        engagement_metrics=EngagementMetrics(citations=citations),
        raw_tags=fields,
        raw_payload={
            "paper_id": paper_id,
            "arxiv_id": arxiv_id,
            "doi": doi,
            "venue": venue,
            "authors": authors,
            "citation_count": citations,
            "influential_citation_count": influential,
            "open_access_pdf": pdf_url,
        },
        topic_scores=ts if ts else None,
        matched_topics=list(ts) if ts else None,
        paper_ids=[arxiv_id] if arxiv_id else ([paper_id] if paper_id else []),
    )


def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""
