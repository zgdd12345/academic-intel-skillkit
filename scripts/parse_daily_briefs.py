"""parse_daily_briefs.py — Parse daily brief Markdown files into structured data.

This module is imported by build_periodic_report.py, not run as a CLI.
Handles both old-format (优先阅读 + 快速扫描 table) and new-format (最新工作 combined)
daily briefs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


@dataclass
class ParsedPaper:
    title: str
    url: str
    source: str = "arXiv"
    published_date: str = ""
    topics: list[str] = field(default_factory=list)
    score: float = 0.0
    authors: str = ""
    paper_id: str = ""
    summary_zh: str = ""
    tier: str = "scan"  # "priority" or "scan"


@dataclass
class ParsedHotspot:
    title: str
    url: str
    platform: str = ""
    summary_zh: str = ""
    signal: str = ""


@dataclass
class DailyBriefData:
    date: str = ""
    candidates: int = 0
    high_signal: int = 0
    hotspots: int = 0
    recommended: int = 0
    overview: str = ""
    papers: list[ParsedPaper] = field(default_factory=list)
    hotspot_items: list[ParsedHotspot] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, Any]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    raw = m.group(1)
    if yaml is not None:
        try:
            data = yaml.safe_load(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            pass
    # Fallback: simple key: value parsing
    result: dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" in line and not line.strip().startswith("-"):
            key, _, val = line.partition(":")
            val = val.strip()
            try:
                result[key.strip()] = int(val)
            except ValueError:
                result[key.strip()] = val
    return result


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def _parse_overview(text: str) -> str:
    # Match the callout block after 今日概览
    m = re.search(r">\s*\[!abstract\]\s*今日概览\s*\n((?:>.*\n?)*)", text)
    if not m:
        return ""
    lines = []
    for line in m.group(1).splitlines():
        cleaned = re.sub(r"^>\s?", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Priority papers (callout blocks in 优先阅读 or 最新工作)
# ---------------------------------------------------------------------------

# Matches: > [!tip] [Title](url)
_CALLOUT_TITLE_RE = re.compile(
    r">\s*\[!tip\]\s*\[([^\]]+)\]\(([^)]+)\)"
)

# Matches: 来源：X | 发布日期：Y | 主题：Z | 评分：W | 作者：A | ID：B
_META_RE = re.compile(
    r"来源：([^|]+)\|.*?发布日期：([^|]+)\|.*?主题：([^|]+)\|.*?评分：([^|]+)\|.*?作者：([^|]+)\|.*?ID：(.+)"
)


def _parse_priority_papers(text: str) -> list[ParsedPaper]:
    papers: list[ParsedPaper] = []
    # Find all callout blocks with [!tip]
    blocks = re.split(r"\n(?=> \[!tip\])", text)
    for block in blocks:
        title_m = _CALLOUT_TITLE_RE.search(block)
        if not title_m:
            continue
        title = title_m.group(1).strip()
        url = title_m.group(2).strip()

        paper = ParsedPaper(title=title, url=url, tier="priority")

        meta_m = _META_RE.search(block)
        if meta_m:
            paper.source = meta_m.group(1).strip()
            paper.published_date = meta_m.group(2).strip()
            paper.topics = [t.strip() for t in meta_m.group(3).split(",")]
            try:
                paper.score = float(meta_m.group(4).strip())
            except ValueError:
                pass
            paper.authors = meta_m.group(5).strip()
            paper.paper_id = meta_m.group(6).strip()

        # Extract summary_zh: lines starting with > after metadata
        summary_lines = []
        in_summary = False
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith(">") and "来源：" not in stripped and "[!tip]" not in stripped and "信号：" not in stripped:
                cleaned = re.sub(r"^>\s?", "", stripped).strip()
                if cleaned:
                    in_summary = True
                    summary_lines.append(cleaned)
            elif in_summary and not stripped.startswith(">"):
                break
        if summary_lines:
            # Skip the first line if it looks like a reading hint
            paper.summary_zh = " ".join(summary_lines)

        papers.append(paper)
    return papers


# ---------------------------------------------------------------------------
# Quick scan table (快速扫描)
# ---------------------------------------------------------------------------

_TABLE_ROW_RE = re.compile(
    r"\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|"
)


def _parse_scan_table(text: str) -> list[ParsedPaper]:
    papers: list[ParsedPaper] = []
    # Find the 快速扫描 section
    section_m = re.search(r"##\s*快速扫描\s*\n(.*?)(?=\n##|\n---|\Z)", text, re.DOTALL)
    if not section_m:
        return papers
    section = section_m.group(1)
    for row_m in _TABLE_ROW_RE.finditer(section):
        title = row_m.group(1).strip()
        url = row_m.group(2).strip()
        topics_str = row_m.group(3).strip()
        pub_date = row_m.group(4).strip()
        score_str = row_m.group(5).strip()
        try:
            score = float(score_str)
        except ValueError:
            score = 0.0
        papers.append(ParsedPaper(
            title=title,
            url=url,
            topics=[t.strip() for t in topics_str.split(",")],
            published_date=pub_date,
            score=score,
            tier="scan",
        ))
    return papers


# ---------------------------------------------------------------------------
# Bullet-list papers in 最新工作 section (new format)
# ---------------------------------------------------------------------------

_BULLET_PAPER_RE = re.compile(
    r"^-\s+(?:`([^`]+)`\s+)?(?:\[([^\]]+)\]\(([^)]+)\)|\*\*\[([^\]]+)\]\(([^)]+)\)\*\*)",
    re.MULTILINE,
)


def _parse_scan_bullets(text: str) -> list[ParsedPaper]:
    papers: list[ParsedPaper] = []
    section_m = re.search(r"##\s*最新工作\s*\n(.*?)(?=\n##|\n---|\Z)", text, re.DOTALL)
    if not section_m:
        return papers
    section = section_m.group(1)
    for m in _BULLET_PAPER_RE.finditer(section):
        paper_id = m.group(1) or ""
        title = m.group(2) or m.group(4) or ""
        url = m.group(3) or m.group(5) or ""
        if title:
            papers.append(ParsedPaper(
                title=title.strip(),
                url=url.strip(),
                paper_id=paper_id.strip(),
                tier="scan",
            ))
    return papers


# ---------------------------------------------------------------------------
# Community hotspots (社区热点)
# ---------------------------------------------------------------------------

def _parse_hotspots(text: str) -> list[ParsedHotspot]:
    hotspots: list[ParsedHotspot] = []
    section_m = re.search(r"##\s*社区热点\s*\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if not section_m:
        return hotspots
    section = section_m.group(1)

    current_platform = ""
    for line in section.splitlines():
        # Platform header: ### reddit, ### hackernews, etc.
        platform_m = re.match(r"###\s+(\S+)", line)
        if platform_m:
            current_platform = platform_m.group(1).strip()
            continue

        # Callout title: > [!tip] [Title](url)
        callout_m = re.match(r">\s*\[!tip\]\s*\[([^\]]+)\]\(([^)]+)\)", line)
        if callout_m:
            hotspots.append(ParsedHotspot(
                title=callout_m.group(1).strip(),
                url=callout_m.group(2).strip(),
                platform=current_platform,
            ))
            continue

        # Signal line: > 信号：...
        signal_m = re.match(r">\s*信号：(.+)", line)
        if signal_m and hotspots and not hotspots[-1].signal:
            hotspots[-1].signal = signal_m.group(1).strip()
            continue

        # Summary line in callout (> text without special markers)
        if line.startswith(">") and hotspots:
            cleaned = re.sub(r"^>\s?", "", line).strip()
            if cleaned and not cleaned.startswith("[!") and "信号：" not in cleaned:
                if hotspots[-1].summary_zh:
                    hotspots[-1].summary_zh += " " + cleaned
                else:
                    hotspots[-1].summary_zh = cleaned
            continue

        # Bullet link: - [Platform](url) Title
        bullet_m = re.match(r"-\s+\[([^\]]+)\]\(([^)]+)\)\s*(.*)", line)
        if bullet_m:
            platform_short = bullet_m.group(1).strip()
            url = bullet_m.group(2).strip()
            title = bullet_m.group(3).strip()
            hotspots.append(ParsedHotspot(
                title=title,
                url=url,
                platform=current_platform or platform_short,
            ))

    return hotspots


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_daily_brief(path: Path) -> DailyBriefData:
    """Parse a single daily brief Markdown file into structured data."""
    text = path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)

    data = DailyBriefData(
        date=str(fm.get("date", "")),
        candidates=int(fm.get("candidates", 0)),
        high_signal=int(fm.get("high_signal", 0)),
        hotspots=int(fm.get("hotspots", 0)),
        recommended=int(fm.get("recommended", 0)),
        overview=_parse_overview(text),
    )

    # Papers: try both formats
    priority = _parse_priority_papers(text)
    # Deduplicate: priority papers should not also appear in scan
    priority_urls = {p.url for p in priority}

    scan = _parse_scan_table(text)
    if not scan:
        scan = _parse_scan_bullets(text)
    scan = [p for p in scan if p.url not in priority_urls]

    data.papers = priority + scan

    # Hotspots
    data.hotspot_items = _parse_hotspots(text)

    return data


def find_daily_briefs(
    vault_root: Path,
    start_date: date,
    end_date: date,
) -> list[Path]:
    """Find daily brief files in the vault within the date range (inclusive)."""
    daily_dir = vault_root / "01_Daily"
    if not daily_dir.is_dir():
        return []

    results: list[tuple[date, Path]] = []
    for f in daily_dir.glob("*_Daily.md"):
        # Extract date from filename: YYYY_MM_DD_Daily.md
        m = re.match(r"(\d{4})_(\d{2})_(\d{2})_Daily\.md$", f.name)
        if not m:
            continue
        try:
            file_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if start_date <= file_date <= end_date:
            results.append((file_date, f))

    results.sort(key=lambda x: x[0])
    return [path for _, path in results]
