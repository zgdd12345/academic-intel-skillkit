from __future__ import annotations

import argparse
from typing import Any

import yaml
from pathlib import Path

from common import (
    ARXIV_QUERY_KEYWORD_LIMIT,
    DEFAULT_LOCAL_CONFIG,
    arxiv_source_config,
    arxiv_topic_query_details,
    build_arxiv_query_plan,
    config_topics,
    configured_arxiv_topic_ids,
    effective_arxiv_topic_ids,
    load_yaml,
    missing_local_config_message,
    select_topics,
    topic_id as get_topic_id,
    validate_config,
)


def clean_list(values: Any) -> list[str]:
    raw_values = values if isinstance(values, list) else []
    return [str(value).strip() for value in raw_values if str(value).strip()]


def topic_id(topic: dict[str, Any]) -> str:
    return get_topic_id(topic) or "<missing-id>"


def topic_name(topic: dict[str, Any]) -> str:
    return str(topic.get("name") or topic_id(topic)).strip()


def topic_status(topic: dict[str, Any]) -> str:
    return "启用" if topic.get("enabled", True) else "停用"


def selected_topics(config: dict[str, Any], topic_id: str = "") -> list[dict[str, Any]]:
    topic_ids = [topic_id] if topic_id else []
    return select_topics(config, topic_ids, enabled_only=False)


def format_topic_list(topics: list[dict[str, Any]]) -> str:
    if not topics:
        return "未找到主题配置。"

    lines: list[str] = []
    for topic in topics:
        topic_key = topic_id(topic)
        name = topic_name(topic)
        status = topic_status(topic)
        priority = str(topic.get("priority") or "未设置").strip()
        include_keywords = len(clean_list(topic.get("include_keywords")))
        exclude_keywords = len(clean_list(topic.get("exclude_keywords")))
        categories = len(clean_list(topic.get("arxiv_categories")))
        lines.append(
            f"- {topic_key} | {status} | priority={priority} | 包含关键词={include_keywords} | "
            f"排除关键词={exclude_keywords} | arXiv 分类={categories} | 名称={name}"
        )
    return "主题总览\n" + "\n".join(lines)


def format_topic_detail(topics: list[dict[str, Any]]) -> str:
    if not topics:
        return "未找到主题配置。"

    blocks: list[str] = []
    for topic in topics:
        topic_key = topic_id(topic)
        name = topic_name(topic)
        status = topic_status(topic)
        priority = str(topic.get("priority") or "未设置").strip()
        include_keywords = ", ".join(clean_list(topic.get("include_keywords"))) or "无"
        exclude_keywords = ", ".join(clean_list(topic.get("exclude_keywords"))) or "无"
        categories = ", ".join(clean_list(topic.get("arxiv_categories"))) or "无"
        blocks.append(
            "\n".join(
                [
                    f"主题：{topic_key}",
                    f"名称：{name}",
                    f"状态：{status}",
                    f"优先级：{priority}",
                    f"包含关键词：{include_keywords}",
                    f"排除关键词：{exclude_keywords}",
                    f"arXiv 分类：{categories}",
                ]
            )
        )
    return "\n\n".join(blocks)


def format_validation_summary(config: dict[str, Any]) -> str:
    topics = config_topics(config)
    enabled_count = sum(1 for topic in topics if topic.get("enabled", True))
    disabled_count = max(0, len(topics) - enabled_count)
    arxiv_config = arxiv_source_config(config)
    source_enabled = arxiv_config.get("enabled", True)
    configured_topic_ids = configured_arxiv_topic_ids(config)
    if configured_topic_ids:
        scoped_count = sum(1 for topic in topics if topic.get("enabled", True) and topic_id(topic) in set(configured_topic_ids))
        scope_note = f"显式限制为 {', '.join(configured_topic_ids)}"
    else:
        scoped_count = enabled_count
        scope_note = "未显式限制，默认覆盖全部启用主题"
    return "\n".join(
        [
            "配置概览：",
            f"- topic 总数={len(topics)} | 启用={enabled_count} | 停用={disabled_count}",
            f"- arXiv 数据源={'启用' if source_enabled else '停用'} | 默认抓取范围={scoped_count} 个 topic | {scope_note}",
        ]
    )


def print_validation(config: dict[str, Any]) -> int:
    errors, warnings = validate_config(config)
    print(format_validation_summary(config))
    if warnings:
        print("警告：")
        for warning in warnings:
            print(f"- {warning}")
    if errors:
        print("错误：")
        for error in errors:
            print(f"- {error}")
        return 1
    print("配置校验通过。")
    return 0


def parse_int_setting(raw_value: Any, fallback: int) -> int:
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return fallback


def topic_scope_note(topic: dict[str, Any], config: dict[str, Any]) -> str:
    source_enabled = arxiv_source_config(config).get("enabled", True)
    configured_topic_ids = configured_arxiv_topic_ids(config)
    if not source_enabled:
        return "未纳入抓取：当前 arXiv 数据源已停用"
    if not topic.get("enabled", True):
        return "未纳入抓取：当前 topic 已停用"
    if configured_topic_ids and topic_id(topic) not in set(configured_topic_ids):
        return "未纳入抓取：不在 sources.arxiv.topic_ids 范围内"
    return "纳入默认抓取"


def topic_diagnostic_notes(topic: dict[str, Any], config: dict[str, Any]) -> list[str]:
    details = arxiv_topic_query_details(topic)
    notes: list[str] = []
    configured_topic_ids = configured_arxiv_topic_ids(config)
    source_enabled = arxiv_source_config(config).get("enabled", True)

    if not source_enabled:
        notes.append("当前 arXiv 数据源已停用，抓取脚本会直接输出空结果。")
    if not topic.get("enabled", True):
        notes.append("当前 topic 已停用，不会进入默认抓取计划。")
    if configured_topic_ids and topic.get("enabled", True) and topic_id(topic) not in set(configured_topic_ids):
        notes.append("当前 sources.arxiv.topic_ids 对抓取范围做了显式限制，这个 topic 不会被默认抓取。")
    if details["uses_default_query"]:
        notes.append("未配置包含关键词或 arXiv 分类；查询会回退到默认 `cat:cs.AI`，相关性较弱。")
    if details["dropped_include_keywords"]:
        notes.append(
            f"包含关键词共 {len(details['include_keywords'])} 个，但 arXiv 查询只会使用前 {ARXIV_QUERY_KEYWORD_LIMIT} 个。"
        )
    if details["dropped_exclude_keywords"]:
        notes.append(
            f"排除关键词共 {len(details['exclude_keywords'])} 个，但 arXiv 查询只会使用前 {ARXIV_QUERY_KEYWORD_LIMIT} 个。"
        )
    return notes or ["未发现明显配置风险。"]


def format_query_plan(config: dict[str, Any], selected_topic: str = "") -> str:
    arxiv_config = arxiv_source_config(config)
    source_enabled = arxiv_config.get("enabled", True)
    selected_topic_ids = effective_arxiv_topic_ids(config, [selected_topic] if selected_topic else [])
    selected_topics_for_display = selected_topics(config, topic_id=selected_topic)
    topic_map = {topic_id(topic): topic for topic in selected_topics_for_display}
    query_plan = build_arxiv_query_plan(config, selected_topic_ids=selected_topic_ids)
    lookback_days = parse_int_setting(arxiv_config.get("lookback_days", 0), 0)
    max_results = parse_int_setting(arxiv_config.get("max_results_per_topic", 25), 25)

    lines = [
        "arXiv 抓取计划",
        f"- 数据源状态：{'启用' if source_enabled else '停用'}",
        f"- lookback_days={lookback_days} | max_results_per_topic={max_results}",
        f"- 实际纳入查询的 topic 数={len(query_plan)}",
    ]

    if selected_topic_ids:
        lines.append(f"- 生效 topic 过滤：{', '.join(selected_topic_ids)}")
    else:
        lines.append("- 生效 topic 过滤：未显式限制，默认覆盖全部启用主题")

    if not source_enabled:
        lines.append("- 当前 arXiv 数据源已停用；执行抓取时会直接写出空结果。")

    if not query_plan:
        lines.append("- 当前没有可执行的 arXiv 查询计划。请检查主题是否启用，以及是否至少配置了关键词或分类。")
        for selected_topic in selected_topics_for_display:
            lines.append(f"- {topic_id(selected_topic)} | 状态={topic_scope_note(selected_topic, config)}")
        return "\n".join(lines)

    for entry in query_plan:
        details = arxiv_topic_query_details(topic_map.get(entry["topic_id"], {}))
        include_note = f"{len(details['active_include_keywords'])}/{len(details['include_keywords'])}"
        exclude_note = f"{len(details['active_exclude_keywords'])}/{len(details['exclude_keywords'])}"
        lines.append(
            f"- {entry['topic_id']} | 名称={entry['topic_name']} | 包含关键词={include_note} | "
            f"排除关键词={exclude_note} | 分类={len(details['categories'])}"
        )
        lines.append(f"  查询={entry['query']}")
    return "\n".join(lines)


def format_topic_diagnostics(config: dict[str, Any], topics: list[dict[str, Any]]) -> str:
    if not topics:
        return "未找到主题配置。"

    blocks: list[str] = []
    for topic in topics:
        details = arxiv_topic_query_details(topic)
        notes = topic_diagnostic_notes(topic, config)
        blocks.append(
            "\n".join(
                [
                    f"主题：{topic_id(topic)}",
                    f"名称：{topic_name(topic)}",
                    f"状态：{topic_status(topic)}",
                    f"arXiv 抓取：{topic_scope_note(topic, config)}",
                    (
                        "包含关键词："
                        f"{len(details['include_keywords'])} 个"
                        f"（实际进入查询 {len(details['active_include_keywords'])} 个"
                        f"，截断 {len(details['dropped_include_keywords'])} 个）"
                    ),
                    (
                        "排除关键词："
                        f"{len(details['exclude_keywords'])} 个"
                        f"（实际进入查询 {len(details['active_exclude_keywords'])} 个"
                        f"，截断 {len(details['dropped_exclude_keywords'])} 个）"
                    ),
                    f"arXiv 分类：{len(details['categories'])} 个",
                    f"查询预览：{details['query']}",
                    "诊断：",
                    *[f"- {note}" for note in notes],
                ]
            )
        )
    return "\n\n".join(blocks)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="查看或校验本地 topic 配置。当前脚本只读，不会修改配置文件。"
    )
    ap.add_argument("--config", default=str(DEFAULT_LOCAL_CONFIG))
    ap.add_argument("--topic", default="")
    mode_group = ap.add_mutually_exclusive_group()
    mode_group.add_argument("--print", action="store_true")
    mode_group.add_argument("--list", action="store_true")
    mode_group.add_argument("--detail", action="store_true")
    mode_group.add_argument("--validate", action="store_true")
    mode_group.add_argument("--query-plan", action="store_true")
    mode_group.add_argument("--diagnose", action="store_true")
    args = ap.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        raise SystemExit(missing_local_config_message(config_path))

    config = load_yaml(args.config)
    if not isinstance(config, dict):
        config = {}
    topics = selected_topics(config, topic_id=args.topic)
    if args.topic and not topics:
        raise SystemExit(f"未找到主题：{args.topic}")

    if args.print:
        print(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
        return

    if args.validate:
        raise SystemExit(print_validation(config))

    if args.query_plan:
        print(format_query_plan(config, selected_topic=args.topic))
        return

    if args.diagnose:
        print(format_topic_diagnostics(config, topics))
        return

    if args.detail:
        print(format_topic_detail(topics))
        return

    print(format_topic_list(topics))


if __name__ == "__main__":
    main()
