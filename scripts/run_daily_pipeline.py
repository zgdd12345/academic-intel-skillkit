from __future__ import annotations

import argparse
import calendar
import subprocess
import sys
from datetime import date, timedelta
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

_REPO = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCES_CONFIG = _REPO / "configs" / "sources.local.yaml"


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


def run_parallel_steps(
    steps: list[tuple[list[str], str, bool]],
) -> dict[str, bool]:
    """Run steps in parallel via Popen. Returns {label: success}.

    Each step is (cmd, label, required). Required steps cause SystemExit on failure.
    """
    procs: list[tuple[subprocess.Popen[bytes], str, bool]] = []
    try:
        for cmd, label, required in steps:
            procs.append((subprocess.Popen(cmd), label, required))

        results: dict[str, bool] = {}
        for proc, label, required in procs:
            rc = proc.wait()
            if required and rc != 0:
                for p, _, _ in procs:
                    if p.poll() is None:
                        p.terminate()
                raise SystemExit(rc)
            if rc != 0:
                print(f"警告：{label} 失败，但本次仍继续生成日报。", file=sys.stderr)
            results[label] = rc == 0
        return results
    except KeyboardInterrupt:
        for p, _, _ in procs:
            if p.poll() is None:
                p.terminate()
        raise


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


def _build_arxiv_cmd(args: argparse.Namespace, topic_args: list[str]) -> list[str]:
    return [
        sys.executable,
        str(_SCRIPTS_DIR / "fetch_arxiv.py"),
        "--config", args.config,
        "--out", args.arxiv_out,
        *topic_args,
    ]


def _build_multi_source_cmd(args: argparse.Namespace, topic_args: list[str]) -> list[str]:
    cmd = [
        sys.executable,
        str(_SCRIPTS_DIR / "run_multi_source.py"),
        "--config", args.config,
        "--out", args.huggingface_out,
        *topic_args,
    ]
    if DEFAULT_SOURCES_CONFIG.exists():
        cmd.extend(["--sources-config", str(DEFAULT_SOURCES_CONFIG)])
    return cmd


def _build_enrich_cmd(
    args: argparse.Namespace,
    *,
    enrich_target: str = "all",
    include_huggingface: bool = False,
) -> list[str]:
    cmd = [
        sys.executable,
        str(_SCRIPTS_DIR / "enrich_summaries.py"),
        "--config", args.config,
        "--arxiv", args.arxiv_out,
        "--enrich-target", enrich_target,
    ]
    if include_huggingface:
        cmd.extend(["--huggingface", args.huggingface_out])
    return cmd


def _build_brief_cmd(
    args: argparse.Namespace,
    brief_out: str,
    hotspot_available: bool,
) -> list[str]:
    cmd = [
        sys.executable,
        str(_SCRIPTS_DIR / "generate_daily_brief.py"),
        "--config", args.config,
        "--arxiv", args.arxiv_out,
        "--out", brief_out,
    ]
    if hotspot_available:
        cmd.extend(["--huggingface", args.huggingface_out])
    return cmd


def _run_serial(args: argparse.Namespace, brief_out: str, topic_args: list[str]) -> bool:
    """Original serial pipeline. Returns hotspot_available."""
    run_step(_build_arxiv_cmd(args, topic_args))

    hotspot_available = False
    if not args.skip_hotspots:
        hotspot_available = run_optional_step(
            _build_multi_source_cmd(args, topic_args), "多源热点抓取"
        )

    if not args.skip_enrich:
        run_optional_step(
            _build_enrich_cmd(args, include_huggingface=hotspot_available),
            "LLM 摘要翻译",
        )

    run_step(_build_brief_cmd(args, brief_out, hotspot_available))
    return hotspot_available


def _run_parallel(args: argparse.Namespace, brief_out: str, topic_args: list[str]) -> bool:
    """Parallel pipeline. Returns hotspot_available."""
    arxiv_cmd = _build_arxiv_cmd(args, topic_args)

    # Phase 1: parallel fetch
    if not args.skip_hotspots:
        multi_source_cmd = _build_multi_source_cmd(args, topic_args)
        fetch_results = run_parallel_steps([
            (arxiv_cmd, "arXiv 抓取", True),
            (multi_source_cmd, "多源热点抓取", False),
        ])
        hotspot_available = fetch_results.get("多源热点抓取", False)
    else:
        run_step(arxiv_cmd)
        hotspot_available = False

    # Phase 2: parallel enrich
    if not args.skip_enrich:
        enrich_steps: list[tuple[list[str], str, bool]] = [
            (
                _build_enrich_cmd(
                    args, enrich_target="arxiv", include_huggingface=hotspot_available
                ),
                "arXiv 摘要翻译",
                False,
            ),
        ]
        if hotspot_available:
            enrich_steps.append((
                _build_enrich_cmd(
                    args, enrich_target="huggingface", include_huggingface=True
                ),
                "HF 热点翻译",
                False,
            ))
        run_parallel_steps(enrich_steps)

    # Phase 3: brief generation
    run_step(_build_brief_cmd(args, brief_out, hotspot_available))
    return hotspot_available


def _is_last_day_of_month(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def _run_periodic_reports(config_path: str, target: date) -> None:
    """日报完成后，按日期自动触发周报/月报。"""
    periodic_script = str(_SCRIPTS_DIR / "build_periodic_report.py")

    # 周日 → 生成本周周报
    if target.weekday() == 6:
        print("\n--- 今天是周日，自动生成本周周报 ---")
        run_optional_step(
            [sys.executable, periodic_script,
             "--config", config_path,
             "--period", "weekly",
             "--date", str(target)],
            "周报生成",
        )

    # 月末 → 生成本月月报
    if _is_last_day_of_month(target):
        print("\n--- 今天是月末，自动生成本月月报 ---")
        run_optional_step(
            [sys.executable, periodic_script,
             "--config", config_path,
             "--period", "monthly",
             "--date", str(target)],
            "月报生成",
        )


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
    ap.add_argument("--skip-hotspots", "--skip-huggingface", action="store_true",
                    dest="skip_hotspots")
    ap.add_argument("--skip-enrich", action="store_true")
    ap.add_argument("--skip-periodic", action="store_true",
                    help="跳过周报/月报的自动触发")
    ap.add_argument("--hotspot-limit", type=int, default=20)
    ap.add_argument("--no-parallel", action="store_true",
                    help="禁用并行执行，回退到串行模式（用于调试）")
    args = ap.parse_args()

    if args.hotspot_limit <= 0:
        raise SystemExit("--hotspot-limit 必须大于 0")

    config = load_config(args.config)
    brief_out = resolve_brief_out(config, args.brief_out, args.date)
    topic_args = [value for topic in args.topic for value in ("--topic", topic)]

    if args.no_parallel:
        hotspot_available = _run_serial(args, brief_out, topic_args)
    else:
        hotspot_available = _run_parallel(args, brief_out, topic_args)

    print(
        f"日常情报链路完成：arXiv={display_path(args.arxiv_out)} | "
        f"hotspots={'已合并' if hotspot_available else '跳过'} | "
        f"brief={display_path(brief_out)}"
    )

    # 日报完成后，按日期自动触发周报/月报
    if not args.skip_periodic:
        target = date.fromisoformat(args.date)
        _run_periodic_reports(args.config, target)


if __name__ == "__main__":
    main()
