# -*- coding: utf-8 -*-
"""7 大指数吞没形态识别器（基于 Tushare Pro）。

覆盖指数：
  - 上证指数    000001.SH
  - 深证成指    399001.SZ
  - 创业板指    399006.SZ
  - 沪深300    000300.SH
  - 科创50      000688.SH
  - 中证500     000905.SH
  - 中证A50     930050.CSI（中证50 的现代名称，2024 上交所发布）

吞没形态（Engulfing Pattern）定义（标准 2 蜡烛线反转型态）：

  看涨吞没 Bullish Engulfing（出现在下跌趋势末端，反转看涨）：
    1) 前一日 K 线：阴线（close < open）
    2) 当日 K 线：阳线（close > open）
    3) 当日开盘价 < 前日收盘价（向下跳空/平开向下切入）
    4) 当日收盘价 > 前日开盘价（阳线实体完全吞没前日阴线实体）
    5) 当日实体长度 ≥ 前日实体长度（实体的"吞没"力度）

  看跌吞没 Bearish Engulfing（出现在上升趋势末端，反转看跌）：
    1) 前一日 K 线：阳线（close > open）
    2) 当日 K 线：阴线（close < open）
    3) 当日开盘价 > 前日收盘价（向上跳空/平开向上切入）
    4) 当日收盘价 < 前日开盘价（阴线实体完全吞没前日阳线实体）
    5) 当日实体长度 ≥ 前日实体长度

数据流：
  复用 FundTracker 已有的指数缓存体系
  （data/fund_tracker_cache/indexes/ 与 data/fund_tracker_cache/custom_indexes/），
  仅在缺失/到期时增量补拉近 3 年数据，写回同一缓存目录。
  → 形态识别 → 结构化 JSON（output/吞没形态/{date}.json）→ NiceGUI 面板渲染

注意：本模块独立维护一份缓存，但使用与 FundTracker 完全相同的目录与文件格式，
      不产生额外的副缓存。当 FundTracker 也引用同代码时，会自动复用本模块写入的数据。
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
import tushare as ts

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = os.path.join(BASE_DIR, "tushare_token.txt")

# 复用 FundTracker 的指数缓存目录结构：
#   data/fund_tracker_cache/indexes/         — FundTracker 的 4 大指数固定缓存
#   data/fund_tracker_cache/custom_indexes/  — FundTracker 的自定义/任意指数缓存
# 为避免与 FundTracker 的 400 天裁剪逻辑冲突，本模块对所有 6 个指数一律写到 custom_indexes/，
# FundTracker 不会触碰此目录（其 _index_cache_path_any 对已知 4 大指数只走 indexes/）。
SHARED_CACHE_DIR = os.path.join(BASE_DIR, "data", "fund_tracker_cache", "custom_indexes")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "吞没形态")

# 3 年窗口（约 750 个交易日，留 1100 自然日覆盖节假日）
LOOKBACK_YEARS = 3
LOOKBACK_CALENDAR_DAYS = LOOKBACK_YEARS * 365 + 30
LOOKBACK_DAYS = LOOKBACK_YEARS * 365 + 30  # 含节假日缓冲

# 7 大指数定义（Tushare 代码 + 中文名 + 短名 + 主题色）
INDEX_DEFS: List[Dict] = [
    {
        "ts_code": "000001.SH",
        "name": "上证指数",
        "short": "上证",
        "color": "red",
        "accent": "#dc2626",
    },
    {
        "ts_code": "399001.SZ",
        "name": "深证成指",
        "short": "深证",
        "color": "blue",
        "accent": "#2563eb",
    },
    {
        "ts_code": "399006.SZ",
        "name": "创业板指",
        "short": "创业板",
        "color": "purple",
        "accent": "#9333ea",
    },
    {
        "ts_code": "000300.SH",
        "name": "沪深300",
        "short": "沪深300",
        "color": "orange",
        "accent": "#ea580c",
    },
    {
        "ts_code": "000688.SH",
        "name": "科创50",
        "short": "科创50",
        "color": "teal",
        "accent": "#0d9488",
    },
    {
        "ts_code": "000905.SH",
        "name": "中证500",
        "short": "中证500",
        "color": "cyan",
        "accent": "#0891b2",
    },
    {
        "ts_code": "930050.CSI",
        "name": "中证A50",
        "short": "中证A50",
        "color": "indigo",
        "accent": "#4f46e5",
    },
]

INDEX_NAME_MAP: Dict[str, str] = {d["ts_code"]: d["name"] for d in INDEX_DEFS}


def load_token() -> str:
    with open(TOKEN_FILE, "r", encoding="utf-8-sig") as f:
        return f.read().strip()


# ---------------------------------------------------------------- 数值格式化

def _fmt(x, digits: int = 2, suffix: str = "") -> str:
    if x is None:
        return "-"
    try:
        if isinstance(x, float) and math.isnan(x):
            return "-"
        return f"{float(x):,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "-"


def _pretty_date(d) -> str:
    """YYYYMMDD 或 datetime/date → YYYY-MM-DD"""
    if d is None:
        return "-"
    if isinstance(d, dt.datetime):
        return d.date().isoformat()
    if isinstance(d, dt.date):
        return d.isoformat()
    s = str(d).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


# ---------------------------------------------------------------- 形态识别

@dataclass
class EngulfingSignal:
    """单条吞没信号。"""
    ts_code: str
    name: str
    trade_date: str          # 交易日 YYYY-MM-DD
    pattern: str             # "bullish" 或 "bearish"
    prev_open: float
    prev_close: float
    prev_high: float
    prev_low: float
    prev_body: float         # |close - open|
    prev_pct_chg: float
    curr_open: float
    curr_close: float
    curr_high: float
    curr_low: float
    curr_body: float
    curr_pct_chg: float
    body_ratio: float        # curr_body / prev_body，>1 表示当日实体>前日实体
    cover_ratio: float       # 吞没比例（curr_body / prev_body，封顶 2.0 用于展示）
    prev_is_streak: bool     # 前一日是否处于连续趋势中
    streak_len: int          # 当前所处的同向连续天数
    note: str = ""           # 文本注释


def _detect_engulfing(df: pd.DataFrame, lookback_streak: int = 5) -> List[EngulfingSignal]:
    """在已经按交易日升序排列的 K 线 DataFrame 中识别所有吞没形态。

    输入 DataFrame 至少需要列：trade_date, open, close, high, low, pct_chg（可选）。
    """
    if df is None or len(df) < 2:
        return []

    # 统一字段类型
    df = df.copy().reset_index(drop=True)
    for c in ("open", "close", "high", "low"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "close", "high", "low"]).reset_index(drop=True)
    if len(df) < 2:
        return []

    df["body"] = (df["close"] - df["open"]).abs()
    df["is_bull"] = df["close"] > df["open"]
    df["is_bear"] = df["close"] < df["open"]
    # 平盘不计入信号（既不阳也不阴）
    df["is_flat"] = df["close"] == df["open"]
    df["prev_is_bull"] = df["is_bull"].shift(1)
    df["prev_is_bear"] = df["is_bear"].shift(1)

    # 连续同向天数（用于确认形态出现在趋势末端，反转更有意义）
    streak = []
    cur = 0
    direction = None
    for _, row in df.iterrows():
        if row["is_bull"]:
            d = "up"
        elif row["is_bear"]:
            d = "down"
        else:
            d = direction  # 平盘沿用前一日
        if d == direction:
            cur += 1
        else:
            cur = 1
            direction = d
        streak.append(cur)
    df["streak_len"] = streak

    signals: List[EngulfingSignal] = []
    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        if pd.isna(prev["open"]) or pd.isna(prev["close"]):
            continue
        if pd.isna(curr["open"]) or pd.isna(curr["close"]):
            continue

        prev_open = float(prev["open"])
        prev_close = float(prev["close"])
        prev_high = float(prev["high"])
        prev_low = float(prev["low"])
        prev_body = abs(prev_close - prev_open)
        curr_open = float(curr["open"])
        curr_close = float(curr["close"])
        curr_high = float(curr["high"])
        curr_low = float(curr["low"])
        curr_body = abs(curr_close - curr_open)

        if prev_body == 0 or curr_body == 0:
            continue  # 平盘不参与

        pattern = None
        # 看涨吞没
        if prev_close < prev_open and curr_close > curr_open:
            if curr_open <= prev_close and curr_close >= prev_open:
                if curr_body >= prev_body:
                    pattern = "bullish"
        # 看跌吞没
        elif prev_close > prev_open and curr_close < curr_open:
            if curr_open >= prev_close and curr_close <= prev_open:
                if curr_body >= prev_body:
                    pattern = "bearish"

        if not pattern:
            continue

        # 取 trend streak：看涨吞没时，看前一日的下跌连续天数；
        # 看跌吞没时，看前一日的上涨连续天数。
        if pattern == "bullish":
            # 前一日是阴线，使用前一日的 streak_len
            streak_len = int(df.iloc[i - 1]["streak_len"])
            streak_at_end = streak_len
            prev_is_streak = streak_len >= 2
        else:
            streak_len = int(df.iloc[i - 1]["streak_len"])
            streak_at_end = streak_len
            prev_is_streak = streak_len >= 2

        ratio = curr_body / prev_body
        note_bits = []
        if ratio >= 2.0:
            note_bits.append("强吞没")
        elif ratio >= 1.5:
            note_bits.append("中度吞没")
        else:
            note_bits.append("标准吞没")
        if not prev_is_streak:
            note_bits.append("前一日无连续趋势，注意反转力度")
        else:
            note_bits.append(f"前续 {streak_at_end} 日同向")

        signals.append(
            EngulfingSignal(
                ts_code=str(curr.get("ts_code", "")),
                name=INDEX_NAME_MAP.get(str(curr.get("ts_code", "")), str(curr.get("ts_code", ""))),
                trade_date=_pretty_date(curr.get("trade_date")),
                pattern=pattern,
                prev_open=prev_open,
                prev_close=prev_close,
                prev_high=prev_high,
                prev_low=prev_low,
                prev_body=prev_body,
                prev_pct_chg=float(prev.get("pct_chg") or 0.0),
                curr_open=curr_open,
                curr_close=curr_close,
                curr_high=curr_high,
                curr_low=curr_low,
                curr_body=curr_body,
                curr_pct_chg=float(curr.get("pct_chg") or 0.0),
                body_ratio=ratio,
                cover_ratio=min(ratio, 2.0),
                prev_is_streak=prev_is_streak,
                streak_len=streak_at_end,
                note=" · ".join(note_bits),
            )
        )
    return signals


def _trim_to_window(df: pd.DataFrame, today: dt.date, lookback_days: int) -> pd.DataFrame:
    """把 df 按 trade_date 裁剪到 [today - lookback_days, today] 窗口内。"""
    if df is None or len(df) == 0 or "trade_date" not in df.columns:
        return df
    try:
        parsed = pd.to_datetime(df["trade_date"], format="%Y%m%d", errors="coerce")
        cutoff = pd.Timestamp(today - dt.timedelta(days=lookback_days))
        keep = parsed >= cutoff
        return df[keep].reset_index(drop=True)
    except Exception:  # noqa: BLE001
        return df


# ---------------------------------------------------------------- 数据抓取与缓存

class EngulfingPatternBoard:
    def __init__(self, token: Optional[str] = None, pro=None):
        self.pro = pro if pro is not None else ts.pro_api(token or load_token())
        os.makedirs(SHARED_CACHE_DIR, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    def _query(self, api: str, **kwargs):
        return self.pro.query(api, **kwargs)

    # -------- 指数 K 线抓取（复用 FundTracker 缓存目录） --------
    def _cache_path(self, ts_code: str) -> str:
        """所有指数统一写到 custom_indexes/，避免 FundTracker 4 大指数索引被裁剪到 400 天。"""
        safe = ts_code.replace(".", "_")
        return os.path.join(SHARED_CACHE_DIR, f"{safe}.csv")

    def load_cache(self, ts_code: str) -> pd.DataFrame:
        """读取共享缓存。trade_date 兼容 YYYYMMDD 字符串 / datetime / date 三种格式。"""
        path = self._cache_path(ts_code)
        if not os.path.exists(path):
            return pd.DataFrame()
        try:
            df = pd.read_csv(path)
        except Exception as exc:  # noqa: BLE001
            print(f"[Engulfing] load cache {ts_code} failed: {exc}")
            return pd.DataFrame()
        if "trade_date" not in df.columns or len(df) == 0:
            return pd.DataFrame()
        # 标准化为 YYYYMMDD 字符串
        try:
            parsed = pd.to_datetime(df["trade_date"], errors="coerce")
            df["trade_date"] = parsed.dt.strftime("%Y%m%d")
            df = df.dropna(subset=["trade_date"])
        except Exception:
            df["trade_date"] = df["trade_date"].astype(str).str.replace(
                r"[^0-9]", "", regex=True
            )
            df = df[df["trade_date"].str.len() == 8]
        return df.reset_index(drop=True)

    def save_cache(self, ts_code: str, df: pd.DataFrame) -> None:
        if df is None or len(df) == 0:
            return
        try:
            os.makedirs(SHARED_CACHE_DIR, exist_ok=True)
            df.to_csv(self._cache_path(ts_code), index=False)
        except Exception as exc:  # noqa: BLE001
            print(f"[Engulfing] save cache {ts_code} failed: {exc}")

    def fetch_index_daily(self, ts_code: str, lookback_days: int = LOOKBACK_CALENDAR_DAYS,
                          force_refresh: bool = False) -> pd.DataFrame:
        """拉取指数近 N 日日线，与共享缓存合并；增量更新、去重、裁剪到目标窗口。

        与 FundTracker 的区别：本模块写入 custom_indexes/，不受 _CACHE_MIN_DAYS=400 裁剪。
        FundTracker 在不知道本模块存在的情况下读 custom_indexes/ 时仍按 400 天裁剪，
        但本模块的窗口更长（≈3 年），适合形态识别需要的历史深度。
        """
        today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
        end_date = today.strftime("%Y%m%d")

        cached = self.load_cache(ts_code)

        # 判断是否需要增量拉取
        need_refresh = force_refresh or cached.empty
        fetch_start = None
        if not need_refresh and len(cached):
            try:
                last_cached = str(cached["trade_date"].max())
                last_dt = dt.datetime.strptime(last_cached, "%Y%m%d").date()
                # 最后日期距今 > 5 个自然日：增量拉取增量区间
                # 否则：缓存足够新，跳过网络
                if (today - last_dt).days > 5:
                    need_refresh = True
                    fetch_start = (last_dt + dt.timedelta(days=1)).strftime("%Y%m%d")
                # 缓存起点超过目标窗口起点：需要往前补拉（首次补拉近 3 年）
                earliest_dt = dt.datetime.strptime(
                    str(cached["trade_date"].min()), "%Y%m%d"
                ).date()
                target_start = today - dt.timedelta(days=lookback_days)
                if earliest_dt > target_start:
                    need_refresh = True
                    fetch_start = target_start.strftime("%Y%m%d")
            except Exception:  # noqa: BLE001
                need_refresh = True

        if not need_refresh:
            # 缓存已足够，直接按目标窗口裁剪返回
            return _trim_to_window(cached, today, lookback_days)

        if fetch_start is None:
            fetch_start = (today - dt.timedelta(days=lookback_days)).strftime("%Y%m%d")

        df_new = pd.DataFrame()
        try:
            df_new = self.pro.index_daily(
                ts_code=ts_code, start_date=fetch_start, end_date=end_date
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[Engulfing] index_daily({ts_code}) failed: {exc}")
            df_new = pd.DataFrame()

        if df_new is None or len(df_new) == 0:
            # 拉取失败 → 使用已有缓存
            return _trim_to_window(cached, today, lookback_days)

        # 标准化 trade_date 为 YYYYMMDD 字符串，便于合并
        df_new = df_new.copy()
        if "trade_date" in df_new.columns:
            try:
                df_new["trade_date"] = pd.to_datetime(
                    df_new["trade_date"], errors="coerce"
                ).dt.strftime("%Y%m%d")
                df_new = df_new.dropna(subset=["trade_date"])
            except Exception:
                df_new["trade_date"] = df_new["trade_date"].astype(str)

        # 合并 + 去重 + 排序
        if cached is not None and len(cached):
            all_df = pd.concat([cached, df_new], ignore_index=True)
        else:
            all_df = df_new.copy()
        all_df = all_df.drop_duplicates(subset=["trade_date"]).sort_values(
            "trade_date"
        ).reset_index(drop=True)

        # 裁剪到目标窗口
        all_df = _trim_to_window(all_df, today, lookback_days)

        self.save_cache(ts_code, all_df)
        return all_df

    # -------- 形态识别（单指数） --------
    def detect_index(self, ts_code: str, force_refresh: bool = False) -> Dict:
        """对单指数执行：拉取 → 检测 → 返回结构化数据。"""
        df = self.fetch_index_daily(ts_code, force_refresh=force_refresh)
        if df is None or len(df) < 2:
            return {
                "ts_code": ts_code,
                "name": INDEX_NAME_MAP.get(ts_code, ts_code),
                "error": "数据不足",
                "kline": [],
                "signals": [],
                "latest": None,
                "last_date": None,
            }

        # 检测
        signals = _detect_engulfing(df)

        # 转 dict 列表
        sig_dicts = [s.__dict__.copy() for s in signals]
        # 倒序（最近优先）
        sig_dicts.sort(key=lambda x: x["trade_date"], reverse=True)

        # 最新一条（最近交易日的吞没信号）
        latest = sig_dicts[0] if sig_dicts else None
        last_date = str(df["trade_date"].iloc[-1]) if "trade_date" in df.columns and len(df) else None

        # 准备 kline 数据（限制近一年长度，避免 JSON 过大）
        last_dt = dt.datetime.strptime(last_date, "%Y%m%d").date() if last_date else dt.date.today()
        one_year_ago = last_dt - dt.timedelta(days=365)
        kline = []
        for _, row in df.iterrows():
            td = str(row.get("trade_date", ""))
            try:
                td_dt = dt.datetime.strptime(td, "%Y%m%d").date()
            except Exception:
                continue
            if td_dt < one_year_ago:
                continue
            kline.append({
                "trade_date": _pretty_date(td),
                "open": float(row["open"]),
                "close": float(row["close"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "pct_chg": float(row.get("pct_chg") or 0.0),
                "vol": float(row.get("vol") or 0.0),
                "amount": float(row.get("amount") or 0.0),
            })

        # 信号时间戳（用于在图上标注）
        sig_dates = {s["trade_date"] for s in sig_dicts}
        sig_map = {s["trade_date"]: s for s in sig_dicts}
        for bar in kline:
            if bar["trade_date"] in sig_dates:
                sig = sig_map[bar["trade_date"]]
                bar["signal"] = sig["pattern"]
                bar["signal_body_ratio"] = sig["body_ratio"]
            else:
                bar["signal"] = None

        # 近 3 年统计
        recent_3y = [s for s in sig_dicts
                     if dt.datetime.strptime(s["trade_date"], "%Y-%m-%d").date()
                     >= (last_dt - dt.timedelta(days=LOOKBACK_YEARS * 365))]
        bullish_count = sum(1 for s in recent_3y if s["pattern"] == "bullish")
        bearish_count = sum(1 for s in recent_3y if s["pattern"] == "bearish")

        return {
            "ts_code": ts_code,
            "name": INDEX_NAME_MAP.get(ts_code, ts_code),
            "last_date": _pretty_date(last_date) if last_date else None,
            "kline": kline,
            "signals": sig_dicts,
            "signals_total": {
                "bullish": bullish_count,
                "bearish": bearish_count,
                "all": len(recent_3y),
            },
            "latest": latest,
        }

    # -------- 全市场构建 --------
    def build_struct_data(self, force_refresh: bool = False) -> Dict:
        """对 7 大指数执行检测，返回页面渲染所需的结构化数据。"""
        results: Dict[str, Dict] = {}
        for d in INDEX_DEFS:
            code = d["ts_code"]
            try:
                results[code] = self.detect_index(code, force_refresh=force_refresh)
            except Exception as exc:  # noqa: BLE001
                print(f"[Engulfing] detect {code} failed: {exc}")
                results[code] = {
                    "ts_code": code,
                    "name": INDEX_NAME_MAP.get(code, code),
                    "error": str(exc),
                    "kline": [],
                    "signals": [],
                    "latest": None,
                    "last_date": None,
                    "signals_total": {"bullish": 0, "bearish": 0, "all": 0},
                }

        # 总体摘要
        summary = {
            "bullish": 0,
            "bearish": 0,
            "index_with_recent_signal": 0,
            "index_total": len(INDEX_DEFS),
        }
        for code, payload in results.items():
            total = payload.get("signals_total", {}) or {}
            summary["bullish"] += int(total.get("bullish", 0))
            summary["bearish"] += int(total.get("bearish", 0))
            latest = payload.get("latest")
            if latest:
                # 最近 5 个交易日内有信号，视为"近期触发"
                try:
                    last_dt = dt.datetime.strptime(payload["last_date"], "%Y-%m-%d").date()
                    sig_dt = dt.datetime.strptime(latest["trade_date"], "%Y-%m-%d").date()
                    if (last_dt - sig_dt).days <= 7:
                        summary["index_with_recent_signal"] += 1
                except Exception:  # noqa: BLE001
                    pass

        generated_at = dt.datetime.now(
            dt.timezone(dt.timedelta(hours=8))
        ).strftime("%Y-%m-%d %H:%M")
        # 业务日期（最近一个有数据的交易日）
        trade_dates = [r.get("last_date") for r in results.values()
                       if r.get("last_date")]
        trade_date = max(trade_dates) if trade_dates else generated_at[:10]

        return {
            "trade_date": trade_date,
            "generated_at": generated_at,
            "lookback_years": LOOKBACK_YEARS,
            "index_defs": INDEX_DEFS,
            "summary": summary,
            "results": results,
        }


# ---------------------------------------------------------------- 落盘

def save_struct_data(payload: Dict, output_dir: Optional[str] = None) -> str:
    out_dir = output_dir or OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    day = payload["trade_date"]
    path = os.path.join(out_dir, f"{day}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def load_struct_data(date_str: str, output_dir: Optional[str] = None) -> Optional[Dict]:
    out_dir = output_dir or OUTPUT_DIR
    path = os.path.join(out_dir, f"{date_str}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _available_dates(output_dir: Optional[str] = None) -> List[str]:
    out_dir = output_dir or OUTPUT_DIR
    if not os.path.isdir(out_dir):
        return []
    dates: List[str] = []
    for name in os.listdir(out_dir):
        if not name.endswith(".json"):
            continue
        stem = name[:-5]
        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
            dates.append(stem)
    return sorted(dates)


# ---------------------------------------------------------------- 自测

if __name__ == "__main__":
    # CLI 自测：python -m utils.engulfing_pattern
    board = EngulfingPatternBoard()
    payload = board.build_struct_data(force_refresh=True)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    for code, r in payload["results"].items():
        latest = r.get("latest") or {}
        print(
            f"{r['name']:<10} "
            f"last={r.get('last_date','-')} "
            f"3y_bull={r.get('signals_total',{}).get('bullish',0)} "
            f"3y_bear={r.get('signals_total',{}).get('bearish',0)} "
            f"latest={latest.get('pattern','-')}@{latest.get('trade_date','-')}"
        )
    path = save_struct_data(payload)
    print(f"saved: {path}")
