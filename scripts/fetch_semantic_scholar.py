from __future__ import annotations

import argparse

from common import display_path, dump_json, utc_now_iso


def main() -> None:
    ap = argparse.ArgumentParser(
        description="脚手架占位的 Semantic Scholar 采集器。当前只会写出空的归一化载荷，不代表仓库已经实现该采集链路。"
    )
    ap.add_argument("--query", required=True)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    # Placeholder skeleton. A real implementation can call the Semantic Scholar API
    # if the user provides a key or if public endpoints are acceptable for the use case.
    dump_json(
        args.out,
        {
            "generated_at": utc_now_iso(),
            "query": args.query,
            "items": [],
            "note": "脚手架占位输出：当前仓库尚未实现 Semantic Scholar 采集器，此文件只是空的归一化载荷示例。",
        },
    )
    print(f"已写入脚手架占位的 Semantic Scholar 空载荷到 {display_path(args.out)}")


if __name__ == "__main__":
    main()
