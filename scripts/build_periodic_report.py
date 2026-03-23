"""build_periodic_report.py — Generate weekly or monthly academic reports.

Reads daily brief Markdown files from the Obsidian vault, aggregates them,
optionally uses LLM for narrative sections, and writes a period report.

Usage:
    python3 scripts/build_periodic_report.py --period weekly
    python3 scripts/build_periodic_report.py --period monthly --date 2026-03-31
    python3 scripts/build_periodic_report.py --period weekly --skip-llm
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    DEFAULT_LOCAL_CONFIG,
    REPO_ROOT,
    display_path,
    load_yaml,
    missing_local_config_message,
    obsidian_monthly_path,
    obsidian_root,
    obsidian_weekly_path,
    render_template,
    write_text,
)
from parse_daily_briefs import DailyBriefData, ParsedPaper, find_daily_briefs, parse_daily_brief
from aggregate_period import (
    PeriodAggregate,
    aggregate_briefs,
    check_thresholds,
    compute_date_range,
    compute_period_id,
)

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_WEEKLY_TEMPLATE = REPO_ROOT / "templates" / "weekly-template.md"
DEFAULT_MONTHLY_TEMPLATE = REPO_ROOT / "templates" / "monthly-template.md"
DEFAULT_THRESHOLDS_CONFIG = REPO_ROOT / "config" / "report-thresholds.example.yaml"


# ---------------------------------------------------------------------------
# LLM helpers (same pattern as enrich_summaries.py)
# ---------------------------------------------------------------------------

def _resolve_llm_settings(config: dict[str, Any]) -> tuple[str | None, str | None, str]:
    llm_cfg = config.get("llm", {}) if isinstance(config.get("llm"), dict) else {}
    base_url = os.environ.get("LLM_BASE_URL") or llm_cfg.get("base_url") or None
    api_key = os.environ.get("LLM_API_KEY") or llm_cfg.get("api_key") or None
    model = os.environ.get("LLM_MODEL") or llm_cfg.get("model") or DEFAULT_MODEL
    return base_url, api_key, str(model)


def _make_client(base_url: str | None, api_key: str | None) -> Any:
    try:
        from openai import OpenAI
    except ImportError:
        return None
    kwargs: dict[str, Any] = {}
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key
    return OpenAI(**kwargs)


def _call_llm(client: Any, model: str, prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
        temperature=0.4,
    )
    return response.choices[0].message.content.strip()


def _llm_or_fallback(
    client: Any, model: str, prompt: str, fallback: str,
) -> str:
    if client is None:
        return fallback
    try:
        return _call_llm(client, model, prompt)
    except Exception as exc:
        print(f"  LLM 调用失败：{exc}，使用回退内容", file=sys.stderr)
        return fallback


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _format_paper_callout(p: ParsedPaper) -> str:
    topics_str = ", ".join(p.topics) if p.topics else "未分类"
    lines = [
        f"> [!tip] [{p.title}]({p.url})",
        f"> 主题：{topics_str} | 评分：{p.score:.1f}",
    ]
    if p.authors:
        lines.append(f"> 作者：{p.authors}")
    if p.summary_zh:
        lines.append(f">")
        lines.append(f"> {p.summary_zh[:300]}")
    return "\n".join(lines)


def _format_paper_table_row(p: ParsedPaper) -> str:
    topics_str = ", ".join(p.topics[:2]) if p.topics else ""
    title_link = f"[{p.title}]({p.url})" if p.url else p.title
    return f"| {title_link} | {topics_str} | {p.published_date} | {p.score:.1f} |"


def format_top_papers(papers: list[ParsedPaper], callout_n: int = 3) -> str:
    if not papers:
        return "_本期没有匹配到论文。_"
    parts: list[str] = []
    # Top N as callout blocks
    for p in papers[:callout_n]:
        parts.append(_format_paper_callout(p))
    # Rest as table
    rest = papers[callout_n:]
    if rest:
        parts.append("")
        parts.append("| 论文标题 | 主题 | 发布日期 | 评分 |")
        parts.append("| -------- | ---- | :------: | :--: |")
        for p in rest:
            parts.append(_format_paper_table_row(p))
    return "\n\n".join(parts) if parts[:callout_n] else "\n".join(parts)


def format_topic_distribution(
    topic_counts: dict[str, int],
    topic_trend: dict[str, list[int]],
) -> str:
    if not topic_counts:
        return "_本期无主题数据。_"
    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
    lines: list[str] = []
    for topic, count in sorted_topics:
        trend = topic_trend.get(topic, [])
        spark = "".join("█" if v > 0 else "░" for v in trend) if trend else ""
        lines.append(f"- **{topic}**：{count} 篇 `{spark}`")
    return "\n".join(lines)


def format_hotspot_recap(hotspots: list, limit: int = 5) -> str:
    if not hotspots:
        return "_本期无社区热点数据。_"
    lines: list[str] = []
    seen_platforms: dict[str, int] = {}
    for h in hotspots:
        platform = h.platform or "其他"
        seen_platforms[platform] = seen_platforms.get(platform, 0) + 1
    for platform, count in sorted(seen_platforms.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- **{platform}**：{count} 条热点")
    # Show top items
    top = hotspots[:limit]
    if top:
        lines.append("")
        for h in top:
            tag = f"[{h.platform}]" if h.platform else ""
            lines.append(f"- {tag} [{h.title}]({h.url})")
    return "\n".join(lines)


def format_source_notes(agg: PeriodAggregate) -> str:
    lines = [
        f"本报告基于 {agg.start_date} 至 {agg.end_date} 期间的 {agg.daily_briefs_found} 份日报汇总生成。",
        f"共处理 {agg.total_candidates} 篇候选论文，{agg.total_high_signal} 篇高信号论文。",
    ]
    if not agg.top_papers:
        lines.append("本期内未检索到可排序的论文（可能是周末/假期）。")
    return "\n> ".join(lines)


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

def _build_overview_prompt(agg: PeriodAggregate, period_label: str) -> str:
    paper_lines = []
    for p in agg.top_papers[:10]:
        topics = ", ".join(p.topics) if p.topics else ""
        paper_lines.append(f"- [{p.score:.1f}] {p.title} ({topics})")
    papers_text = "\n".join(paper_lines) if paper_lines else "本期无论文数据"

    topic_text = ", ".join(
        f"{t}({c}篇)" for t, c in sorted(agg.topic_counts.items(), key=lambda x: x[1], reverse=True)
    ) or "无"

    overviews = "\n".join(agg.daily_overviews[:7]) if agg.daily_overviews else "无每日概览"

    return (
        f"你是一位学术情报分析师。请根据以下数据，用中文写 2-3 段{period_label}概述，"
        f"总结本期学术追踪的关键发展、趋势变化和值得关注的方向。语气专业简洁。\n\n"
        f"时间范围：{agg.start_date} ~ {agg.end_date}\n"
        f"日报数量：{agg.daily_briefs_found}\n"
        f"主题分布：{topic_text}\n\n"
        f"重点论文：\n{papers_text}\n\n"
        f"每日概览摘要：\n{overviews}\n\n"
        f"只输出中文概述段落，不要标题，不要 Markdown 格式符号。"
    )


def _build_watchlist_prompt(agg: PeriodAggregate) -> str:
    late_papers = [p for p in agg.top_papers if p.score > 0][-5:]
    items = "\n".join(f"- {p.title} ({', '.join(p.topics)})" for p in late_papers) or "无"
    return (
        "你是一位学术情报分析师。根据本周追踪到的最新动向，"
        "建议 3-5 个值得下周持续关注的研究方向或具体论文。"
        f"用中文列表输出。\n\n本周末段关注项：\n{items}\n\n"
        "只输出中文建议列表，不要标题。"
    )


def _build_next_month_prompt(agg: PeriodAggregate) -> str:
    topic_text = ", ".join(
        f"{t}({c}篇)" for t, c in sorted(agg.topic_counts.items(), key=lambda x: x[1], reverse=True)
    ) or "无"
    return (
        "你是一位学术情报分析师。基于本月主题趋势和论文分布，"
        "建议下个月重点关注的 3-5 个研究方向。"
        f"用中文输出。\n\n本月主题分布：{topic_text}\n\n"
        "只输出中文建议，不要标题。"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="生成学术周报或月报。")
    ap.add_argument(
        "--period", required=True, choices=["weekly", "monthly"],
        help="报告周期类型",
    )
    ap.add_argument("--config", default=str(DEFAULT_LOCAL_CONFIG))
    ap.add_argument("--date", default=str(date.today()), help="目标日期 (YYYY-MM-DD)")
    ap.add_argument("--out", default="", help="输出路径（默认写入 Obsidian）")
    ap.add_argument("--skip-llm", action="store_true", help="跳过 LLM 叙述生成")
    ap.add_argument("--dry-run", action="store_true", help="只打印摘要，不写文件")
    args = ap.parse_args()

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        print(missing_local_config_message(config_path), file=sys.stderr)
        sys.exit(1)
    config = load_yaml(str(config_path))
    if not isinstance(config, dict):
        config = {}

    # Compute date range
    target = date.fromisoformat(args.date)
    period_id = compute_period_id(target, args.period)
    start_date, end_date = compute_date_range(target, args.period)
    period_label = "周报" if args.period == "weekly" else "月报"

    print(f"生成{period_label}：{period_id}（{start_date} ~ {end_date}）")

    # Find and parse daily briefs
    vault = obsidian_root(config)
    if vault is None:
        print("错误：未配置 obsidian.vault_path", file=sys.stderr)
        sys.exit(1)

    brief_paths = find_daily_briefs(vault, start_date, end_date)
    print(f"  找到 {len(brief_paths)} 份日报")

    if not brief_paths:
        print("  没有找到任何日报，跳过生成。", file=sys.stderr)
        sys.exit(0)

    briefs: list[DailyBriefData] = []
    for p in brief_paths:
        try:
            briefs.append(parse_daily_brief(p))
            print(f"  ✓ 解析 {p.name}")
        except Exception as exc:
            print(f"  ✗ 解析失败 {p.name}: {exc}", file=sys.stderr)

    # Aggregate
    agg = aggregate_briefs(briefs, args.period, period_id, start_date, end_date)

    # Threshold check
    thresholds_path = DEFAULT_THRESHOLDS_CONFIG
    thresholds = load_yaml(str(thresholds_path)) if thresholds_path.exists() else {}
    if not isinstance(thresholds, dict):
        thresholds = {}
    passes, reasons = check_thresholds(agg, thresholds)
    if not passes:
        print(f"  ⚠ 阈值未满足：{'; '.join(reasons)}")
        print("  仍将继续生成报告，但会在报告中标注。")

    if args.dry_run:
        print(f"\n[Dry run] {period_label} {period_id}")
        print(f"  日报：{agg.daily_briefs_found} 份")
        print(f"  候选：{agg.total_candidates} 篇")
        print(f"  高信号：{agg.total_high_signal} 篇")
        print(f"  去重后论文：{len(agg.top_papers)} 篇")
        print(f"  热点：{len(agg.hotspot_highlights)} 条")
        print(f"  主题：{dict(agg.topic_counts)}")
        return

    # LLM client
    client = None
    model = DEFAULT_MODEL
    if not args.skip_llm:
        base_url, api_key, model = _resolve_llm_settings(config)
        client = _make_client(base_url, api_key)
        if client:
            print(f"  LLM：{model}")
        else:
            print("  LLM 未配置（缺少 openai 包或凭证），使用数据回退模式")

    # Build template variables
    fallback_overview = (
        f"本{period_label}覆盖 {agg.start_date} 至 {agg.end_date}，"
        f"共汇总 {agg.daily_briefs_found} 份日报，"
        f"{agg.total_candidates} 篇候选论文，"
        f"{agg.total_high_signal} 篇高信号论文。"
    )
    if not passes:
        fallback_overview += f" 注意：{'; '.join(reasons)}。"

    overview = _llm_or_fallback(
        client, model,
        _build_overview_prompt(agg, period_label),
        fallback_overview,
    )
    if overview:
        print("  ✓ 概述已生成")

    top_papers_text = format_top_papers(agg.top_papers)
    topic_text = format_topic_distribution(agg.topic_counts, agg.topic_trend)
    hotspot_text = format_hotspot_recap(agg.hotspot_highlights)
    source_text = format_source_notes(agg)

    # Load and render template
    if args.period == "weekly":
        template_path = DEFAULT_WEEKLY_TEMPLATE
        watchlist = _llm_or_fallback(
            client, model,
            _build_watchlist_prompt(agg),
            "_LLM 未配置，无法生成观察清单。_",
        )
        if watchlist and client:
            print("  ✓ 观察清单已生成")

        values = {
            "week_id": period_id,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "briefs_count": str(agg.daily_briefs_found),
            "papers_count": str(len(agg.top_papers)),
            "overview": overview,
            "top_papers": top_papers_text,
            "topic_shifts": topic_text,
            "hotspot_recap": hotspot_text,
            "watchlist": watchlist,
            "source_notes": source_text,
        }
        default_out_fn = obsidian_weekly_path
        default_out_arg = period_id
    else:
        template_path = DEFAULT_MONTHLY_TEMPLATE
        next_month = _llm_or_fallback(
            client, model,
            _build_next_month_prompt(agg),
            "_LLM 未配置，无法生成下月建议。_",
        )
        if next_month and client:
            print("  ✓ 下月建议已生成")

        values = {
            "month_id": period_id,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "briefs_count": str(agg.daily_briefs_found),
            "papers_count": str(len(agg.top_papers)),
            "overview": overview,
            "representative_papers": top_papers_text,
            "topic_trends": topic_text,
            "hotspot_recap": hotspot_text,
            "next_month": next_month,
            "source_notes": source_text,
        }
        default_out_fn = obsidian_monthly_path
        default_out_arg = period_id

    template = template_path.read_text(encoding="utf-8")
    content = render_template(template, values)

    # Resolve output path
    if args.out:
        out_path = args.out
    else:
        obsidian_path = default_out_fn(config, default_out_arg)
        if obsidian_path:
            out_path = str(obsidian_path)
        else:
            out_path = str(REPO_ROOT / "output" / f"{period_id}-{args.period}.md")

    write_text(out_path, content)
    print(f"\n{period_label}已写入 {display_path(out_path)}")


if __name__ == "__main__":
    main()
