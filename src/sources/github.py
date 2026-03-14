"""GitHub source adapter.

Searches GitHub Issues and Discussions for mentions of papers/models using the
GitHub Search API.  Requires a personal access token for rate limits above
10 req/min.

Config keys (under sources.github in YAML):
  enabled:             bool
  api_token:           str    (or set GITHUB_TOKEN env var)
  search_queries:      list   keyword queries to run against issues/discussions
  min_stars:           int    minimum repo stars to include (default 0)
  limit:               int    max results per query (default 30)
  lookback_days:       int    only include issues updated in last N days (default 7)
  requests_per_minute: float  (default 20 with token, 6 without)
  max_retries:         int    (default 3)

Rate limits:
  Unauthenticated: 10 req/min search API
  Authenticated:   30 req/min search API
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from src.normalize.schema import (
    EngagementMetrics,
    NormalizedItem,
    SOURCE_TYPE_DISCUSSION,
    SOURCE_TYPE_REPO,
)
from src.sources.base import SourceAdapter, SourceError

from common import match_topics, utc_now_iso  # noqa: E402

_GH_SEARCH_ISSUES = "https://api.github.com/search/issues"
_GH_SEARCH_REPOS = "https://api.github.com/search/repositories"
_DEFAULT_QUERIES = [
    "arxiv paper implementation",
    "machine learning benchmark",
    "large language model fine-tuning",
]


class GitHubAdapter(SourceAdapter):
    name = "github"
    source_type = SOURCE_TYPE_DISCUSSION

    def _do_fetch(self, topics: list[dict[str, Any]]) -> list[NormalizedItem]:
        token = (
            _s(self._cfg("api_token"))
            or os.environ.get("GITHUB_TOKEN", "")
        )
        queries: list[str] = self._cfg("search_queries", _DEFAULT_QUERIES)
        limit: int = min(int(self._cfg("limit", 30)), 100)
        lookback_days: int = int(self._cfg("lookback_days", 7))
        min_stars: int = int(self._cfg("min_stars", 0))

        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=lookback_days)
        ).strftime("%Y-%m-%d")

        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            import logging
            logging.getLogger(__name__).info(
                "[github] no token configured — rate limit is 10 req/min; "
                "set GITHUB_TOKEN or sources.github.api_token"
            )
            # Adjust rate limiter if no token
            self._rate_limiter._interval = max(self._rate_limiter._interval, 6.0)

        fetched_at = utc_now_iso()
        seen_ids: set[str] = set()
        items: list[NormalizedItem] = []

        for query in queries:
            full_query = f"{query} updated:>{cutoff}"
            params = {
                "q": full_query,
                "sort": "updated",
                "order": "desc",
                "per_page": limit,
            }
            try:
                resp = self._http_get(
                    _GH_SEARCH_ISSUES, params=params, headers=headers
                )
            except SourceError as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "[github] query %r failed: %s", query, exc
                )
                continue

            try:
                data = resp.json()
            except ValueError:
                continue

            issues = data.get("items", []) if isinstance(data, dict) else []
            for issue in issues:
                if not isinstance(issue, dict):
                    continue
                issue_id = str(issue.get("id") or "")
                if issue_id in seen_ids:
                    continue
                seen_ids.add(issue_id)
                item = _normalize_issue(issue, fetched_at, topics, min_stars)
                if item is not None:
                    items.append(item)

        return items


def _normalize_issue(
    issue: dict[str, Any],
    fetched_at: str,
    topics: list[dict[str, Any]],
    min_stars: int,
) -> NormalizedItem | None:
    title = _s(issue.get("title") or "")
    if not title:
        return None

    issue_id = str(issue.get("id") or "")
    url = _s(issue.get("html_url") or "")
    body = _s(issue.get("body") or "")
    author = _s((issue.get("user") or {}).get("login") or "")
    comments_count = int(issue.get("comments") or 0)
    reactions = issue.get("reactions") or {}
    upvotes = int(reactions.get("+1") or reactions.get("heart") or 0)

    repo_info = _extract_repo(url)
    repo_stars = 0  # Would require extra API call; skip for now

    created_at = _s(issue.get("created_at") or "")
    published_at = created_at or None

    combined = f"{title} {body} {url}"

    from src.normalize.entity_resolver import (
        extract_arxiv_ids,
        extract_github_repos,
        extract_hf_models,
    )
    arxiv_ids = extract_arxiv_ids(combined)

    if topics:
        import sys
        from pathlib import Path
        _scripts = str(Path(__file__).resolve().parents[2] / "scripts")
        if _scripts not in sys.path:
            sys.path.insert(0, _scripts)
        from common import CandidateItem as _CI  # noqa: PLC0415
        proxy = _CI(source="github", title=title, url=url, summary=body)
        ts = match_topics(proxy, topics)
        if not ts and not arxiv_ids:
            return None
    else:
        ts = {}

    labels = [_s(lb.get("name") or "") for lb in (issue.get("labels") or [])]
    stype = SOURCE_TYPE_DISCUSSION
    if repo_info:
        stype = SOURCE_TYPE_REPO

    return NormalizedItem(
        source="github",
        source_type=stype,
        external_id=issue_id,
        url=url,
        title=title,
        content=body[:2000],  # truncate very long issue bodies
        author=author,
        published_at=published_at,
        fetched_at=fetched_at,
        engagement_metrics=EngagementMetrics(
            upvotes=upvotes,
            comments=comments_count,
        ),
        raw_tags=labels,
        raw_payload={
            "repo": repo_info,
            "state": _s(issue.get("state") or ""),
            "is_pull_request": "pull_request" in issue,
        },
        topic_scores=ts if ts else None,
        matched_topics=list(ts) if ts else None,
        paper_ids=arxiv_ids,
        repo_urls=extract_github_repos(combined) or ([repo_info] if repo_info else []),
        model_ids=extract_hf_models(combined),
    )


def _extract_repo(url: str) -> str:
    """Extract 'owner/repo' from a GitHub issue URL."""
    # https://github.com/owner/repo/issues/123
    parts = url.replace("https://github.com/", "").split("/")
    if len(parts) >= 2:
        return f"https://github.com/{parts[0]}/{parts[1]}"
    return ""


def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""
