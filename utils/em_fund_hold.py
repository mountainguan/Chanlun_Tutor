#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
东方财富「主力持仓」数据抓取。

背景
----
AKShare 的 ``stock_report_fund_hold`` 依据上游 JSON 的 **字段位置** 重命名列
（``big_df.columns = [...]``）。东财一旦新增字段（例如 ``HOLDCHA_VALUE``），
所有列就会整体错位，导致股票代码、持股市值等数值全部串列。

本模块直接请求东财原始 JSON 接口，并 **按字段名** 映射，
上游新增/调整字段顺序都不会再影响结果。
"""

from __future__ import annotations

import pandas as pd
import requests

EM_HOLD_URL = 'http://data.eastmoney.com/dataapi/zlsj/list'

# 东财 type 参数：1=基金 2=QFII 3=社保 4=券商 5=保险 6=信托
FUND_TYPE_MAP = {
    '基金持仓': '1',
    'QFII持仓': '2',
    '社保持仓': '3',
    '券商持仓': '4',
    '保险持仓': '5',
    '信托持仓': '6',
}

# 上游 JSON 字段名 -> 输出列名（按名映射，不依赖字段顺序）
RAW_FIELD_MAP = {
    'SECURITY_CODE': '股票代码',
    'SECURITY_NAME_ABBR': '股票简称',
    'HOULD_NUM': '持有基金家数',
    'TOTAL_SHARES': '持股总数',
    'HOLD_VALUE': '持股市值',
    'HOLDCHA': '持股变化',
    'HOLDCHA_NUM': '持股变动数值',
    'HOLDCHA_RATIO': '持股变动比例',
}

HOLDING_COLUMNS = [
    '序号',
    '股票代码',
    '股票简称',
    '持有基金家数',
    '持股总数',
    '持股市值',
    '持股变化',
    '持股变动数值',
    '持股变动比例',
]

_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'),
    'Referer': 'http://data.eastmoney.com/zlsj/',
}


def _normalize_date(report_date: str) -> str:
    """``'20260930'`` / ``'2026-09-30'`` -> ``'2026-09-30'``"""
    digits = ''.join(ch for ch in str(report_date) if ch.isdigit())
    if len(digits) != 8:
        raise ValueError(f'非法的报告期日期: {report_date}')
    return f'{digits[:4]}-{digits[4:6]}-{digits[6:]}'


def _request_page(type_code: str, date: str, page: int, page_size: int, timeout: int):
    """请求东财分页接口，返回 ``(rows, total_pages)``"""
    params = {
        'date': date,
        'type': type_code,
        'zjc': '0',
        'sortField': 'HOULD_NUM',
        'sortDirec': '1',
        'pageNum': page,
        'pageSize': page_size,
        'p': page,
        'pageNo': page,
    }
    resp = requests.get(EM_HOLD_URL, params=params, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    # 报告期不存在/尚未披露时，东财返回裸列表 [] 而不是字典
    if not isinstance(payload, dict):
        return [], 0
    return payload.get('data') or [], int(payload.get('pages') or 0)


def fetch_fund_holdings(report_date: str, symbol: str = '社保持仓',
                        timeout: int = 30, page_size: int = 500) -> pd.DataFrame:
    """
    抓取东方财富主力持仓明细（按字段名映射，列序稳定）。

    Args:
        report_date: 报告期，``'YYYYMMDD'`` 或 ``'YYYY-MM-DD'``
        symbol: 持仓类型，见 :data:`FUND_TYPE_MAP`
        timeout: 单次请求超时（秒）
        page_size: 每页条数

    Returns:
        DataFrame: 列为 :data:`HOLDING_COLUMNS`，按 ``持有基金家数`` 降序、
        ``股票代码`` 升序排列；报告期无数据时返回空 DataFrame。
    """
    if symbol not in FUND_TYPE_MAP:
        raise ValueError(f'不支持的持仓类型: {symbol}（可选: {", ".join(FUND_TYPE_MAP)}）')

    type_code = FUND_TYPE_MAP[symbol]
    date = _normalize_date(report_date)

    rows = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        page_rows, total_pages = _request_page(type_code, date, page, page_size, timeout)
        rows.extend(page_rows)
        page += 1

    if not rows:
        return pd.DataFrame(columns=HOLDING_COLUMNS)

    records = []
    for raw in rows:
        record = {}
        for raw_key, column in RAW_FIELD_MAP.items():
            record[column] = raw.get(raw_key)
        records.append(record)

    df = pd.DataFrame(records)

    # 股票代码统一为 6 位字符串（下游用 df['股票代码'] == stock_code 做匹配）
    df['股票代码'] = df['股票代码'].astype(str).str.zfill(6)

    for column in ('持有基金家数', '持股总数', '持股市值', '持股变动数值', '持股变动比例'):
        df[column] = pd.to_numeric(df[column], errors='coerce')

    df['持股变化'] = df['持股变化'].fillna('不变')
    df = df[HOLDING_COLUMNS[1:]]
    df = df.sort_values(
        by=['持有基金家数', '股票代码'], ascending=[False, True], kind='mergesort'
    ).reset_index(drop=True)
    df.insert(0, '序号', range(1, len(df) + 1))

    return df
