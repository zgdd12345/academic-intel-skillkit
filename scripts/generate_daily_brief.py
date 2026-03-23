from __future__ import annotations

import argparse
import os
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


def _strip_tags(text: str) -> str:
    """Remove HTML/XML-like tags to prevent Obsidian rendering breakage."""
    return re.sub(r"<[^>]+>", "", text)


def truncate_report_text(text: str, word_limit: int = 48, char_limit: int = 120) -> str:
    clean_text = re.sub(r"\s+", " ", (text or "").strip())
    if not clean_text:
        return ""
    if re.search(r"[\u3400-\u9fff]", clean_text):
        return clean_text if len(clean_text) <= char_limit else clean_text[:char_limit].rstrip() + "…"
    return truncate_words(clean_text, word_limit)


def format_authors(authors: list[str] | None) -> str:
    clean = [a for a in (authors or []) if a]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    return f"{clean[0]} 等"


def topic_ids_for_item(item: Any) -> list[str]:
    return item.matched_topics or list((item.topic_scores or {}).keys())


def format_topics(item_topic_ids: list[str], topic_names: dict[str, str]) -> str:
    if not item_topic_ids:
        return "未分类"
    return ", ".join(topic_names.get(topic_id, topic_id) for topic_id in item_topic_ids[:3])


_SOURCE_SHORT = {
    "hackernews": "HN",
    "reddit": "reddit",
    "github": "GitHub",
    "huggingface": "HF",
    "arxiv": "arXiv",
    "semantic_scholar": "S2",
    "openalex": "OpenAlex",
}


def _source_short(source: str) -> str:
    return _SOURCE_SHORT.get(source.lower(), source)


def format_link(title: str, url: str) -> str:
    clean_title = title or "未命名论文"
    if url:
        # Escape brackets in title to prevent Obsidian from treating [[...]] as wiki links
        safe_title = clean_title.replace("[", "\\[").replace("]", "\\]")
        return f"[{safe_title}]({url})"
    return clean_title


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


def build_report_summary(item: Any, topic_names: dict[str, str]) -> str:
    if item.summary_zh:
        return _strip_tags(item.summary_zh.strip())
    sentences = [
        f"{topic_phrase(item, topic_names)}，{relative_freshness(item.published_at)}，{signal_phrase(item.score)}。"
    ]
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


def format_latest_work(
    detailed_items: list[Any],
    brief_items: list[Any],
    topic_names: dict[str, str],
) -> str:
    if not detailed_items and not brief_items:
        return "_今天没有匹配到候选论文。_"

    parts: list[str] = []

    # Detailed callout blocks
    detail_blocks: list[str] = []
    for item in detailed_items:
        title_link = format_link(item.title, item.url)
        metadata = build_metadata_line(item, topic_names)
        summary = build_report_summary(item, topic_names)
        detail_blocks.append("\n".join([
            f"> [!tip] {title_link}",
            f"> {metadata}",
            ">",
            f"> {summary}",
        ]))
    if detail_blocks:
        parts.append("\n\n".join(detail_blocks))

    # Quick-scan bullet list — paper ID is mandatory per spec
    if brief_items:
        brief_lines: list[str] = []
        for item in brief_items:
            link = format_link(item.title or "未命名论文", item.url)
            paper_id = item.paper_id or ""
            id_prefix = f"`{paper_id}` " if paper_id else ""
            brief_lines.append(f"- {id_prefix}{link}")
        parts.append("\n".join(brief_lines))

    return "\n\n".join(parts)


def load_hotspots(path: str) -> list[dict[str, Any]]:
    payload = load_json(path, default={}) if path else {}
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("items", [])
    return [item for item in raw_items if isinstance(item, dict)]


def _hfield(item: dict[str, Any], *keys: str) -> Any:
    """Look up keys in item, then raw_payload, then engagement_metrics."""
    for key in keys:
        val = item.get(key)
        if val is not None and val != "":
            return val
    for nested in ("raw_payload", "engagement_metrics"):
        sub = item.get(nested)
        if isinstance(sub, dict):
            for key in keys:
                val = sub.get(key)
                if val is not None and val != "":
                    return val
    return None


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
    rank = coerce_int(_hfield(item, "rank"))
    if rank is not None:
        fragments.append(f"排名第 {rank} 位")
    upvotes = coerce_int(_hfield(item, "upvotes"))
    num_comments = coerce_int(_hfield(item, "num_comments", "numComments", "comments"))
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

    # Group by source/platform; arXiv items belong to 最新工作 only
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        source = str(item.get("source") or item.get("platform") or "其他").strip()
        if source.lower() == "arxiv":
            continue
        if source not in groups:
            groups[source] = []
        groups[source].append(item)

    sections: list[str] = []
    for source, group_items in groups.items():
        section_parts: list[str] = [f"### {source}"]

        # Top 1: full callout block (most important)
        for item in group_items[:1]:
            title = str(item.get("title") or item.get("name") or "未命名热点").strip()
            title_zh = _strip_tags(str(item.get("title_zh") or "").strip())
            display_title = title_zh if title_zh else title
            url = str(item.get("url") or item.get("link") or "").strip()

            meta_parts: list[str] = []
            org = str(_hfield(item, "organization") or "").strip()
            if org:
                meta_parts.append(f"机构：{org}")
            rank = coerce_int(_hfield(item, "rank"))
            if rank is not None:
                meta_parts.append(f"热榜第 {rank} 位")
            upvotes = coerce_int(_hfield(item, "upvotes"))
            num_comments = coerce_int(_hfield(item, "num_comments", "numComments", "comments"))
            signal_parts: list[str] = []
            if upvotes:
                signal_parts.append(f"{upvotes} 点赞")
            if num_comments:
                signal_parts.append(f"{num_comments} 评论")
            if signal_parts:
                meta_parts.append("信号：" + "、".join(signal_parts))

            summary_zh = _strip_tags(str(item.get("summary_zh") or item.get("summaryZh") or "").strip())
            ai_summary = _strip_tags(str(_hfield(item, "ai_summary") or "").strip())
            if summary_zh:
                intro = truncate_report_text(summary_zh, word_limit=60, char_limit=150)
            elif ai_summary and re.search(r"[\u3400-\u9fff]", ai_summary):
                intro = truncate_report_text(ai_summary, word_limit=60, char_limit=150)
            else:
                _, note = build_hotspot_note(item, topic_names)
                intro = note

            block_lines = [f"> [!tip] {format_link(display_title, url)}"]
            if meta_parts:
                block_lines.append(f"> {' | '.join(meta_parts)}")
            block_lines.append(">")
            block_lines.append(f"> {intro}")
            section_parts.append("\n".join(block_lines))

        # Items 2–3: news-headline one-liners (secondary)
        for item in group_items[1:3]:
            title = str(item.get("title") or item.get("name") or "未命名热点").strip()
            title_zh = _strip_tags(str(item.get("title_zh") or "").strip())
            url = str(item.get("url") or item.get("link") or "").strip()
            src_short = _source_short(source)
            display_title = title_zh if title_zh else title
            section_parts.append(f"- [{src_short}]({url}) {display_title}")

        sections.append("\n\n".join(section_parts))

    return "\n\n".join(sections)


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
    if lead_item.summary_zh:
        lead_desc = lead_item.summary_zh.strip()
        first_period = lead_desc.find("。")
        if 0 < first_period < 150:
            lead_desc = lead_desc[:first_period + 1]
        elif len(lead_desc) > 150:
            lead_desc = lead_desc[:150] + "…"
    else:
        lead_desc = f"{topic_phrase(lead_item, topic_names)}，{signal_phrase(lead_item.score)}。"

    sentences = [
        f"今日共整理 {len(ranked_candidates)} 篇候选论文，{len(shortlisted_items)} 篇入选日报。"
        f"当前较活跃的方向集中在 {topic_summary}。"
        f"最新亮点：{format_link(lead_item.title, lead_item.url)}（评分 {lead_item.score:.1f}），{lead_desc}"
    ]

    if hotspots:
        top_hotspot = hotspots[0]
        hs_title = str(top_hotspot.get("title") or top_hotspot.get("name") or "未命名热点").strip()
        hs_url = str(top_hotspot.get("url") or top_hotspot.get("link") or "").strip()
        hs_source = str(top_hotspot.get("source") or top_hotspot.get("platform") or "社区").strip()
        sentences.append(f"社区热点方面，{format_link(hs_title, hs_url)} 在 {hs_source} 上引发关注。")

    return "".join(sentences)


def format_hotspot_analysis(
    detailed_items: list[Any],
    brief_items: list[Any],
    hotspot_items: list[dict[str, Any]],
    config: dict[str, Any],
) -> str:
    llm_cfg = config.get("llm", {}) if isinstance(config.get("llm"), dict) else {}
    base_url = os.environ.get("LLM_BASE_URL") or llm_cfg.get("base_url")
    api_key = os.environ.get("LLM_API_KEY") or llm_cfg.get("api_key")
    model = os.environ.get("LLM_MODEL") or llm_cfg.get("model") or "gpt-4o-mini"

    if not base_url or not api_key:
        return "_（未配置 LLM，热点趋势分析不可用。请设置 LLM_BASE_URL 和 LLM_API_KEY 以启用此功能。）_"

    try:
        from openai import OpenAI  # noqa: PLC0415
    except ImportError:
        return "_（openai 包未安装，热点趋势分析不可用。请执行：pip install openai>=1.0）_"

    item_descs: list[str] = []
    for item in detailed_items + brief_items:
        title = item.title or "未命名"
        summary = item.summary_zh or item.summary or ""
        if summary:
            item_descs.append(f"- 论文：{title}\n  摘要：{summary[:200]}")
        else:
            item_descs.append(f"- 论文：{title}")
    for item in hotspot_items:
        title = str(item.get("title") or item.get("name") or "未命名热点").strip()
        desc = str(item.get("summary_zh") or item.get("summaryZh") or item.get("ai_summary") or "").strip()
        if desc:
            item_descs.append(f"- 热点：{title}\n  简介：{desc[:200]}")
        else:
            item_descs.append(f"- 热点：{title}")

    if not item_descs:
        return "_（今天没有足够的数据生成热点趋势分析。）_"

    prompt = (
        "你是研究情报分析专家。以下是今日学术论文精选和社区热点，请给出3-5个值得关注的研究热点趋势分析，"
        "以简洁的中文段落形式输出，不要使用列表。重点关注技术趋势、交叉方向和新兴话题。\n\n"
        + "\n".join(item_descs)
        + "\n\n只输出趋势分析内容，不要任何标题或前言。"
    )

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=str(model),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:  # noqa: BLE001
        print(f"警告：热点趋势分析 LLM 调用失败：{exc}", file=sys.stderr)
        return "_（热点趋势分析生成失败，请检查 LLM 配置。）_"


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

    content = render_template(
        template,
        {
            "date": str(date.today()),
            "overview": build_overview(ranked_candidates, high_signal_items, hotspots, topic_names),
            "candidate_count": str(len(ranked_candidates)),
            "high_signal_count": str(len(high_signal_items)),
            "hotspot_count": str(len(hotspots)),
            "recommended_count": str(len(detailed_items)),
            "latest_work": format_latest_work(detailed_items, brief_items, topic_names),
            "hotspots": format_hotspots(hotspots, topic_names),
            "hotspot_analysis": format_hotspot_analysis(detailed_items, brief_items, hotspots, config),
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
