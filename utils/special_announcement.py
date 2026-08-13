# -*- coding: utf-8 -*-
"""每日股市特殊公告栏 —— 基于 Tushare Pro 的每日数据抓取与排版。

覆盖内容：
1. 交易异动
   - 交易所异常波动公告（stk_shock / stk_high_shock）
   - 龙虎榜（top_list）
   - 每日涨跌停 / 炸板（limit_list_d）
   - 每日停复牌（suspend_d）
2. 大股东增减持公告（stk_holdertrade）

辅助接口：stock_basic（代码->名称/行业）、trade_cal（最近交易日）、index_daily（大盘指数）。
"""
from __future__ import annotations

import datetime as dt
import math
import os
from typing import Dict, Optional

import pandas as pd
import tushare as ts

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = os.path.join(BASE_DIR, "tushare_token.txt")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "每日股市特殊公告栏")
RAW_DIR = os.path.join(BASE_DIR, "data", "special_announcements")

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
HOLDER_TYPE_CN = {"C": "公司", "P": "个人", "G": "高管"}
SUSPEND_TYPE_CN = {"S": "停牌", "R": "复牌"}
INDEX_LIST = [
    ("000001.SH", "上证指数"),
    ("399001.SZ", "深证成指"),
    ("399006.SZ", "创业板指"),
    ("899050.BJ", "北证50"),
]


def load_token() -> str:
    with open(TOKEN_FILE, "r", encoding="utf-8-sig") as f:
        return f.read().strip()


# ---------------------------------------------------------------- 数值格式化

def _fmt(x, digits=2, suffix=""):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return "-"
        return f"{float(x):,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "-"


def _wan(x):
    """元 -> 万元"""
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return "-"
        return f"{float(x) / 1e4:,.0f}"
    except (TypeError, ValueError):
        return "-"


def _yi(x):
    """元 -> 亿元"""
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return "-"
        return f"{float(x) / 1e8:,.2f}"
    except (TypeError, ValueError):
        return "-"


def _clock(t):
    """132727 -> 13:27:27"""
    try:
        s = str(int(t)).zfill(6)
        return f"{s[:2]}:{s[2:4]}:{s[4:]}"
    except (TypeError, ValueError):
        return "-"


def _fmt_period(p):
    """异常期间统一格式：2026081320260827 或 2026-08-12-2026-08-13 -> 2026-08-12 ~ 2026-08-13"""
    try:
        if p is None or (isinstance(p, float) and math.isnan(p)):
            return "-"
    except (TypeError, ValueError):
        pass
    s = str(p).strip()
    if len(s) == 16 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]} ~ {s[8:12]}-{s[12:14]}-{s[14:]}"
    if (
        len(s) == 21
        and s[4] == "-"
        and s[7] == "-"
        and s[10] == "-"
        and s[15] == "-"
        and s[18] == "-"
    ):
        return f"{s[:10]} ~ {s[11:]}"
    return s


def _short_reason(reason):
    """把交易所原文公告原因压缩成短标签，便于一眼扫读。"""
    if reason is None or (isinstance(reason, float) and math.isnan(reason)):
        return "-"
    text = str(reason).strip()
    replacements = [
        ("有价格涨跌幅限制的日收盘价格涨幅偏离值达到", "日涨幅偏离"),
        ("有价格涨跌幅限制的日收盘价格跌幅偏离值达到", "日跌幅偏离"),
        ("有价格涨跌幅限制的日收盘价格涨幅达到", "日涨幅"),
        ("有价格涨跌幅限制的日收盘价格跌幅达到", "日跌幅"),
        ("有价格涨跌幅限制的日价格振幅达到", "日振幅"),
        ("有价格涨跌幅限制的日换手率达到", "日换手率"),
        ("非S证券连续三个交易日内收盘价格涨幅偏离值累计达到", "3日涨幅偏离累计"),
        ("非S证券连续三个交易日内收盘价格跌幅偏离值累计达到", "3日跌幅偏离累计"),
        ("连续三个交易日内，涨幅偏离值累计达到", "3日涨幅偏离累计"),
        ("连续三个交易日内，跌幅偏离值累计达到", "3日跌幅偏离累计"),
        ("连续三个交易日内跌幅偏离值累计达到", "3日跌幅偏离累计"),
        ("连续三个交易日涨跌幅偏离值累计达到", "3日涨跌幅偏离累计"),
        ("连续三个交易日收盘价格涨跌幅偏离值累计达到", "3日涨跌幅偏离累计"),
        ("连续三个交易日内", "3日内"),
        ("连续10个交易日内", "10日内"),
        ("连续30个交易日内", "30日内"),
        ("日收盘价格涨幅偏离值达到", "日涨幅偏离"),
        ("日收盘价格跌幅偏离值达到", "日跌幅偏离"),
        ("日涨幅偏离值达到", "日涨幅偏离"),
        ("日跌幅偏离值达到", "日跌幅偏离"),
        ("日振幅值达到", "日振幅"),
        ("日换手率达到", "日换手率"),
        ("日涨幅达到", "日涨幅"),
        ("收盘价格涨幅偏离值累计达到", "涨幅偏离累计"),
        ("收盘价格跌幅偏离值累计达到", "跌幅偏离累计"),
        ("收盘价格涨跌幅偏离值累计达", "涨跌幅偏离累计"),
        ("涨跌幅偏离值累计达", "涨跌幅偏离累计"),
        ("的前5只证券", ""),
        ("的前五只证券", ""),
        ("的前5只", ""),
        ("的前五只", ""),
        ("的证券", ""),
        ("证券", ""),
        ("股票", ""),
    ]
    for src, dst in replacements:
        text = text.replace(src, dst)
    return text.strip("，, ")


def _clean_name(name):
    """去掉 tushare 名称里的占位空格，如 '金 螳 螂' -> '金螳螂'。"""
    try:
        return str(name).replace(" ", "").replace("　", "")
    except (TypeError, ValueError):
        return "-"


def _table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------- 数据抓取

class SpecialAnnouncementBoard:
    def __init__(self, token: Optional[str] = None, pro=None):
        self.pro = pro if pro is not None else ts.pro_api(token or load_token())
        self._basic: Optional[pd.DataFrame] = None

    def _query(self, api: str, **kwargs) -> pd.DataFrame:
        return self.pro.query(api, **kwargs)

    def stock_basic(self) -> pd.DataFrame:
        if self._basic is None:
            self._basic = self._query(
                "stock_basic", exchange="", list_status="L", fields="ts_code,name,industry"
            )
        return self._basic

    def name_map(self) -> Dict[str, Dict[str, str]]:
        df = self.stock_basic()
        return df.set_index("ts_code")[["name", "industry"]].to_dict("index")

    def latest_trade_date(self, ref: Optional[dt.date] = None) -> str:
        ref = ref or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
        start = (ref - dt.timedelta(days=20)).strftime("%Y%m%d")
        end = ref.strftime("%Y%m%d")
        cal = self._query("trade_cal", exchange="SSE", start_date=start, end_date=end)
        days = cal.loc[cal["is_open"] == 1, "cal_date"]
        if days.empty:
            raise RuntimeError(f"{end} 前 20 天内没有找到交易日")
        return str(days.sort_values().iloc[-1])

    def fetch_day(self, trade_date: str) -> Dict:
        """抓取单日全部板块数据（兼容旧逻辑，保留指数/龙虎榜/涨跌停等扩展信息）。"""
        trade_date = str(trade_date)
        data = {"trade_date": trade_date, "sections": {}}

        # 交易所异常波动公告
        data["sections"]["stk_shock"] = self._query("stk_shock", trade_date=trade_date)
        data["sections"]["stk_high_shock"] = self._query(
            "stk_high_shock", trade_date=trade_date
        )

        # 大盘指数（可选，取不到不阻塞）
        rows = []
        for code, _ in INDEX_LIST:
            try:
                idx = self._query("index_daily", ts_code=code, trade_date=trade_date)
                if len(idx):
                    rows.append(idx.iloc[0])
            except Exception:  # noqa: BLE001
                continue
        data["sections"]["index_daily"] = pd.DataFrame(rows)

        # 交易异动与股东增减持
        data["sections"]["top_list"] = self._query("top_list", trade_date=trade_date)
        data["sections"]["limit_list_d"] = self._query("limit_list_d", trade_date=trade_date)
        data["sections"]["suspend_d"] = self._query("suspend_d", trade_date=trade_date)
        data["sections"]["stk_holdertrade"] = self._query(
            "stk_holdertrade", ann_date=trade_date
        )
        data["name_map"] = self.name_map()
        return data

    def fetch_day_simple(self, trade_date: str) -> Dict:
        """精简抓取：仅抓取「交易异动」与「股东增减持」公告。

        - 交易异动：stk_shock（异常波动）+ stk_high_shock（严重异常波动）
        - 股东增减持：stk_holdertrade

        接口稳定性好、调用额度低，适合每日公告栏页面快速刷新。
        """
        trade_date = str(trade_date)
        data = {
            "trade_date": trade_date,
            "sections": {
                "stk_shock": self._query("stk_shock", trade_date=trade_date),
                "stk_high_shock": self._query("stk_high_shock", trade_date=trade_date),
                "stk_holdertrade": self._query("stk_holdertrade", ann_date=trade_date),
            },
            "name_map": self.name_map(),
        }
        return data


# ---------------------------------------------------------------- 落盘

def save_raw(data: Dict, raw_dir: Optional[str] = None) -> str:
    base = raw_dir or RAW_DIR
    out = os.path.join(base, data["trade_date"])
    os.makedirs(out, exist_ok=True)
    for name, df in data["sections"].items():
        if df is not None and len(df):
            df.to_csv(os.path.join(out, f"{name}.csv"), index=False, encoding="utf-8-sig")
    return out


def save_board(markdown: str, trade_date: str, output_dir: Optional[str] = None) -> str:
    out_dir = output_dir or OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    day = dt.datetime.strptime(str(trade_date), "%Y%m%d").date().isoformat()
    path = os.path.join(out_dir, f"{day}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown)
    return path


def save_struct_data(payload: Dict, output_dir: Optional[str] = None) -> str:
    """把页面所需的结构化数据落盘为 JSON，便于页面快速读取渲染。"""
    import json

    out_dir = output_dir or OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    day = dt.datetime.strptime(str(payload["trade_date"]), "%Y%m%d").date().isoformat()
    path = os.path.join(out_dir, f"{day}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def load_struct_data(date_str: str, output_dir: Optional[str] = None) -> Optional[Dict]:
    """读取某日的结构化公告数据。"""
    import json

    out_dir = output_dir or OUTPUT_DIR
    path = os.path.join(out_dir, f"{date_str}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_struct_data(data: Dict) -> Dict:
    """把 fetch_day_simple 的原始 DataFrame 转成页面可直接渲染的结构化字典。

    输出结构：
    {
        "trade_date": "20260813",
        "generated_at": "2026-08-13 23:30",
        "summary": {"shock": 22, "high_shock": 2, "holder_in": 2, "holder_de": 31, "significant": 1},
        "shock": [{"ts_code","name","market","reason","period"}, ...],
        "high_shock": [...],
        "holder_in": [...],   # 增持
        "holder_de": [...],   # 减持
    }
    """
    trade_date = data["trade_date"]
    sections = data["sections"]
    shock_df = sections.get("stk_shock")
    high_df = sections.get("stk_high_shock")
    ht_df = sections.get("stk_holdertrade")

    def _safe_len(df):
        return 0 if df is None else int(len(df))

    summary = {
        "shock": _safe_len(shock_df),
        "high_shock": _safe_len(high_df),
        "holder_total": _safe_len(ht_df),
        "holder_in": 0,
        "holder_de": 0,
        "significant": 0,
    }

    # ---------- 异动 ----------
    def _shock_rows(df):
        if df is None or len(df) == 0:
            return []
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "ts_code": str(r.get("ts_code", "")),
                "name": _clean_name(r.get("name")),
                "market": str(r.get("trade_market", "-")),
                "reason": _short_reason(r.get("reason")),
                "period": _fmt_period(r.get("period")),
            })
        return rows

    shock_rows = _shock_rows(shock_df)
    high_rows = _shock_rows(high_df)

    # ---------- 增减持 ----------
    holder_in_rows: list = []
    holder_de_rows: list = []
    name_map = data.get("name_map") or {}
    if ht_df is not None and len(ht_df):
        ht = ht_df.copy()
        ht = ht.drop_duplicates(
            subset=["ts_code", "holder_name", "change_vol", "change_ratio", "avg_price"]
        )
        # 估算变动金额（万元）
        amt = ht["avg_price"].fillna(0) * ht["change_vol"].fillna(0)
        ht["est_amount_wan"] = amt / 1e4
        # 是否大额（变动比例 ≥5% 或 估算金额 ≥1亿）
        ht["significant"] = (ht["change_ratio"].fillna(0) >= 5) | (amt >= 1e8)
        summary["significant"] = int(ht["significant"].sum())

        # 增持
        sub_in = ht[ht["in_de"] == "IN"].copy().sort_values("change_ratio", ascending=False)
        summary["holder_in"] = int(len(sub_in))
        for _, r in sub_in.iterrows():
            code = str(r.get("ts_code", ""))
            # stk_holdertrade 不含 name 字段，从 name_map 补全
            raw_name = r.get("name")
            if raw_name is None or (isinstance(raw_name, float) and pd.isna(raw_name)) or str(raw_name).strip() == "" or str(raw_name) == "nan":
                raw_name = name_map.get(code, {}).get("name", "-")
            holder_in_rows.append({
                "ts_code": code,
                "name": _clean_name(raw_name),
                "holder_name": str(r.get("holder_name", "-")),
                "holder_type": HOLDER_TYPE_CN.get(r.get("holder_type"), str(r.get("holder_type", "-"))),
                "change_vol_wan": _fmt(r.get("change_vol") / 1e4, 0) if pd.notna(r.get("change_vol")) else "-",
                "change_ratio": _fmt(r.get("change_ratio")),
                "avg_price": _fmt(r.get("avg_price")),
                "est_amount_wan": _fmt(r.get("est_amount_wan"), 0),
                "after_share_wan": _fmt(r.get("after_share") / 1e4, 0) if pd.notna(r.get("after_share")) else "-",
                "after_ratio": _fmt(r.get("after_ratio")),
                "significant": bool(r.get("significant")),
            })

        # 减持
        sub_de = ht[ht["in_de"] == "DE"].copy().sort_values("change_ratio", ascending=False)
        summary["holder_de"] = int(len(sub_de))
        for _, r in sub_de.iterrows():
            code = str(r.get("ts_code", ""))
            raw_name = r.get("name")
            if raw_name is None or (isinstance(raw_name, float) and pd.isna(raw_name)) or str(raw_name).strip() == "" or str(raw_name) == "nan":
                raw_name = name_map.get(code, {}).get("name", "-")
            holder_de_rows.append({
                "ts_code": code,
                "name": _clean_name(raw_name),
                "holder_name": str(r.get("holder_name", "-")),
                "holder_type": HOLDER_TYPE_CN.get(r.get("holder_type"), str(r.get("holder_type", "-"))),
                "change_vol_wan": _fmt(r.get("change_vol") / 1e4, 0) if pd.notna(r.get("change_vol")) else "-",
                "change_ratio": _fmt(r.get("change_ratio")),
                "avg_price": _fmt(r.get("avg_price")),
                "est_amount_wan": _fmt(r.get("est_amount_wan"), 0),
                "after_share_wan": _fmt(r.get("after_share") / 1e4, 0) if pd.notna(r.get("after_share")) else "-",
                "after_ratio": _fmt(r.get("after_ratio")),
                "significant": bool(r.get("significant")),
            })

    generated_at = dt.datetime.now(
        dt.timezone(dt.timedelta(hours=8))
    ).strftime("%Y-%m-%d %H:%M")

    return {
        "trade_date": trade_date,
        "generated_at": generated_at,
        "summary": summary,
        "shock": shock_rows,
        "high_shock": high_rows,
        "holder_in": holder_in_rows,
        "holder_de": holder_de_rows,
    }


# ---------------------------------------------------------------- 版式生成

def build_board(data: Dict, generated_at: Optional[str] = None) -> str:
    trade_date = data["trade_date"]
    sections = data["sections"]
    d = dt.datetime.strptime(trade_date, "%Y%m%d").date()
    weekday = WEEKDAYS[d.weekday()]
    if generated_at is None:
        generated_at = dt.datetime.now(
            dt.timezone(dt.timedelta(hours=8))
        ).strftime("%Y-%m-%d %H:%M")

    top = sections.get("top_list")
    lmt = sections.get("limit_list_d")
    sus = sections.get("suspend_d")
    ht = sections.get("stk_holdertrade")
    shock = sections.get("stk_shock")
    high_shock = sections.get("stk_high_shock")
    idx = sections.get("index_daily")

    def _empty(df):
        return df is None or len(df) == 0

    # 涨跌停 / 炸板
    u_df = d_df = z_df = pd.DataFrame()
    if lmt is not None and len(lmt):
        u_df = lmt[lmt["limit"] == "U"].copy()
        d_df = lmt[lmt["limit"] == "D"].copy()
        z_df = lmt[lmt["limit"] == "Z"].copy()

    def _st_cnt(df):
        if _empty(df):
            return 0
        return int(df["name"].astype(str).str.contains("ST", na=False).sum())

    # 股东增减持
    ht_in = ht_de = pd.DataFrame()
    if ht is not None and len(ht):
        ht_in = ht[ht["in_de"] == "IN"].copy()
        ht_de = ht[ht["in_de"] == "DE"].copy()

    def _significant(df):
        if _empty(df):
            return 0
        cond_ratio = df["change_ratio"].fillna(0) >= 5
        cond_amt = df["avg_price"].fillna(0) * df["change_vol"].fillna(0) >= 1e8
        return int((cond_ratio | cond_amt).sum())

    # 连板统计
    max_limit = 0
    limit_cnt = {}
    if len(u_df):
        max_limit = int(u_df["limit_times"].max())
        limit_cnt = u_df["limit_times"].value_counts().to_dict()

    # ------------------------------------------------------------ 标题
    lines = [
        "# 每日股市特殊公告栏",
        "",
        f"**交易日**：{d.isoformat()}（{weekday}）　|　**生成时间**：{generated_at}　|　"
        f"**数据源**：Tushare Pro（全市场）",
        "",
    ]

    # ------------------------------------------------------------ 大盘指数
    if idx is not None and len(idx):
        lines += ["## 一、今日大盘", ""]
        idx_rows = []
        for _, row in idx.iterrows():
            code = row.get("ts_code", "")
            name = dict(INDEX_LIST).get(code, code)
            chg = row.get("pct_chg")
            chg_txt = "-"
            if chg is not None and not (isinstance(chg, float) and math.isnan(chg)):
                sign = "+" if chg > 0 else ""
                chg_txt = f"{sign}{float(chg):.2f}%"
            idx_rows.append((name, _fmt(row.get("close"), 2), chg_txt))
        lines += [_table(("指数", "收盘", "涨跌幅"), idx_rows), "", ""]

    # ------------------------------------------------------------ 概览
    shock_txt = f"{len(shock)} 条" if shock is not None and len(shock) else "无"
    high_txt = f"{len(high_shock)} 条" if high_shock is not None and len(high_shock) else "无"

    sus_s = 0
    sus_r = 0
    if sus is not None and len(sus):
        sus_s = int((sus["suspend_type"] == "S").sum())
        sus_r = int((sus["suspend_type"] == "R").sum())

    overview = [
        ("交易所异常波动公告", shock_txt),
        ("交易所严重异常波动", high_txt),
        ("龙虎榜上榜", f"{len(top)} 条 / {int(top['ts_code'].nunique())} 家" if top is not None and len(top) else "无"),
        ("涨停", f"{len(u_df)} 家" + (f"（含ST {_st_cnt(u_df)}家）" if _st_cnt(u_df) else "")),
        ("炸板", f"{len(z_df)} 家" if len(z_df) else "无"),
        ("跌停", f"{len(d_df)} 家" + (f"（含ST {_st_cnt(d_df)}家）" if _st_cnt(d_df) else "")),
        ("最高连板", f"{max_limit} 板 × {limit_cnt.get(max_limit, 0)} 家" if max_limit else "无"),
        ("停牌 / 复牌", f"{sus_s} / {sus_r}"),
        ("股东增持公告", f"{len(ht_in)} 条" if len(ht_in) else "无"),
        ("股东减持公告", f"{len(ht_de)} 条" if len(ht_de) else "无"),
        ("大额增减持(比例≥5%或金额≥1亿)", f"{_significant(ht_in) + _significant(ht_de)} 条"),
    ]
    lines += ["## 二、今日概览", "", _table(("指标", "数值"), overview), "", ""]

    # ------------------------------------------------------------ 交易异动
    lines += ["## 三、交易异动", ""]

    lines += ["### 3.1 交易所异常波动公告", ""]
    if shock is not None and len(shock):
        rows = [
            (r["ts_code"], r.get("name", "-"), r.get("trade_market", "-"),
             _short_reason(r.get("reason")), _fmt_period(r.get("period")))
            for _, r in shock.iterrows()
        ]
        lines += [_table(("代码", "名称", "交易所", "异常说明", "异常期间"), rows), "", ""]
    else:
        lines += ["（当日无）", "", ""]

    lines += ["### 3.2 交易所严重异常波动公告", ""]
    if high_shock is not None and len(high_shock):
        rows = [
            (r["ts_code"], r.get("name", "-"), r.get("trade_market", "-"),
             _short_reason(r.get("reason")), _fmt_period(r.get("period")))
            for _, r in high_shock.iterrows()
        ]
        lines += [_table(("代码", "名称", "交易所", "异常说明", "异常期间"), rows), "", ""]
    else:
        lines += ["（当日无）", "", ""]

    lines += ["### 3.3 龙虎榜上榜原因分布", ""]
    if top is not None and len(top):
        reason_summary = (
            top["reason"].map(_short_reason).value_counts().head(10).to_dict()
        )
        rows = [(k, v) for k, v in reason_summary.items()]
        lines += [_table(("上榜原因", "条数"), rows), ""]

    lines += ["### 3.4 龙虎榜明细（按净买额绝对值排序，净买额单位：万元）", ""]
    if top is not None and len(top):
        g = (
            top.groupby("ts_code")
            .agg(
                name=("name", "first"),
                pct=("pct_change", "first"),
                turnover=("turnover_rate", "first"),
                amount=("amount", "first"),
                net=("net_amount", "sum"),
                cnt=("reason", "count"),
                reasons=("reason", lambda s: "；".join(dict.fromkeys(s))),
            )
            .reset_index()
        )
        g["abs_net"] = g["net"].abs()
        g = g.sort_values("abs_net", ascending=False)
        rows = []
        for _, r in g.iterrows():
            net = r["net"]
            net_txt = _wan(net)
            if net is not None and not (isinstance(net, float) and math.isnan(net)):
                if net > 0:
                    net_txt = f"▲ {net_txt}"
                elif net < 0:
                    net_txt = f"▼ {_wan(abs(net))}"
            reasons = "、".join(dict.fromkeys(_short_reason(x) for x in str(r["reasons"]).split("；")))
            rows.append(
                (r["ts_code"], _clean_name(r["name"]), _fmt(r["pct"]), _fmt(r["turnover"], 1),
                 _yi(r["amount"]), net_txt, r["cnt"], reasons[:60])
            )
        lines += [_table(("代码", "名称", "涨跌幅%", "换手率%", "成交额(亿)", "净买额(万)", "次数", "上榜原因"), rows), "", ""]
    else:
        lines += ["（当日无）", "", ""]

    # ------------------------------------------------------------ 涨跌停
    lines += ["## 四、涨跌停", ""]

    lines += ["### 4.1 连板高度", ""]
    if len(u_df):
        rows = []
        for times in sorted(limit_cnt, reverse=True):
            sub = u_df[u_df["limit_times"] == times]
            names = "、".join(_clean_name(x) for x in sub["name"].astype(str).head(8).tolist())
            label = "首板" if times == 1 else f"{int(times)}连板"
            rows.append((label, int(limit_cnt[times]), names))
        lines += [_table(("高度", "家数", "个股"), rows), ""]
    else:
        lines += ["（当日无涨停）", ""]

    lines += ["### 4.2 涨停明细", ""]
    if len(u_df):
        u2 = u_df.copy()
        u2["fd"] = u2["fd_amount"].fillna(0)
        u2 = u2.sort_values(["limit_times", "fd"], ascending=[False, False])
        rows = []
        for _, r in u2.iterrows():
            name = _clean_name(r["name"])
            if "ST" in str(name):
                name = f"{name}⚠️"
            rows.append(
                (r["ts_code"], name, r.get("industry", "-"), _fmt(r["close"]),
                 _fmt(r["pct_chg"]), _yi(r["amount"]), _wan(r["fd_amount"]),
                 _clock(r.get("first_time")), _fmt(r.get("open_times"), 0),
                 _fmt(r["limit_times"], 0), r.get("up_stat", "-"))
            )
        lines += [
            _table(
                ("代码", "名称", "行业", "收盘", "涨跌幅%", "成交额(亿)", "封单(万)",
                 "首封时间", "开板次数", "连板", "涨停统计"),
                rows,
            ),
            "",
            "",
        ]
    else:
        lines += ["（当日无涨停）", "", ""]

    lines += ["### 4.3 炸板明细", ""]
    if len(z_df):
        rows = [
            (r["ts_code"], _clean_name(r["name"]), r.get("industry", "-"), _fmt(r["close"]),
             _fmt(r["pct_chg"]), _yi(r["amount"]), r.get("up_stat", "-"))
            for _, r in z_df.iterrows()
        ]
        lines += [_table(("代码", "名称", "行业", "收盘", "涨跌幅%", "成交额(亿)", "涨停统计"), rows), "", ""]
    else:
        lines += ["（当日无炸板）", "", ""]

    lines += ["### 4.4 跌停明细", ""]
    if len(d_df):
        rows = [
            (r["ts_code"], _clean_name(r["name"]), r.get("industry", "-"), _fmt(r["close"]),
             _fmt(r["pct_chg"]), _yi(r["amount"]), _fmt(r.get("open_times"), 0))
            for _, r in d_df.iterrows()
        ]
        lines += [_table(("代码", "名称", "行业", "收盘", "涨跌幅%", "成交额(亿)", "开板次数"), rows), "", ""]
    else:
        lines += ["（当日无跌停）", "", ""]

    # ------------------------------------------------------------ 停复牌
    lines += ["## 五、停复牌", ""]
    if sus is not None and len(sus):
        name_map = data.get("name_map") or {}
        rows = []
        for _, r in sus.iterrows():
            code = r["ts_code"]
            nm = name_map.get(code, {}).get("name", "-")
            st = SUSPEND_TYPE_CN.get(r.get("suspend_type"), str(r.get("suspend_type")))
            timing = r.get("suspend_timing")
            timing_txt = "-" if timing is None or (isinstance(timing, float) and math.isnan(timing)) else timing
            rows.append((code, nm, st, timing_txt))
        lines += [_table(("代码", "名称", "状态", "停牌时段说明"), rows), "", ""]
    else:
        lines += ["（当日无停复牌）", "", ""]

    # ------------------------------------------------------------ 股东增减持
    lines += ["## 六、大股东增减持公告", ""]
    lines += [
        "> 口径说明：变动数量为公告披露的股份数（展示为万股）；变动比例 = 占流通比例（%）；"
        "⭐ 表示变动比例 ≥5% 或按均价估算金额 ≥1亿元；同一股东同日完全相同的重复公告已合并展示。",
        "",
    ]

    name_map = data.get("name_map") or {}

    def _holder_rows(df):
        if _empty(df):
            return []
        df2 = df.drop_duplicates(
            subset=["ts_code", "holder_name", "change_vol", "change_ratio", "avg_price"]
        ).copy()
        df2["sort_ratio"] = df2["change_ratio"].fillna(0)
        df2 = df2.sort_values("sort_ratio", ascending=False)
        rows = []
        for _, r in df2.iterrows():
            code = r["ts_code"]
            nm = name_map.get(code, {}).get("name", "-")
            amt = r["avg_price"] * r["change_vol"] if pd.notna(r.get("avg_price")) else None
            star = ""
            ratio = r.get("change_ratio")
            if (ratio is not None and pd.notna(ratio) and float(ratio) >= 5) or (
                amt is not None and amt >= 1e8
            ):
                star = "⭐"
            holder = f"{star}{r['holder_name']}"
            rows.append(
                (code, nm, holder, HOLDER_TYPE_CN.get(r.get("holder_type"), r.get("holder_type", "-")),
                 _fmt(r.get("change_vol") / 1e4, 0) if pd.notna(r.get("change_vol")) else "-",
                 _fmt(ratio), _fmt(r.get("avg_price")), _wan(amt),
                 _fmt(r.get("after_share") / 1e4, 0) if pd.notna(r.get("after_share")) else "-",
                 _fmt(r.get("after_ratio")))
            )
        return rows

    lines += [f"### 6.1 增持公告（{len(ht_in)} 条）", ""]
    rows = _holder_rows(ht_in)
    if rows:
        lines += [
            _table(
                ("代码", "名称", "股东", "类型", "变动(万股)", "变动比例%", "均价(元)",
                 "变动金额(万)", "变动后持股(万股)", "变动后占比%"),
                rows,
            ),
            "",
            "",
        ]
    else:
        lines += ["（当日无增持公告）", "", ""]

    lines += [f"### 6.2 减持公告（{len(ht_de)} 条）", ""]
    rows = _holder_rows(ht_de)
    if rows:
        lines += [
            _table(
                ("代码", "名称", "股东", "类型", "变动(万股)", "变动比例%", "均价(元)",
                 "变动金额(万)", "变动后持股(万股)", "变动后占比%"),
                rows,
            ),
            "",
            "",
        ]
    else:
        lines += ["（当日无减持公告）", "", ""]

    # ------------------------------------------------------------ 页脚
    lines += ["---", ""]
    lines += [
        "> 数据来源：Tushare Pro（`stk_shock` / `stk_high_shock` 异常波动公告 / "
        "`top_list` 龙虎榜 / `limit_list_d` 涨跌停 / `suspend_d` 停复牌 / "
        "`stk_holdertrade` 股东增减持）。",
    ]
    if shock is None or high_shock is None:
        lines += ["> 交易所异常波动公告接口暂不可用，本栏以龙虎榜 + 涨跌停覆盖交易异动。"]
    lines += ["> 仅供研究参考，不构成投资建议。", ""]
    return "\n".join(lines)
