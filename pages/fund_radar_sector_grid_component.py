from nicegui import ui
from utils.sector_grid_logic import get_sector_grid_data
from utils.sector_analysis import sector_analyzer
from pages.fund_flow_calendar_component import render_fund_flow_calendar
import pandas as pd
import asyncio
import datetime


def render_sector_grid_view(radar):
    try:
        dates, grid_data = get_sector_grid_data(radar.cache_dir, days=6)
        if not dates:
            return

        with ui.card().classes('w-full border border-gray-200 rounded-xl shadow-sm bg-white p-0 flex flex-col gap-0 mt-4'):
            with ui.row().classes('w-full justify-between items-center p-3 border-b border-gray-200 bg-gray-50/50'):
                with ui.column().classes('gap-0'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('grid_view', color='indigo').classes('text-lg')
                        ui.label('核心板块资金流向雷达 (Core Sector Flow Radar)').classes('text-sm font-bold text-gray-800')
                        last_analysis_time = ui.label('').classes('text-[10px] text-gray-400 font-mono ml-2')
                    ui.label('备注：2.24日开始，净流入为主力净流入，之前为全口径净流入').classes('text-[10px] text-gray-400 transform scale-90 origin-left ml-7')

                with ui.row().classes('items-center gap-4'):
                    btn_refresh_analysis = ui.button('刷新分析', icon='refresh', on_click=lambda: run_analysis(force=True)).props('flat dense size=sm color=indigo').classes('text-xs font-bold')
                    with ui.row().classes('items-center gap-2 text-[10px] text-gray-500'):
                        with ui.row().classes('items-center gap-1'):
                            ui.element('div').classes('w-2 h-2 bg-red-600 rounded-sm')
                            ui.label('超入')
                        with ui.row().classes('items-center gap-1'):
                            ui.element('div').classes('w-2 h-2 bg-red-400 rounded-sm')
                            ui.label('强入')
                        with ui.row().classes('items-center gap-1'):
                            ui.element('div').classes('w-2 h-2 bg-green-600 rounded-sm')
                            ui.label('超出')
                        with ui.row().classes('items-center gap-1'):
                            ui.element('div').classes('w-2 h-2 bg-green-400 rounded-sm')
                            ui.label('强出')
                    ui.label('单位: 亿元').classes('text-[10px] text-gray-400')

            detail_dialog = ui.dialog().classes('w-full')
            with detail_dialog, ui.card().classes('w-full max-w-5xl p-6 rounded-2xl shadow-xl bg-white'):
                with ui.row().classes('w-full justify-between items-start mb-6'):
                    with ui.row().classes('items-end gap-4'):
                        detail_title = ui.label('板块详情').classes('text-3xl font-black text-gray-900 tracking-tight')
                        detail_price = ui.label('').classes('text-2xl font-bold font-mono')
                        detail_change = ui.label('').classes('text-lg font-bold px-2 py-0.5 rounded-lg')
                        detail_subtitle = ui.label('').classes('text-sm text-gray-400 font-bold mb-1')
                    ui.button(icon='close', on_click=detail_dialog.close).props('flat round dense color=grey size=lg')
                detail_content = ui.column().classes('w-full gap-6')

            def show_sector_detail(name):
                detail_title.set_text(name)
                detail_price.set_text('')
                detail_change.set_text('')
                detail_change.classes(remove='bg-red-50 text-red-600 bg-green-50 text-green-600')
                detail_content.clear()
                detail_dialog.open()

                async def load_detail():
                    with detail_content:
                        ui.spinner(type='dots', size='3rem', color='indigo')

                    res = await asyncio.get_event_loop().run_in_executor(None, lambda: sector_analyzer.analyze(name))
                    if 'market_data' in res:
                        md = res['market_data']
                        detail_price.set_text(f"{md['close']:.2f}")
                        chg = md['change']
                        detail_change.set_text(f"{chg:+.2f}%")
                        if chg > 0:
                            detail_change.classes('bg-red-50 text-red-600')
                            detail_price.classes('text-red-600')
                        else:
                            detail_change.classes('bg-green-50 text-green-600')
                            detail_price.classes('text-green-600')
                        detail_subtitle.set_text(f"数据日期: {md['date']}")

                    detail_content.clear()
                    with detail_content:
                        if 'chart_data' in res:
                            cd = res['chart_data']
                            k_data = []
                            for i in range(len(cd['dates'])):
                                o = None if pd.isna(cd['open'][i]) else round(float(cd['open'][i]), 1)
                                c = None if pd.isna(cd['close'][i]) else round(float(cd['close'][i]), 1)
                                l = None if pd.isna(cd['low'][i]) else round(float(cd['low'][i]), 1)
                                h = None if pd.isna(cd['high'][i]) else round(float(cd['high'][i]), 1)
                                k_data.append([o, c, l, h])

                            ma5_data = [None if pd.isna(v) else round(float(v), 1) for v in cd.get('ma5', [])]
                            ma20_data = [None if pd.isna(v) else round(float(v), 1) for v in cd.get('ma20', [])]
                            bi_line_data = []
                            mark_point_data = []

                            if res['bi_points']:
                                for bi in res['bi_points']:
                                    date_str = str(bi['date'])
                                    price = bi['price']
                                    bi_type = bi['type']
                                    bi_line_data.append([date_str, price])
                                    is_top = (bi_type == 'top')
                                    mark_color = "#22c55e" if is_top else "#ef4444"
                                    mark_point_data.append({
                                        "coord": [date_str, price],
                                        "value": f"{price:.2f}",
                                        "name": f"{'顶分' if is_top else '底分'}",
                                        "itemStyle": {"color": mark_color},
                                        "label": {"show": True, "position": "top" if is_top else "bottom", "formatter": "{b}\n{c}", "color": mark_color, "fontWeight": "bold", "fontSize": 11},
                                        "symbol": "arrow",
                                        "symbolSize": 12,
                                        "symbolRotate": 180 if is_top else 0,
                                        "symbolOffset": [0, -12] if is_top else [0, 12],
                                    })

                            macd = res.get('macd', {})
                            raw_dif = macd.get('dif', [])
                            raw_dea = macd.get('dea', [])
                            dif = [None if pd.isna(v) else round(float(v), 1) for v in raw_dif]
                            dea = [None if pd.isna(v) else round(float(v), 1) for v in raw_dea]
                            hist = [None if pd.isna(v) else round(float(v), 1) for v in macd.get('hist', [])]
                            macd_mark_points = []
                            if raw_dif and raw_dea:
                                for i in range(1, len(raw_dif)):
                                    if raw_dif[i] > raw_dea[i] and raw_dif[i-1] <= raw_dea[i-1]:
                                        macd_mark_points.append({"coord": [str(cd['dates'][i]), None if pd.isna(raw_dif[i]) else round(float(raw_dif[i]), 1)], "value": "金叉", "itemStyle": {"color": "#ef4444"}, "label": {"position": "bottom", "color": "#ef4444", "fontSize": 10, "fontWeight": "bold"}})
                                    elif raw_dif[i] < raw_dea[i] and raw_dif[i-1] >= raw_dea[i-1]:
                                        macd_mark_points.append({"coord": [str(cd['dates'][i]), None if pd.isna(raw_dif[i]) else round(float(raw_dif[i]), 1)], "value": "死叉", "itemStyle": {"color": "#22c55e"}, "label": {"position": "top", "color": "#22c55e", "fontSize": 10, "fontWeight": "bold"}})

                            center_mark_areas = []
                            centers = res.get('centers', [])
                            valid_dates = set([str(d) for d in cd['dates']])
                            for c in centers:
                                s_date = str(c['start_date'])
                                e_date = str(c['end_date'])
                                if s_date not in valid_dates or e_date not in valid_dates:
                                    continue
                                center_mark_areas.append([
                                    {"coord": [s_date, c['zg']], "itemStyle": {"color": "rgba(255, 165, 0, 0.15)", "borderWidth": 1, "borderType": "dashed", "borderColor": "rgba(255, 165, 0, 0.8)"}},
                                    {"coord": [e_date, c['zd']]},
                                ])

                            chart_option = {
                                "animation": False,
                                "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross", "link": {"xAxisIndex": "all"}}, "backgroundColor": "rgba(255, 255, 255, 0.9)", "borderColor": "#ccc", "borderWidth": 1, "textStyle": {"color": "#333"}},
                                "axisPointer": {"link": {"xAxisIndex": "all"}},
                                "legend": {"data": ["日K", "MA5", "MA20", "缠论笔", "DIF", "DEA", "MACD"], "top": 0},
                                "grid": [{"left": "5%", "right": "5%", "top": "10%", "height": "55%", "containLabel": True}, {"left": "5%", "right": "5%", "top": "75%", "height": "15%", "containLabel": True}],
                                "xAxis": [{"type": "category", "data": cd['dates'], "scale": True, "boundaryGap": False, "axisLine": {"onZero": False}, "splitLine": {"show": False}, "min": "dataMin", "max": "dataMax"}, {"type": "category", "gridIndex": 1, "data": cd['dates'], "scale": True, "boundaryGap": False, "axisLine": {"onZero": False}, "axisLabel": {"show": False}, "axisTick": {"show": False}, "splitLine": {"show": False}, "min": "dataMin", "max": "dataMax"}],
                                "yAxis": [{"scale": True, "splitArea": {"show": False}, "splitLine": {"show": True, "lineStyle": {"color": "#eee"}}}, {"gridIndex": 1, "scale": True, "splitArea": {"show": False}, "splitLine": {"show": False}}],
                                "dataZoom": [{"type": "inside", "xAxisIndex": [0, 1], "start": 70, "end": 100}, {"show": True, "type": "slider", "xAxisIndex": [0, 1], "top": "94%", "height": 20}],
                                "series": [
                                    {"name": "日K", "type": "candlestick", "data": k_data, "itemStyle": {"color": "#ef4444", "color0": "#22c55e", "borderColor": "#ef4444", "borderColor0": "#22c55e"}, "markArea": {"data": center_mark_areas, "label": {"show": True, "position": "insideTopLeft", "formatter": "中枢", "color": "rgba(255, 165, 0, 0.8)", "fontSize": 10}}},
                                    {"name": "MA5", "type": "line", "data": ma5_data, "smooth": True, "showSymbol": False, "lineStyle": {"width": 1, "opacity": 0.6, "color": "#f59e0b"}},
                                    {"name": "MA20", "type": "line", "data": ma20_data, "smooth": True, "showSymbol": False, "lineStyle": {"width": 1, "opacity": 0.6, "color": "#8b5cf6"}},
                                    {"name": "缠论笔", "type": "line", "data": bi_line_data, "symbol": "circle", "symbolSize": 6, "lineStyle": {"color": "#3b82f6", "width": 2}, "itemStyle": {"color": "#3b82f6", "borderColor": "#fff", "borderWidth": 1}, "connectNulls": False, "markPoint": {"data": mark_point_data, "label": {"show": True, "formatter": "{b}\n{c}"}}},
                                    {"name": "MACD", "type": "bar", "xAxisIndex": 1, "yAxisIndex": 1, "data": [{"value": h, "itemStyle": {"color": "#ef4444" if h > 0 else "#22c55e"}} for h in hist]},
                                    {"name": "DIF", "type": "line", "xAxisIndex": 1, "yAxisIndex": 1, "data": dif, "symbol": "none", "lineStyle": {"color": "#3b82f6", "width": 1}, "markPoint": {"data": macd_mark_points, "symbolSize": 30}},
                                    {"name": "DEA", "type": "line", "xAxisIndex": 1, "yAxisIndex": 1, "data": dea, "symbol": "none", "lineStyle": {"color": "#f59e0b", "width": 1}},
                                ],
                            }

                            with ui.card().classes('w-full p-4 rounded-2xl border border-gray-100 shadow-sm'):
                                ui.label('缠论 K 线结构图 (Chan Lun K-Line)').classes('text-base font-black text-gray-800 mb-2')
                                ui.echart(options=chart_option).classes('w-full h-[400px]')

                        with ui.grid(columns=2).classes('w-full gap-6'):
                            with ui.card().classes('p-5 rounded-2xl border border-gray-100 bg-gradient-to-br from-gray-50 to-white shadow-sm relative overflow-hidden group hover:shadow-md transition-all'):
                                ui.icon('bolt', color='gray-200').classes('absolute -right-4 -bottom-4 text-8xl opacity-20 rotate-12 group-hover:scale-110 transition-transform')
                                ui.label('短线机会 (Short Term)').classes('text-sm font-black text-gray-400 uppercase tracking-widest mb-3')
                                ui.label(res['short_term']['status']).classes(f"text-3xl font-black tracking-tight {res['short_term']['color']}")
                                with ui.row().classes('items-center gap-2 mt-2'):
                                    ui.icon('info', size='xs', color='gray-400')
                                    ui.label(res['short_term']['signal']).classes('text-sm text-gray-600 font-medium')
                            with ui.card().classes('p-5 rounded-2xl border border-gray-100 bg-gradient-to-br from-gray-50 to-white shadow-sm relative overflow-hidden group hover:shadow-md transition-all'):
                                ui.icon('trending_up', color='gray-200').classes('absolute -right-4 -bottom-4 text-8xl opacity-20 rotate-12 group-hover:scale-110 transition-transform')
                                ui.label('中线趋势 (Medium Term)').classes('text-sm font-black text-gray-400 uppercase tracking-widest mb-3')
                                ui.label(res['mid_long_term']['status']).classes(f"text-3xl font-black tracking-tight {res['mid_long_term']['color']}")
                                with ui.row().classes('items-center gap-2 mt-2'):
                                    ui.icon('analytics', size='xs', color='gray-400')
                                    ui.label(res['mid_long_term']['signal']).classes('text-sm text-gray-600 font-medium')

                        with ui.card().classes('w-full p-6 rounded-2xl border border-gray-100 shadow-sm'):
                            ui.label('技术指标透视 (Technical Indicators)').classes('text-base font-black text-gray-800 mb-6 pb-3 border-b border-gray-100 w-full')
                            with ui.grid(columns=4).classes('w-full gap-8'):
                                with ui.column().classes('gap-2'):
                                    ui.label('MACD 趋势').classes('text-xs font-bold text-gray-400 uppercase')
                                    ui.label(res['macd_info']['text']).classes(f"text-lg font-black {res['macd_info']['color']}")
                                    if res['macd'] and res['macd']['dif']:
                                        with ui.column().classes('gap-0 mt-1 bg-gray-50 p-2 rounded-lg w-full'):
                                            with ui.row().classes('justify-between w-full'):
                                                ui.label('DIF').classes('text-[10px] text-gray-500 font-bold')
                                                ui.label(f"{res['macd']['dif'][-1]:.2f}").classes('text-xs font-mono font-bold text-gray-700')
                                            with ui.row().classes('justify-between w-full'):
                                                ui.label('DEA').classes('text-[10px] text-gray-500 font-bold')
                                                ui.label(f"{res['macd']['dea'][-1]:.2f}").classes('text-xs font-mono font-bold text-gray-700')
                                with ui.column().classes('gap-2'):
                                    ui.label('RSI (14) 强弱').classes('text-xs font-bold text-gray-400 uppercase')
                                    rsi_val = res['last_rsi']
                                    rsi_color = 'text-red-500' if rsi_val > 70 else ('text-green-500' if rsi_val < 30 else 'text-gray-800')
                                    with ui.row().classes('items-baseline gap-1'):
                                        ui.label(f"{rsi_val:.1f}").classes(f"text-3xl font-black {rsi_color} leading-none")
                                        ui.label('/ 100').classes('text-xs text-gray-400 font-bold')
                                    with ui.element('div').classes('w-full h-2 bg-gray-100 rounded-full overflow-hidden mt-1 relative'):
                                        ui.element('div').classes('absolute left-0 top-0 h-full bg-green-100 w-[30%]')
                                        ui.element('div').classes('absolute right-0 top-0 h-full bg-red-100 w-[30%]')
                                        bar_color = 'bg-red-500' if rsi_val > 70 else ('bg-green-500' if rsi_val < 30 else 'bg-indigo-500')
                                        ui.element('div').classes(f'h-full {bar_color} transition-all duration-500').style(f'width: {rsi_val}%')
                                with ui.column().classes('gap-2'):
                                    ui.label('布林线 (Bollinger)').classes('text-xs font-bold text-gray-400 uppercase')
                                    ui.label(res['boll_info']['text']).classes(f"text-lg font-black {res['boll_info']['color']}")
                                    if 'bollinger_bands' in res:
                                        bb = res['bollinger_bands']
                                        with ui.column().classes('gap-0 mt-1 bg-gray-50 p-2 rounded-lg w-full'):
                                            with ui.row().classes('justify-between w-full'):
                                                ui.label('上轨').classes('text-[10px] text-gray-500 font-bold')
                                                ui.label(f"{bb['upper']:.1f}").classes('text-xs font-mono font-bold text-gray-700')
                                            with ui.row().classes('justify-between w-full'):
                                                ui.label('中轨').classes('text-[10px] text-gray-500 font-bold')
                                                ui.label(f"{bb['middle']:.1f}").classes('text-xs font-mono font-bold text-gray-700')
                                            with ui.row().classes('justify-between w-full'):
                                                ui.label('下轨').classes('text-[10px] text-gray-500 font-bold')
                                                ui.label(f"{bb['lower']:.1f}").classes('text-xs font-mono font-bold text-gray-700')
                                with ui.column().classes('gap-2'):
                                    ui.label('均线排列 (MA)').classes('text-xs font-bold text-gray-400 uppercase')
                                    if 'ma_data' in res:
                                        ma_align = res['ma_data']['alignment']
                                        align_text = "多头排列" if ma_align == 'bull' else ("空头排列" if ma_align == 'bear' else "纠缠/震荡")
                                        align_color = "text-red-500" if ma_align == 'bull' else ("text-green-500" if ma_align == 'bear' else "text-gray-500")
                                        ui.label(align_text).classes(f"text-lg font-black {align_color}")
                                        with ui.column().classes('gap-0 mt-1 bg-gray-50 p-2 rounded-lg w-full'):
                                            ma_vals = res['ma_data']
                                            for ma_name in ['ma5', 'ma10', 'ma20', 'ma60']:
                                                with ui.row().classes('justify-between w-full'):
                                                    ui.label(ma_name.upper()).classes('text-[10px] text-gray-500 font-bold')
                                                    ui.label(f"{ma_vals[ma_name]:.1f}").classes('text-xs font-mono font-bold text-gray-700')

                        with ui.card().classes('w-full p-6 rounded-2xl border border-gray-100 bg-gradient-to-r from-indigo-50 to-white shadow-sm'):
                            ui.label('缠论结构分析 (Chan Lun Structure)').classes('text-base font-black text-indigo-900 mb-4 pb-2 border-b border-indigo-100 w-full')
                            with ui.row().classes('w-full gap-8'):
                                with ui.column().classes('flex-1 gap-2'):
                                    ui.label('当前笔状态').classes('text-xs font-bold text-indigo-400 uppercase')
                                    ui.label(res['chan_info']['text']).classes(f"text-2xl font-black {res['chan_info']['color']}")
                                    ui.label(res['summary']).classes('text-sm text-gray-600 font-medium leading-relaxed mt-2 bg-white/50 p-3 rounded-lg border border-indigo-50')
                                with ui.column().classes('flex-1 gap-2'):
                                    ui.label('近期笔走势 (Recent Strokes)').classes('text-xs font-bold text-indigo-400 uppercase')
                                    if res['bi_points']:
                                        recent_bi = list(reversed(res['bi_points']))[:5]
                                        with ui.column().classes('w-full gap-1'):
                                            for i, bi in enumerate(recent_bi):
                                                bi_type = "顶分型 (Top)" if bi['type'] == 'top' else "底分型 (Bottom)"
                                                bi_color = "text-green-600" if bi['type'] == 'top' else "text-red-600"
                                                bi_icon = "arrow_downward" if bi['type'] == 'top' else "arrow_upward"
                                                with ui.row().classes('w-full justify-between items-center bg-white/60 px-3 py-1.5 rounded border border-indigo-50/50'):
                                                    with ui.row().classes('items-center gap-2'):
                                                        ui.label(f"{len(res['bi_points'])-i}").classes('text-[10px] font-bold text-gray-300 w-4')
                                                        ui.icon(bi_icon, size='xs', color=bi_color.split('-')[1])
                                                        ui.label(bi_type).classes(f"text-xs font-bold {bi_color}")
                                                    with ui.row().classes('items-center gap-4'):
                                                        ui.label(f"{bi['price']:.2f}").classes('text-xs font-mono font-bold text-gray-700')
                                                        ui.label(str(bi['date'])).classes('text-[10px] text-gray-400 font-mono')
                                    else:
                                        ui.label('暂无笔结构数据').classes('text-sm text-gray-400 italic')

                        await render_fund_flow_calendar(name, radar.cache_dir)

                run_in_bg(load_detail)

            def run_in_bg(task):
                asyncio.create_task(task())

            with ui.column().classes('w-full gap-0 border-t border-gray-200'):
                with ui.element('div').classes('w-full flex flex-row bg-gray-100 border-b border-gray-200 h-8 items-center gap-0'):
                    ui.label('板块').classes('w-20 md:w-24 pl-4 flex items-center text-[11px] font-bold text-gray-500')
                    ui.label('短线机会').classes('gt-xs flex items-center justify-center w-24 text-[11px] font-bold text-gray-500 border-l border-gray-200')
                    ui.label('中线趋势').classes('gt-xs flex items-center justify-center w-24 text-[11px] font-bold text-gray-500 border-l border-gray-200')
                    ui.label('缠论结构').classes('gt-xs flex items-center justify-center w-24 text-[11px] font-bold text-gray-500 border-l border-gray-200')
                    ui.label('MACD').classes('gt-xs flex items-center justify-center w-20 text-[11px] font-bold text-gray-500 border-l border-gray-200')
                    ui.label('RSI').classes('gt-xs flex items-center justify-center w-12 text-[11px] font-bold text-gray-500 border-l border-gray-200')
                    ui.label('布林').classes('gt-xs flex items-center justify-center w-16 text-[11px] font-bold text-gray-500 border-l border-gray-200')
                    for d in dates:
                        ui.label(d).classes('flex-1 flex items-center justify-center text-[11px] font-bold text-gray-500 border-l border-gray-200')

                all_rows = []
                analysis_targets = []
                sector_count = 0
                initial_show_count = 15

                for category, sectors in grid_data.items():
                    if not sectors:
                        continue
                    cat_row = ui.row().classes('w-full bg-indigo-50 border-y border-indigo-100 py-1.5 px-4 items-center')
                    with cat_row:
                        ui.label(category).classes('text-[11px] font-black text-indigo-800 tracking-widest')
                    all_rows.append({'row': cat_row, 'type': 'category'})

                    for sector in sectors:
                        s_row = ui.element('div').classes('w-full flex flex-row border-b border-gray-100 h-9 items-center gap-0 hover:bg-gray-50 transition-colors group')
                        with s_row:
                            with ui.element('div').classes('w-20 md:w-24 pl-4 h-full flex items-center border-r border-gray-100'):
                                ui.label(sector['name']).classes('text-[11px] font-bold text-gray-700 truncate')
                            with ui.element('div').classes('gt-xs flex flex-row w-24 h-full items-center justify-center border-r border-gray-100 px-1'):
                                lbl_short = ui.label('-').classes('text-[10px] text-gray-400')
                            with ui.element('div').classes('gt-xs flex flex-row w-24 h-full items-center justify-center border-r border-gray-100 px-1'):
                                lbl_mid = ui.label('-').classes('text-[10px] text-gray-400')
                            with ui.element('div').classes('gt-xs flex flex-row w-24 h-full items-center justify-center border-r border-gray-100 px-1'):
                                lbl_chan = ui.label('-').classes('text-[10px] text-gray-400')
                            with ui.element('div').classes('gt-xs flex flex-row w-20 h-full items-center justify-center border-r border-gray-100 px-1'):
                                lbl_macd = ui.label('-').classes('text-[10px] text-gray-400')
                            with ui.element('div').classes('gt-xs flex flex-row w-12 h-full items-center justify-center border-r border-gray-100 px-1'):
                                lbl_rsi = ui.label('-').classes('text-[10px] text-gray-400')
                            with ui.element('div').classes('gt-xs flex flex-row w-16 h-full items-center justify-center border-r border-gray-100 px-1'):
                                lbl_boll = ui.label('-').classes('text-[10px] text-gray-400')
                            analysis_targets.append({'name': sector['name'], 'short': lbl_short, 'mid': lbl_mid, 'chan': lbl_chan, 'macd': lbl_macd, 'rsi': lbl_rsi, 'boll': lbl_boll})
                            s_row.on('click', lambda name=sector['name']: show_sector_detail(name))
                            s_row.classes('cursor-pointer')
                            for day_data in sector['history']:
                                with ui.row().classes(f'flex-1 h-full items-center justify-center {day_data["color_class"]} border-r border-gray-100 px-1 relative'):
                                    ui.label(day_data['status']).classes('text-[11px] font-bold leading-none')
                                    ui.tooltip(f"{day_data['date']} {sector['name']}\n净流入: {day_data['inflow']:.1f}亿\n成交额: {day_data['turnover']:.1f}亿\n强度: {day_data['ratio']:.1f}%").classes('text-xs bg-gray-800 text-white shadow-lg whitespace-pre-line')
                        all_rows.append({'row': s_row, 'type': 'sector'})
                        sector_count += 1

                visible_sectors = 0
                hidden_row_elements = []
                for item in all_rows:
                    if visible_sectors >= initial_show_count:
                        item['row'].set_visibility(False)
                        hidden_row_elements.append(item['row'])
                    if item['type'] == 'sector':
                        visible_sectors += 1

                if hidden_row_elements:
                    with ui.row().classes('w-full justify-center py-3 bg-gray-50 border-t border-gray-200 cursor-pointer hover:bg-gray-100 transition-colors') as btn_container:
                        icon = ui.icon('expand_more', color='gray-500').classes('text-xl transition-transform duration-300')
                        lbl = ui.label(f'展开剩余 {sector_count - initial_show_count} 个板块').classes('text-xs font-bold text-gray-500')
                        is_expanded = {'val': False}

                        def toggle_grid():
                            is_expanded['val'] = not is_expanded['val']
                            for r in hidden_row_elements:
                                r.set_visibility(is_expanded['val'])
                            if is_expanded['val']:
                                lbl.set_text('收起列表')
                                icon.classes(remove='rotate-0', add='rotate-180')
                            else:
                                lbl.set_text(f'展开剩余 {sector_count - initial_show_count} 个板块')
                                icon.classes(remove='rotate-180', add='rotate-0')

                        btn_container.on('click', toggle_grid)

                async def run_analysis(force=False):
                    utc_now = datetime.datetime.now(datetime.timezone.utc)
                    cn_now = utc_now + datetime.timedelta(hours=8)
                    time_str = cn_now.strftime('%H:%M:%S')
                    if not last_analysis_time.is_deleted:
                        last_analysis_time.set_text(f"最后刷新: {time_str}")
                    if force:
                        ui.notify('正在强制刷新板块分析数据...', type='info', position='top')
                        if not btn_refresh_analysis.is_deleted:
                            btn_refresh_analysis.disable()

                    for target in analysis_targets:
                        if s_row.is_deleted:
                            return
                        try:
                            def analyze_wrapper(name, force_flag):
                                if force_flag:
                                    sector_analyzer.fetch_history(name, force_update=True)
                                return sector_analyzer.analyze(name)

                            res = await asyncio.get_event_loop().run_in_executor(None, lambda: analyze_wrapper(target['name'], force))
                            target['short'].set_text(res['short_term']['status'])
                            target['short'].classes(replace=f"text-[10px] font-bold {res['short_term']['color']}")
                            target['short'].tooltip(res['short_term']['signal'])
                            target['mid'].set_text(res['mid_long_term']['status'])
                            target['mid'].classes(replace=f"text-[10px] font-bold {res['mid_long_term']['color']}")
                            target['mid'].tooltip(res['mid_long_term']['signal'])
                            target['chan'].set_text(res['chan_info']['text'])
                            target['chan'].classes(replace=f"text-[10px] font-bold {res['chan_info']['color']}")
                            chan_tooltip = f"{res['summary']}\nRSI: {res['last_rsi']}\n{res['boll_info']['text']}\n{res['breakout_info']['text']}"
                            target['chan'].tooltip(chan_tooltip).classes('whitespace-pre-line')
                            target['macd'].set_text(res['macd_info']['text'])
                            target['macd'].classes(replace=f"text-[10px] font-bold {res['macd_info']['color']}")
                            target['rsi'].set_text(str(int(res['last_rsi'])))
                            if res['last_rsi'] > 70:
                                target['rsi'].classes(replace='text-[10px] text-red-500 font-bold')
                            elif res['last_rsi'] < 30:
                                target['rsi'].classes(replace='text-[10px] text-green-500 font-bold')
                            else:
                                target['rsi'].classes(replace='text-[10px] text-gray-500')
                            target['boll'].set_text(res['boll_info']['text'])
                            target['boll'].classes(replace=f"text-[10px] font-bold {res['boll_info']['color']}")
                            await asyncio.sleep(0.05)
                        except Exception as e:
                            print(f"Analysis error for {target['name']}: {e}")
                            target['short'].set_text('Error')

                    if force:
                        if not btn_refresh_analysis.is_deleted:
                            btn_refresh_analysis.enable()
                        ui.notify('板块分析数据刷新完成', type='positive', position='top')

                ui.timer(0.5, run_analysis, once=True)
    except Exception as e:
        print(f"Error rendering sector grid: {e}")
        ui.label(f"Error loading sector grid: {str(e)}").classes('text-red-500 text-xs p-4')
