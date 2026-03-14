"""Reddit source adapter.

Uses Reddit's public JSON API (no credentials required for read-only access).
Fetches hot/new posts from configured subreddits, extracts arXiv/GitHub entity
links from post text and URLs, and filters by topic relevance.

Config keys (under sources.reddit in YAML):
  enabled:               bool   (default true)
  subreddits:            list   (default: [MachineLearning, artificial, LocalLLaMA])
  sort:                  str    "hot" | "new" | "top"  (default "hot")
  limit_per_subreddit:   int    (default 25)
  min_upvotes:           int    filter posts below this score (default 5)
  requests_per_minute:   float  (default 20 — be polite to Reddit)
  max_retries:           int    (default 3)
"""
from __future__ import annotations

from typing import Any

from src.normalize.schema import (
    EngagementMetrics,
    NormalizedItem,
    SOURCE_TYPE_DISCUSSION,
    SOURCE_TYPE_PAPER,
)
from src.sources.base import SourceAdapter, SourceError

from common import match_topics, utc_now_iso  # noqa: E402 (scripts/ on path)

_DEFAULT_SUBREDDITS = ["MachineLearning", "artificial", "LocalLLaMA", "learnmachinelearning"]
_REDDIT_JSON = "https://www.reddit.com/r/{sub}/{sort}.json"
_REDDIT_HEADERS = {
    "User-Agent": "academic-intel-skillkit/0.2 (reddit-adapter; educational scraper)",
    "Accept": "application/json",
}


class RedditAdapter(SourceAdapter):
    name = "reddit"
    source_type = SOURCE_TYPE_DISCUSSION

    def _do_fetch(self, topics: list[dict[str, Any]]) -> list[NormalizedItem]:
        subreddits: list[str] = self._cfg("subreddits", _DEFAULT_SUBREDDITS)
        sort: str = self._cfg("sort", "hot")
        limit: int = int(self._cfg("limit_per_subreddit", 25))
        min_upvotes: int = int(self._cfg("min_upvotes", 5))
        fetched_at = utc_now_iso()
        items: list[NormalizedItem] = []

        for sub in subreddits:
            url = _REDDIT_JSON.format(sub=sub, sort=sort)
            try:
                resp = self._http_get(
                    url,
                    params={"limit": limit, "raw_json": 1},
                    headers=_REDDIT_HEADERS,
                )
            except SourceError as exc:
                # Isolate per-subreddit failures — continue with others
                import logging
                logging.getLogger(__name__).warning(
                    "[reddit] subreddit r/%s failed: %s", sub, exc
                )
                continue

            try:
                data = resp.json()
            except ValueError:
                continue

            posts = (
                data.get("data", {}).get("children", [])
                if isinstance(data, dict)
                else []
            )
            for child in posts:
                post = child.get("data", {}) if isinstance(child, dict) else {}
                item = _normalize_post(post, sub, fetched_at, min_upvotes, topics)
                if item is not None:
                    items.append(item)

        return items


def _normalize_post(
    post: dict[str, Any],
    subreddit: str,
    fetched_at: str,
    min_upvotes: int,
    topics: list[dict[str, Any]],
) -> NormalizedItem | None:
    score_val = post.get("score") or 0
    if int(score_val) < min_upvotes:
        return None

    title = _s(post.get("title") or "")
    if not title:
        return None

    post_id = _s(post.get("id") or "")
    permalink = _s(post.get("permalink") or "")
    url = (
        _s(post.get("url") or "")
        or (f"https://www.reddit.com{permalink}" if permalink else "")
    )
    selftext = _s(post.get("selftext") or "")
    combined = f"{title} {selftext} {url}"
    author = _s(post.get("author") or "")
    created_utc = post.get("created_utc")
    published_at: str | None = None
    if created_utc:
        from datetime import datetime, timezone
        published_at = datetime.fromtimestamp(
            float(created_utc), tz=timezone.utc
        ).isoformat()

    # Determine source type: paper-linked posts are SOURCE_TYPE_PAPER
    from src.normalize.entity_resolver import extract_arxiv_ids
    arxiv_ids = extract_arxiv_ids(combined)
    stype = SOURCE_TYPE_PAPER if arxiv_ids else SOURCE_TYPE_DISCUSSION

    # Topic filter
    if topics:
        import sys
        from pathlib import Path
        _scripts = str(Path(__file__).resolve().parents[2] / "scripts")
        if _scripts not in sys.path:
            sys.path.insert(0, _scripts)
        from common import CandidateItem as _CI  # noqa: PLC0415
        proxy = _CI(source="reddit", title=title, url=url, summary=selftext)
        ts = match_topics(proxy, topics)
        if not ts and not arxiv_ids:
            return None
    else:
        ts = {}

    from src.normalize.entity_resolver import extract_github_repos, extract_hf_models
    return NormalizedItem(
        source="reddit",
        source_type=stype,
        external_id=post_id,
        url=url,
        title=title,
        content=selftext,
        author=author,
        published_at=published_at,
        fetched_at=fetched_at,
        engagement_metrics=EngagementMetrics(
            upvotes=int(score_val),
            comments=int(post.get("num_comments") or 0),
        ),
        raw_tags=[subreddit, _s(post.get("link_flair_text") or "")],
        raw_payload={
            "subreddit": subreddit,
            "is_self": bool(post.get("is_self")),
            "over_18": bool(post.get("over_18")),
            "flair": _s(post.get("link_flair_text") or ""),
        },
        topic_scores=ts if ts else None,
        matched_topics=list(ts) if ts else None,
        paper_ids=arxiv_ids,
        repo_urls=extract_github_repos(combined),
        model_ids=extract_hf_models(combined),
    )


def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""
