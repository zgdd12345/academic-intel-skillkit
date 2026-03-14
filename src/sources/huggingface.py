"""HuggingFace Papers source adapter.

Wraps the existing scripts/fetch_huggingface.py logic in the SourceAdapter
interface.  Calls the official HF daily_papers API.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_scripts = str(Path(__file__).resolve().parents[2] / "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from common import match_topics, utc_now_iso  # noqa: E402
from src.normalize.schema import (  # noqa: E402
    NormalizedItem,
    EngagementMetrics,
    SOURCE_TYPE_PAPER,
)
from src.sources.base import SourceAdapter, SourceError  # noqa: E402

_HF_API = "https://huggingface.co/api/daily_papers"


class HuggingFaceAdapter(SourceAdapter):
    name = "huggingface"
    source_type = SOURCE_TYPE_PAPER

    def _do_fetch(self, topics: list[dict[str, Any]]) -> list[NormalizedItem]:
        limit = int(self._cfg("limit", 20))
        sort = str(self._cfg("sort", "trending"))

        resp = self._http_get(_HF_API, params={"limit": limit, "sort": sort})
        try:
            raw = resp.json()
        except ValueError as exc:
            raise SourceError("[huggingface] response is not valid JSON") from exc
        if not isinstance(raw, list):
            raise SourceError("[huggingface] unexpected response format (not a list)")

        fetched_at = utc_now_iso()
        items: list[NormalizedItem] = []

        for rank, entry in enumerate(raw, start=1):
            if not isinstance(entry, dict):
                continue
            paper = entry.get("paper") or {}
            if not isinstance(paper, dict):
                paper = {}

            paper_id = _s(paper.get("id") or entry.get("paper_id") or "")
            title = _s(paper.get("title") or entry.get("title") or "")
            if not title:
                continue

            summary = _s(paper.get("summary") or entry.get("summary") or "")
            url = (
                _s(entry.get("url") or "")
                or (f"https://huggingface.co/papers/{paper_id}" if paper_id else "")
            )
            published_at = _s(
                paper.get("submittedOnDailyAt")
                or entry.get("publishedAt")
                or paper.get("publishedAt")
                or ""
            ) or None

            authors = [
                _s(a.get("name") or a.get("fullname") or "")
                for a in (paper.get("authors") or [])
                if isinstance(a, dict)
            ]
            first_author = next((a for a in authors if a), "")

            github_repo = _s(paper.get("githubRepo") or "")
            repo_urls = [f"https://github.com/{github_repo}"] if github_repo else []

            # Topic matching
            proxy_item = NormalizedItem(
                source=self.name,
                source_type=SOURCE_TYPE_PAPER,
                external_id=paper_id,
                url=url,
                title=title,
                content=summary,
                author=first_author,
                published_at=published_at,
                fetched_at=fetched_at,
                raw_tags=list(paper.get("aiKeywords") or []),
                repo_urls=repo_urls,
                paper_ids=[paper_id] if paper_id else [],
            )

            if topics:
                # Re-use legacy keyword matcher
                from common import CandidateItem as _CI  # noqa: PLC0415
                proxy_ci = _CI(
                    source=self.name,
                    title=title,
                    url=url,
                    summary=summary,
                    categories=list(paper.get("aiKeywords") or []),
                )
                ts = match_topics(proxy_ci, topics)
                if not ts:
                    continue
                proxy_item.topic_scores = ts
                proxy_item.matched_topics = list(ts)

            proxy_item.engagement_metrics = EngagementMetrics(
                upvotes=_int(entry.get("upvotes")),
                comments=_int(entry.get("numComments") or entry.get("num_comments")),
                stars=_int(paper.get("githubRepoStars")),
            )
            proxy_item.raw_payload = {
                "rank": rank,
                "organization": _s(
                    (paper.get("organization") or {}).get("fullname") or ""
                ),
                "submitted_by": _s(
                    (entry.get("submittedBy") or {}).get("fullname") or ""
                ),
                "ai_summary": _s(paper.get("ai_summary") or paper.get("aiSummary") or ""),
                "project_page": _s(paper.get("projectPage") or ""),
                "github_repo": github_repo,
            }
            items.append(proxy_item)

        return items


def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None
