from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from common import (
    DEFAULT_ARXIV_OUTPUT,
    DEFAULT_DAILY_BRIEF_OUTPUT,
    DEFAULT_HUGGINGFACE_OUTPUT,
    DEFAULT_LOCAL_CONFIG,
    display_path,
    load_yaml,
    missing_local_config_message,
    obsidian_daily_brief_path,
)


def run_step(args: list[str]) -> None:
    result = subprocess.run(args, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def run_optional_step(args: list[str], label: str) -> bool:
    result = subprocess.run(args, check=False)
    if result.returncode == 0:
        return True
    print(f"警告：{label} 失败，但本次仍继续生成日报。", file=sys.stderr)
    return False


def load_config(config_path: str) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise SystemExit(missing_local_config_message(path))
    config = load_yaml(config_path)
    return config if isinstance(config, dict) else {}


def resolve_brief_out(config: dict[str, Any], configured_path: str, target_date: str) -> str:
    if configured_path:
        return configured_path
    obsidian_path = obsidian_daily_brief_path(config, target_date)
    if obsidian_path is not None:
        return str(obsidian_path)
    return str(DEFAULT_DAILY_BRIEF_OUTPUT)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="串联 arXiv 抓取、可选热点抓取与日报生成，供 OpenClaw/cron 直接按单命令调度。"
    )
    ap.add_argument("--config", default=str(DEFAULT_LOCAL_CONFIG))
    ap.add_argument("--date", default=str(date.today()))
    ap.add_argument("--topic", action="append", default=[])
    ap.add_argument("--arxiv-out", default=str(DEFAULT_ARXIV_OUTPUT))
    ap.add_argument("--huggingface-out", default=str(DEFAULT_HUGGINGFACE_OUTPUT))
    ap.add_argument("--brief-out", default="")
    ap.add_argument("--skip-huggingface", action="store_true")
    ap.add_argument("--skip-enrich", action="store_true")
    ap.add_argument("--hotspot-limit", type=int, default=20)
    args = ap.parse_args()

    if args.hotspot_limit <= 0:
        raise SystemExit("--hotspot-limit 必须大于 0")

    config = load_config(args.config)
    brief_out = resolve_brief_out(config, args.brief_out, args.date)
    topic_args = [value for topic in args.topic for value in ("--topic", topic)]

    run_step(
        [
            sys.executable,
            str(Path(__file__).with_name("fetch_arxiv.py")),
            "--config",
            args.config,
            "--out",
            args.arxiv_out,
            *topic_args,
        ]
    )

    hotspot_available = False
    if not args.skip_huggingface:
        hotspot_available = run_optional_step(
            [
                sys.executable,
                str(Path(__file__).with_name("fetch_huggingface.py")),
                "--config",
                args.config,
                "--out",
                args.huggingface_out,
                "--limit",
                str(args.hotspot_limit),
                *topic_args,
            ],
            "Hugging Face 热点抓取",
        )

    if not args.skip_enrich:
        enrich_args = [
            sys.executable,
            str(Path(__file__).with_name("enrich_summaries.py")),
            "--config",
            args.config,
            "--arxiv",
            args.arxiv_out,
        ]
        if hotspot_available:
            enrich_args.extend(["--huggingface", args.huggingface_out])
        run_optional_step(enrich_args, "LLM 摘要翻译")

    brief_command = [
        sys.executable,
        str(Path(__file__).with_name("generate_daily_brief.py")),
        "--config",
        args.config,
        "--arxiv",
        args.arxiv_out,
        "--out",
        brief_out,
    ]
    if hotspot_available:
        brief_command.extend(["--huggingface", args.huggingface_out])
    run_step(brief_command)

    print(
        f"日常情报链路完成：arXiv={display_path(args.arxiv_out)} | "
        f"hotspots={'已合并' if hotspot_available else '跳过'} | "
        f"brief={display_path(brief_out)}"
    )


if __name__ == "__main__":
    main()
