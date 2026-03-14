from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    DEFAULT_ARXIV_OUTPUT,
    DEFAULT_DAILY_TEMPLATE,
    DEFAULT_DAILY_BRIEF_OUTPUT,
    DEFAULT_LOCAL_CONFIG,
    display_path,
    enabled_topics,
    JsonLoadError,
    load_json,
    load_yaml,
    missing_local_config_message,
    parse_datetime,
    rank_candidates,
    read_candidate_items,
    render_template,
    truncate_words,
    validate_config,
    write_text,
)

def topic_name_map(topics: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(topic.get("id")): str(topic.get("name") or topic.get("id"))
        for topic in topics
        if topic.get("id")
    }


def format_date(value: str | None) -> str:
    parsed = parse_datetime(value)
    return parsed.date().isoformat() if parsed else "未知"


def truncate_report_text(text: str, word_limit: int = 48, char_limit: int = 120) -> str:
    clean_text = re.sub(r"\s+", " ", (text or "").strip())
    if not clean_text:
        return ""
    if re.search(r"[\u3400-\u9fff]", clean_text):
        return clean_text if len(clean_text) <= char_limit else clean_text[:char_limit].rstrip() + "…"
    return truncate_words(clean_text, word_limit)


def format_authors(authors: list[str] | None) -> str:
    clean_authors = [author for author in authors or [] if author]
    if not clean_authors:
        return ""
    if len(clean_authors) <= 4:
        return ", ".join(clean_authors)
    return ", ".join(clean_authors[:4]) + ", et al."


def topic_ids_for_item(item: Any) -> list[str]:
    return item.matched_topics or list((item.topic_scores or {}).keys())


def format_topics(item_topic_ids: list[str], topic_names: dict[str, str]) -> str:
    if not item_topic_ids:
        return "未分类"
    return ", ".join(topic_names.get(topic_id, topic_id) for topic_id in item_topic_ids[:3])


def format_link(title: str, url: str) -> str:
    clean_title = title or "未命名论文"
    return f"[{clean_title}]({url})" if url else clean_title


def coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def merge_original_names(*groups: list[str] | None) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for value in group or []:
            clean_value = str(value).strip()
            if clean_value and clean_value not in merged:
                merged.append(clean_value)
    return merged


def format_original_names(values: list[str] | None, limit: int = 3) -> str:
    clean_values = [value for value in values or [] if value]
    if not clean_values:
        return ""
    if len(clean_values) <= limit:
        return ", ".join(clean_values)
    return ", ".join(clean_values[:limit]) + ", ..."


def relative_freshness(value: str | None) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return "发布时间未明确"
    age_days = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 86400.0)
    if age_days <= 2:
        return "属于近两天的新论文"
    if age_days <= 7:
        return "属于近一周内的论文"
    if age_days <= 30:
        return "属于近一个月内的论文"
    return "发布时间相对较早"


def signal_phrase(score: float) -> str:
    if score >= 6:
        return "综合信号很强"
    if score >= 4:
        return "综合信号较强"
    if score >= 2:
        return "具备持续跟踪价值"
    return "更适合作为补充浏览"


def topic_phrase(item: Any, topic_names: dict[str, str]) -> str:
    matched_topics = topic_ids_for_item(item)
    topic_label = format_topics(matched_topics, topic_names)
    if len(matched_topics) > 1:
        return f"与 {topic_label} 等主题都有相关性"
    if matched_topics:
        return f"主要对应 {topic_label} 方向"
    return "当前主题匹配信号有限"


def build_report_summary(item: Any, topic_names: dict[str, str], detailed: bool = False) -> str:
    if item.summary_zh:
        return f"中文摘要：{truncate_report_text(item.summary_zh, word_limit=60, char_limit=140)}"

    sentences = [
        f"{topic_phrase(item, topic_names)}，{relative_freshness(item.published_at)}，{signal_phrase(item.score)}。"
    ]
    if detailed:
        if item.summary:
            sentences.append("当前 MVP 尚未内置自动翻译，因此建议结合论文链接中的原始摘要与正文继续判断是否进入深读。")
        else:
            sentences.append("当前条目没有可用摘要，建议优先检查标题、作者和论文链接页中的原始信息。")
    return "中文导读：" + "".join(sentences)


def build_metadata_line(item: Any, topic_names: dict[str, str]) -> str:
    topic_label = format_topics(topic_ids_for_item(item), topic_names)
    metadata = [
        f"来源：{item.source or '未知来源'}",
        f"发布日期：{format_date(item.published_at)}",
    ]
    if item.venue:
        metadata.append(f"发表信息：{item.venue}")
    metadata.append(f"主题：{topic_label}")
    metadata.append(f"评分：{item.score:.1f}")

    authors = format_authors(item.authors)
    if authors:
        metadata.append(f"作者：{authors}")

    institutions = format_original_names(merge_original_names(item.institutions, item.affiliations))
    if institutions:
        metadata.append(f"机构：{institutions}")

    if item.paper_id:
        metadata.append(f"ID：{item.paper_id}")
    return " | ".join(metadata)


def format_detailed(items: list[Any], topic_names: dict[str, str]) -> str:
    if not items:
        return "_今天没有匹配到候选论文。_"
    blocks: list[str] = []
    for item in items:
        title_link = format_link(item.title, item.url)
        metadata = build_metadata_line(item, topic_names)
        summary = build_report_summary(item, topic_names, detailed=True)
        blocks.append("\n".join([
            f"> [!tip] {title_link}",
            f"> {metadata}",
            ">",
            f"> {summary}",
        ]))
    return "\n\n".join(blocks)


def escape_pipe(text: str) -> str:
    return text.replace("|", "\\|")


def format_brief(items: list[Any], topic_names: dict[str, str]) -> str:
    if not items:
        return "_今天没有额外需要补看的论文。_"
    lines: list[str] = []
    for item in items:
        topic_label = format_topics(topic_ids_for_item(item), topic_names)
        link = format_link(item.title or "未命名论文", item.url)
        if item.summary_zh:
            desc = truncate_report_text(item.summary_zh, word_limit=40, char_limit=80)
        else:
            desc = f"{topic_phrase(item, topic_names)}，{signal_phrase(item.score)}。"
        lines.append(f"- **{link}** · {topic_label} · {format_date(item.published_at)} · {item.score:.1f}分")
        lines.append(f"  {desc}")
    return "\n".join(lines)


def load_hotspots(path: str) -> list[dict[str, Any]]:
    payload = load_json(path, default={}) if path else {}
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("items", [])
    return [item for item in raw_items if isinstance(item, dict)]


def hotspot_topic_ids(item: dict[str, Any]) -> list[str]:
    raw_ids = item.get("matched_topics")
    if isinstance(raw_ids, list):
        return [str(value).strip() for value in raw_ids if str(value).strip()]
    raw_scores = item.get("topic_scores")
    if isinstance(raw_scores, dict):
        return [str(topic_id).strip() for topic_id in raw_scores if str(topic_id).strip()]
    return []


def build_hotspot_note(item: dict[str, Any], topic_names: dict[str, str]) -> tuple[str, str]:
    summary_zh = str(item.get("summary_zh") or item.get("summaryZh") or "").strip()
    if summary_zh:
        return "中文摘要", truncate_report_text(summary_zh, word_limit=28, char_limit=80)

    note_zh = str(item.get("note_zh") or item.get("noteZh") or "").strip()
    if note_zh:
        return "中文提示", truncate_report_text(note_zh, word_limit=40, char_limit=100)

    source = str(item.get("source") or item.get("platform") or "社区").strip()
    fragments: list[str] = [f"{source} 上出现了值得留意的热点线索"]
    topic_ids = hotspot_topic_ids(item)
    if topic_ids:
        fragments.append(f"相关方向：{format_topics(topic_ids, topic_names)}")
    rank = coerce_int(item.get("rank"))
    if rank is not None:
        fragments.append(f"排名第 {rank} 位")
    upvotes = coerce_int(item.get("upvotes"))
    num_comments = coerce_int(item.get("num_comments") or item.get("numComments"))
    signal_parts: list[str] = []
    if upvotes is not None:
        signal_parts.append(f"{upvotes} 点赞")
    if num_comments is not None:
        signal_parts.append(f"{num_comments} 评论")
    if signal_parts:
        fragments.append("社区信号：" + "、".join(signal_parts))
    return "中文提示", "，".join(fragments) + "。建议打开原链接快速核对。"


def format_hotspots(items: list[dict[str, Any]], topic_names: dict[str, str]) -> str:
    if not items:
        return "_暂无社区热点数据；这不会影响当前 arXiv 主链路日报生成。_"
    lines: list[str] = []
    for item in items[:5]:
        title = str(item.get("title") or item.get("name") or "未命名热点").strip()
        url = str(item.get("url") or item.get("link") or "").strip()

        meta_parts: list[str] = []
        org = str(item.get("organization") or "").strip()
        if org:
            meta_parts.append(f"机构：{org}")
        rank = coerce_int(item.get("rank"))
        if rank is not None:
            meta_parts.append(f"热榜第 {rank} 位")
        signal_parts: list[str] = []
        upvotes = coerce_int(item.get("upvotes"))
        num_comments = coerce_int(item.get("num_comments") or item.get("numComments"))
        if upvotes:
            signal_parts.append(f"{upvotes} 点赞")
        if num_comments:
            signal_parts.append(f"{num_comments} 评论")
        if signal_parts:
            meta_parts.append("信号：" + "、".join(signal_parts))

        summary_zh = str(item.get("summary_zh") or item.get("summaryZh") or "").strip()
        ai_summary = str(item.get("ai_summary") or "").strip()
        if summary_zh:
            intro = f"中文摘要：{truncate_report_text(summary_zh, word_limit=60, char_limit=140)}"
        elif ai_summary:
            intro = f"工作简介：{truncate_report_text(ai_summary, word_limit=40, char_limit=120)}"
        else:
            _, note = build_hotspot_note(item, topic_names)
            intro = f"提示：{note}"

        lines.append(f"- **{format_link(title, url)}**")
        if meta_parts:
            lines.append(f"  {' | '.join(meta_parts)}")
        lines.append(f"  {intro}")
    return "\n".join(lines)


def count_topics(items: list[Any]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for item in items:
        topic_ids = topic_ids_for_item(item)
        if topic_ids:
            counter[topic_ids[0]] += 1
    return counter


def build_overview(
    ranked_candidates: list[Any],
    shortlisted_items: list[Any],
    hotspots: list[dict[str, Any]],
    topic_names: dict[str, str],
) -> str:
    if not ranked_candidates:
        return "今天没有可排序的候选论文，建议先检查 arXiv 抓取结果、时间窗口或 topic 配置。"

    focus_items = shortlisted_items or ranked_candidates
    topic_counter = count_topics(focus_items)
    topic_summary = "、".join(
        topic_names.get(topic_id, topic_id)
        for topic_id, _ in topic_counter.most_common(3)
    )
    if not topic_summary:
        topic_summary = "当前还没有形成稳定的主题聚类"

    lead_item = focus_items[0]
    hotspot_note = (
        f"另外合并了 {len(hotspots)} 条社区热点线索。"
        if hotspots
        else "本次没有合并社区热点输入，不影响当前 arXiv 主链路。"
    )
    stats_line = (
        f"今天共整理 {len(ranked_candidates)} 篇候选论文，其中 {len(shortlisted_items)} 篇进入最终日报。"
        f"当前较活跃的方向主要集中在 {topic_summary}。"
        f"建议先看 {format_link(lead_item.title, lead_item.url)}，它的综合评分最高（{lead_item.score:.1f}）。"
        f"{hotspot_note}"
    )

    key_lines: list[str] = ["**今日精选重点：**"]
    for i, item in enumerate(focus_items, 1):
        if item.summary_zh:
            desc = truncate_report_text(item.summary_zh, word_limit=30, char_limit=60)
        else:
            desc = f"{format_topics(topic_ids_for_item(item), topic_names)}方向，{signal_phrase(item.score)}"
        key_lines.append(f"{i}. {format_link(item.title, item.url)}：{desc}")
    key_block = "\n> ".join(key_lines)
    return f"{stats_line}\n> \n> {key_block}"


def format_topic_snapshot(items: list[Any], topic_names: dict[str, str]) -> str:
    if not items:
        return "_今天没有形成可汇总的主题观察。_"

    grouped: dict[str, list[Any]] = {}
    for item in items:
        topic_ids = topic_ids_for_item(item)
        primary_topic_id = topic_ids[0] if topic_ids else ""
        grouped.setdefault(primary_topic_id, []).append(item)

    blocks: list[str] = []
    ordered_groups = sorted(
        grouped.items(),
        key=lambda entry: (
            -len(entry[1]),
            -max(candidate.score for candidate in entry[1]),
            topic_names.get(entry[0], entry[0] or "未分类"),
        ),
    )
    for topic_id, group in ordered_groups[:5]:
        topic_label = topic_names.get(topic_id, topic_id) if topic_id else "未分类"
        top_item = max(group, key=lambda candidate: candidate.score)
        cross_topics = [
            topic_names.get(extra_topic_id, extra_topic_id)
            for candidate in group
            for extra_topic_id in topic_ids_for_item(candidate)[1:3]
        ]
        seen_cross_topics: list[str] = []
        for label in cross_topics:
            if label and label not in seen_cross_topics:
                seen_cross_topics.append(label)
        block_lines = [f"> [!abstract]- {topic_label}  ·  {len(group)} 篇入选"]
        block_lines.append(f"> **最高优先项**：{format_link(top_item.title, top_item.url)}（评分 {top_item.score:.1f}）")
        if seen_cross_topics:
            block_lines.append(f"> **跨主题关联**：{', '.join(seen_cross_topics[:2])}")
        blocks.append("\n".join(block_lines))
    return "\n\n".join(blocks)


def format_source_notes(semantic_scholar_path: str, hotspot_path: str) -> str:
    lines = [
        "当前稳定实现链路是 arXiv 抓取、归一化去重、主题匹配评分和 Markdown 日报渲染。",
        "论文标题、作者、机构、ID、URL 和 Venue 名称保持原文；报告结构、说明和建议使用中文。",
        "若条目包含 `summary_zh` 字段，报告会直接展示对应中文摘要；否则展示的是基于元数据和打分信号生成的中文导读，不等同于原摘要翻译。",
    ]

    semantic_scholar_available = bool(semantic_scholar_path and Path(semantic_scholar_path).exists())
    hotspot_available = bool(hotspot_path and Path(hotspot_path).exists())

    if semantic_scholar_available:
        lines.append("已合并外部提供的 Semantic Scholar 归一化 JSON；本仓库本轮仍然没有内置采集。")
    elif semantic_scholar_path:
        lines.append("指定了 Semantic Scholar JSON，但当前文件不存在，因此本次没有合并该输入。")
    else:
        lines.append("本次未提供 Semantic Scholar 归一化 JSON；这不会影响当前 MVP 主链路。")

    if hotspot_available:
        lines.append("已合并社区热点 JSON；当前仓库已提供最小可用的 `scripts/fetch_huggingface.py` 采集器。")
    elif hotspot_path:
        lines.append("指定了社区热点 JSON，但当前文件不存在，因此该板块只保留空状态说明。")
    else:
        lines.append("本次未提供社区热点 JSON，因此社区热点板块只显示空状态说明。")

    return "\n".join(f"> {line}" for line in lines)


def format_suggested_actions(items: list[Any], topic_names: dict[str, str]) -> str:
    if not items:
        return "- 今天没有新增深读建议。"
    lines: list[str] = []
    for index, item in enumerate(items[:2], start=1):
        topic_label = format_topics(topic_ids_for_item(item), topic_names)
        if index == 1:
            lines.append(
                f"- 优先阅读 {format_link(item.title, item.url)}：它在 {topic_label} 上的综合评分最高（{item.score:.1f}），适合先判断是否进入后续深读。"
            )
            continue
        lines.append(
            f"- 补充扫描 {format_link(item.title, item.url)}：这篇论文可以作为 {topic_label} 方向的第二优先项，帮助完善今天的观察面。"
        )
    return "\n".join(lines)


def emit_config_diagnostics(config: dict[str, Any]) -> None:
    errors, warnings = validate_config(config)
    for warning in warnings:
        print(f"配置警告：{warning}", file=sys.stderr)
    if errors:
        error_lines = "\n".join(f"- {error}" for error in errors)
        raise SystemExit(f"配置校验失败：\n{error_lines}")


def warn_missing_optional_inputs(label: str, path: str) -> None:
    if path and not Path(path).exists():
        print(f"警告：未找到可选输入 {label}，本次会跳过：{display_path(path)}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="生成当前 MVP 的中文学术日报。稳定主链路为 arXiv 抓取 + 归一化排名 + Markdown 渲染。"
    )
    parser.add_argument("--config", default=str(DEFAULT_LOCAL_CONFIG))
    parser.add_argument("--template", default=str(DEFAULT_DAILY_TEMPLATE))
    parser.add_argument("--arxiv", default=str(DEFAULT_ARXIV_OUTPUT))
    parser.add_argument("--semantic-scholar", dest="semantic_scholar", default="")
    parser.add_argument("--huggingface", default="")
    parser.add_argument("--out", default=str(DEFAULT_DAILY_BRIEF_OUTPUT))
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        raise SystemExit(missing_local_config_message(config_path))
    if not Path(args.arxiv).exists():
        raise SystemExit(f"未找到 arXiv 输入文件：{display_path(args.arxiv)}")
    if not Path(args.template).exists():
        raise SystemExit(f"未找到模板文件：{display_path(args.template)}")

    warn_missing_optional_inputs("Semantic Scholar", args.semantic_scholar)
    warn_missing_optional_inputs("社区热点", args.huggingface)

    config = load_yaml(args.config)
    emit_config_diagnostics(config)
    topics = enabled_topics(config)
    topic_names = topic_name_map(topics)
    template = Path(args.template).read_text(encoding="utf-8")

    all_candidates = []
    try:
        all_candidates.extend(read_candidate_items(args.arxiv, strict=True))
    except JsonLoadError as exc:
        raise SystemExit(str(exc)) from exc
    all_candidates.extend(read_candidate_items(args.semantic_scholar))

    ranked_candidates = rank_candidates(all_candidates, topics)
    reporting = config.get("reporting", {})
    daily_top_n = max(1, int(reporting.get("daily_top_n", 8) or 8))
    detailed_top_n = max(0, int(reporting.get("daily_detailed_top_n", 3) or 3))
    high_signal_items = [item for item in ranked_candidates if item.score > 0]
    if not high_signal_items:
        high_signal_items = ranked_candidates
    high_signal_items = high_signal_items[:daily_top_n]
    detailed_top_n = min(detailed_top_n, len(high_signal_items))
    detailed_items = high_signal_items[:detailed_top_n]
    brief_items = high_signal_items[detailed_top_n:]
    hotspots = load_hotspots(args.huggingface)
    recommended_items = detailed_items[:2]

    content = render_template(
        template,
        {
            "date": str(date.today()),
            "overview": build_overview(ranked_candidates, high_signal_items, hotspots, topic_names),
            "candidate_count": str(len(ranked_candidates)),
            "high_signal_count": str(len(high_signal_items)),
            "hotspot_count": str(len(hotspots)),
            "recommended_count": str(len(recommended_items)),
            "top_detailed": format_detailed(detailed_items, topic_names),
            "top_brief": format_brief(brief_items, topic_names),
            "topic_snapshot": format_topic_snapshot(high_signal_items, topic_names),
            "hotspots": format_hotspots(hotspots, topic_names),
            "suggested_actions": format_suggested_actions(recommended_items, topic_names),
            "source_notes": format_source_notes(args.semantic_scholar, args.huggingface),
        },
    )
    write_text(args.out, content)
    print(
        f"已写入日报 {display_path(args.out)}，共处理 {len(ranked_candidates)} 条合并候选，"
        f"输出 {len(high_signal_items)} 条入选论文，附带 {len(hotspots)} 条社区热点。"
    )


if __name__ == "__main__":
    main()
