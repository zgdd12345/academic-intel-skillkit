from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import feedparser

from common import (
    DEFAULT_ARXIV_OUTPUT,
    DEFAULT_LOCAL_CONFIG,
    CandidateItem,
    arxiv_source_config,
    build_arxiv_query_plan,
    display_path,
    dump_json,
    effective_arxiv_topic_ids,
    enabled_topics,
    filter_recent_candidates,
    load_yaml,
    missing_local_config_message,
    rank_candidates,
    utc_now_iso,
    validate_config,
)


class ArxivFeedError(RuntimeError):
    pass


def validate_feed(feed: Any, url: str) -> None:
    status = getattr(feed, "status", None)
    try:
        status_code = int(status) if status is not None else None
    except (TypeError, ValueError):
        status_code = None

    if status_code is not None and status_code >= 400:
        raise ArxivFeedError(f"arXiv 请求失败：HTTP {status_code} | {url}")

    entries = getattr(feed, "entries", [])
    if getattr(feed, "bozo", False) and not entries:
        error = getattr(feed, "bozo_exception", None)
        detail = str(error).strip() if error else "响应解析失败"
        raise ArxivFeedError(f"arXiv 返回异常响应：{detail} | {url}")


def fetch(query: str, max_results: int = 30) -> list[CandidateItem]:
    url = (
        "https://export.arxiv.org/api/query?search_query="
        + quote_plus(query)
        + f"&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    )
    feed = feedparser.parse(url)
    validate_feed(feed, url)
    items: list[CandidateItem] = []
    for entry in getattr(feed, "entries", []):
        items.append(
            CandidateItem(
                source="arXiv",
                title=getattr(entry, "title", "").replace("\n", " ").strip(),
                url=getattr(entry, "link", ""),
                summary=getattr(entry, "summary", "").replace("\n", " ").strip(),
                authors=[author.name for author in getattr(entry, "authors", [])],
                paper_id=getattr(entry, "id", "").rsplit("/", 1)[-1],
                published_at=getattr(entry, "published", None),
                categories=[tag.get("term", "") for tag in getattr(entry, "tags", []) if tag.get("term")],
            )
        )
    return items


def emit_config_diagnostics(config: dict[str, Any]) -> None:
    errors, warnings = validate_config(config)
    for warning in warnings:
        print(f"配置警告：{warning}", file=sys.stderr)
    if errors:
        error_lines = "\n".join(f"- {error}" for error in errors)
        raise SystemExit(f"配置校验失败：\n{error_lines}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="为当前 MVP 日报链路抓取并归一化 arXiv 候选论文。"
    )
    parser.add_argument("--query")
    parser.add_argument("--config", default=str(DEFAULT_LOCAL_CONFIG))
    parser.add_argument("--topic", action="append", default=[])
    parser.add_argument("--max-results", type=int)
    parser.add_argument("--lookback-days", type=int)
    parser.add_argument("--out", default=str(DEFAULT_ARXIV_OUTPUT))
    args = parser.parse_args()

    if args.max_results is not None and args.max_results <= 0:
        raise SystemExit("--max-results 必须大于 0")
    if args.lookback_days is not None and args.lookback_days < 0:
        raise SystemExit("--lookback-days 必须大于等于 0")

    if args.query:
        max_results = args.max_results or 30
        lookback_days = args.lookback_days or 0
        try:
            items = filter_recent_candidates(fetch(args.query, max_results=max_results), lookback_days)
        except ArxivFeedError as exc:
            raise SystemExit(str(exc)) from exc
        dump_json(
            args.out,
            {
                "generated_at": utc_now_iso(),
                "mode": "query",
                "query": args.query,
                "lookback_days": lookback_days,
                "items": [item.to_dict() for item in items],
            },
        )
        print(f"已写入 {len(items)} 条 arXiv 候选到 {display_path(args.out)}")
        return

    config_path = Path(args.config)
    if not config_path.exists():
        raise SystemExit(missing_local_config_message(config_path))

    config = load_yaml(args.config)
    emit_config_diagnostics(config)
    arxiv_config = arxiv_source_config(config)
    selected_topic_ids = effective_arxiv_topic_ids(config, args.topic)
    available_topic_ids = {
        str(topic.get("id")).strip()
        for topic in enabled_topics(config)
        if str(topic.get("id") or "").strip()
    }
    unknown_topic_ids = sorted({topic_id for topic_id in selected_topic_ids if topic_id not in available_topic_ids})
    if unknown_topic_ids:
        unknown_list = ", ".join(unknown_topic_ids)
        raise SystemExit(f"未知 topic id：{unknown_list}")
    max_results = args.max_results or int(arxiv_config.get("max_results_per_topic", 25) or 25)
    lookback_days = args.lookback_days if args.lookback_days is not None else int(arxiv_config.get("lookback_days", 0) or 0)
    query_plan = build_arxiv_query_plan(config, selected_topic_ids=selected_topic_ids)

    if not arxiv_config.get("enabled", True) or not query_plan:
        dump_json(
            args.out,
            {
                "generated_at": utc_now_iso(),
                "mode": "config",
                "queries": query_plan,
                "lookback_days": lookback_days,
                "items": [],
            },
        )
        print(f"已写入 0 条 arXiv 候选到 {display_path(args.out)}")
        return

    topics = enabled_topics(config)
    collected_items: list[CandidateItem] = []
    for plan_entry in query_plan:
        try:
            fetched_items = fetch(plan_entry["query"], max_results=max_results)
        except ArxivFeedError as exc:
            raise SystemExit(f"topic `{plan_entry['topic_id']}` 抓取失败：{exc}") from exc
        for item in fetched_items:
            item.topic_scores = {plan_entry["topic_id"]: 1.0}
            item.matched_topics = [plan_entry["topic_id"]]
        collected_items.extend(fetched_items)

    ranked_items = rank_candidates(filter_recent_candidates(collected_items, lookback_days), topics)
    dump_json(
        args.out,
        {
            "generated_at": utc_now_iso(),
            "mode": "config",
            "queries": query_plan,
            "lookback_days": lookback_days,
            "items": [item.to_dict() for item in ranked_items],
        },
    )
    print(f"已写入 {len(ranked_items)} 条 arXiv 候选到 {display_path(args.out)}")


if __name__ == "__main__":
    main()
