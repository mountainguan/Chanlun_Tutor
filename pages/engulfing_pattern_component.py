# -*- coding: utf-8 -*-
"""6 大指数吞没形态识别器 —— 公告栏子面板渲染。

布局：
  顶部品牌色标题条
  数据口径说明（折叠）
  4 张概览卡（近 3 年看涨/看跌 / 近期触发指数 / 总指数数）
  日期选择器 + 刷新按钮
  「最新吞没信号」 6 张指数卡（每指数显示：最新信号 + 最近 5 次信号 mini list）
  「近 3 年信号总览」表格（按指数聚合）
  「形态识别详情」 —— 选中某指数后展示 K 线 + 信号标注（Plotly）
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
from typing import Optional

from nicegui import ui

from utils.engulfing_pattern import (
    INDEX_DEFS,
    OUTPUT_DIR,
    _available_dates,
    _pretty_date,
    load_struct_data,
)
from pages.shared import setup_common_ui  # noqa: F401  兼容旧引用


# ---------------------------------------------------------------- 工具

def _fmt(x, digits: int = 2, suffix: str = "") -> str:
    try:
        if x is None:
            return "-"
        if isinstance(x, float) and (x != x):  # NaN
            return "-"
        return f"{float(x):,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "-"


def _pct(x) -> str:
    try:
        if x is None:
            return "-"
        v = float(x)
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.2f}%"
    except (TypeError, ValueError):
        return "-"


def _pattern_label(pattern: str) -> str:
    return "看涨吞没" if pattern == "bullish" else "看跌吞没"


def _pattern_color(pattern: str) -> tuple[str, str, str]:
    """(bg, text/border, icon)。

    大 A 配色习惯：涨 = 红、跌 = 绿。
      - 看涨吞没 bullish（多头信号 = 涨色） → 红色 rose
      - 看跌吞没 bearish（空头信号 = 跌色） → 绿色 emerald
    """
    if pattern == "bullish":
        return ("bg-rose-50 border-rose-200", "text-rose-700", "trending_up")
    return ("bg-emerald-50 border-emerald-200", "text-emerald-700", "trending_down")


# ---------------------------------------------------------------- K 线 + 信号 图表

def _build_candlestick_figure(index_def: dict, kline: list, signals: list) -> "object":
    """构造带吞没信号标注的 Plotly K 线图。

    交互能力：
      - 鼠标拖动：在 X 方向框选可缩放区间
      - 双击：重置视图
      - 底部 rangeslider：快速拖拽缩窗
      - 右上角 rangeselector：1M / 3M / 6M / 1Y / All 快捷切换
      - 默认显示最近 3 个月
    """
    try:
        import plotly.graph_objects as go
    except Exception:  # noqa: BLE001
        import plotly.graph_objects as go  # type: ignore

    dates = [bar["trade_date"] for bar in kline]
    opens = [bar["open"] for bar in kline]
    closes = [bar["close"] for bar in kline]
    highs = [bar["high"] for bar in kline]
    lows = [bar["low"] for bar in kline]
    pct = [bar.get("pct_chg", 0.0) for bar in kline]

    fig = go.Figure()

    # K 线（type="date" 启用 rangeslider / rangeselector）
    fig.add_trace(
        go.Candlestick(
            x=dates,
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            increasing=dict(line=dict(color="#dc2626"), fillcolor="#fee2e2"),
            decreasing=dict(line=dict(color="#16a34a"), fillcolor="#dcfce7"),
            name="K线",
            showlegend=False,
            hovertemplate=(
                "<b>%{x}</b><br>"
                "开：%{open:.2f}<br>"
                "收：%{close:.2f}<br>"
                "高：%{high:.2f}<br>"
                "低：%{low:.2f}<extra></extra>"
            ),
        )
    )

    # 信号标注（按 trade_date 排序映射回主序列索引）
    sig_by_date = {s["trade_date"]: s for s in signals}
    bull_x, bull_y, bull_txt = [], [], []
    bear_x, bear_y, bear_txt = [], [], []

    for i, bar in enumerate(kline):
        sig = sig_by_date.get(bar["trade_date"])
        if not sig:
            continue
        if sig["pattern"] == "bullish":
            bull_x.append(bar["trade_date"])
            bull_y.append(bar["low"] * 0.998)
            bull_txt.append(
                f"看涨吞没<br>{bar['trade_date']}<br>"
                f"实体比={sig['body_ratio']:.2f}<br>"
                f"前阴 {sig['prev_pct_chg']:+.2f}% → 今阳 {sig['curr_pct_chg']:+.2f}%"
            )
        else:
            bear_x.append(bar["trade_date"])
            bear_y.append(bar["high"] * 1.002)
            bear_txt.append(
                f"看跌吞没<br>{bar['trade_date']}<br>"
                f"实体比={sig['body_ratio']:.2f}<br>"
                f"前阳 {sig['prev_pct_chg']:+.2f}% → 今阴 {sig['curr_pct_chg']:+.2f}%"
            )

    fig.add_trace(
        go.Scatter(
            x=bull_x,
            y=bull_y,
            mode="markers",
            name="看涨吞没",
            marker=dict(
                symbol="triangle-up",
                size=14,
                color="#e11d48",  # 大 A：看涨（多头）= 红
                line=dict(color="#881337", width=1.5),
            ),
            text=bull_txt,
            hovertemplate="%{text}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=bear_x,
            y=bear_y,
            mode="markers",
            name="看跌吞没",
            marker=dict(
                symbol="triangle-down",
                size=14,
                color="#10b981",  # 大 A：看跌（空头）= 绿
                line=dict(color="#065f46", width=1.5),
            ),
            text=bear_txt,
            hovertemplate="%{text}<extra></extra>",
        )
    )

    # 颜色（用指数 accent）
    accent = index_def.get("accent", "#6366f1")

    # 默认视图：最近 3 个月（约 60 个交易日）；若数据不足则全显
    default_window = 60
    last_date_str = dates[-1] if dates else None
    first_date_str = dates[0] if dates else None
    xaxis_range = None
    if last_date_str:
        try:
            from datetime import datetime, timedelta
            last_dt = datetime.strptime(last_date_str, "%Y-%m-%d")
            start_dt = last_dt - timedelta(days=90)
            if first_date_str:
                first_dt = datetime.strptime(first_date_str, "%Y-%m-%d")
                if start_dt < first_dt:
                    start_dt = first_dt
            xaxis_range = [start_dt.strftime("%Y-%m-%d"), last_date_str]
        except Exception:
            xaxis_range = None

    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        # 时间轴：启用 rangeslider + rangeselector + 拖动缩放
        xaxis=dict(
            showgrid=False,
            tickfont=dict(size=11, color="#374151"),
            type="date",
            rangeslider=dict(
                visible=True,
                thickness=0.06,
                bgcolor="rgba(99, 102, 241, 0.08)",
                bordercolor="#c7d2fe",
                borderwidth=1,
            ),
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(count=1, label="1Y", step="year", stepmode="backward"),
                    dict(step="all", label="All"),
                ],
                bgcolor="rgba(255,255,255,0.85)",
                activecolor="#6366f1",
                font=dict(size=11, color="#374151"),
                x=1.0,
                xanchor="right",
                y=1.06,
                yanchor="bottom",
            ),
            range=xaxis_range,
        ),
        yaxis=dict(
            title=dict(text="点位", font=dict(size=11, color="#6B7280")),
            showgrid=True,
            gridcolor="rgba(0,0,0,0.06)",
            tickfont=dict(size=11, color="#374151"),
            # y 轴固定，避免缩放时被压扁
            fixedrange=False,
        ),
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.04,
            yanchor="bottom",
            font=dict(size=11, color="#374151"),
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="x unified",
        title=dict(
            text=f"{index_def['name']} · 日 K（含吞没信号标注）",
            font=dict(size=13, color=accent),
            x=0.01,
            xanchor="left",
            y=0.96,
        ),
        dragmode="zoom",
    )
    # 添加辅助提示（右侧 rangeselector 旁 + 图表下方 rangeslider 旁），用 annotation 而非 title
    fig.add_annotation(
        text=(
            "💡 拖动缩放 / 双击重置 / 顶部 1M·3M·6M·1Y·All 切换时间区间"
        ),
        xref="paper", yref="paper",
        x=0.01, y=-0.12,
        xanchor="left", yanchor="top",
        showarrow=False,
        font=dict(size=10, color="#6B7280"),
    )
    return fig


# ---------------------------------------------------------------- 区块渲染

def _render_summary_cards(summary: dict) -> None:
    bullish = int(summary.get("bullish", 0))
    bearish = int(summary.get("bearish", 0))
    recent = int(summary.get("index_with_recent_signal", 0))
    total = int(summary.get("index_total", 0))
    total_signals = bullish + bearish

    with ui.grid(columns="1fr 1fr 1fr 1fr").classes("w-full gap-4"):
        # 近 3 年看涨吞没（大 A：涨=红）
        with ui.card().classes(
            "p-5 bg-gradient-to-br from-rose-50 to-pink-50 "
            "border border-rose-100 shadow-sm"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("trending_up", color="red").classes("text-2xl")
                ui.label("近 3 年看涨吞没").classes("text-sm text-rose-700 font-medium")
            ui.label(f"{bullish}").classes("text-3xl font-bold text-rose-900 mt-2 leading-none")
            ui.label("Bullish Engulfing 累计次数").classes("text-xs text-rose-600 mt-1")

        # 近 3 年看跌吞没（大 A：跌=绿）
        with ui.card().classes(
            "p-5 bg-gradient-to-br from-emerald-50 to-green-50 "
            "border border-emerald-100 shadow-sm"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("trending_down", color="green").classes("text-2xl")
                ui.label("近 3 年看跌吞没").classes("text-sm text-emerald-700 font-medium")
            ui.label(f"{bearish}").classes("text-3xl font-bold text-emerald-900 mt-2 leading-none")
            ui.label("Bearish Engulfing 累计次数").classes("text-xs text-emerald-600 mt-1")

        # 近期触发指数数
        with ui.card().classes(
            "p-5 bg-gradient-to-br from-amber-50 to-orange-50 "
            "border border-amber-100 shadow-sm"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("bolt", color="amber").classes("text-2xl")
                ui.label("近期触发").classes("text-sm text-amber-700 font-medium")
            ui.label(f"{recent} / {total}").classes(
                "text-3xl font-bold text-amber-900 mt-2 leading-none"
            )
            ui.label("近 5 个交易日有吞没信号的指数").classes("text-xs text-amber-600 mt-1")

        # 信号总次数
        with ui.card().classes(
            "p-5 bg-gradient-to-br from-indigo-50 to-blue-50 "
            "border border-indigo-100 shadow-sm"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("insights", color="indigo").classes("text-2xl")
                ui.label("形态总次数").classes("text-sm text-indigo-700 font-medium")
            ui.label(f"{total_signals}").classes(
                "text-3xl font-bold text-indigo-900 mt-2 leading-none"
            )
            ratio = (bullish / total_signals * 100) if total_signals else 0
            ui.label(f"看涨占比 {ratio:.1f}%").classes("text-xs text-indigo-600 mt-1")


def _render_latest_index_card(index_def: dict, payload: dict, plot_func) -> None:
    """单个指数的「最新吞没信号」卡片。"""
    accent = index_def.get("accent", "#6366f1")
    code = index_def["ts_code"]
    res = payload.get("results", {}).get(code, {})
    latest = res.get("latest")
    last_date = res.get("last_date")
    total = res.get("signals_total", {}) or {}
    err = res.get("error")

    with ui.card().classes(
        "w-full p-4 bg-white border border-gray-100 shadow-sm rounded-xl"
    ).style(f"border-top: 3px solid {accent}"):
        # 标题行
        with ui.row().classes("items-center gap-2 mb-2"):
            ui.element("div").classes(
                "w-9 h-9 rounded-lg flex items-center justify-center text-white font-bold"
            ).style(f"background-color: {accent}")
            with ui.column().classes("gap-0"):
                ui.label(index_def["name"]).classes("text-base font-bold text-gray-900 leading-none")
                ui.label(code).classes("text-xs text-gray-500 font-mono mt-1")
            ui.space()
            ui.chip(
                f"{total.get('all', 0)} 次/3y",
                icon="show_chart",
                color="indigo",
            ).props("dense square outline").classes("text-indigo-700")

        # 最新日期
        if last_date:
            ui.label(f"最新交易日 {last_date}").classes(
                "text-xs text-gray-500 mb-2 font-mono"
            )

        # 错误兜底
        if err:
            with ui.row().classes("items-center gap-2 p-2 bg-amber-50 rounded-lg"):
                ui.icon("warning", color="amber").classes("text-lg")
                ui.label(f"数据异常：{err}").classes("text-xs text-amber-800")
            return

        # 最新信号
        if not latest:
            with ui.row().classes("items-center gap-2 p-2 bg-gray-50 rounded-lg"):
                ui.icon("remove", color="grey").classes("text-lg")
                ui.label("近期 3 年内无吞没形态").classes("text-xs text-gray-500")
            return

        bg, txt, icon = _pattern_color(latest["pattern"])
        with ui.column().classes(f"w-full p-3 rounded-lg border {bg} gap-1"):
            with ui.row().classes("items-center gap-2"):
                ui.icon(icon, color="green" if latest["pattern"] == "bullish" else "red").classes(
                    "text-lg"
                )
                ui.label(_pattern_label(latest["pattern"])).classes(
                    f"text-sm font-bold {txt}"
                )
                ui.space()
                ui.label(latest["trade_date"]).classes("text-xs font-mono text-gray-600")
            with ui.row().classes("w-full gap-3 text-xs font-mono"):
                with ui.column().classes("flex-1 gap-0"):
                    ui.label("前一日").classes("text-[10px] text-gray-500")
                    ui.label(
                        f"开 {_fmt(latest['prev_open'])} → 收 {_fmt(latest['prev_close'])}"
                    ).classes("text-xs text-gray-700")
                    # 大 A 配色：涨=红、跌=绿
                    ui.label(_pct(latest["prev_pct_chg"])).classes(
                        "text-xs " + (
                            "text-emerald-700" if latest["prev_pct_chg"] < 0 else "text-rose-700"
                        )
                    )
                with ui.column().classes("flex-1 gap-0"):
                    ui.label("当日").classes("text-[10px] text-gray-500")
                    ui.label(
                        f"开 {_fmt(latest['curr_open'])} → 收 {_fmt(latest['curr_close'])}"
                    ).classes("text-xs text-gray-700 font-semibold")
                    # 大 A 配色：涨=红、跌=绿
                    ui.label(_pct(latest["curr_pct_chg"])).classes(
                        "text-xs font-bold " + (
                            "text-rose-700" if latest["curr_pct_chg"] > 0 else "text-emerald-700"
                        )
                    )
            with ui.row().classes("w-full gap-3 text-xs"):
                ui.label(f"实体比 {latest['body_ratio']:.2f}x").classes("text-gray-500 font-mono")
                ui.label(latest["note"]).classes("text-gray-500")

        # 最近 5 次信号
        signals = res.get("signals", [])[:5]
        if signals:
            with ui.column().classes("w-full mt-3 gap-1"):
                ui.label("最近 5 次信号").classes(
                    "text-[10px] font-semibold text-gray-500 uppercase tracking-wider"
                )
                for sig in signals:
                    is_bull = sig["pattern"] == "bullish"
                    # 大 A 配色：看涨（多头）= 红，看跌（空头）= 绿
                    color_cls = (
                        "text-rose-700 bg-rose-50/60"
                        if is_bull
                        else "text-emerald-700 bg-emerald-50/60"
                    )
                    icon_name = "arrow_upward" if is_bull else "arrow_downward"
                    with ui.row().classes(
                        f"w-full justify-between items-center px-2 py-1 rounded {color_cls}"
                    ):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon(icon_name, size="14px").classes(
                                "text-rose-700" if is_bull else "text-emerald-700"
                            )
                            ui.label(sig["trade_date"]).classes("text-xs font-mono")
                        ui.label(
                            f"实体比 {sig['body_ratio']:.2f}x"
                        ).classes("text-xs font-mono opacity-80")


def _render_signals_overview_table(payload: dict) -> None:
    """近 3 年信号总览表。"""
    with ui.card().classes(
        "w-full p-5 bg-white border border-gray-100 shadow-sm rounded-xl"
    ):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon("grid_view", color="indigo").classes("text-xl")
            ui.label("近 3 年信号总览").classes("text-lg font-bold text-gray-800")
            ui.space()
            ui.label("按指数聚合").classes("text-xs text-gray-500")

        # 表头
        with ui.row().classes(
            "w-full px-3 py-2 bg-gray-50 rounded-t-lg border-b border-gray-200 "
            "text-xs font-semibold text-gray-600 uppercase tracking-wider"
        ):
            for w, txt in [
                ("w-32", "指数"),
                ("w-32", "代码"),
                ("w-20", "近 3 年总数"),
                ("w-20", "看涨"),
                ("w-20", "看跌"),
                ("w-24", "看涨/跌比"),
                ("flex-1", "最近信号"),
            ]:
                align = "text-right" if w not in ("w-32", "flex-1") else ""
                with ui.element("div").classes(f"{w} px-2 {align}"):
                    ui.label(txt).classes(align)

        for idx, d in enumerate(INDEX_DEFS):
            res = payload.get("results", {}).get(d["ts_code"], {})
            total = res.get("signals_total", {}) or {}
            latest = res.get("latest") or {}
            bull = int(total.get("bullish", 0))
            bear = int(total.get("bearish", 0))
            ratio = bull / max(bull + bear, 1)
            ratio_txt = f"{ratio * 100:.1f}% / {(1 - ratio) * 100:.1f}%"

            bg = (
                "bg-white hover:bg-gray-50"
                if idx % 2 == 0
                else "bg-gray-50/40 hover:bg-gray-50"
            )
            with ui.row().classes(
                f"w-full px-3 py-3 border-b border-gray-100 items-center "
                f"transition-colors {bg}"
            ):
                with ui.element("div").classes("w-32 px-2"):
                    with ui.row().classes("items-center gap-2"):
                        ui.element("div").classes(
                            "w-2 h-8 rounded-full"
                        ).style(f"background-color: {d.get('accent', '#6366f1')}")
                        ui.label(d["name"]).classes("text-sm font-semibold text-gray-900")
                with ui.element("div").classes("w-32 px-2"):
                    ui.label(d["ts_code"]).classes("text-xs font-mono text-gray-700")
                with ui.element("div").classes("w-20 px-2 text-right"):
                    ui.label(str(int(total.get("all", 0)))).classes(
                        "text-sm font-mono font-bold text-gray-900"
                    )
                with ui.element("div").classes("w-20 px-2 text-right"):
                    # 大 A：看涨=红、看跌=绿
                    ui.label(str(bull)).classes("text-sm font-mono text-rose-700")
                with ui.element("div").classes("w-20 px-2 text-right"):
                    ui.label(str(bear)).classes("text-sm font-mono text-emerald-700")
                with ui.element("div").classes("w-24 px-2 text-right"):
                    ui.label(ratio_txt).classes("text-xs font-mono text-gray-600")
                with ui.element("div").classes("flex-1 px-2"):
                    if latest:
                        is_bull = latest["pattern"] == "bullish"
                        # 大 A：看涨=红、看跌=绿
                        color_cls = (
                            "text-rose-700 bg-rose-50 border-rose-200"
                            if is_bull
                            else "text-emerald-700 bg-emerald-50 border-emerald-200"
                        )
                        with ui.element("div").classes(
                            f"inline-flex items-center gap-1 px-2 py-0.5 rounded border {color_cls}"
                        ):
                            ui.label(
                                _pattern_label(latest["pattern"])
                            ).classes("text-xs font-medium")
                            ui.label(f"@{latest['trade_date']}").classes(
                                "text-xs font-mono opacity-80"
                            )
                    else:
                        ui.label("—").classes("text-xs text-gray-400")


def _render_index_detail_card(index_def: dict, payload: dict, plot_func) -> None:
    """单个指数的 K 线 + 信号详情卡。"""
    accent = index_def.get("accent", "#6366f1")
    code = index_def["ts_code"]
    res = payload.get("results", {}).get(code, {})
    kline = res.get("kline", []) or []
    signals = res.get("signals", []) or []

    # 捕获图表元素引用 + kline 日期范围（用于跳转时裁剪 x 轴范围）
    plot_holder: dict = {"elem": None}
    first_date_str = kline[0]["trade_date"] if kline else None
    last_date_str = kline[-1]["trade_date"] if kline else None

    def jump_to_date(date_str: str) -> None:
        """点击信号日期时调用：把 K 线图 x 轴缩放到目标日期前后各 60 个交易日。"""
        elem = plot_holder.get("elem")
        if elem is None or not date_str:
            return
        try:
            from datetime import datetime, timedelta
            target = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            return
        window_days = 90  # 前后各 90 个自然日 ≈ 60 个交易日
        start = (target - timedelta(days=window_days)).strftime("%Y-%m-%d")
        end = (target + timedelta(days=window_days)).strftime("%Y-%m-%d")
        # 边界裁剪到当前 K 线图实际范围
        if first_date_str:
            try:
                if datetime.strptime(start, "%Y-%m-%d") < datetime.strptime(first_date_str, "%Y-%m-%d"):
                    start = first_date_str
            except Exception:
                pass
        if last_date_str:
            try:
                if datetime.strptime(end, "%Y-%m-%d") > datetime.strptime(last_date_str, "%Y-%m-%d"):
                    end = last_date_str
            except Exception:
                pass
        try:
            elem.run_plot_method("relayout", {"xaxis.range": [start, end]})
        except Exception as exc:  # noqa: BLE001
            print(f"[Engulfing] jump_to_date relayout error: {exc}")

    with ui.card().classes(
        "w-full p-4 bg-white border border-gray-100 shadow-sm rounded-xl"
    ):
        with ui.row().classes("items-center gap-2 mb-2"):
            ui.element("div").classes(
                "w-2 h-6 rounded-full"
            ).style(f"background-color: {accent}")
            ui.label(f"{index_def['name']} 形态识别详情").classes(
                "text-base font-bold text-gray-800"
            )
            ui.space()
            ui.label(
                f"近一年 K 线 {len(kline)} 根 · 近 3 年共 {len(signals)} 次信号"
            ).classes("text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-full")

        if not kline:
            with ui.row().classes("items-center gap-2 py-6 justify-center w-full text-gray-400"):
                ui.icon("inbox", size="32px")
                ui.label("暂无 K 线数据").classes("text-sm")
            return

        # K 线图（保留元素引用，用于跳转时调用 Plotly.relayout）
        fig = _build_candlestick_figure(index_def, kline, signals)
        plot_elem = plot_func(fig)
        plot_elem.classes("w-full").style("height: 420px")
        plot_holder["elem"] = plot_elem

        # 该指数最近 10 条信号 —— 卡片式排版，避免 8 列挤在一起
        recent = signals[:10]
        if recent:
            with ui.column().classes("w-full mt-4 gap-2"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("format_list_bulleted", color="indigo").classes(
                        "text-base"
                    )
                    ui.label(f"最近 {len(recent)} 条吞没信号").classes(
                        "text-sm font-bold text-gray-700"
                    )
                    ui.label("（点击日期跳转 K 线）").classes(
                        "text-xs text-gray-400"
                    )

                with ui.grid(columns="1fr 1fr").classes("w-full gap-2"):
                    for sig in recent:
                        _render_signal_card(sig, on_jump=jump_to_date)


def _render_signal_card(sig: dict, on_jump=None) -> None:
    """单条吞没信号卡片（紧凑排版，PC 2 列、移动 1 列）。

    配色遵循大 A 习惯：涨 = 红、跌 = 绿。
      - 看涨吞没 bullish → 红色 rose（多头 = 涨色）
      - 看跌吞没 bearish → 绿色 emerald（空头 = 跌色）

    参数：
        on_jump: 可选回调函数 on_jump(date_str: str) -> None。
                 传入时，卡片日期会渲染为可点击按钮，触发后跳转到 K 线对应区间。
    """
    is_bull = sig["pattern"] == "bullish"
    # 大 A：看涨=红、看跌=绿
    accent = "#e11d48" if is_bull else "#10b981"
    bg = "bg-rose-50/60 border-rose-200" if is_bull else "bg-emerald-50/60 border-emerald-200"
    text_cls = "text-rose-700" if is_bull else "text-emerald-700"
    icon_name = "trending_up" if is_bull else "trending_down"
    pattern_txt = "看涨吞没" if is_bull else "看跌吞没"

    with ui.element("div").classes(
        f"w-full p-3 rounded-lg border {bg} hover:shadow-sm transition-shadow"
    ):
        # 顶部行：日期 + 形态标签 + 力度标签
        with ui.row().classes("items-center gap-2 mb-2 flex-wrap"):
            # 日期：可点击时变成按钮
            if on_jump is not None:
                ui.button(
                    sig["trade_date"],
                    icon="event",
                    on_click=lambda d=sig["trade_date"]: on_jump(d),
                ).props(
                    f"flat dense no-caps color={'red' if is_bull else 'green'}-7"
                ).classes(
                    f"text-sm font-mono font-bold px-2 py-0.5 "
                    f"{'text-rose-700' if is_bull else 'text-emerald-700'}"
                ).tooltip("点击跳转 K 线图到该日期")
            else:
                ui.label(sig["trade_date"]).classes(
                    "text-sm font-mono font-bold text-gray-900"
                )
            with ui.row().classes(
                f"items-center gap-1 px-2 py-0.5 rounded bg-white border "
                f"{'border-rose-300' if is_bull else 'border-emerald-300'}"
            ):
                ui.icon(icon_name, color=accent).classes("text-sm")
                ui.label(pattern_txt).classes(f"text-xs font-bold {text_cls}")
            ui.space()
            # 实体比 + 力度标签
            ratio = sig["body_ratio"]
            if ratio >= 2.0:
                # 强吞没：警示色（红色系），与形态正反色无关
                label, label_cls = "强吞没", "text-rose-700 bg-rose-100"
            elif ratio >= 1.5:
                label, label_cls = "中度", "text-amber-700 bg-amber-100"
            else:
                label, label_cls = "标准", "text-gray-600 bg-gray-100"
            with ui.row().classes("items-center gap-1"):
                ui.label(f"{ratio:.2f}x").classes(
                    "text-xs font-mono font-bold text-gray-800"
                )
                ui.label(label).classes(
                    f"px-1.5 py-0.5 rounded text-[10px] font-medium {label_cls}"
                )

        # 中段：OHLC + 涨跌幅（两列对照）
        with ui.grid(columns="1fr 1fr").classes("w-full gap-2 mb-1"):
            # 前日
            with ui.column().classes(
                "bg-white/70 rounded p-2 border border-gray-200 gap-0.5"
            ):
                ui.label("前日").classes("text-[10px] text-gray-500 font-medium")
                ui.label(
                    f"{sig['prev_open']:.2f} → {sig['prev_close']:.2f}"
                ).classes("text-xs font-mono text-gray-700")
                v = sig["prev_pct_chg"]
                # 大 A：涨=红、跌=绿
                color_cls = "text-rose-700" if v > 0 else "text-emerald-700" if v < 0 else "text-gray-500"
                ui.label(_pct(v)).classes(f"text-xs font-mono font-bold {color_cls}")

            # 当日
            with ui.column().classes(
                f"rounded p-2 border gap-0.5 "
                f"{'bg-rose-50 border-rose-200' if is_bull else 'bg-emerald-50 border-emerald-200'}"
            ):
                ui.label("当日").classes(
                    f"text-[10px] font-medium {'text-rose-600' if is_bull else 'text-emerald-600'}"
                )
                ui.label(
                    f"{sig['curr_open']:.2f} → {sig['curr_close']:.2f}"
                ).classes(f"text-xs font-mono font-bold {text_cls}")
                v = sig["curr_pct_chg"]
                # 大 A：涨=红、跌=绿
                color_cls = "text-rose-700" if v > 0 else "text-emerald-700" if v < 0 else "text-gray-500"
                ui.label(_pct(v)).classes(f"text-xs font-mono font-bold {color_cls}")

        # 底部：辅助说明
        if sig.get("note"):
            ui.label(sig["note"]).classes(
                "text-[10px] text-gray-500 leading-snug"
            )


# ---------------------------------------------------------------- 面板入口

def render_engulfing_pattern_panel(plotly_renderer=None):
    """吞没形态面板入口（在公告栏 tab 内调用）。"""
    plot_func = plotly_renderer if plotly_renderer else ui.plotly
    state = {"date": None, "busy": False, "selected_index": INDEX_DEFS[0]["ts_code"]}

    with ui.column().classes("w-full gap-4"):
        # 顶部品牌色标题条
        with ui.row().classes(
            "w-full items-center gap-3 px-5 py-4 bg-gradient-to-r "
            "from-indigo-500 via-purple-500 to-pink-500 rounded-xl shadow-sm"
        ):
            ui.icon("candlestick_chart", color="white").classes("text-3xl")
            with ui.column().classes("gap-0"):
                ui.label("6 大指数 · 吞没形态识别器").classes(
                    "text-xl font-bold text-white tracking-wide leading-tight"
                )
                ui.label("Engulfing Pattern Detector · Tushare Pro").classes(
                    "text-xs text-white/85 font-light mt-0.5"
                )
            ui.space()
            ui.chip("近 3 年窗口", icon="schedule", color="white").props(
                "dense square outline"
            ).classes("text-white border-white/80")

        # 数据口径说明
        with ui.expansion(
            "数据口径说明 · 形态定义", icon="info", value=False
        ).classes(
            "w-full bg-white border border-gray-100 rounded-lg shadow-sm"
        ):
            with ui.column().classes("p-4 text-gray-600 text-sm gap-2"):
                ui.markdown(
                    "- **覆盖指数**：上证指数、深证成指、创业板指、沪深300、科创50、中证A50（俗称『中证50』）。\n"
                    "- **数据源**：Tushare Pro `index_daily`，近 3 年日线（缓存于 `data/engulfing_cache/`）。\n"
                    "- **形态定义（标准 2 蜡烛线反转型态）**：\n"
                    "  - **看涨吞没 Bullish Engulfing**：前一日阴线、当日阳线，且**当日开盘价 ≤ 前日收盘价**、"
                    "**当日收盘价 ≥ 前日开盘价**、**当日实体 ≥ 前日实体**。常出现在下跌趋势末端。\n"
                    "  - **看跌吞没 Bearish Engulfing**：前一日阳线、当日阴线，且**当日开盘价 ≥ 前日收盘价**、"
                    "**当日收盘价 ≤ 前日开盘价**、**当日实体 ≥ 前日实体**。常出现在上升趋势末端。\n"
                    "- **实体比**：当日 K 线实体长度 / 前日实体长度，>1 即视为有效吞没，越大力度越强。\n"
                    "- **辅助说明**：标注『前续 N 日同向』，提示形态出现在连续趋势末端的反转意义。\n"
                    "- 数据仅供参考，不构成投资建议。"
                )

        @ui.refreshable
        def render_content():
            dates = _available_dates()
            if not dates:
                with ui.card().classes(
                    "w-full p-10 items-center gap-3 bg-white"
                ):
                    ui.icon("inbox", size="48px").classes("text-gray-300")
                    ui.label(
                        "还没有生成过吞没形态快照，请点击右上角「生成/刷新」"
                    ).classes("text-lg text-gray-600")
                return

            if state["date"] not in dates:
                state["date"] = dates[-1]
            current = state["date"]
            payload = load_struct_data(current)
            if payload is None:
                with ui.card().classes(
                    "w-full p-8 items-center gap-2 bg-white"
                ):
                    ui.icon("cloud_off", size="32px").classes("text-gray-300")
                    ui.label(f"{current} 暂无吞没形态数据").classes("text-gray-500")
                return

            # 顶部：交易日概览条
            with ui.card().classes(
                "w-full p-5 bg-gradient-to-br from-white via-indigo-50/40 "
                "to-purple-50/40 border border-indigo-100 shadow-sm rounded-xl"
            ):
                with ui.row().classes("w-full items-center gap-4 flex-wrap"):
                    # 左侧：大字日期 + 星期
                    with ui.row().classes("items-center gap-3 min-w-[260px]"):
                        ui.element("div").classes(
                            "w-12 h-12 rounded-xl bg-gradient-to-br "
                            "from-indigo-500 to-purple-500 flex "
                            "items-center justify-center shadow-md"
                        ).style("display:flex")
                        ui.icon("event", color="white").classes(
                            "text-2xl"
                        ).style("margin-left:-48px")
                        with ui.column().classes("gap-0 ml-3"):
                            ui.label(current).classes(
                                "text-2xl font-bold text-gray-900 "
                                "leading-none tracking-wide font-mono"
                            )
                            weekday = ""
                            try:
                                d = dt.datetime.strptime(current, "%Y-%m-%d").date()
                                weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][d.weekday()]
                            except Exception:
                                pass
                            ui.label(weekday or "交易日").classes(
                                "text-xs text-indigo-700 mt-1 font-medium"
                            )

                    ui.separator().props("vertical").classes("h-12 bg-indigo-200")

                    with ui.column().classes("gap-0"):
                        ui.label("数据状态").classes("text-xs text-gray-500")
                        if state["busy"]:
                            with ui.row().classes("items-center gap-1 mt-1"):
                                ui.spinner(size="xs", color="indigo")
                                ui.label("正在拉取指数 K 线并检测…").classes(
                                    "text-sm text-indigo-600 font-medium"
                                )
                        else:
                            with ui.column().classes("gap-0 mt-1"):
                                ui.label("✓ 已就绪").classes(
                                    "text-sm text-emerald-700 font-medium"
                                )
                                ui.label(
                                    f"快照：{payload.get('generated_at', '-')}"
                                ).classes("text-xs text-gray-500 mt-0.5")

                    ui.space()

                    with ui.row().classes(
                        "items-center gap-1 bg-white px-1 py-1 "
                        "rounded-lg border border-indigo-200 shadow-sm"
                    ):
                        ui.button(
                            icon="chevron_left",
                            on_click=lambda: _nav(-1),
                        ).props("flat dense round color=indigo-7").tooltip(
                            "上一交易日"
                        )
                        ui.select(
                            dates,
                            value=current,
                            on_change=lambda e: _select_date(e.value),
                        ).props(
                            "outlined dense options-dense color=indigo-7"
                        ).classes("min-w-[140px] border-none")
                        ui.button(
                            icon="chevron_right",
                            on_click=lambda: _nav(1),
                        ).props("flat dense round color=indigo-7").tooltip(
                            "下一交易日"
                        )
                        ui.separator().props("vertical").classes(
                            "h-6 mx-1 bg-indigo-200"
                        )
                        refresh_btn = ui.button(
                            "生成/刷新",
                            icon="refresh",
                            on_click=regenerate,
                        ).props("outline color=indigo-7 dense no-caps").classes(
                            "font-medium"
                        )
                        state["refresh_btn"] = refresh_btn

            # 概览卡
            _render_summary_cards(payload.get("summary", {}))

            # 最新信号卡片区（6 张指数卡）
            with ui.card().classes(
                "w-full p-5 bg-white border border-gray-100 shadow-sm rounded-xl"
            ):
                with ui.row().classes("items-center gap-2 mb-3"):
                    ui.icon("campaign", color="indigo").classes("text-xl")
                    ui.label("各指数最新吞没信号").classes("text-lg font-bold text-gray-800")
                    ui.space()
                    ui.label(
                        f"近 3 年总计 {payload.get('summary', {}).get('bullish', 0) + payload.get('summary', {}).get('bearish', 0)} 次"
                    ).classes("text-xs text-gray-500")

                with ui.grid(columns="1fr 1fr 1fr").classes("w-full gap-3"):
                    for d in INDEX_DEFS:
                        _render_latest_index_card(d, payload, plot_func)

            # 近 3 年信号总览表
            _render_signals_overview_table(payload)

            # 单指数详情（默认显示第一个指数）
            with ui.card().classes(
                "w-full p-5 bg-white border border-gray-100 shadow-sm rounded-xl"
            ):
                with ui.row().classes("items-center gap-2 mb-3 flex-wrap"):
                    ui.icon("insights", color="indigo").classes("text-xl")
                    ui.label("形态识别详情").classes("text-lg font-bold text-gray-800")
                    ui.label("（点击指数切换）").classes("text-xs text-gray-500 ml-1")

                    ui.space()

                    # 指数选择 chip 组
                    with ui.row().classes("items-center gap-1 flex-wrap"):
                        for d in INDEX_DEFS:
                            is_active = (state["selected_index"] == d["ts_code"])
                            btn = ui.button(
                                d["short"],
                                on_click=lambda c=d["ts_code"]: _select_index(c),
                            )
                            if is_active:
                                btn.props(
                                    f"outline color={d['color']}-7 dense no-caps"
                                ).classes(
                                    f"text-xs font-bold border-2 px-3"
                                ).style(
                                    f"color: {d['accent']}; border-color: {d['accent']}; background-color: {d['accent']}1A"
                                )
                            else:
                                btn.props(
                                    f"flat color={d['color']}-7 dense no-caps"
                                ).classes("text-xs px-3")

                # 选中指数详情
                sel_code = state["selected_index"]
                sel_def = next(
                    (d for d in INDEX_DEFS if d["ts_code"] == sel_code),
                    INDEX_DEFS[0],
                )
                _render_index_detail_card(sel_def, payload, plot_func)

            with ui.row().classes(
                "w-full justify-center items-center py-3 mt-2 text-xs text-gray-400"
            ):
                ui.label(
                    f"源文件：{os.path.join(OUTPUT_DIR, current + '.json')}"
                )
                ui.label("·").classes("mx-2")
                ui.label("近 3 年吞没形态识别 · 仅供研究参考，不构成投资建议")

        def _nav(step):
            dates = _available_dates()
            if not dates:
                return
            if state["date"] not in dates:
                state["date"] = dates[-1]
            idx = dates.index(state["date"])
            idx = max(0, min(len(dates) - 1, idx + step))
            state["date"] = dates[idx]
            render_content.refresh()

        def _select_date(value):
            state["date"] = value
            render_content.refresh()

        def _select_index(code: str):
            state["selected_index"] = code
            render_content.refresh()

        async def regenerate():
            if state["busy"]:
                return
            state["busy"] = True
            btn = state.get("refresh_btn")
            if btn is not None:
                btn.props("loading disable")
            try:
                def _work():
                    from utils.engulfing_pattern import (
                        EngulfingPatternBoard,
                        save_struct_data,
                    )
                    board = EngulfingPatternBoard()
                    payload = board.build_struct_data(force_refresh=False)
                    return save_struct_data(payload)

                loop = asyncio.get_running_loop()
                path = await loop.run_in_executor(None, _work)
                state["date"] = os.path.basename(path)[:10]
            except Exception as exc:  # noqa: BLE001
                try:
                    ui.notify(f"生成失败：{exc}", type="negative")
                except Exception:  # noqa: BLE001
                    pass
            else:
                try:
                    ui.notify(f"已生成 {state['date']} 吞没形态快照", type="positive")
                except Exception:  # noqa: BLE001
                    pass
            finally:
                state["busy"] = False
                if btn is not None:
                    btn.props(remove="loading").props(remove="disable")
                render_content.refresh()

        render_content()


if __name__ == "__main__":
    # 模块级自测：渲染 ASCII 摘要
    from utils.engulfing_pattern import (
        EngulfingPatternBoard,
        _available_dates,
    )

    board = EngulfingPatternBoard()
    dates = _available_dates()
    if dates:
        latest_date = dates[-1]
        print(f"Latest snapshot: {latest_date}")
        payload = load_struct_data(latest_date)
        print("Summary:", payload.get("summary"))
    else:
        print("No snapshot found, building new one…")
        payload = board.build_struct_data()
        from utils.engulfing_pattern import save_struct_data
        save_struct_data(payload)
        print("Summary:", payload.get("summary"))
