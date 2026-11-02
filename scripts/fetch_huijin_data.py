#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
获取中央汇金持股数据。

数据来源：东方财富「十大流通股东」全市场报表，按股东名称筛选“中央汇金”。
汇金的相关主体包括：
    - 中央汇金投资有限责任公司
    - 中央汇金资产管理有限责任公司
    - 华夏基金-中央汇金资产管理有限责任公司-汇金资管单一资产管理计划

输出：
    data/huijin/中央汇金持股_<YYYYMMDD>.xlsx  归档（按股票汇总）
    data/huijin_fund_cache.json                 前端缓存

用法：
    python scripts/fetch_huijin_data.py [YYYYMMDD]
"""

import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils.em_gdfx_hold import fetch_free_holders, filter_by_holder
from utils.social_security_fund import SocialSecurityFund

# 归档 Excel 的列顺序与既有归档保持一致
ARCHIVE_COLUMNS = [
    '股票代码',
    '股票简称',
    '持股总数',
    '持股市值',
    '持股变动数值',
    '持股变动比例',
    '持有基金家数',
    '持股变化',
    '序号',
]

# 只匹配“中央汇金”，避免把中汇金玖锐信、钎镱汇金1号等无关产品算进来
HUIJIN_KEYWORDS = ['中央汇金']

DEFAULT_REPORT_DATE = '20260930'


def get_huijin_holdings(report_date):
    """
    获取指定报告期的中央汇金持股明细（按股票汇总）

    :param report_date: 财报统计截止日期，格式 'YYYYMMDD' (例如 '20260930')
    :return: DataFrame 或 None
    """
    print(f"开始获取 {report_date} 的中央汇金持股数据...")
    print("注意：该接口获取全市场数据，可能需要几分钟，请耐心等待...")

    df = fetch_free_holders(report_date)
    if df is None or df.empty:
        print(f"未获取到 {report_date} 的数据")
        return None

    print(f"成功获取全市场数据，共 {len(df)} 条记录")

    huijin_rows = filter_by_holder(df, HUIJIN_KEYWORDS)
    if huijin_rows.empty:
        print("未找到中央汇金持仓记录")
        return None

    print(f"筛选出 {len(huijin_rows)} 条中央汇金持仓记录")

    # 同一只股票可能有多个汇金账户（投资/资产管理/资管计划），需要合并
    grouped = huijin_rows.groupby(['股票代码', '股票简称'], as_index=False).agg({
        '期末持股-数量': 'sum',
        '期末持股-流通市值': 'sum',
        '期末持股-数量变化': 'sum',
        '期末持股-数量变化比例': 'mean',
        '股东名称': 'count',
    })
    grouped = grouped.rename(columns={
        '期末持股-数量': '持股总数',
        '期末持股-流通市值': '持股市值',
        '期末持股-数量变化': '持股变动数值',
        '期末持股-数量变化比例': '持股变动比例',
        '股东名称': '持有基金家数',
    })

    grouped['持股变化'] = grouped.apply(
        lambda row: '新进' if (row['持股变动数值'] == row['持股总数'] and row['持股总数'] > 0) else
                   ('增加' if row['持股变动数值'] > 0 else
                    ('减少' if row['持股变动数值'] < 0 else '不变')),
        axis=1
    )

    grouped = grouped.sort_values('股票代码').reset_index(drop=True)
    grouped.insert(0, '序号', range(1, len(grouped) + 1))

    return grouped[ARCHIVE_COLUMNS]


def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REPORT_DATE

    holdings = get_huijin_holdings(target_date)
    if holdings is None or holdings.empty:
        print("未获取到任何数据，不进行保存")
        return

    # 归档到 data/huijin 目录
    output_dir = os.path.join(ROOT, 'data', 'huijin')
    os.makedirs(output_dir, exist_ok=True)
    file_name = os.path.join(output_dir, f"中央汇金持股_{target_date}.xlsx")
    holdings.to_excel(file_name, index=False)
    print(f"数据已保存至 {file_name}")

    # 同步刷新前端缓存（口径与 utils/social_security_fund.py 保持一致）
    ssf = SocialSecurityFund(fund_type='huijin')
    cache_df = ssf.load_huijin_from_excel(file_name, target_date)
    cache_file = ssf.write_cache(cache_df, target_date)
    print(f"JSON 缓存已保存至 {cache_file}")
    print(f"共获取 {len(cache_df)} 只股票的中央汇金持仓数据")


if __name__ == "__main__":
    main()
