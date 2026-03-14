"""Multi-source collection pipeline.

Orchestrates all enabled source adapters, applies entity resolution,
scores items with hot_score, and returns a merged, deduplicated, ranked list.

Usage:
    pipeline = CollectPipeline(config)
    items = pipeline.run(topics)
    # items: list[NormalizedItem], sorted by score descending
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.normalize.entity_resolver import EntityResolver
from src.normalize.schema import NormalizedItem
from src.scoring.hot_score import score_items
from src.storage.cache import DiskCache

logger = logging.getLogger(__name__)

# Registry: source name → adapter class (lazy imports to avoid heavy deps at import)
_ADAPTER_REGISTRY: dict[str, str] = {
    "arxiv": "src.sources.arxiv.ArxivAdapter",
    "huggingface": "src.sources.huggingface.HuggingFaceAdapter",
    "reddit": "src.sources.reddit.RedditAdapter",
    "hackernews": "src.sources.hackernews.HackerNewsAdapter",
    "github": "src.sources.github.GitHubAdapter",
    "semantic_scholar": "src.sources.semantic_scholar.SemanticScholarAdapter",
    "openalex": "src.sources.openalex.OpenAlexAdapter",
}


class CollectPipeline:
    """Collect → enrich → resolve → score → rank."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        cache_dir: str | Path = "output/.cache",
        cache_ttl: int = 3600,
        use_cache: bool = True,
    ) -> None:
        self._config = config
        self._sources_cfg: dict[str, Any] = (
            config.get("sources", {}) if isinstance(config, dict) else {}
        )
        self._resolver = EntityResolver()
        self._cache = DiskCache(directory=cache_dir, ttl_seconds=cache_ttl)
        self._use_cache = use_cache

    # ── public interface ───────────────────────────────────────────────────────
    def run(
        self,
        topics: list[dict[str, Any]],
        *,
        source_names: list[str] | None = None,
        now: datetime | None = None,
    ) -> list[NormalizedItem]:
        """Run the full pipeline and return ranked NormalizedItems.

        Args:
            topics:       List of topic dicts (from config).
            source_names: Optionally restrict to these source names.
            now:          Override reference time (for testing).
        """
        raw_items = self._collect_all(topics, source_names=source_names)
        logger.info("[pipeline] collected %d raw items across all sources", len(raw_items))

        enriched = self._resolver.enrich_all(raw_items)
        groups = self._resolver.group_by_entity(enriched)
        merged = [self._resolver.merge_group(grp) for grp in groups.values()]
        logger.info(
            "[pipeline] after entity resolution: %d unique items (from %d raw)",
            len(merged),
            len(raw_items),
        )

        ranked = score_items(merged, topics, now=now)
        return ranked

    def save(self, items: list[NormalizedItem], path: str | Path) -> None:
        """Serialise ranked items to JSON."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "item_count": len(items),
            "items": [item.to_dict() for item in items],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[pipeline] saved %d items to %s", len(items), path)

    # ── internal ───────────────────────────────────────────────────────────────
    def _collect_all(
        self,
        topics: list[dict[str, Any]],
        source_names: list[str] | None = None,
    ) -> list[NormalizedItem]:
        candidates = list(_ADAPTER_REGISTRY)
        if source_names:
            candidates = [s for s in candidates if s in source_names]

        all_items: list[NormalizedItem] = []
        for src_name in candidates:
            src_cfg = self._sources_cfg.get(src_name, {})
            if not isinstance(src_cfg, dict):
                src_cfg = {}
            if not src_cfg.get("enabled", False):
                logger.debug("[pipeline] source %r disabled — skipping", src_name)
                continue

            cache_key = f"{src_name}_fetch"
            if self._use_cache:
                cached = self._cache.get(cache_key)
                if cached is not None:
                    logger.info("[pipeline] cache hit for %r (%d items)", src_name, len(cached))
                    items = [NormalizedItem.from_dict(d) for d in cached]
                    all_items.extend(items)
                    continue

            adapter = _load_adapter(src_name, src_cfg)
            if adapter is None:
                continue

            items = adapter.fetch(topics)
            logger.info("[pipeline] %r → %d items", src_name, len(items))

            if self._use_cache and items:
                self._cache.set(cache_key, [i.to_dict() for i in items])

            all_items.extend(items)

        return all_items


def _load_adapter(name: str, config: dict[str, Any]) -> Any | None:
    """Dynamically import and instantiate a source adapter."""
    cls_path = _ADAPTER_REGISTRY.get(name)
    if not cls_path:
        logger.warning("[pipeline] unknown source %r — skipping", name)
        return None
    module_path, cls_name = cls_path.rsplit(".", 1)
    try:
        import importlib
        module = importlib.import_module(module_path)
        cls = getattr(module, cls_name)
        return cls(config)
    except Exception as exc:
        logger.warning("[pipeline] failed to load adapter %r: %s", name, exc)
        return None
