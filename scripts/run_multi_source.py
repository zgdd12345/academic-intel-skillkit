"""run_multi_source.py — Multi-source collection pipeline CLI.

Replaces or augments run_daily_pipeline.py when additional sources
(Reddit, HN, GitHub, S2, OpenAlex) are enabled.

Usage:
    python scripts/run_multi_source.py --help
    python scripts/run_multi_source.py \\
        --config config/research-topics.local.yaml \\
        --sources-config configs/sources.local.yaml \\
        --out output/multi-source.json \\
        --sources reddit hackernews github

The output JSON can be fed into generate_daily_brief.py via --huggingface
(the brief generator already handles the normalised hotspot format).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Allow running from the project root
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "scripts"))
sys.path.insert(0, str(_REPO))

from common import load_yaml, enabled_topics, DEFAULT_LOCAL_CONFIG  # noqa: E402
from src.pipelines.collect import CollectPipeline  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_SOURCES_CONFIG = _REPO / "configs" / "sources.local.yaml"
DEFAULT_MULTI_OUTPUT = _REPO / "output" / "multi-source.json"


def _load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        logger.error("Config not found: %s", path)
        sys.exit(1)
    data = load_yaml(path)
    return data if isinstance(data, dict) else {}


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Run multi-source collection pipeline (Reddit, HN, GitHub, S2, OpenAlex)."
        )
    )
    ap.add_argument(
        "--config",
        default=str(DEFAULT_LOCAL_CONFIG),
        help="research-topics.local.yaml path (for topic definitions)",
    )
    ap.add_argument(
        "--sources-config",
        default=str(DEFAULT_SOURCES_CONFIG),
        help="sources.local.yaml path (for per-source settings)",
    )
    ap.add_argument(
        "--out",
        default=str(DEFAULT_MULTI_OUTPUT),
        help="Output JSON path",
    )
    ap.add_argument(
        "--sources",
        nargs="*",
        help="Restrict to these source names (default: all enabled in config)",
    )
    ap.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable disk cache (always fetch fresh)",
    )
    ap.add_argument(
        "--cache-dir",
        default="output/.cache",
        help="Disk cache directory",
    )
    ap.add_argument(
        "--cache-ttl",
        type=int,
        default=3600,
        help="Cache TTL in seconds (default 3600)",
    )
    ap.add_argument(
        "--topic",
        action="append",
        default=[],
        help="Restrict to specific topic IDs (repeatable)",
    )
    ap.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = ap.parse_args()

    logging.getLogger().setLevel(args.log_level)

    topic_config = _load_config(args.config)

    # Sources config: merge into topic_config under "sources" key
    if Path(args.sources_config).exists():
        sources_cfg = _load_config(args.sources_config)
        topic_config.setdefault("sources", {})
        for src_name, src_val in (sources_cfg.get("sources") or {}).items():
            topic_config["sources"].setdefault(src_name, {})
            if isinstance(src_val, dict):
                topic_config["sources"][src_name].update(src_val)
    else:
        logger.warning(
            "Sources config not found: %s\n"
            "  Copy configs/sources.example.yaml → %s and configure.",
            args.sources_config,
            args.sources_config,
        )

    topics = enabled_topics(topic_config)
    if args.topic:
        selected_ids = set(args.topic)
        topics = [t for t in topics if str(t.get("id", "")) in selected_ids]

    if not topics:
        logger.error("No enabled topics found. Check your config.")
        sys.exit(1)

    logger.info("Running multi-source pipeline with %d topic(s)", len(topics))

    pipeline = CollectPipeline(
        topic_config,
        cache_dir=args.cache_dir,
        cache_ttl=args.cache_ttl,
        use_cache=not args.no_cache,
    )
    items = pipeline.run(topics, source_names=args.sources or None)
    pipeline.save(items, args.out)

    logger.info(
        "Done: %d items → %s",
        len(items),
        args.out,
    )
    # Print top-5 for quick review
    for i, item in enumerate(items[:5], 1):
        print(f"  {i}. [{item.score:.2f}] {item.title[:72]}")


if __name__ == "__main__":
    main()
