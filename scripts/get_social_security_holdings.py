#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
获取社保基金（主力机构）持股数据并归档。

用法:
    python scripts/get_social_security_holdings.py [YYYYMMDD]

输出:
    data/shebaojijin/社保基金持股_<日期>.xlsx   季度归档
    data/social_security_fund_cache.json        前端读取的缓存

说明:
    数据直接来自东方财富「主力持仓」接口并按字段名映射（见 utils/em_fund_hold.py）。
    早期版本使用 AKShare 的 stock_report_fund_hold，该函数按 **字段位置** 重命名列，
    东财新增字段（如 HOLDCHA_VALUE）会导致所有列整体错位、数据被静默污染。
"""

import os
import sys
import json
import time

import pandas as pd

# 添加项目根目录到路径，便于直接运行本脚本
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.em_fund_hold import HOLDING_COLUMNS, fetch_fund_holdings


def get_social_security_holdings(report_date):
    """
    获取指定报告期的社保基金持股信息
    :param report_date: 财报统计截止日期，格式 'YYYYMMDD' (例如 '20260930')
    """
    print(f"正在获取 {report_date} 社保基金持股数据，请耐心等待...")

    try:
        df = fetch_fund_holdings(report_date, symbol='社保持仓')

        if df is None or df.empty:
            print(f"未获取到 {report_date} 的数据，请检查日期是否为财报截止日或数据尚未披露。")
            return None

        print(f"筛选完成！共找到 {len(df)} 条社保基金持股记录。")
        return df

    except Exception as e:
        print(f"发生错误: {e}")
        return None


def _to_json_records(df):
    """把 DataFrame 转成可被 json 序列化的记录列表（NaN -> None）"""
    records = []
    for _, row in df.iterrows():
        record = {}
        for col, value in row.items():
            if pd.isna(value):
                record[col] = None
            elif hasattr(value, 'item'):
                record[col] = value.item()
            else:
                record[col] = value
        records.append(record)
    return records


def main(target_date):
    holdings = get_social_security_holdings(target_date)

    if holdings is None or holdings.empty:
        return

    # 显示前 10 条
    print("\n前10条持仓记录：")
    print(holdings.head(10).to_string(index=False))

    # 保存为 Excel (按季度归档到 data/shebaojijin 目录)
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'shebaojijin')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    file_name = os.path.join(output_dir, f"社保基金持股_{target_date}.xlsx")
    holdings.to_excel(file_name, index=False)
    print(f"\n完整数据已保存至：{file_name}")

    # 同步写入 social_security_fund_cache.json (JSON 格式，供前端读取)
    # 注意：接口返回的字段已经是目标格式（持股总数/持股市值/持股变化等），
    # 不需要按股票代码再聚合，直接以 6 位字符串股票代码保存即可。
    df_cache = holdings.copy()

    # 确保股票代码为 6 位字符串
    df_cache['股票代码'] = df_cache['股票代码'].astype(str).str.zfill(6)

    # 补全必要的列，避免前端 KeyError
    for col, default in [
        ('持有基金家数', 1),
        ('持股总数', 0),
        ('持股市值', 0.0),
        ('持股变动数值', 0.0),
        ('持股变动比例', 0.0),
        ('持股变化', '不变'),
        ('序号', None),
    ]:
        if col not in df_cache.columns:
            df_cache[col] = default

    if '序号' in df_cache.columns and df_cache['序号'].isna().all():
        df_cache['序号'] = range(1, len(df_cache) + 1)

    # 数值列统一为数字类型；缺失值填 0（新进等场景比例为空），
    # 与 scripts/sync_latest_data.py 及 utils 中从 Excel 加载的路径保持一致
    for col in ['持有基金家数', '持股总数', '持股市值', '持股变动数值', '持股变动比例']:
        df_cache[col] = pd.to_numeric(df_cache[col], errors='coerce').fillna(0)

    df_cache['持股变化'] = df_cache['持股变化'].fillna('不变')

    cache_data = {
        'timestamp': time.time(),
        'date': target_date,
        'data': _to_json_records(df_cache[HOLDING_COLUMNS]),
    }
    cache_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'social_security_fund_cache.json')
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(f"JSON 缓存已同步至：{cache_file} (共 {len(df_cache)} 条)")


if __name__ == "__main__":
    # 查询指定季度的财报 (例如：2026年三季度 20260930, 或 2026年四季度 20261231)
    target_date = "20260930"

    if len(sys.argv) > 1:
        target_date = sys.argv[1]

    main(target_date)

