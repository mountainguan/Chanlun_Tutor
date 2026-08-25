# -*- coding: utf-8 -*-
"""生成 6 大指数吞没形态快照。

用法：
  python scripts/build_engulfing_patterns.py                  # 默认（增量更新 + 检测）
  python scripts/build_engulfing_patterns.py --refresh        # 强制从 Tushare 拉取 3 年数据
  python scripts/build_engulfing_patterns.py --date 2026-08-25  # 指定输出日期
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.engulfing_pattern import (  # noqa: E402
    EngulfingPatternBoard,
    INDEX_DEFS,
    OUTPUT_DIR,
    save_struct_data,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成 6 大指数吞没形态快照")
    parser.add_argument("--refresh", action="store_true", help="强制从 Tushare 拉取 3 年数据")
    parser.add_argument("--date", help="指定输出日期 YYYY-MM-DD（默认取数据最后一日）")
    parser.add_argument("--output", default=OUTPUT_DIR, help="输出目录")
    args = parser.parse_args(argv)

    board = EngulfingPatternBoard()
    print(f"开始生成 6 大指数吞没形态快照（lookback=3y, refresh={args.refresh})...")
    payload = board.build_struct_data(force_refresh=args.refresh)

    if args.date:
        payload["trade_date"] = args.date

    path = save_struct_data(payload, args.output)
    print(f"快照文件: {path}")
    print(
        f"近 3 年总计：看涨吞没 {payload['summary']['bullish']} 条，"
        f"看跌吞没 {payload['summary']['bearish']} 条"
    )
    print("各指数信号数：")
    for d in INDEX_DEFS:
        r = payload["results"][d["ts_code"]]
        total = r.get("signals_total", {}) or {}
        latest = r.get("latest") or {}
        latest_txt = (
            f"{'看涨' if latest.get('pattern') == 'bullish' else '看跌'}"
            f"@{latest.get('trade_date', '-')}"
            if latest else "无"
        )
        print(
            f"  {d['name']:<8} ({d['ts_code']}) "
            f"近 3 年={total.get('all', 0)} (↑{total.get('bullish', 0)} / ↓{total.get('bearish', 0)}) "
            f"最近信号={latest_txt}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
