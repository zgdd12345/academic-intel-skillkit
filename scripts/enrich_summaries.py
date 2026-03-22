"""enrich_summaries.py — Translate English abstracts → Chinese summary_zh via LLM.

Reads arxiv.json (and optionally huggingface.json), scores candidates to find the
top-N shortlist, then calls an OpenAI-compatible API to fill in summary_zh for
shortlisted items that have an English abstract but no Chinese summary.

Config priority (highest → lowest):
  1. CLI args  (--model, --base-url, --api-key)
  2. Env vars  (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL)
  3. YAML config (llm.base_url, llm.api_key, llm.model)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Allow running from the scripts/ directory directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    DEFAULT_ARXIV_OUTPUT,
    DEFAULT_HUGGINGFACE_OUTPUT,
    DEFAULT_LOCAL_CONFIG,
    dump_json,
    enabled_topics,
    load_json,
    load_yaml,
    missing_local_config_message,
    rank_candidates,
    read_candidate_items,
)

TRANSLATE_PROMPT = (
    "你是技术内容翻译专家。请将以下英文内容完整翻译为中文，"
    "忠实于原文，保留关键技术术语，不要省略任何内容，将全文合并为一段连续的中文段落，不要分段：\n\n{summary}\n\n只输出中文翻译，不要任何其他内容。"
)

TITLE_PROMPT = (
    "请将以下英文标题翻译为简洁的中文新闻标题，保留专有名词和产品名称，不要多余解释："
    "\n\n{title}\n\n只输出中文标题，不要任何其他内容。"
)

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TOP_N = 8


def _load_config(config_path: str) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        print(missing_local_config_message(path), file=sys.stderr)
        sys.exit(1)
    result = load_yaml(config_path)
    return result if isinstance(result, dict) else {}


def _resolve_llm_settings(
    config: dict[str, Any],
    cli_base_url: str | None,
    cli_api_key: str | None,
    cli_model: str | None,
) -> tuple[str | None, str | None, str]:
    """Return (base_url, api_key, model) merging CLI > env > YAML."""
    llm_cfg: dict[str, Any] = config.get("llm", {}) if isinstance(config.get("llm"), dict) else {}

    base_url = (
        cli_base_url
        or os.environ.get("LLM_BASE_URL")
        or llm_cfg.get("base_url")
        or None
    )
    api_key = (
        cli_api_key
        or os.environ.get("LLM_API_KEY")
        or llm_cfg.get("api_key")
        or None
    )
    model = (
        cli_model
        or os.environ.get("LLM_MODEL")
        or llm_cfg.get("model")
        or DEFAULT_MODEL
    )
    return base_url, api_key, str(model)


def _resolve_top_n(config: dict[str, Any], cli_top_n: int | None) -> int:
    if cli_top_n is not None:
        return cli_top_n
    reporting = config.get("reporting", {})
    if isinstance(reporting, dict):
        raw = reporting.get("daily_top_n")
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    return DEFAULT_TOP_N


def _shortlisted_paper_ids(
    arxiv_path: str,
    huggingface_path: str,
    config: dict[str, Any],
    top_n: int,
) -> set[str]:
    """Score and rank candidates; return paper_ids of top-N."""
    items = read_candidate_items(arxiv_path)
    if huggingface_path:
        items += read_candidate_items(huggingface_path)
    topics = enabled_topics(config)
    ranked = rank_candidates(items, topics)
    shortlist = ranked[:top_n]
    return {item.paper_id for item in shortlist if item.paper_id}


def _call_llm(client: Any, model: str, summary: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": TRANSLATE_PROMPT.format(summary=summary)}],
        max_tokens=800,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def _enrich_items(
    items: list[dict[str, Any]],
    shortlisted_ids: set[str],
    client: Any,
    model: str,
    dry_run: bool,
) -> int:
    """Mutate items in-place, adding summary_zh. Returns count of enriched items."""
    enriched = 0
    for item in items:
        paper_id = (
            item.get("paper_id") or item.get("paperId") or item.get("id")
            or item.get("external_id")
            or next(iter(item.get("paper_ids") or []), None)
            or ""
        )
        summary = (
            item.get("summary") or item.get("abstract") or item.get("content")
            or item.get("ai_summary") or ""
        ).strip()
        summary_zh = (item.get("summary_zh") or item.get("summaryZh") or "").strip()

        if paper_id not in shortlisted_ids:
            continue
        if not summary:
            continue
        if summary_zh:
            continue

        if dry_run:
            print(f"[dry-run] Would translate paper_id={paper_id!r}:")
            print(f"  {summary[:120]}{'...' if len(summary) > 120 else ''}")
            enriched += 1
            continue

        try:
            result = _call_llm(client, model, summary)
            item["summary_zh"] = result
            enriched += 1
            print(f"  ✓ {paper_id}: {result[:60]}{'...' if len(result) > 60 else ''}")
        except Exception as exc:  # noqa: BLE001
            print(f"警告：paper_id={paper_id!r} 翻译失败：{exc}", file=sys.stderr)

    return enriched


def _enrich_titles(
    items: list[dict[str, Any]],
    client: Any,
    model: str,
    dry_run: bool,
) -> int:
    """Translate English titles → title_zh for hotspot items. Returns count enriched."""
    enriched = 0
    for item in items:
        title = str(item.get("title") or item.get("name") or "").strip()
        title_zh = str(item.get("title_zh") or "").strip()
        if not title or title_zh:
            continue
        if re.search(r"[\u3400-\u9fff]", title):
            continue  # already Chinese

        if dry_run:
            print(f"[dry-run] Would translate title: {title[:80]}")
            enriched += 1
            continue

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": TITLE_PROMPT.format(title=title)}],
                max_tokens=80,
                temperature=0.3,
            )
            item["title_zh"] = response.choices[0].message.content.strip()
            enriched += 1
        except Exception as exc:  # noqa: BLE001
            print(f"警告：标题翻译失败 {title[:40]!r}：{exc}", file=sys.stderr)

    return enriched


def _load_raw_items(path: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load JSON, return (payload_dict, items_list). payload_dict is mutated in-place."""
    payload = load_json(path, default={})
    if isinstance(payload, list):
        # Rare: top-level list — wrap it
        wrapper: dict[str, Any] = {"items": payload}
        return wrapper, payload
    if isinstance(payload, dict):
        if "items" not in payload:
            payload["items"] = []
        items = payload["items"]
        if not isinstance(items, list):
            payload["items"] = []
            items = payload["items"]
        return payload, items
    wrapper = {"items": []}
    return wrapper, wrapper["items"]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="用 LLM 为 arxiv.json 中的 top-N 候选论文翻译中文摘要。"
    )
    ap.add_argument("--arxiv", default=str(DEFAULT_ARXIV_OUTPUT), help="arxiv.json 路径")
    ap.add_argument("--huggingface", default="", help="huggingface.json 路径（可选）")
    ap.add_argument("--out", default="", help="输出路径（默认原地覆盖 --arxiv）")
    ap.add_argument("--config", default=str(DEFAULT_LOCAL_CONFIG))
    ap.add_argument("--model", default="", help="LLM 模型名（覆盖 env/config）")
    ap.add_argument("--top-n", type=int, default=None, help="enrichment 的候选数量上限")
    ap.add_argument("--base-url", default="", help="OpenAI-compatible base URL（覆盖 LLM_BASE_URL）")
    ap.add_argument("--api-key", default="", help="API key（覆盖 LLM_API_KEY）")
    ap.add_argument("--dry-run", action="store_true", help="打印将翻译的摘要，不真正调用 API")
    ap.add_argument(
        "--enrich-target",
        choices=["all", "arxiv", "huggingface"],
        default="all",
        help="翻译目标：all=全部（默认）, arxiv=仅arXiv摘要, huggingface=仅HF热点",
    )
    args = ap.parse_args()

    config = _load_config(args.config)
    base_url, api_key, model = _resolve_llm_settings(
        config,
        args.base_url or None,
        args.api_key or None,
        args.model or None,
    )
    top_n = _resolve_top_n(config, args.top_n)
    out_path = args.out or args.arxiv

    if not args.dry_run:
        if not base_url:
            print(
                "错误：未配置 LLM_BASE_URL（或 --base-url / llm.base_url）。跳过摘要翻译。",
                file=sys.stderr,
            )
            sys.exit(1)
        if not api_key:
            print(
                "错误：未配置 LLM_API_KEY（或 --api-key / llm.api_key）。跳过摘要翻译。",
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            from openai import OpenAI
        except ImportError:
            print("错误：openai 包未安装。请执行：pip install openai>=1.0", file=sys.stderr)
            sys.exit(1)

        client = OpenAI(api_key=api_key, base_url=base_url)
    else:
        client = None

    target = args.enrich_target

    # --- Phase: arXiv enrichment ---
    if target in ("all", "arxiv"):
        shortlisted_ids = _shortlisted_paper_ids(
            args.arxiv, args.huggingface, config, top_n
        )
        if not shortlisted_ids:
            print("警告：arXiv shortlist 为空（可能是周末无新论文），跳过 arXiv 翻译，继续处理热点数据。", file=sys.stderr)

        print(f"LLM 摘要翻译：top_n={top_n}, model={model}, shortlist={len(shortlisted_ids)} 篇")

        payload, items = _load_raw_items(args.arxiv)
        count = _enrich_items(items, shortlisted_ids, client, model, dry_run=args.dry_run)

        if args.dry_run:
            print(f"[dry-run] 共 {count} 篇待翻译（未调用 API）。")
            if target == "arxiv":
                sys.exit(0)
        else:
            dump_json(out_path, payload)
            print(f"完成：翻译 arXiv {count} 篇，已写入 {out_path}")

    # --- Phase: HF hotspot enrichment ---
    if target in ("all", "huggingface"):
        if args.huggingface and Path(args.huggingface).exists():
            hf_payload, hf_items = _load_raw_items(args.huggingface)
            all_hf_ids = {
                (
                    item.get("paper_id") or item.get("paperId") or item.get("id")
                    or item.get("external_id")
                    or next(iter(item.get("paper_ids") or []), None)
                    or ""
                ).strip()
                for item in hf_items
            } - {""}
            if all_hf_ids:
                print(f"LLM 翻译 HF 热点摘要：{len(all_hf_ids)} 篇")
                hf_count = _enrich_items(hf_items, all_hf_ids, client, model, dry_run=args.dry_run)
                print(f"完成：翻译 HF 热点摘要 {hf_count} 篇")

            if not args.dry_run:
                print(f"LLM 翻译 HF 热点标题：{len(hf_items)} 条")
                title_count = _enrich_titles(hf_items, client, model, dry_run=False)
                dump_json(args.huggingface, hf_payload)
                print(f"完成：翻译标题 {title_count} 条，已写入 {args.huggingface}")


if __name__ == "__main__":
    main()
