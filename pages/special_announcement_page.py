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

def render_special_announcement_panel():
    """公告栏面板：可嵌入到 mood 板块或其他位置。

    不含外层 header / 导航栏，由调用方提供上下文。
    """
    state = {"date": None, "busy": False, "refresh_btn": None}

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

        @ui.refreshable
        def render_content():
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
                    # 左侧：大字日期 + 星期
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

                    # 中部：数据状态
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

                    # 右侧：日期切换 + 刷新
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
                    data = board.fetch_day_simple(trade_date)
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