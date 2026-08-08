"""
构建成交集中度拥挤度三年历史数据
================================
用法：
    python scripts/build_trading_crowding_history.py
    python scripts/build_trading_crowding_history.py --years 3 --max-days 5
    python scripts/build_trading_crowding_history.py --start 20260701 --end 20260731

默认从当前日期往前 3 年逐交易日拉取，断点续跑（已有缓存则只补最新）。
行业维度写入 data/trading_crowding/trading_crowding_history.csv，
指数维度写入 data/trading_crowding/trading_crowding_index_history.csv。
"""

import argparse
import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.trading_crowding import TradingCrowding


def main():
    parser = argparse.ArgumentParser(description='构建成交集中度拥挤度历史数据')
    parser.add_argument('--years', type=int, default=TradingCrowding.HISTORY_YEARS,
                        help='回溯年数（默认 3）')
    parser.add_argument('--start', type=str, default=None,
                        help='开始日期 YYYYMMDD（默认 3 年前）')
    parser.add_argument('--end', type=str, default=None,
                        help='结束日期 YYYYMMDD（默认今天）')
    parser.add_argument('--max-days', type=int, default=None,
                        help='本次最多拉取天数（调试用）')
    parser.add_argument('--no-resume', action='store_true',
                        help='忽略已有缓存，重新拉取')
    parser.add_argument('--delay', type=float, default=0.35,
                        help='接口调用间隔秒数（默认 0.35）')
    args = parser.parse_args()

    tc = TradingCrowding()
    if args.start is None:
        start = (datetime.date.today()
                 - datetime.timedelta(days=365 * args.years)).strftime('%Y%m%d')
    else:
        start = args.start.replace('-', '')
    end = args.end.replace('-', '') if args.end else None

    print(f'开始构建成交集中度拥挤度历史: {start} ~ {end or "今天"}')
    t0 = datetime.datetime.now()

    def progress(done, total, cur_date, latest):
        if done % 10 == 0 or done == total:
            eta_sec = (datetime.datetime.now() - t0).total_seconds() / done * (total - done)
            print(f'  进度 {done}/{total} ({cur_date}) 最新成功 {latest} '
                  f'预计剩余 {eta_sec/60:.1f} 分钟')

    added = tc.build_history(
        start_date=start,
        end_date=end,
        max_days=args.max_days,
        resume=not args.no_resume,
        call_delay=args.delay,
        progress_cb=progress,
    )
    dt = (datetime.datetime.now() - t0).total_seconds()
    print(f'完成：本次新增 {added} 个交易日，耗时 {dt/60:.1f} 分钟')

    latest = tc.get_latest()
    if not latest.empty:
        top = latest.head(10)[['industry', 'vol_concentration_pct',
                               'amount_concentration_pct', 'stock_count']]
        print(f'\n最新日期 {latest["trade_date"].iloc[0].date()} 集中度 TOP10:')
        print(top.to_string(index=False))


if __name__ == '__main__':
    main()
