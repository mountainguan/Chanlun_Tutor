#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
东方财富「股东分析」十大流通股东数据抓取。

背景
----
养老金（基本养老保险基金）与中央汇金的持仓不在东财「主力持仓」接口里，
只能从「十大流通股东」报表中按股东名称筛选后得到。

AKShare 的 ``stock_gdfx_free_holding_analyse_em`` 使用的是按名重命名，本身不会
出现「整列错位」的问题；但它每次都要下载全市场 5~7 万行，养老金与汇金两个脚本
各跑一遍会重复下载。

本模块直接请求东财原始 JSON 接口，**按字段名** 映射（上游增删字段不影响结果），
并支持把全市场结果缓存到本地 pkl，避免重复下载。
"""

from __future__ import annotations

import os
import pickle
import tempfile
import time

import pandas as pd
import requests

EM_GDFX_URL = 'https://datacenter-web.eastmoney.com/api/data/v1/get'

# 十大流通股东（社保/养老金/汇金口径）
FREE_HOLDER_REPORT = 'RPT_CUSTOM_F10_EH_FREEHOLDERS_JOIN_FREEHOLDER_SHAREANALYSIS'
# 十大股东（含限售股，仅用于交叉校验）
ALL_HOLDER_REPORT = 'RPT_CUSTOM_DMSK_HOLDERS_JOIN_HOLDER_SHAREANALYSIS'

# 上游 JSON 字段名 -> 输出列名（按名映射，不依赖字段顺序）
RAW_FIELD_MAP = {
    'SECURITY_CODE': '股票代码',
    'SECURITY_NAME_ABBR': '股票简称',
    'HOLDER_NAME': '股东名称',
    'HOLDER_RANK': '股东名次',
    'HOLD_NUM': '期末持股-数量',
    'XZCHANGE': '期末持股-数量变化',
    'HOLD_RATIO_CHANGE': '期末持股-数量变化比例',
    'HOLDNUM_CHANGE_NAME': '期末持股-持股变动',
    'HOLDER_MARKET_CAP': '期末持股-流通市值',
    'HOLD_RATIO': '持股占流通比例',
    'UPDATE_DATE': '公告日',
}

HOLDER_COLUMNS = [
    '股票代码',
    '股票简称',
    '股东名称',
    '股东名次',
    '期末持股-数量',
    '期末持股-数量变化',
    '期末持股-数量变化比例',
    '期末持股-持股变动',
    '期末持股-流通市值',
    '持股占流通比例',
    '公告日',
]

_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'),
    'Referer': 'https://data.eastmoney.com/gdfx/HoldingAnalyse.html',
}

# 本地全市场缓存默认放在系统临时目录，避免污染仓库
DEFAULT_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'em_gdfx_cache')

# 缓存有效期（秒）；财报数据披露后仍可能被上游修订
CACHE_TTL = 6 * 3600


def _normalize_date(report_date: str) -> str:
    """``'20260930'`` / ``'2026-09-30'`` -> ``'2026-09-30'``"""
    digits = ''.join(ch for ch in str(report_date) if ch.isdigit())
    if len(digits) != 8:
        raise ValueError(f'非法的报告期日期: {report_date}')
    return f'{digits[:4]}-{digits[4:6]}-{digits[6:]}'


def _request_page(report_date: str, page: int, page_size: int, timeout: int,
                  report_name: str, sort_columns: str, sort_types: str):
    """请求东财分页接口，返回 ``(rows, total_pages)``"""
    params = {
        'sortColumns': sort_columns,
        'sortTypes': sort_types,
        'pageSize': str(page_size),
        'pageNumber': str(page),
        'reportName': report_name,
        'columns': 'ALL',
        'source': 'WEB',
        'client': 'WEB',
        'filter': f"(END_DATE='{_normalize_date(report_date)}')",
    }
    resp = requests.get(EM_GDFX_URL, params=params, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    result = payload.get('result')
    if not result:
        return [], 0
    return result.get('data') or [], int(result.get('pages') or 0)


def _to_dataframe(rows: list) -> pd.DataFrame:
    """把上游原始行按字段名映射成中文列"""
    records = []
    for raw in rows:
        record = {}
        for raw_key, column in RAW_FIELD_MAP.items():
            record[column] = raw.get(raw_key)
        records.append(record)

    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=HOLDER_COLUMNS)

    df['股票代码'] = df['股票代码'].astype(str).str.zfill(6)
    for column in ('股东名次', '期末持股-数量', '期末持股-数量变化',
                   '期末持股-数量变化比例', '期末持股-流通市值', '持股占流通比例'):
        df[column] = pd.to_numeric(df[column], errors='coerce')

    df = df[HOLDER_COLUMNS]
    df = df.sort_values(
        by=['公告日', '股票代码', '股东名次'],
        ascending=[False, True, True],
        kind='mergesort',
        na_position='last',
    ).reset_index(drop=True)
    return df


def _cache_path(cache_dir: str, report_date: str, report_name: str) -> str:
    tag = 'free' if report_name == FREE_HOLDER_REPORT else 'all'
    return os.path.join(cache_dir, f'gdfx_{tag}_{_normalize_date(report_date)}.pkl')


def fetch_free_holders(report_date: str, timeout: int = 60, page_size: int = 500,
                       cache_dir: str = DEFAULT_CACHE_DIR, use_cache: bool = True,
                       report_name: str = FREE_HOLDER_REPORT,
                       sort_columns: str = 'UPDATE_DATE,SECURITY_CODE,HOLDER_RANK',
                       sort_types: str = '-1,1,1') -> pd.DataFrame:
    """
    抓取全市场十大流通股东明细（按字段名映射，列序稳定）。

    Args:
        report_date: 报告期，``'YYYYMMDD'`` 或 ``'YYYY-MM-DD'``
        timeout: 单次请求超时（秒）
        page_size: 每页条数
        cache_dir: 本地 pkl 缓存目录，传 ``None`` 关闭缓存
        use_cache: 是否允许读写本地缓存
        report_name: 东财报表名，默认十大流通股东
        sort_columns / sort_types: 东财排序参数

    Returns:
        DataFrame: 列为 :data:`HOLDER_COLUMNS`，按 ``股票代码``、``股东名次`` 升序；
        报告期无数据时返回空 DataFrame。
    """
    path = None
    if use_cache and cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        path = _cache_path(cache_dir, report_date, report_name)
        if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < CACHE_TTL:
            with open(path, 'rb') as f:
                return pickle.load(f)

    rows = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        page_rows, total_pages = _request_page(
            report_date, page, page_size, timeout, report_name, sort_columns, sort_types
        )
        rows.extend(page_rows)
        page += 1

    df = _to_dataframe(rows)

    if path:
        with open(path, 'wb') as f:
            pickle.dump(df, f)

    return df


def filter_by_holder(df: pd.DataFrame, keywords) -> pd.DataFrame:
    """
    按股东名称关键字筛选。

    Args:
        df: :func:`fetch_free_holders` 返回的 DataFrame
        keywords: 关键字列表（如 ``['基本养老保险']`` / ``['中央汇金']``），
            任一关键字命中即保留。

    Returns:
        DataFrame: 命中行，保持原有排序
    """
    if df.empty:
        return df
    if isinstance(keywords, str):
        keywords = [keywords]
    mask = df['股东名称'].fillna('').str.contains('|'.join(keywords), na=False, regex=True)
    return df[mask].reset_index(drop=True)
