from __future__ import annotations

import argparse
from pathlib import Path

from common import display_path, render_template, write_text


def main() -> None:
    ap = argparse.ArgumentParser(
        description="脚手架占位的周期报告生成器。当前只会把占位说明写入模板，不代表仓库已经实现周报或月报综合。"
    )
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--period-id", required=True)
    args = ap.parse_args()

    template = Path(args.template).read_text(encoding="utf-8")
    scaffold_notice = "当前仓库尚未实现周期报告综合生成；这里仍是脚手架占位内容。"
    content = render_template(
        template,
        {
            "week_id": args.period_id,
            "month_id": args.period_id,
            "overview": scaffold_notice,
            "top_papers": scaffold_notice,
            "topic_shifts": scaffold_notice,
            "deep_dives": scaffold_notice,
            "watchlist": scaffold_notice,
            "representative_papers": scaffold_notice,
            "topic_trends": scaffold_notice,
            "deep_dive_recap": scaffold_notice,
            "next_month": scaffold_notice,
        },
    )
    write_text(args.out, content)
    print(f"已写入脚手架占位的周期报告到 {display_path(args.out)}")


if __name__ == "__main__":
    main()
