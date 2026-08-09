"""
为成交集中度历史回填「板块成交占比」字段
========================================
行业历史新增 vol_market_share_pct / amount_market_share_pct 两个字段：

    板块成交量占比 = 板块 total_vol ÷ 全A total_vol × 100%
    板块成交额占比 = 板块 total_amount ÷ 全A total_amount × 100%

全A（index_code='ALL'）总量已存在于
data/trading_crowding/trading_crowding_index_history.csv，
因此本脚本仅做本地计算回填，不额外请求接口。

幂等：重复执行结果一致，可安全重复运行。

用法：
    python scripts/backfill_trading_crowding_share.py
"""

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.trading_crowding import TradingCrowding


def main():
    tc = TradingCrowding()
    if not os.path.exists(tc.history_file) \
            or os.path.getsize(tc.history_file) == 0:
        print('暂无行业历史，请先运行 scripts/build_trading_crowding_history.py')
        return
    if not os.path.exists(tc.index_history_file) \
            or os.path.getsize(tc.index_history_file) == 0:
        print('暂无指数历史，请先运行 scripts/build_trading_crowding_history.py')
        return

    ind = pd.read_csv(tc.history_file, dtype={'trade_date': str})
    idx = pd.read_csv(tc.index_history_file, dtype={'trade_date': str})
    all_rows = idx[idx['index_code'] == 'ALL'][
        ['trade_date', 'total_vol', 'total_amount']].copy()
    if all_rows.empty:
        print('指数历史中缺少全A（ALL）行，'
              '请先运行 scripts/backfill_trading_crowding_market.py')
        return

    merged = ind.merge(all_rows, on='trade_date', how='left',
                       suffixes=('', '_market'))
    missing = int(merged['total_vol_market'].isna().sum())
    merged['vol_market_share_pct'] = (
        merged['total_vol'] / merged['total_vol_market'] * 100.0)
    merged['amount_market_share_pct'] = (
        merged['total_amount'] / merged['total_amount_market'] * 100.0)

    out = merged[TradingCrowding.CSV_COLUMNS]
    tmp_file = tc.history_file + '.tmp'
    out.to_csv(tmp_file, index=False, encoding='utf-8-sig')
    os.replace(tmp_file, tc.history_file)

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

    tc.invalidate_history_cache()
    day_sum = out.groupby('trade_date')['amount_market_share_pct'].sum()
    print(f'完成：共回填 {len(out)} 行（{ind["trade_date"].nunique()} 个交易日），'
          f'缺少全A行的交易日 {missing} 个；'
          f'每日成交额占比合计均值 {day_sum.mean():.2f}%')


if __name__ == '__main__':
    main()
