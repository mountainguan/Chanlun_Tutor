"""
为成交集中度历史回填「涨跌幅榜前5%成交额占比」
==============================================
每日涨幅榜 / 跌幅榜前 5% 个股（按 pct_chg 排序，k = max(1, ceil(股票数×5%))）
成交额合计 ÷ 全A成交额 × 100%，写入
data/trading_crowding/trading_crowding_extreme_history.csv。

该指标需要逐日 pro.daily 的 pct_chg，历史缓存未存个股涨跌幅，
因此本脚本会对每个交易日补拉一次 pro.daily（与
scripts/backfill_trading_crowding_market.py 同一模式）。

幂等：已有数据的交易日自动跳过，可安全重复执行。

用法：
    python scripts/backfill_trading_crowding_extreme.py
    python scripts/backfill_trading_crowding_extreme.py --max-days 30
    python scripts/backfill_trading_crowding_extreme.py --start 20260801 --end 20260807
"""

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.trading_crowding import TradingCrowding


def main():
    parser = argparse.ArgumentParser(description='回填涨跌幅榜前5%成交额占比历史')
    parser.add_argument('--max-days', type=int, default=None,
                        help='本次最多补拉天数（调试用）')
    parser.add_argument('--start', type=str, default=None,
                        help='开始日期 YYYYMMDD（默认取行业历史最早）')
    parser.add_argument('--end', type=str, default=None,
                        help='结束日期 YYYYMMDD（默认取行业历史最晚）')
    parser.add_argument('--delay', type=float, default=0.35,
                        help='接口调用间隔秒数（默认 0.35）')
    args = parser.parse_args()

    tc = TradingCrowding()
    if not os.path.exists(tc.history_file) \
            or os.path.getsize(tc.history_file) == 0:
        print('暂无行业历史，请先运行 scripts/build_trading_crowding_history.py')
        return

    dates = sorted(
        tc.load_history(force=True)['trade_date'].dt.strftime('%Y%m%d').unique())
    if args.start:
        dates = [d for d in dates if d >= args.start.replace('-', '')]
    if args.end:
        dates = [d for d in dates if d <= args.end.replace('-', '')]
    if args.max_days:
        dates = dates[:args.max_days]
    if not dates:
        print('日期范围为空')
        return

    ext = tc.load_extreme_history(force=True)
    have = set()
    if not ext.empty:
        have = set(ext['trade_date'].dt.strftime('%Y%m%d').unique())
    todo = [d for d in dates if d not in have]
    if not todo:
        print(f'涨跌幅榜历史已齐全（{len(dates)} 个交易日），无需补拉')
        return

    print(f'共 {len(dates)} 个交易日，需要补拉 {len(todo)} 天：'
          f'{todo[0]} ~ {todo[-1]}')
    t0 = datetime.datetime.now()
    rows = []
    done = 0
    for d in todo:
        ext_df = tc.fetch_extreme(d)
        if not ext_df.empty:
            ext_df['trade_date'] = d
            rows.append(ext_df.iloc[0].to_dict())
        done += 1
        if len(rows) >= 20:
            tc._append_rows(rows, tc.extreme_file,
                            TradingCrowding.EXTREME_CSV_COLUMNS)
            rows = []
        if done % 20 == 0 or done == len(todo):
            eta_sec = ((datetime.datetime.now() - t0).total_seconds()
                       / done * (len(todo) - done))
            print(f'  进度 {done}/{len(todo)} ({d}) '
                  f'预计剩余 {eta_sec/60:.1f} 分钟')
        if args.delay > 0:
            import time
            time.sleep(args.delay)
    if rows:
        tc._append_rows(rows, tc.extreme_file,
                        TradingCrowding.EXTREME_CSV_COLUMNS)
    # 同步更新 meta.json 的 schema_version
    if os.path.exists(tc.meta_file):
        try:
            with open(tc.meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            meta['schema_version'] = TradingCrowding.SCHEMA_VERSION
            with open(tc.meta_file + '.tmp', 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            os.replace(tc.meta_file + '.tmp', tc.meta_file)
        except Exception as e:
            print(f'更新 meta.json 失败（不影响数据回填）: {e}')
    dt = (datetime.datetime.now() - t0).total_seconds()
    print(f'完成：补拉 {done} 天涨跌幅榜占比，耗时 {dt/60:.1f} 分钟')


if __name__ == '__main__':
    main()
