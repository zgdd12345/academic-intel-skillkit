from __future__ import annotations

from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import re
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_CONFIG = REPO_ROOT / "config" / "research-topics.local.yaml"
DEFAULT_DAILY_TEMPLATE = REPO_ROOT / "templates" / "daily-brief-template.md"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output"
DEFAULT_ARXIV_OUTPUT = DEFAULT_OUTPUT_DIR / "arxiv.json"
DEFAULT_HUGGINGFACE_OUTPUT = DEFAULT_OUTPUT_DIR / "huggingface.json"
DEFAULT_DAILY_BRIEF_OUTPUT = DEFAULT_OUTPUT_DIR / "daily-brief.md"
ARXIV_QUERY_KEYWORD_LIMIT = 6


@dataclass
class CandidateItem:
    source: str
    title: str
    url: str
    summary: str = ""
    summary_zh: str = ""
    authors: list[str] | None = None
    affiliations: list[str] | None = None
    institutions: list[str] | None = None
    venue: str | None = None
    paper_id: str | None = None
    published_at: str | None = None
    topic_scores: dict[str, float] | None = None
    score: float = 0.0
    categories: list[str] | None = None
    matched_topics: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def coerce_str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    raw_values = value if isinstance(value, list) else [value]
    clean_values = [str(item).strip() for item in raw_values if str(item).strip()]
    return clean_values or None


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_authors(value: Any) -> list[str] | None:
    if value is None:
        return None
    raw_authors = value if isinstance(value, list) else [value]
    authors: list[str] = []
    for author in raw_authors:
        if isinstance(author, dict):
            name = coerce_optional_str(author.get("name") or author.get("authorName"))
        else:
            name = coerce_optional_str(author)
        if name and name not in authors:
            authors.append(name)
    return authors or None


def normalize_named_entities(value: Any, keys: tuple[str, ...]) -> list[str] | None:
    if value is None:
        return None
    raw_values = value if isinstance(value, list) else [value]
    entities: list[str] = []
    for raw_value in raw_values:
        if isinstance(raw_value, dict):
            entity = None
            for key in keys:
                entity = coerce_optional_str(raw_value.get(key))
                if entity:
                    break
        else:
            entity = coerce_optional_str(raw_value)
        if entity and entity not in entities:
            entities.append(entity)
    return entities or None


def coerce_named_value(value: Any, keys: tuple[str, ...] = ("name", "title", "display_name")) -> str | None:
    if isinstance(value, dict):
        for key in keys:
            text = coerce_optional_str(value.get(key))
            if text:
                return text
        return None
    return coerce_optional_str(value)


def normalize_topic_scores(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    scores: dict[str, float] = {}
    for topic_id, score in value.items():
        try:
            scores[str(topic_id)] = float(score)
        except (TypeError, ValueError):
            continue
    return scores or None


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())).strip()


def normalize_title(text: str) -> str:
    return normalize_text(text)


def normalize_paper_id(text: str) -> str:
    return re.sub(r"v\d+$", "", (text or "").strip().lower())


def item_key(item: CandidateItem) -> str:
    base = (
        normalize_paper_id(item.paper_id or "")
        or (item.url or "").strip().lower()
        or normalize_title(item.title)
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def load_yaml(path: str) -> Any:
    import yaml

    with open(path, "r", encoding="utf-8") as file_handle:
        return yaml.safe_load(file_handle)


def config_topics(config: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(config, dict):
        return []
    return [topic for topic in config.get("topics", []) if isinstance(topic, dict)]


def topic_id(topic: dict[str, Any]) -> str:
    return str(topic.get("id") or "").strip()


def select_topics(
    config: dict[str, Any],
    topic_ids: Iterable[str] | None = None,
    *,
    enabled_only: bool = False,
) -> list[dict[str, Any]]:
    topics = config_topics(config)
    selected = ordered_unique(str(raw_topic_id).strip() for raw_topic_id in (topic_ids or []) if str(raw_topic_id).strip())
    if selected:
        selected_ids = set(selected)
        topics = [topic for topic in topics if topic_id(topic) in selected_ids]
    if enabled_only:
        topics = [topic for topic in topics if topic.get("enabled", True)]
    return topics


def arxiv_source_config(config: dict[str, Any]) -> dict[str, Any]:
    sources = config.get("sources", {}) if isinstance(config, dict) else {}
    if not isinstance(sources, dict):
        return {}
    arxiv_config = sources.get("arxiv", {})
    return arxiv_config if isinstance(arxiv_config, dict) else {}


def configured_arxiv_topic_ids(config: dict[str, Any]) -> list[str]:
    topic_ids = arxiv_source_config(config).get("topic_ids", [])
    if not isinstance(topic_ids, list):
        return []
    return ordered_unique(str(raw_topic_id).strip() for raw_topic_id in topic_ids if str(raw_topic_id).strip())


def effective_arxiv_topic_ids(config: dict[str, Any], cli_topic_ids: Iterable[str] | None = None) -> list[str]:
    cli_selected = ordered_unique(str(raw_topic_id).strip() for raw_topic_id in (cli_topic_ids or []) if str(raw_topic_id).strip())
    if cli_selected:
        return cli_selected
    return configured_arxiv_topic_ids(config)


def build_arxiv_keyword_terms(values: Iterable[Any], *, limit: int = ARXIV_QUERY_KEYWORD_LIMIT) -> list[str]:
    terms: list[str] = []
    for raw_value in values:
        keyword = str(raw_value).strip()
        if not keyword:
            continue
        if any(character in keyword for character in [" ", "-"]):
            terms.append(f'all:"{keyword}"')
        else:
            terms.append(f"all:{keyword}")
        if len(terms) >= limit:
            break
    return terms


def arxiv_topic_query_details(topic: dict[str, Any]) -> dict[str, Any]:
    raw_keywords = topic.get("include_keywords", []) if isinstance(topic.get("include_keywords", []), list) else []
    raw_exclude_keywords = topic.get("exclude_keywords", []) if isinstance(topic.get("exclude_keywords", []), list) else []
    raw_categories = topic.get("arxiv_categories", []) if isinstance(topic.get("arxiv_categories", []), list) else []
    keywords = [str(keyword).strip() for keyword in raw_keywords if str(keyword).strip()]
    exclude_keywords = [str(keyword).strip() for keyword in raw_exclude_keywords if str(keyword).strip()]
    categories = [str(category).strip() for category in raw_categories if str(category).strip()]
    active_keywords = keywords[:ARXIV_QUERY_KEYWORD_LIMIT]
    dropped_keywords = keywords[ARXIV_QUERY_KEYWORD_LIMIT:]
    active_exclude_keywords = exclude_keywords[:ARXIV_QUERY_KEYWORD_LIMIT]
    dropped_exclude_keywords = exclude_keywords[ARXIV_QUERY_KEYWORD_LIMIT:]
    keyword_terms = build_arxiv_keyword_terms(active_keywords)
    exclude_terms = build_arxiv_keyword_terms(active_exclude_keywords)
    category_terms = [f"cat:{category}" for category in categories]
    keyword_part = f"({' OR '.join(keyword_terms)})" if keyword_terms else ""
    exclude_part = f"({' OR '.join(exclude_terms)})" if exclude_terms else ""
    category_part = f"({' OR '.join(category_terms)})" if category_terms else ""
    positive_parts = [part for part in (keyword_part, category_part) if part]
    uses_default_query = not positive_parts
    query = " AND ".join(positive_parts) if positive_parts else "cat:cs.AI"
    if exclude_part:
        query = f"{query} ANDNOT {exclude_part}"
    return {
        "include_keywords": keywords,
        "active_include_keywords": active_keywords,
        "dropped_include_keywords": dropped_keywords,
        "exclude_keywords": exclude_keywords,
        "active_exclude_keywords": active_exclude_keywords,
        "dropped_exclude_keywords": dropped_exclude_keywords,
        "categories": categories,
        "uses_default_query": uses_default_query,
        "query": query,
    }


def build_arxiv_topic_query(topic: dict[str, Any]) -> str:
    return str(arxiv_topic_query_details(topic)["query"])


def build_arxiv_query_plan(config: dict[str, Any], selected_topic_ids: Iterable[str] | None = None) -> list[dict[str, str]]:
    topics = select_topics(config, selected_topic_ids, enabled_only=True)
    return [
        {
            "topic_id": topic_id(topic),
            "topic_name": str(topic.get("name") or topic_id(topic)),
            "query": build_arxiv_topic_query(topic),
        }
        for topic in topics
        if topic_id(topic)
    ]


def display_path(path: str | Path) -> str:
    candidate_path = Path(path)
    try:
        return candidate_path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(candidate_path)


def missing_local_config_message(path: str | Path = DEFAULT_LOCAL_CONFIG) -> str:
    config_path = Path(path)
    example_path = DEFAULT_LOCAL_CONFIG.parent / "research-topics.example.yaml"
    if config_path.resolve() == DEFAULT_LOCAL_CONFIG.resolve():
        return (
            f"未找到本地配置文件：{display_path(config_path)}。"
            f"请先执行：cp {display_path(example_path)} {display_path(DEFAULT_LOCAL_CONFIG)}"
        )
    return f"未找到配置文件：{display_path(config_path)}"


def obsidian_root(config: dict[str, Any]) -> Path | None:
    if not isinstance(config, dict):
        return None
    obsidian = config.get("obsidian", {})
    if not isinstance(obsidian, dict):
        return None
    vault_path = coerce_optional_str(obsidian.get("vault_path"))
    root_dir = coerce_optional_str(obsidian.get("root_dir"))
    if not vault_path or not root_dir:
        return None
    return Path(vault_path).expanduser() / root_dir


def obsidian_daily_brief_path(config: dict[str, Any], target_date: str) -> Path | None:
    root = obsidian_root(config)
    if root is None:
        return None
    note_date = str(target_date).strip().replace("-", "_")
    return root / "01_Daily" / f"{note_date}_Daily.md"


class JsonLoadError(RuntimeError):
    pass


def load_json(path: str | Path, default: Any = None, *, strict: bool = False) -> Any:
    if not path:
        if strict:
            raise JsonLoadError("未提供必需的 JSON 输入路径。")
        return {} if default is None else default
    candidate_path = Path(path)
    if not candidate_path.exists():
        if strict:
            raise JsonLoadError(f"未找到 JSON 文件：{display_path(candidate_path)}")
        return {} if default is None else default
    try:
        with open(candidate_path, "r", encoding="utf-8") as file_handle:
            return json.load(file_handle)
    except json.JSONDecodeError as exc:
        if strict:
            raise JsonLoadError(
                f"JSON 解析失败：{display_path(candidate_path)}:{exc.lineno}:{exc.colno} ({exc.msg})"
            ) from exc
    except OSError as exc:
        if strict:
            raise JsonLoadError(f"读取 JSON 文件失败：{display_path(candidate_path)} ({exc})") from exc
        return {} if default is None else default
    return {} if default is None else default


def write_text(path: str, content: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def render_template(template: str, values: dict[str, str]) -> str:
    rendered = re.sub(r"^\s*<!--.*?-->\s*", "", template, count=1, flags=re.DOTALL)
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump_json(path: str, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, ensure_ascii=False, indent=2)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def enabled_topics(config: dict[str, Any]) -> list[dict[str, Any]]:
    return select_topics(config, enabled_only=True)


def validate_config(config: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(config, dict):
        return ["配置文件根节点必须是一个映射。"], warnings

    topics_value = config.get("topics", [])
    if topics_value is None:
        topics_value = []
    if not isinstance(topics_value, list):
        errors.append("`topics` 必须是列表。")
        topics: list[dict[str, Any]] = []
    else:
        topics = []
        seen_topic_ids: set[str] = set()
        enabled_count = 0
        for index, raw_topic in enumerate(topics_value, start=1):
            if not isinstance(raw_topic, dict):
                errors.append(f"主题 #{index} 必须是映射。")
                continue
            topics.append(raw_topic)
            topic_id = str(raw_topic.get("id") or "").strip()
            if not topic_id:
                errors.append(f"主题 #{index} 缺少 `id`。")
                continue
            if topic_id in seen_topic_ids:
                errors.append(f"发现重复的 topic id：`{topic_id}`。")
            seen_topic_ids.add(topic_id)
            if raw_topic.get("enabled", True):
                enabled_count += 1
            include_keywords = normalize_keywords(list_or_empty(raw_topic.get("include_keywords")))
            categories = [
                str(category).strip()
                for category in list_or_empty(raw_topic.get("arxiv_categories"))
                if str(category).strip()
            ]
            for field_name in ("include_keywords", "exclude_keywords", "arxiv_categories"):
                field_value = raw_topic.get(field_name)
                if field_value is not None and not isinstance(field_value, list):
                    warnings.append(f"主题 `{topic_id}` 的 `{field_name}` 建议使用列表。")
            if raw_topic.get("enabled", True) and not include_keywords and not categories:
                warnings.append(
                    f"启用中的主题 `{topic_id}` 没有 include_keywords 或 arXiv categories，可能永远匹配不到论文。"
                )
            priority = str(raw_topic.get("priority") or "").strip().lower()
            if priority and priority not in {"high", "medium", "low"}:
                warnings.append(
                    f"主题 `{topic_id}` 使用了未识别的 priority `{raw_topic.get('priority')}`；建议使用 high、medium 或 low。"
                )
        if enabled_count == 0:
            warnings.append("当前没有启用任何主题。")

    topic_ids = {str(topic.get("id")).strip() for topic in topics if str(topic.get("id") or "").strip()}

    reporting = config.get("reporting", {})
    if reporting and not isinstance(reporting, dict):
        errors.append("`reporting` 存在时必须是映射。")
        reporting = {}

    def parse_int_setting(raw_value: Any, setting_name: str) -> int | None:
        if raw_value is None or raw_value == "":
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            errors.append(f"`{setting_name}` 必须是整数。")
            return None

    daily_top_n = parse_int_setting(reporting.get("daily_top_n"), "reporting.daily_top_n")
    detailed_top_n = parse_int_setting(reporting.get("daily_detailed_top_n"), "reporting.daily_detailed_top_n")
    if daily_top_n is not None and daily_top_n <= 0:
        errors.append("`reporting.daily_top_n` 必须大于 0。")
    if detailed_top_n is not None and detailed_top_n < 0:
        errors.append("`reporting.daily_detailed_top_n` 必须大于等于 0。")
    if (
        daily_top_n is not None
        and detailed_top_n is not None
        and daily_top_n > 0
        and detailed_top_n > daily_top_n
    ):
        warnings.append(
            "`reporting.daily_detailed_top_n` 大于 `reporting.daily_top_n`；详细条目数量会在最终 shortlist 中被截断。"
        )

    sources = config.get("sources", {})
    if sources and not isinstance(sources, dict):
        errors.append("`sources` 存在时必须是映射。")
        sources = {}
    arxiv_config = sources.get("arxiv", {})
    if arxiv_config and not isinstance(arxiv_config, dict):
        errors.append("`sources.arxiv` 存在时必须是映射。")
        arxiv_config = {}

    if isinstance(arxiv_config, dict):
        max_results = parse_int_setting(arxiv_config.get("max_results_per_topic"), "sources.arxiv.max_results_per_topic")
        lookback_days = parse_int_setting(arxiv_config.get("lookback_days"), "sources.arxiv.lookback_days")
        if max_results is not None and max_results <= 0:
            errors.append("`sources.arxiv.max_results_per_topic` 必须大于 0。")
        if lookback_days is not None and lookback_days < 0:
            errors.append("`sources.arxiv.lookback_days` 必须大于等于 0。")

        configured_topic_ids = arxiv_config.get("topic_ids", [])
        if configured_topic_ids in (None, ""):
            configured_topic_ids = []
        if configured_topic_ids and not isinstance(configured_topic_ids, list):
            errors.append("`sources.arxiv.topic_ids` 存在时必须是列表。")
        elif isinstance(configured_topic_ids, list):
            unknown_topic_ids = [
                str(topic_id).strip()
                for topic_id in configured_topic_ids
                if str(topic_id).strip() and str(topic_id).strip() not in topic_ids
            ]
            for topic_id in unknown_topic_ids:
                errors.append(f"`sources.arxiv.topic_ids` 引用了未知主题 `{topic_id}`。")

    return errors, warnings


def candidate_from_dict(data: dict[str, Any]) -> CandidateItem:
    categories_value = data.get("categories")
    if categories_value is None and isinstance(data.get("tags"), list):
        categories_value = [
            tag.get("term")
            for tag in data.get("tags", [])
            if isinstance(tag, dict) and tag.get("term")
        ]
    return CandidateItem(
        source=str(data.get("source", "unknown")),
        title=str(data.get("title") or data.get("name") or "").strip(),
        url=str(data.get("url") or data.get("link") or "").strip(),
        summary=str(data.get("summary") or data.get("abstract") or data.get("description") or "").replace("\n", " ").strip(),
        summary_zh=str(data.get("summary_zh") or data.get("summaryZh") or "").replace("\n", " ").strip(),
        authors=normalize_authors(data.get("authors")),
        affiliations=normalize_named_entities(
            data.get("affiliations"),
            ("name", "affiliation", "institution", "display_name"),
        ),
        institutions=normalize_named_entities(
            data.get("institutions"),
            ("name", "institution", "affiliation", "display_name"),
        ),
        venue=coerce_named_value(
            data.get("venue") or data.get("journal") or data.get("conference") or data.get("publicationVenue"),
            ("name", "venue", "journal", "conference", "display_name"),
        ),
        paper_id=coerce_optional_str(data.get("paper_id") or data.get("paperId") or data.get("id")),
        published_at=coerce_optional_str(data.get("published_at") or data.get("publicationDate") or data.get("published")),
        topic_scores=normalize_topic_scores(data.get("topic_scores")),
        score=coerce_float(data.get("score"), default=0.0),
        categories=coerce_str_list(categories_value),
        matched_topics=coerce_str_list(data.get("matched_topics")),
    )


def read_candidate_items(path: str | Path, *, strict: bool = False) -> list[CandidateItem]:
    payload = load_json(path, default={}, strict=strict)
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = payload.get("items", [])
    else:
        raw_items = []
    return [candidate_from_dict(item) for item in raw_items if isinstance(item, dict)]


def split_sources(source: str) -> list[str]:
    parts = [part.strip() for part in (source or "").split("+")]
    ordered: list[str] = []
    for part in parts:
        if part and part not in ordered:
            ordered.append(part)
    return ordered


def ordered_unique(values: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    for value in values:
        if value and value not in ordered:
            ordered.append(value)
    return ordered


def normalize_keywords(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        keyword = normalize_text(str(value))
        if keyword and keyword not in normalized:
            normalized.append(keyword)
    return normalized


def keyword_in_text(text: str, keyword: str) -> bool:
    if not text or not keyword:
        return False
    if " " in keyword:
        return keyword in text
    return re.search(r"\b" + re.escape(keyword) + r"s?\b", text) is not None


def merge_topic_scores(*score_maps: dict[str, float] | None) -> dict[str, float]:
    merged: dict[str, float] = {}
    for score_map in score_maps:
        if not score_map:
            continue
        for topic_id, score in score_map.items():
            try:
                numeric_score = float(score)
            except (TypeError, ValueError):
                continue
            merged[topic_id] = max(merged.get(topic_id, 0.0), numeric_score)
    return dict(sorted(merged.items(), key=lambda item: (-item[1], item[0])))


def match_topics(item: CandidateItem, topics: list[dict[str, Any]]) -> dict[str, float]:
    title_text = normalize_text(item.title)
    summary_text = normalize_text(item.summary)
    combined_text = f"{title_text} {summary_text}".strip()
    categories = {str(category).strip().lower() for category in item.categories or [] if str(category).strip()}
    priority_bonus = {"high": 0.6, "medium": 0.3, "low": 0.0}
    scores: dict[str, float] = {}

    for topic in topics:
        topic_id = str(topic.get("id") or topic.get("name") or "").strip()
        if not topic_id:
            continue
        include_keywords = normalize_keywords(list_or_empty(topic.get("include_keywords")))
        exclude_keywords = normalize_keywords(list_or_empty(topic.get("exclude_keywords")))
        topic_categories = {
            str(category).strip().lower()
            for category in list_or_empty(topic.get("arxiv_categories"))
            if str(category).strip()
        }
        title_hits = [keyword for keyword in include_keywords if keyword_in_text(title_text, keyword)]
        summary_hits = [
            keyword
            for keyword in include_keywords
            if keyword not in title_hits and keyword_in_text(summary_text, keyword)
        ]
        exclude_hits = [keyword for keyword in exclude_keywords if keyword_in_text(combined_text, keyword)]
        category_hits = topic_categories & categories
        base_score = (
            len(title_hits) * 1.6
            + len(summary_hits) * 0.9
            + len(category_hits) * 1.2
            - len(exclude_hits) * 2.5
        )
        if base_score > 0:
            score = base_score + priority_bonus.get(str(topic.get("priority", "")).lower(), 0.0)
            scores[topic_id] = round(score, 3)

    return dict(sorted(scores.items(), key=lambda item: (-item[1], item[0])))


def preferred_url(items: list[CandidateItem]) -> str:
    for item in items:
        if item.url and ("arxiv" in (item.source or "").lower() or "arxiv.org" in item.url.lower()):
            return item.url
    for item in items:
        if item.url:
            return item.url
    return ""


def merge_candidates(items: list[CandidateItem]) -> list[CandidateItem]:
    grouped: dict[str, list[CandidateItem]] = {}
    for item in items:
        grouped.setdefault(item_key(item), []).append(item)

    merged_items: list[CandidateItem] = []
    for group in grouped.values():
        titles = [item.title.strip() for item in group if item.title.strip()]
        summaries = [item.summary.strip() for item in group if item.summary.strip()]
        summaries_zh = [item.summary_zh.strip() for item in group if item.summary_zh.strip()]
        paper_ids = ordered_unique(item.paper_id.strip() for item in group if item.paper_id and item.paper_id.strip())
        published_values = [item.published_at for item in group if parse_datetime(item.published_at)]
        venues = [item.venue.strip() for item in group if item.venue and item.venue.strip()]
        published_at = None
        if published_values:
            published_at = max(
                published_values,
                key=lambda value: parse_datetime(value) or datetime(1970, 1, 1, tzinfo=timezone.utc),
            )
        merged_scores = merge_topic_scores(*(item.topic_scores for item in group))
        merged_items.append(
            CandidateItem(
                source=" + ".join(ordered_unique(source for item in group for source in split_sources(item.source))),
                title=max(titles, key=len) if titles else "",
                url=preferred_url(group),
                summary=max(summaries, key=len) if summaries else "",
                summary_zh=max(summaries_zh, key=len) if summaries_zh else "",
                authors=ordered_unique(author for item in group for author in item.authors or []),
                affiliations=ordered_unique(value for item in group for value in item.affiliations or []),
                institutions=ordered_unique(value for item in group for value in item.institutions or []),
                venue=max(venues, key=len) if venues else None,
                paper_id=paper_ids[0] if paper_ids else None,
                published_at=published_at,
                topic_scores=merged_scores or None,
                score=max((item.score for item in group), default=0.0),
                categories=ordered_unique(category for item in group for category in item.categories or []),
                matched_topics=list(merged_scores) if merged_scores else None,
            )
        )
    return merged_items


def recency_score(published_at: str | None, now: datetime | None = None) -> float:
    published = parse_datetime(published_at)
    if published is None:
        return 0.0
    reference_time = now or datetime.now(timezone.utc)
    age_days = max(0.0, (reference_time - published).total_seconds() / 86400.0)
    if age_days <= 2:
        return 3.0
    if age_days <= 7:
        return 2.0
    if age_days <= 30:
        return 1.0
    return 0.0


def score_candidate(item: CandidateItem, topics: list[dict[str, Any]], now: datetime | None = None) -> CandidateItem:
    discovered_scores = match_topics(item, topics)
    item.topic_scores = merge_topic_scores(item.topic_scores, discovered_scores) or None
    item.matched_topics = list(item.topic_scores) if item.topic_scores else None
    best_topic_score = max((item.topic_scores or {}).values(), default=0.0)
    supporting_topics = max(0, len(item.topic_scores or {}) - 1) * 0.25
    summary_bonus = 0.2 if item.summary else 0.0
    item.score = round(best_topic_score + supporting_topics + recency_score(item.published_at, now=now) + summary_bonus, 3)
    return item


def rank_candidates(items: list[CandidateItem], topics: list[dict[str, Any]], now: datetime | None = None) -> list[CandidateItem]:
    ranked_items = [score_candidate(item, topics, now=now) for item in merge_candidates(items)]
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return sorted(
        ranked_items,
        key=lambda item: (
            -item.score,
            -(parse_datetime(item.published_at) or epoch).timestamp(),
            normalize_title(item.title),
        ),
    )


def filter_recent_candidates(items: list[CandidateItem], lookback_days: int, now: datetime | None = None) -> list[CandidateItem]:
    if lookback_days <= 0:
        return list(items)
    reference_time = now or datetime.now(timezone.utc)
    cutoff = reference_time - timedelta(days=lookback_days)
    filtered_items: list[CandidateItem] = []
    for item in items:
        published = parse_datetime(item.published_at)
        if published is None or published >= cutoff:
            filtered_items.append(item)
    return filtered_items


def truncate_words(text: str, limit: int) -> str:
    words = [word for word in re.sub(r"\s+", " ", (text or "").strip()).split(" ") if word]
    if len(words) <= limit:
        return " ".join(words)
    return " ".join(words[:limit]) + "…"
