# -*- coding: utf-8 -*-
"""每日股市特殊公告栏 —— 仅展示「交易异动」与「大股东增减持」。

数据流：Tushare Pro（stk_shock / stk_high_shock / stk_holdertrade）→ JSON 缓存 →
页面结构化渲染（卡片 + 数据表 + 统计摘要）。

设计：本模块以「面板 + 标题条」的方式提供给「市场情绪与资金」板块使用，
不再单独占用顶层入口页面。
"""
import asyncio
import datetime as dt
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nicegui import ui

from pages.shared import setup_common_ui
from pages.engulfing_pattern_component import render_engulfing_pattern_panel
from utils.special_announcement import (
    OUTPUT_DIR,
    SpecialAnnouncementBoard,
    build_struct_data,
    load_struct_data,
    save_struct_data,
)


# ---------------------------------------------------------------- 工具

def _available_dates() -> list[str]:
    """列出已生成的结构化 JSON 日期（YYYY-MM-DD）。"""
    if not os.path.isdir(OUTPUT_DIR):
        return []
    dates = []
    for name in os.listdir(OUTPUT_DIR):
        if name.endswith(".json"):
            stem = name[: -len(".json")]
            if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
                dates.append(stem)
    return sorted(dates)


def _color_for_market(market: str) -> str:
    """交易所标识配色。"""
    if market and ("上" in market):
        return "bg-red-50 text-red-700 border-red-200"
    if market and ("深" in market):
        return "bg-blue-50 text-blue-700 border-blue-200"
    if market and ("北" in market):
        return "bg-purple-50 text-purple-700 border-purple-200"
    return "bg-gray-50 text-gray-700 border-gray-200"


def _weekday_cn(date_str: str) -> str:
    """YYYY-MM-DD -> 周X。"""
    try:
        d = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
        return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][d.weekday()]
    except Exception:  # noqa: BLE001
        return ""


def _pretty_date(trade_date: str) -> str:
    """YYYYMMDD -> YYYY-MM-DD。"""
    s = str(trade_date)
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


# ---------------------------------------------------------------- 区块渲染

def _render_summary_cards(summary: dict) -> None:
    """顶部 4 张统计卡片。"""
    with ui.grid(columns="1fr 1fr 1fr 1fr").classes("w-full gap-4"):
        with ui.card().classes(
            "p-5 bg-gradient-to-br from-amber-50 to-orange-50 "
            "border border-amber-100 shadow-sm"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("bolt", color="amber").classes("text-2xl")
                ui.label("异常波动公告").classes("text-sm text-amber-700 font-medium")
            ui.label(f"{summary.get('shock', 0)}").classes(
                "text-3xl font-bold text-amber-900 mt-2"
            )
            ui.label("交易所披露").classes("text-xs text-amber-600 mt-1")

        with ui.card().classes(
            "p-5 bg-gradient-to-br from-rose-50 to-pink-50 "
            "border border-rose-100 shadow-sm"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("whatshot", color="red").classes("text-2xl")
                ui.label("严重异常波动").classes("text-sm text-rose-700 font-medium")
            ui.label(f"{summary.get('high_shock', 0)}").classes(
                "text-3xl font-bold text-rose-900 mt-2"
            )
            ui.label("10/30日累计 ≥100%").classes("text-xs text-rose-600 mt-1")

        with ui.card().classes(
            "p-5 bg-gradient-to-br from-emerald-50 to-green-50 "
            "border border-emerald-100 shadow-sm"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("trending_up", color="green").classes("text-2xl")
                ui.label("股东增持公告").classes("text-sm text-emerald-700 font-medium")
            ui.label(f"{summary.get('holder_in', 0)}").classes(
                "text-3xl font-bold text-emerald-900 mt-2"
            )
            ui.label("看好信号").classes("text-xs text-emerald-600 mt-1")

        with ui.card().classes(
            "p-5 bg-gradient-to-br from-indigo-50 to-blue-50 "
            "border border-indigo-100 shadow-sm"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("sell", color="indigo").classes("text-2xl")
                ui.label("股东减持公告").classes("text-sm text-indigo-700 font-medium")
            ui.label(f"{summary.get('holder_de', 0)}").classes(
                "text-3xl font-bold text-indigo-900 mt-2"
            )
            ui.label(
                f"含 {summary.get('significant', 0)} 条大额(≥5%/1亿)"
            ).classes("text-xs text-indigo-600 mt-1")


def _render_shock_trend_chart(trend: dict, plot_func=None) -> None:
    """异动/严重异动每日波动图（双柱状图 + 折线）。

    trend 结构：
    {
        "dates": [...],
        "shock": [...],
        "high_shock": [...],
        "window_count": int,
        "max_shock": int, "max_high": int,
    }
    """
    plot_func = plot_func or ui.plotly
    dates = trend.get("dates") or []
    shock = trend.get("shock") or []
    high = trend.get("high_shock") or []
    window_count = int(trend.get("window_count") or len(dates))

    if not dates:
        return

    # 计算总量 / 均值
    total_shock = int(sum(shock))
    total_high = int(sum(high))
    avg_shock = total_shock / max(len(shock), 1)
    avg_high = total_high / max(len(high), 1)
    peak_idx = (
        max(range(len(shock)), key=lambda i: shock[i]) if shock else 0
    )
    peak_date = dates[peak_idx] if 0 <= peak_idx < len(dates) else "-"
    peak_val = shock[peak_idx] if 0 <= peak_idx < len(shock) else 0

    # 构建 plotly 图
    fig = _build_shock_trend_figure(dates, shock, high)

    with ui.card().classes(
        "w-full p-5 bg-white border border-gray-100 shadow-sm rounded-xl"
    ):
        with ui.row().classes("items-center gap-2 mb-2"):
            ui.icon("show_chart", color="amber").classes("text-xl")
            ui.label("异动波动走势").classes("text-lg font-bold text-gray-800")
            ui.space()
            ui.label(f"{window_count} 个交易日").classes(
                "text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-full"
            )

        # 顶部小摘要
        with ui.grid(columns="1fr 1fr 1fr").classes("w-full gap-3 mb-3"):
            with ui.column().classes(
                "p-3 bg-amber-50/60 rounded-lg border border-amber-100"
            ):
                ui.label("异常波动均值").classes("text-xs text-amber-700")
                ui.label(f"{avg_shock:,.1f} 条/日").classes(
                    "text-xl font-bold text-amber-900 font-mono mt-1"
                )
            with ui.column().classes(
                "p-3 bg-rose-50/60 rounded-lg border border-rose-100"
            ):
                ui.label("严重异常波动均值").classes("text-xs text-rose-700")
                ui.label(f"{avg_high:,.1f} 条/日").classes(
                    "text-xl font-bold text-rose-900 font-mono mt-1"
                )
            with ui.column().classes(
                "p-3 bg-orange-50/60 rounded-lg border border-orange-100"
            ):
                ui.label("异动峰值日").classes("text-xs text-orange-700")
                ui.label(f"{peak_date}").classes(
                    "text-base font-bold text-orange-900 font-mono mt-1"
                )
                ui.label(f"{peak_val} 条").classes(
                    "text-xs text-orange-700 font-mono"
                )

        # plotly 图
        plot_func(fig).classes("w-full").style("height: 320px")


def _build_shock_trend_figure(dates, shock, high):
    """构造异动走势的 Plotly Figure。"""
    try:
        import plotly.graph_objects as go
    except Exception:
        # plotly 不可用，返回一个简单的占位
        import plotly.graph_objects as go  # type: ignore

    fig = go.Figure()

    # 异常波动柱状（橙色半透明）
    fig.add_trace(
        go.Bar(
            x=dates,
            y=shock,
            name="异常波动",
            marker=dict(
                color="rgba(245, 158, 11, 0.55)",  # amber-500
                line=dict(color="rgba(245, 158, 11, 1)", width=1.5),
            ),
            hovertemplate="<b>%{x}</b><br>异常波动：%{y} 条<extra></extra>",
        )
    )

    # 严重异常波动柱状（玫红色）
    fig.add_trace(
        go.Bar(
            x=dates,
            y=high,
            name="严重异常波动",
            marker=dict(
                color="rgba(244, 63, 94, 0.85)",  # rose-500
                line=dict(color="rgba(190, 18, 60, 1)", width=1.5),
            ),
            hovertemplate="<b>%{x}</b><br>严重异动：%{y} 条<extra></extra>",
        )
    )

    # 异常波动趋势线（深橙）
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=shock,
            name="异常波动趋势",
            mode="lines+markers",
            line=dict(color="rgba(217, 119, 6, 1)", width=2.5, shape="spline"),
            marker=dict(size=7, color="rgba(217, 119, 6, 1)"),
            hovertemplate="<b>%{x}</b><br>异常：%{y} 条<extra></extra>",
        )
    )

    fig.update_layout(
        barmode="overlay",
        bargap=0.25,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            showgrid=False,
            tickfont=dict(size=11, color="#374151"),
            tickangle=0,
        ),
        yaxis=dict(
            title=dict(text="公告条数", font=dict(size=11, color="#6B7280")),
            showgrid=True,
            gridcolor="rgba(0,0,0,0.06)",
            zeroline=False,
            tickfont=dict(size=11, color="#374151"),
            rangemode="tozero",
        ),
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.12,
            yanchor="bottom",
            font=dict(size=11, color="#374151"),
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="x unified",
    )
    return fig


def _render_weekly_summary(weekly: dict) -> None:
    """增减持周汇总卡：企业数 / 总金额 / 净流向 / 每日趋势。"""
    in_data = weekly.get("in", {}) or {}
    de_data = weekly.get("de", {}) or {}
    net_wan = float(weekly.get("net_wan", 0.0) or 0.0)
    window_count = int(weekly.get("window_count", 0) or 0)
    has_avg = bool(weekly.get("has_avg_price", False))

    net_yi = net_wan / 1e4  # 万元 -> 亿元
    in_yi = in_data.get("amount_wan", 0.0) / 1e4
    de_yi = de_data.get("amount_wan", 0.0) / 1e4

    net_color = (
        "text-rose-700 bg-rose-50 border-rose-200"
        if net_wan > 0
        else "text-emerald-700 bg-emerald-50 border-emerald-200"
        if net_wan < 0
        else "text-gray-700 bg-gray-50 border-gray-200"
    )
    net_arrow = "↑ 净减持" if net_wan > 0 else "↓ 净增持" if net_wan < 0 else "持平"
    net_txt = (
        f"{net_arrow} {abs(net_yi):,.2f} 亿元"
        if abs(net_yi) >= 0.01
        else f"{net_arrow} {abs(net_wan):,.0f} 万元"
    )

    with ui.card().classes(
        "w-full p-5 bg-white border border-gray-100 shadow-sm rounded-xl"
    ):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon("bar_chart", color="indigo").classes("text-xl")
            ui.label("增减持周汇总").classes("text-lg font-bold text-gray-800")
            ui.space()
            if window_count:
                ui.label(f"含 {window_count} 个交易日").classes(
                    "text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-full"
                )
            if not has_avg:
                ui.label("未披露均价，按成交参考").classes(
                    "text-xs text-amber-700 bg-amber-50 border border-amber-200 "
                    "px-2 py-1 rounded-full ml-1"
                )

        if (in_data.get("firms", 0) == 0 and de_data.get("firms", 0) == 0):
            with ui.row().classes(
                "items-center gap-2 py-8 justify-center w-full text-gray-400"
            ):
                ui.icon("inbox", size="32px")
                ui.label("本周窗口内无增减持披露").classes("text-sm")
            return

        # 三段：增持 / 减持 / 净流向
        with ui.grid(columns="1fr 1fr 1fr").classes("w-full gap-4"):
            # 增持
            with ui.card().classes(
                "p-4 bg-gradient-to-br from-emerald-50 to-green-50 "
                "border border-emerald-100"
            ):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("trending_up", color="green").classes("text-lg")
                    ui.label("增持").classes("text-sm text-emerald-700 font-medium")
                ui.label(f"{in_data.get('firms', 0)}").classes(
                    "text-3xl font-bold text-emerald-900 mt-2 leading-none"
                )
                ui.label("家企业披露").classes("text-xs text-emerald-600 mt-1")
                ui.label(
                    f"总金额 {in_yi:,.2f} 亿元" if in_yi >= 0.01
                    else f"总金额 {in_data.get('amount_wan', 0.0):,.0f} 万元"
                ).classes("text-xs text-emerald-700 font-mono mt-1")

            # 减持
            with ui.card().classes(
                "p-4 bg-gradient-to-br from-rose-50 to-pink-50 "
                "border border-rose-100"
            ):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("sell", color="red").classes("text-lg")
                    ui.label("减持").classes("text-sm text-rose-700 font-medium")
                ui.label(f"{de_data.get('firms', 0)}").classes(
                    "text-3xl font-bold text-rose-900 mt-2 leading-none"
                )
                ui.label("家企业披露").classes("text-xs text-rose-600 mt-1")
                ui.label(
                    f"总金额 {de_yi:,.2f} 亿元" if de_yi >= 0.01
                    else f"总金额 {de_data.get('amount_wan', 0.0):,.0f} 万元"
                ).classes("text-xs text-rose-700 font-mono mt-1")

            # 净流向
            with ui.element("div").classes(
                f"p-4 rounded-lg border {net_color} flex flex-col justify-between"
            ):
                with ui.row().classes("items-center gap-2"):
                    ui.icon(
                        "trending_down" if net_wan > 0 else "trending_up",
                        color="rose" if net_wan > 0 else "emerald" if net_wan < 0 else "gray",
                    ).classes("text-lg")
                    ui.label("净流向").classes("text-sm font-medium")
                ui.label(net_txt).classes(
                    "text-2xl font-bold mt-2 leading-none font-mono"
                )
                ui.label(
                    "减持 > 增持 = 市场资金净流出" if net_wan > 0
                    else "增持 > 减持 = 市场资金净流入" if net_wan < 0
                    else "本周增减基本平衡"
                ).classes("text-xs mt-1 opacity-80")

        # 每日趋势表
        in_by_day = in_data.get("by_day", []) or []
        de_by_day = de_data.get("by_day", []) or []
        if in_by_day or de_by_day:
            with ui.column().classes("w-full mt-4"):
                ui.label("每日企业数分布").classes(
                    "text-xs font-semibold text-gray-600 uppercase tracking-wider mb-1"
                )
                with ui.row().classes(
                    "w-full px-3 py-2 bg-gray-50 rounded-t-lg border-b border-gray-200 "
                    "text-xs font-semibold text-gray-600"
                ):
                    for w, txt in [
                        ("w-32", "交易日"),
                        ("flex-1", "增持"),
                        ("flex-1", "减持"),
                        ("flex-1", "净流向"),
                    ]:
                        align = "text-right" if w != "w-32" else ""
                        with ui.element("div").classes(f"{w} px-2 {align}"):
                            ui.label(txt).classes(align)

                # 合并每日数据
                days_map = {}
                for r in in_by_day:
                    days_map[r["date"]] = {"in": r, "de": {"firms": 0, "amount_wan": 0.0}}
                for r in de_by_day:
                    if r["date"] not in days_map:
                        days_map[r["date"]] = {"in": {"firms": 0, "amount_wan": 0.0}, "de": r}
                    else:
                        days_map[r["date"]]["de"] = r

                for idx, d in enumerate(sorted(days_map.keys(), reverse=True)):
                    row = days_map[d]
                    in_firms = row["in"].get("firms", 0)
                    de_firms = row["de"].get("firms", 0)
                    in_amt = row["in"].get("amount_wan", 0.0)
                    de_amt = row["de"].get("amount_wan", 0.0)
                    net_amt = de_amt - in_amt
                    in_yi = in_amt / 1e4
                    de_yi = de_amt / 1e4
                    net_yi_day = net_amt / 1e4

                    bg = "bg-white hover:bg-gray-50" if idx % 2 == 0 else "bg-gray-50/40 hover:bg-gray-50"
                    with ui.row().classes(
                        f"w-full px-3 py-2 border-b border-gray-100 items-center {bg}"
                    ):
                        with ui.element("div").classes("w-32 px-2"):
                            ui.label(d).classes(
                                "text-xs font-mono text-gray-700 font-medium"
                            )
                        with ui.element("div").classes("flex-1 px-2 text-right"):
                            ui.label(
                                f"{in_firms} 家 / "
                                f"{in_yi:,.2f} 亿" if in_yi >= 0.01
                                else f"{in_firms} 家 / {in_amt:,.0f} 万"
                            ).classes("text-xs font-mono text-emerald-700")
                        with ui.element("div").classes("flex-1 px-2 text-right"):
                            ui.label(
                                f"{de_firms} 家 / "
                                f"{de_yi:,.2f} 亿" if de_yi >= 0.01
                                else f"{de_firms} 家 / {de_amt:,.0f} 万"
                            ).classes("text-xs font-mono text-rose-700")
                        with ui.element("div").classes("flex-1 px-2 text-right"):
                            ui.label(
                                f"{'↑' if net_yi_day >= 0 else '↓'} "
                                f"{abs(net_yi_day):,.2f} 亿"
                                if abs(net_yi_day) >= 0.01
                                else f"{'↑' if net_amt >= 0 else '↓'} "
                                     f"{abs(net_amt):,.0f} 万"
                            ).classes(
                                "text-xs font-mono font-semibold "
                                + ("text-rose-700" if net_amt > 0 else "text-emerald-700")
                            )


def _render_shock_table(rows: list[dict], title: str, accent: str, icon: str) -> None:
    """交易异动列表卡片。"""
    with ui.card().classes(
        "w-full p-5 bg-white border border-gray-100 shadow-sm"
    ):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon(icon, color=accent).classes("text-xl")
            ui.label(title).classes("text-lg font-bold text-gray-800")
            ui.space()
            ui.label(f"{len(rows)} 条").classes(
                "text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-full"
            )

        if not rows:
            with ui.row().classes(
                "items-center gap-2 py-8 justify-center w-full text-gray-400"
            ):
                ui.icon("inbox", size="32px")
                ui.label("当日无相关公告").classes("text-sm")
            return

        with ui.row().classes(
            "w-full px-3 py-2 bg-gray-50 rounded-t-lg border-b border-gray-200 "
            "text-xs font-semibold text-gray-600 uppercase tracking-wider"
        ):
            for w, txt in [
                ("w-32", "代码"),
                ("w-32", "名称"),
                ("w-24", "交易所"),
                ("flex-1", "异常说明"),
                ("w-56", "异常期间"),
            ]:
                with ui.element("div").classes(f"{w} px-2"):
                    ui.label(txt)

        for idx, row in enumerate(rows):
            row_class = (
                "bg-white hover:bg-amber-50/40"
                if idx % 2 == 0
                else "bg-gray-50/40 hover:bg-amber-50/40"
            )
            with ui.row().classes(
                f"w-full px-3 py-3 border-b border-gray-100 items-center "
                f"transition-colors {row_class}"
            ):
                with ui.element("div").classes("w-32 px-2"):
                    ui.label(row["ts_code"]).classes(
                        "text-xs font-mono text-gray-700"
                    )
                with ui.element("div").classes("w-32 px-2"):
                    ui.label(row["name"]).classes(
                        "text-sm font-semibold text-gray-900"
                    )
                with ui.element("div").classes("w-24 px-2"):
                    ui.label(row["market"]).classes(
                        f"text-xs px-2 py-0.5 rounded border "
                        f"{_color_for_market(row['market'])}"
                    )
                with ui.element("div").classes("flex-1 px-2"):
                    ui.label(row["reason"]).classes("text-sm text-gray-700")
                with ui.element("div").classes("w-56 px-2"):
                    ui.label(row["period"]).classes(
                        "text-xs text-gray-500 font-mono"
                    )


def _render_holder_table(
    rows: list[dict], title: str, accent_color: str, icon: str
) -> None:
    """增减持列表卡片（带大额高亮）。"""
    with ui.card().classes(
        "w-full p-5 bg-white border border-gray-100 shadow-sm"
    ):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon(icon, color=accent_color).classes("text-xl")
            ui.label(title).classes("text-lg font-bold text-gray-800")
            ui.space()
            significant_n = sum(1 for r in rows if r.get("significant"))
            if significant_n:
                ui.label(f"⭐ 大额 {significant_n} 条").classes(
                    "text-xs text-amber-700 bg-amber-50 px-2 py-1 "
                    "rounded-full font-medium"
                )
            ui.label(f"{len(rows)} 条").classes(
                "text-xs text-gray-500 bg-gray-100 px-2 py-1 "
                "rounded-full ml-1"
            )

        if not rows:
            with ui.row().classes(
                "items-center gap-2 py-8 justify-center w-full text-gray-400"
            ):
                ui.icon("inbox", size="32px")
                ui.label("当日无相关公告").classes("text-sm")
            return

        with ui.row().classes(
            "w-full px-3 py-2 bg-gray-50 rounded-t-lg border-b border-gray-200 "
            "text-xs font-semibold text-gray-600 uppercase tracking-wider"
        ):
            for w, txt in [
                ("w-28", "代码"),
                ("w-28", "名称"),
                ("flex-1", "股东"),
                ("w-16", "类型"),
                ("w-28", "变动(万股)"),
                ("w-20", "比例%"),
                ("w-20", "均价"),
                ("w-24", "金额(万)"),
                ("w-20", "后续%"),
            ]:
                align = "text-right" if w not in ("flex-1",) else ""
                with ui.element("div").classes(f"{w} px-2 {align}"):
                    ui.label(txt).classes(align)

        for idx, row in enumerate(rows):
            row_bg = (
                "bg-amber-50/30 hover:bg-amber-50/60"
                if row.get("significant")
                else (
                    "bg-white hover:bg-gray-50"
                    if idx % 2 == 0
                    else "bg-gray-50/40 hover:bg-gray-50"
                )
            )
            star = "⭐ " if row.get("significant") else ""
            with ui.row().classes(
                f"w-full px-3 py-3 border-b border-gray-100 items-center "
                f"transition-colors {row_bg}"
            ):
                with ui.element("div").classes("w-28 px-2"):
                    ui.label(row["ts_code"]).classes(
                        "text-xs font-mono text-gray-700"
                    )
                with ui.element("div").classes("w-28 px-2"):
                    ui.label(row["name"]).classes(
                        "text-sm font-semibold text-gray-900"
                    )
                with ui.element("div").classes("flex-1 px-2"):
                    ui.label(f"{star}{row['holder_name']}").classes(
                        "text-sm text-gray-800"
                    )
                with ui.element("div").classes("w-16 px-2"):
                    ui.label(row["holder_type"]).classes(
                        "text-xs text-gray-600 bg-gray-100 px-2 py-0.5 rounded"
                    )
                with ui.element("div").classes("w-28 px-2 text-right"):
                    cls = "text-sm font-mono "
                    cls += (
                        "text-amber-700 font-semibold"
                        if row.get("significant")
                        else "text-gray-700"
                    )
                    ui.label(row["change_vol_wan"]).classes(cls)
                with ui.element("div").classes("w-20 px-2 text-right"):
                    cls = "text-sm font-mono "
                    cls += (
                        "text-amber-700 font-semibold"
                        if row.get("significant")
                        else "text-gray-700"
                    )
                    ui.label(row["change_ratio"]).classes(cls)
                with ui.element("div").classes("w-20 px-2 text-right"):
                    ui.label(row["avg_price"]).classes(
                        "text-xs font-mono text-gray-600"
                    )
                with ui.element("div").classes("w-24 px-2 text-right"):
                    cls = "text-sm font-mono "
                    cls += (
                        "text-amber-700 font-semibold"
                        if row.get("significant")
                        else "text-gray-700"
                    )
                    ui.label(row["est_amount_wan"]).classes(cls)
                with ui.element("div").classes("w-20 px-2 text-right"):
                    ui.label(row["after_ratio"]).classes(
                        "text-xs font-mono text-gray-600"
                    )


# ---------------------------------------------------------------- 面板入口

def render_special_announcement_panel(plotly_renderer=None):
    """公告栏面板：可嵌入到 mood 板块或其他位置。

    子面板：
      - 「异动 / 增减持」：原交易异动与股东增减持公告
      - 「吞没形态」：6 大指数 Engulfing Pattern 识别器

    参数：
        plotly_renderer: 可选，传入 None 或 ui.plotly 以保证面板独立可调。
    """
    plot_func = plotly_renderer if plotly_renderer else ui.plotly
    state = {"date": None, "busy": False, "refresh_btn": None, "subtab": "shock"}

    with ui.column().classes("w-full gap-4"):
        # ========== 顶部：子 Tab 切换 ==========
        with ui.row().classes(
            "w-full bg-white p-1 rounded-xl shadow-sm border border-gray-200 gap-1"
        ):
            shock_tab = ui.button(
                "异动 / 增减持",
                icon="campaign",
                on_click=lambda: _switch_subtab("shock"),
            ).props("no-caps flat dense").classes(
                "flex-1 rounded-lg font-bold text-sm transition-all"
            )
            engulf_tab = ui.button(
                "吞没形态",
                icon="candlestick_chart",
                on_click=lambda: _switch_subtab("engulf"),
            ).props("no-caps flat dense").classes(
                "flex-1 rounded-lg font-bold text-sm transition-all"
            )
            state["shock_tab_btn"] = shock_tab
            state["engulf_tab_btn"] = engulf_tab

        # ========== 子面板：异动 / 增减持 ==========
        @ui.refreshable
        def render_shock_subtab():
            with ui.column().classes("w-full gap-4"):
                with ui.expansion(
                    "数据口径说明", icon="info", value=False
                ).classes(
                    "w-full bg-white border border-gray-100 rounded-lg shadow-sm"
                ):
                    with ui.column().classes(
                        "p-4 text-gray-600 text-sm gap-1"
                    ):
                        ui.markdown(
                            "- **交易异动**：交易所异常波动公告（`stk_shock`）与严重异常波动（`stk_high_shock`，"
                            "通常为 10/30 个交易日累计涨跌幅 ≥ 100%）。\n"
                            "- **股东增减持**：当日披露的大股东增持/减持公告（`stk_holdertrade`，"
                            "`IN` 为增持，`DE` 为减持；⭐ 表示变动比例 ≥ 5% 或按均价估算金额 ≥ 1 亿元）。\n"
                            "- **数据来源**：Tushare Pro，每日北京时间晚间生成当日快照，"
                            "数据以交易所/上市公司公告披露为准，仅供参考，不构成投资建议。"
                        )

                dates = _available_dates()
                if not dates:
                    with ui.card().classes(
                        "w-full p-10 items-center gap-3 bg-white"
                    ):
                        ui.icon("inbox", size="48px").classes("text-gray-300")
                        ui.label(
                            "还没有生成过公告栏，请点击右上角「生成/刷新当日」"
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
                        ui.label(f"{current} 暂无公告数据").classes("text-gray-500")
                    return

                # 交易日概览条（大字日期 + 元信息 + 日期切换 + 刷新）
                with ui.card().classes(
                    "w-full p-5 bg-gradient-to-br from-white via-amber-50/40 "
                    "to-orange-50/40 border border-amber-100 shadow-sm rounded-xl"
                ):
                    with ui.row().classes("w-full items-center gap-4 flex-wrap"):
                        with ui.row().classes("items-center gap-3 min-w-[260px]"):
                            ui.element("div").classes(
                                "w-12 h-12 rounded-xl bg-gradient-to-br "
                                "from-amber-500 to-orange-500 flex "
                                "items-center justify-center shadow-md"
                            ).style("display:flex")
                            ui.icon("event", color="white").classes(
                                "text-2xl"
                            ).style("margin-left:-48px")
                            with ui.column().classes("gap-0 ml-3"):
                                ui.label(_pretty_date(payload["trade_date"])).classes(
                                    "text-2xl font-bold text-gray-900 "
                                    "leading-none tracking-wide font-mono"
                                )
                                weekday = _weekday_cn(payload["trade_date"])
                                meta_text = weekday or "交易日"
                                ui.label(meta_text).classes(
                                    "text-xs text-amber-700 mt-1 font-medium"
                                )

                        ui.separator().props("vertical").classes("h-12 bg-amber-200")

                        with ui.column().classes("gap-0"):
                            ui.label("数据状态").classes("text-xs text-gray-500")
                            if state["busy"]:
                                with ui.row().classes("items-center gap-1 mt-1"):
                                    ui.spinner(size="xs", color="amber")
                                    ui.label("正在抓取 Tushare 数据…").classes(
                                        "text-sm text-orange-600 font-medium"
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
                            "rounded-lg border border-amber-200 shadow-sm"
                        ):
                            ui.button(
                                icon="chevron_left",
                                on_click=lambda: _nav(-1),
                            ).props("flat dense round color=amber-7").tooltip(
                                "上一交易日"
                            )
                            ui.select(
                                dates,
                                value=current,
                                on_change=lambda e: _select_date(e.value),
                            ).props(
                                "outlined dense options-dense color=amber-7"
                            ).classes("min-w-[140px] border-none")
                            ui.button(
                                icon="chevron_right",
                                on_click=lambda: _nav(1),
                            ).props("flat dense round color=amber-7").tooltip(
                                "下一交易日"
                            )
                            ui.separator().props("vertical").classes(
                                "h-6 mx-1 bg-amber-200"
                            )
                            refresh_btn = ui.button(
                                "生成/刷新",
                                icon="refresh",
                                on_click=regenerate,
                            ).props("outline color=amber-7 dense no-caps").classes(
                                "font-medium"
                            )
                            state["refresh_btn"] = refresh_btn

                _render_summary_cards(payload.get("summary", {}))

                _render_shock_trend_chart(
                    payload.get("shock_trend", {}), plot_func=plot_func
                )

                _render_weekly_summary(payload.get("weekly_summary", {}))

                _render_shock_table(
                    payload.get("high_shock", []),
                    "严重异常波动公告",
                    "red",
                    "whatshot",
                )
                _render_shock_table(
                    payload.get("shock", []),
                    "异常波动公告",
                    "amber",
                    "bolt",
                )
                _render_holder_table(
                    payload.get("holder_in", []),
                    "股东增持公告",
                    "green",
                    "trending_up",
                )
                _render_holder_table(
                    payload.get("holder_de", []),
                    "股东减持公告",
                    "indigo",
                    "sell",
                )

                with ui.row().classes(
                    "w-full justify-center items-center py-3 mt-2 text-xs text-gray-400"
                ):
                    ui.label(
                        f"源文件：{os.path.join(OUTPUT_DIR, current + '.json')}"
                    )
                    ui.label("·").classes("mx-2")
                    ui.label("仅供研究参考，不构成投资建议")

        # ========== 子面板：吞没形态 ==========
        @ui.refreshable
        def render_engulf_subtab():
            render_engulfing_pattern_panel(plotly_renderer=plot_func)

        # 容器：根据 subtab 显示
        @ui.refreshable
        def render_content():
            _apply_subtab_style(state["subtab"])
            if state["subtab"] == "shock":
                render_shock_subtab()
            else:
                render_engulf_subtab()

        def _apply_subtab_style(active: str) -> None:
            """子 Tab 按钮高亮切换。"""
            try:
                shock_btn = state.get("shock_tab_btn")
                engulf_btn = state.get("engulf_tab_btn")
                if shock_btn is None or engulf_btn is None:
                    return
                if active == "shock":
                    shock_btn.classes(
                        "flex-1 rounded-lg font-bold text-sm transition-all "
                        "bg-gradient-to-r from-amber-500 to-orange-500 text-white shadow-md"
                    )
                    shock_btn.props(remove="flat")
                    shock_btn.props("unelevated")
                    engulf_btn.classes("flex-1 rounded-lg font-bold text-sm transition-all text-gray-500 hover:bg-gray-50")
                    engulf_btn.props("flat")
                    engulf_btn.props(remove="unelevated")
                else:
                    engulf_btn.classes(
                        "flex-1 rounded-lg font-bold text-sm transition-all "
                        "bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-md"
                    )
                    engulf_btn.props(remove="flat")
                    engulf_btn.props("unelevated")
                    shock_btn.classes("flex-1 rounded-lg font-bold text-sm transition-all text-gray-500 hover:bg-gray-50")
                    shock_btn.props("flat")
                    shock_btn.props(remove="unelevated")
            except Exception:  # noqa: BLE001
                pass

        def _switch_subtab(tab: str) -> None:
            state["subtab"] = tab
            render_content.refresh()

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

        async def regenerate():
            if state["busy"]:
                return
            state["busy"] = True
            btn = state.get("refresh_btn")
            if btn is not None:
                btn.props("loading disable")
            try:
                def _work():
                    board = SpecialAnnouncementBoard()
                    trade_date = board.latest_trade_date()
                    # 增减持窗口 = 5 个交易日（本周窗口）
                    data = board.fetch_day_simple(trade_date, holder_window=5)
                    payload = build_struct_data(data)
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
                    ui.notify(f"已生成 {state['date']} 公告栏", type="positive")
                except Exception:  # noqa: BLE001
                    pass
            finally:
                state["busy"] = False
                if btn is not None:
                    btn.props(remove="loading").props(remove="disable")
                render_content.refresh()

        render_content()


def create_special_announcement_page():
    """兼容旧入口：直接跳转到 mood 板块的公告栏 tab。"""
    @ui.page("/special-announcement")
    def special_announcement_page():
        setup_common_ui()
        ui.navigate.to("/mood?tab=announce")

    return special_announcement_page


special_announcement_page_instance = create_special_announcement_page()