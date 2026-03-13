from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import requests
except ModuleNotFoundError:
    requests = None

from common import (
    DEFAULT_HUGGINGFACE_OUTPUT,
    DEFAULT_LOCAL_CONFIG,
    CandidateItem,
    coerce_named_value,
    coerce_optional_str,
    display_path,
    dump_json,
    enabled_topics,
    load_yaml,
    match_topics,
    missing_local_config_message,
    select_topics,
    topic_id,
    utc_now_iso,
    validate_config,
)


HUGGINGFACE_DAILY_PAPERS_API = "https://huggingface.co/api/daily_papers"


class HuggingFaceFetchError(RuntimeError):
    pass


def coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_author_names(value: Any) -> list[str]:
    raw_values = value if isinstance(value, list) else []
    names: list[str] = []
    for raw_value in raw_values:
        name = coerce_named_value(raw_value, ("name", "fullname", "username"))
        if name and name not in names:
            names.append(name)
    return names


def topic_name_map(topics: list[dict[str, Any]]) -> dict[str, str]:
    return {
        topic_id(topic): str(topic.get("name") or topic_id(topic))
        for topic in topics
        if topic_id(topic)
    }


def emit_config_diagnostics(config: dict[str, Any]) -> None:
    errors, warnings = validate_config(config)
    for warning in warnings:
        print(f"配置警告：{warning}", file=sys.stderr)
    if errors:
        error_lines = "\n".join(f"- {error}" for error in errors)
        raise SystemExit(f"配置校验失败：\n{error_lines}")


def http_get(*args: Any, **kwargs: Any) -> Any:
    if requests is None:
        raise HuggingFaceFetchError("缺少依赖 `requests`，请先执行 `pip install -r requirements.txt`。")
    try:
        return requests.get(*args, **kwargs)
    except Exception as exc:
        raise HuggingFaceFetchError(f"Hugging Face 热点请求失败：{exc}") from exc


def fetch_daily_papers(
    *,
    limit: int = 20,
    sort: str = "trending",
    date: str = "",
    week: str = "",
    month: str = "",
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit, "sort": sort}
    if date:
        params["date"] = date
    if week:
        params["week"] = week
    if month:
        params["month"] = month

    response = http_get(
        HUGGINGFACE_DAILY_PAPERS_API,
        params=params,
        timeout=20,
        headers={"User-Agent": "academic-intel-skillkit/0.1"},
    )
    try:
        response.raise_for_status()
    except Exception as exc:
        raise HuggingFaceFetchError(f"Hugging Face 热点请求失败：{exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise HuggingFaceFetchError("Hugging Face 热点响应不是合法 JSON。") from exc

    if not isinstance(payload, list):
        raise HuggingFaceFetchError("Hugging Face 热点响应格式异常：预期为列表。")
    return [item for item in payload if isinstance(item, dict)]


def build_hotspot_note(item: dict[str, Any], topic_names: dict[str, str]) -> str:
    parts: list[str] = []
    rank = coerce_int(item.get("rank"))
    if rank is not None:
        parts.append(f"Hugging Face 热榜第 {rank} 位")

    matched_topics = [str(value).strip() for value in item.get("matched_topics", []) if str(value).strip()]
    if matched_topics:
        topic_label = ", ".join(topic_names.get(topic_key, topic_key) for topic_key in matched_topics[:2])
        parts.append(f"主要对应 {topic_label} 方向")

    organization = coerce_optional_str(item.get("organization"))
    if organization:
        parts.append(f"关联机构为 {organization}")

    signal_parts: list[str] = []
    upvotes = coerce_int(item.get("upvotes"))
    num_comments = coerce_int(item.get("num_comments"))
    if upvotes is not None:
        signal_parts.append(f"{upvotes} 个点赞")
    if num_comments is not None:
        signal_parts.append(f"{num_comments} 条评论")
    if signal_parts:
        parts.append("社区信号为 " + "、".join(signal_parts))

    if coerce_optional_str(item.get("github_repo")):
        parts.append("附带 GitHub 仓库线索")
    elif coerce_optional_str(item.get("project_page")):
        parts.append("附带项目页线索")

    submitted_by = coerce_optional_str(item.get("submitted_by"))
    if submitted_by:
        parts.append(f"由 {submitted_by} 提交到 Hugging Face Papers")

    if not parts:
        parts.append("这是 Hugging Face Papers 上出现的一条热点论文线索")
    return "，".join(parts) + "。建议结合原摘要、评论区和外链快速判断是否纳入跟踪。"


def normalize_hotspot_item(
    raw_item: dict[str, Any],
    *,
    rank: int,
    topics: list[dict[str, Any]],
    topic_names: dict[str, str],
) -> dict[str, Any] | None:
    paper = raw_item.get("paper", {})
    if not isinstance(paper, dict):
        paper = {}

    paper_id = coerce_optional_str(paper.get("id") or raw_item.get("paper_id") or raw_item.get("id"))
    title = coerce_optional_str(paper.get("title") or raw_item.get("title"))
    if not title:
        return None

    summary = coerce_optional_str(raw_item.get("summary") or paper.get("summary")) or ""
    url = (
        coerce_optional_str(raw_item.get("url"))
        or (f"https://huggingface.co/papers/{paper_id}" if paper_id else None)
        or ""
    )
    published_at = coerce_optional_str(
        paper.get("submittedOnDailyAt") or raw_item.get("publishedAt") or paper.get("publishedAt")
    )
    authors = normalize_author_names(paper.get("authors"))
    organization = coerce_named_value(paper.get("organization"), ("fullname", "name", "display_name", "title"))
    submitted_by = coerce_named_value(raw_item.get("submittedBy"), ("fullname", "name", "username", "display_name"))
    github_repo = coerce_optional_str(paper.get("githubRepo"))
    project_page = coerce_optional_str(paper.get("projectPage"))
    github_stars = coerce_int(paper.get("githubRepoStars"))
    ai_keywords = [
        str(value).strip()
        for value in (paper.get("aiKeywords") if isinstance(paper.get("aiKeywords"), list) else [])
        if str(value).strip()
    ]

    candidate = CandidateItem(
        source="Hugging Face Papers",
        title=title,
        url=url,
        summary=summary,
        authors=authors or None,
        paper_id=paper_id,
        published_at=published_at,
    )
    topic_scores = match_topics(candidate, topics) if topics else {}
    if topics and not topic_scores:
        return None

    item = {
        "source": "Hugging Face Papers",
        "title": title,
        "url": url,
        "summary": summary,
        "paper_id": paper_id,
        "published_at": published_at,
        "authors": authors,
        "organization": organization,
        "submitted_by": submitted_by,
        "rank": rank,
        "upvotes": coerce_int(raw_item.get("upvotes")),
        "num_comments": coerce_int(raw_item.get("numComments")),
        "github_repo": github_repo,
        "github_stars": github_stars,
        "project_page": project_page,
        "ai_summary": coerce_optional_str(paper.get("ai_summary") or paper.get("aiSummary")),
        "ai_keywords": ai_keywords,
        "matched_topics": list(topic_scores) if topic_scores else [],
        "topic_scores": topic_scores or None,
    }
    item["note_zh"] = build_hotspot_note(item, topic_names)
    return item


def collect_hotspots(raw_items: list[dict[str, Any]], topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    topic_names = topic_name_map(topics)
    collected_items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items, start=1):
        normalized = normalize_hotspot_item(raw_item, rank=index, topics=topics, topic_names=topic_names)
        if normalized:
            collected_items.append(normalized)
    return collected_items


def load_topics(config_path: str, cli_topic_ids: list[str]) -> tuple[list[dict[str, Any]], bool]:
    path = Path(config_path)
    default_path = DEFAULT_LOCAL_CONFIG
    if not path.exists():
        if cli_topic_ids:
            raise SystemExit(missing_local_config_message(path))
        if path.resolve() != default_path.resolve():
            raise SystemExit(missing_local_config_message(path))
        print(
            f"警告：未找到配置文件 {display_path(path)}，本次不会做 topic 过滤。",
            file=sys.stderr,
        )
        return [], False

    config = load_yaml(config_path)
    if not isinstance(config, dict):
        config = {}
    emit_config_diagnostics(config)

    topics = enabled_topics(config)
    if cli_topic_ids:
        selected = select_topics(config, cli_topic_ids, enabled_only=True)
        selected_ids = {topic_id(topic) for topic in selected}
        unknown_topic_ids = sorted({topic_key for topic_key in cli_topic_ids if topic_key not in selected_ids})
        if unknown_topic_ids:
            raise SystemExit(f"未知或未启用的 topic id：{', '.join(unknown_topic_ids)}")
        topics = selected
    return topics, True


def main() -> None:
    ap = argparse.ArgumentParser(
        description="抓取 Hugging Face Papers 官方热点接口，并输出可被日报消费的规范化 JSON。"
    )
    ap.add_argument("--config", default=str(DEFAULT_LOCAL_CONFIG))
    ap.add_argument("--topic", action="append", default=[])
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--sort", choices=("publishedAt", "trending"), default="trending")
    period_group = ap.add_mutually_exclusive_group()
    period_group.add_argument("--date", default="")
    period_group.add_argument("--week", default="")
    period_group.add_argument("--month", default="")
    ap.add_argument("--out", default=str(DEFAULT_HUGGINGFACE_OUTPUT))
    args = ap.parse_args()

    if args.limit <= 0:
        raise SystemExit("--limit 必须大于 0")

    topics, used_config = load_topics(args.config, [str(topic_key).strip() for topic_key in args.topic if str(topic_key).strip()])

    try:
        raw_items = fetch_daily_papers(
            limit=args.limit,
            sort=args.sort,
            date=args.date,
            week=args.week,
            month=args.month,
        )
    except HuggingFaceFetchError as exc:
        raise SystemExit(str(exc)) from exc

    items = collect_hotspots(raw_items, topics)
    dump_json(
        args.out,
        {
            "generated_at": utc_now_iso(),
            "source": "Hugging Face Papers",
            "api": {
                "endpoint": HUGGINGFACE_DAILY_PAPERS_API,
                "limit": args.limit,
                "sort": args.sort,
                "date": args.date,
                "week": args.week,
                "month": args.month,
            },
            "topic_filter_ids": [topic_id(topic) for topic in topics],
            "config_applied": used_config,
            "raw_item_count": len(raw_items),
            "items": items,
        },
    )
    print(
        f"已写入 {len(items)} 条 Hugging Face 社区热点到 {display_path(args.out)}"
        f"（原始返回 {len(raw_items)} 条，topic 过滤后保留 {len(items)} 条）。"
    )


if __name__ == "__main__":
    main()
