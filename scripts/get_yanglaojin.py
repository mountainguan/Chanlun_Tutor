#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
获取基本养老保险（养老金）持股数据。

数据来源：东方财富「十大流通股东」全市场报表，按股东名称筛选“基本养老保险”。

输出：
    data/yanglaojin/基本养老保险持股_<YYYYMMDD>.xlsx  归档（与接口逐条对应）
    data/pension_fund_cache.json                      前端缓存（按股票汇总）

用法：
    python scripts/get_yanglaojin.py [YYYYMMDD]
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils.em_gdfx_hold import fetch_free_holders, filter_by_holder
from utils.social_security_fund import SocialSecurityFund

# 归档 Excel 的列顺序与既有归档保持一致
ARCHIVE_COLUMNS = [
    '股票代码',
    '股票简称',
    '股东名称',
    '期末持股-数量',
    '期末持股-数量变化',
    '期末持股-数量变化比例',
    '公告日',
]

# 养老金组合的股东名称均含“基本养老保险”
PENSION_KEYWORDS = ['基本养老保险', '养老保险基金']

DEFAULT_REPORT_DATE = '20260930'


def get_pension_holdings(report_date):
    """
    获取指定报告期的基本养老保险持股明细

    :param report_date: 财报统计截止日期，格式 'YYYYMMDD' (例如 '20260930')
    :return: DataFrame 或 None
    """
    print(f"正在获取 {report_date} 全市场十大流通股东数据，数据量较大请耐心等待...")

    df = fetch_free_holders(report_date)
    if df is None or df.empty:
        print(f"未获取到 {report_date} 的数据，请检查日期是否为财报截止日"
              f"（3月31日/6月30日/9月30日/12月31日）或数据尚未披露。")
        return None

    print(f"获取到全市场十大流通股东数据 {len(df)} 条")

    pension_df = filter_by_holder(df, PENSION_KEYWORDS)
    if pension_df.empty:
        print(f"{report_date} 没有匹配到基本养老保险持股记录")
        return None

    print(f"筛选完成！共找到 {len(pension_df)} 条基本养老保险持股记录。")
    return pension_df[ARCHIVE_COLUMNS].reset_index(drop=True)


def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REPORT_DATE

    holdings = get_pension_holdings(target_date)
    if holdings is None or holdings.empty:
        return

    # 保存为 Excel (按季度归档到 data/yanglaojin 目录)
    output_dir = os.path.join(ROOT, 'data', 'yanglaojin')
    os.makedirs(output_dir, exist_ok=True)
    file_name = os.path.join(output_dir, f"基本养老保险持股_{target_date}.xlsx")
    holdings.to_excel(file_name, index=False)
    print(f"数据已保存至 {file_name}")

    # 同步刷新前端缓存（按股票汇总，口径与 utils/social_security_fund.py 保持一致）
    ssf = SocialSecurityFund(fund_type='pension')
    cache_df = ssf.load_pension_from_excel(file_name, target_date)
    cache_file = ssf.write_cache(cache_df, target_date)
    print(f"JSON 缓存已保存至：{cache_file} (共 {len(cache_df)} 条)")


if __name__ == "__main__":
    main()
