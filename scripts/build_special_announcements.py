# -*- coding: utf-8 -*-
"""生成每日股市特殊公告栏 Markdown。

用法：
  python scripts/build_special_announcements.py                  # 最近一个交易日
  python scripts/build_special_announcements.py --date 20260813  # 指定交易日
  python scripts/build_special_announcements.py --print          # 同时打印全文
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.special_announcement import (  # noqa: E402
    OUTPUT_DIR,
    SpecialAnnouncementBoard,
    build_board,
    save_board,
    save_raw,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成每日股市特殊公告栏 Markdown")
    parser.add_argument("--date", help="交易日 YYYYMMDD，默认最近一个交易日")
    parser.add_argument("--output", default=OUTPUT_DIR, help="公告栏输出目录")
    parser.add_argument("--print", action="store_true", help="同时打印完整 Markdown")
    args = parser.parse_args(argv)

    board = SpecialAnnouncementBoard()
    trade_date = args.date or board.latest_trade_date()
    print(f"抓取交易日: {trade_date} ...")

    data = board.fetch_day(trade_date)
    raw_dir = save_raw(data)
    markdown = build_board(data)
    path = save_board(markdown, trade_date, args.output)

    print(f"公告栏文件: {path}")
    print(f"原始数据:   {raw_dir}")
    counts = {
        name: (0 if df is None else len(df))
        for name, df in data["sections"].items()
    }
    print(
        f"板块数量:   交易所异常波动={counts.get('stk_shock', 0)} "
        f"| 龙虎榜={counts.get('top_list', 0)} "
        f"| 涨跌停+炸板={counts.get('limit_list_d', 0)} "
        f"| 停复牌={counts.get('suspend_d', 0)} "
        f"| 股东增减持={counts.get('stk_holdertrade', 0)}"
    )
    if args.print:
        print("\n" + markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
