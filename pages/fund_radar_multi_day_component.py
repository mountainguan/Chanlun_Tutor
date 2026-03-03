from nicegui import ui
import plotly.graph_objects as go
import pandas as pd
import numpy as np


def render_attribution_section(radar, radar_state, df_input, is_mobile=False):
    with ui.card().classes('w-full p-0 rounded-xl shadow-sm border border-slate-300 bg-white overflow-hidden'):
        duration = radar_state.get('duration', 1)
        attribution = radar.analyze_flow_attribution(df_input, days=duration)
        all_quadrants = [
            {"key": "joint_push", "title": "合力拉升", "desc": "主力强流入 + 大涨", "theme": "rose", "icon": "rocket_launch"},
            {"key": "pure_main_force", "title": "纯主力拉升", "desc": "主力强流入 + 涨幅温和", "theme": "indigo", "icon": "trending_up"},
            {"key": "accumulation", "title": "主力吸筹", "desc": "主力强流入 + 横盘震荡", "theme": "amber", "icon": "workspace_premium"},
            {"key": "shakeout", "title": "主力洗盘", "desc": "主力强流入 + 下跌", "theme": "violet", "icon": "waves"},
            {"key": "panic_selling", "title": "合力砸盘", "desc": "主力强流出 + 大跌", "theme": "emerald", "icon": "landslide"},
            {"key": "inst_exit", "title": "主力出货", "desc": "主力强流出 + 下跌", "theme": "teal", "icon": "logout"},
            {"key": "bull_trap", "title": "主力诱多", "desc": "主力强流出 + 上涨", "theme": "orange", "icon": "warning"},
            {"key": "retail_crowd", "title": "散户扎堆", "desc": "无强主力 + 大涨", "theme": "lime", "icon": "groups"},
        ]
        active_quadrants = [q for q in all_quadrants if len(attribution.get(q['key'], [])) > 0]
        total_sector_count = sum(len(attribution.get(q['key'], [])) for q in all_quadrants)
        switch_state = {'mode': 'active', 'page': 0}

        with ui.column().classes('w-full bg-white border-b border-slate-200'):
            with ui.row().classes('w-full px-4 py-2.5 items-center justify-between'):
                with ui.row().classes('items-center gap-2'):
                    with ui.element('div').classes('w-8 h-8 rounded-md bg-indigo-50 border border-indigo-100 flex items-center justify-center'):
                        ui.icon('query_stats', color='indigo').classes('text-base')
                    with ui.column().classes('gap-0'):
                        ui.label('主力/散户流向归因分析').classes('font-black text-slate-800 text-sm md:text-base leading-tight')
                        ui.label('ATTRIBUTION MATRIX').classes('font-bold text-slate-400 text-[10px] tracking-[0.14em] leading-tight')
                with ui.row().classes('items-center gap-2'):
                    ui.label(f'{duration}D').classes('text-[10px] font-black text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-full px-2 py-0.5')
                    ui.label(f'活跃 {len(active_quadrants)}').classes('text-[10px] font-black text-cyan-700 bg-cyan-50 border border-cyan-200 rounded-full px-2 py-0.5')
                    with ui.icon('help_outline', color='gray-500').classes('text-sm cursor-help hover:text-indigo-500 transition-colors'):
                        ui.tooltip('资金归因分析 (阈值: 强度±2%, 涨跌±3%):\n[强流入] 合力拉升(大涨)、纯主力(温和)、吸筹(横盘)、洗盘(下跌)\n[强流出] 砸盘(大跌)、出货(阴跌)、诱多(上涨)\n[弱平衡] 散户扎堆(无强主力参与的大涨)').classes('text-xs whitespace-pre-line bg-gray-900 text-white p-2 rounded shadow-lg')

            with ui.row().classes('w-full px-4 py-1.5 border-t border-slate-100 items-center justify-between bg-slate-50/70'):
                with ui.row().classes('items-center gap-1.5'):
                    btn_active = ui.button('活跃象限', on_click=lambda: set_mode('active')).props('dense flat size=sm').classes('text-[11px] font-bold rounded px-2 py-0.5')
                    btn_all = ui.button('全部象限', on_click=lambda: set_mode('all')).props('dense flat size=sm').classes('text-[11px] font-bold rounded px-2 py-0.5')
                    ui.label(f'覆盖 {total_sector_count}').classes('text-[10px] text-slate-500 font-bold ml-1')
                with ui.row().classes('items-center gap-1'):
                    btn_prev = ui.button(icon='chevron_left', on_click=lambda: prev_page()).props('flat dense round size=sm color=grey-7')
                    page_label = ui.label('1 / 1').classes('text-[11px] text-slate-500 font-black min-w-[48px] text-center')
                    btn_next = ui.button(icon='chevron_right', on_click=lambda: next_page()).props('flat dense round size=sm color=grey-7')

        quick_tabs = ui.row().classes('w-full px-3 py-1 gap-1.5 border-b border-slate-100 bg-white flex-wrap')
        grid_container = ui.column().classes('w-full')

        def get_source_quadrants():
            return active_quadrants if switch_state['mode'] == 'active' else all_quadrants

        def goto_quadrant(q_key):
            switch_state['mode'] = 'all'
            source = all_quadrants
            page_size = 1 if is_mobile else 4
            idx = next((i for i, q in enumerate(source) if q['key'] == q_key), 0)
            switch_state['page'] = idx // page_size
            render_grid()

        def set_mode(mode):
            switch_state['mode'] = mode
            switch_state['page'] = 0
            render_grid()

        def prev_page():
            if switch_state['page'] > 0:
                switch_state['page'] -= 1
                render_grid()

        def next_page():
            source = get_source_quadrants()
            page_size = 1 if is_mobile else 4
            total_pages = max(1, int(np.ceil(len(source) / page_size)))
            if switch_state['page'] < total_pages - 1:
                switch_state['page'] += 1
                render_grid()

        def render_quick_tabs():
            quick_tabs.clear()
            with quick_tabs:
                for q in all_quadrants:
                    count = len(attribution.get(q['key'], []))
                    color = q['theme']
                    btn_cls = f'text-[10px] font-bold rounded border px-2 py-0.5 text-{color}-700 border-{color}-200 bg-{color}-50/60'
                    if count == 0:
                        btn_cls = 'text-[10px] font-bold rounded border px-2 py-0.5 text-slate-400 border-slate-200 bg-slate-50'
                    ui.button(f'{q["title"]} {count}', on_click=lambda k=q['key']: goto_quadrant(k)).props('dense flat size=sm').classes(btn_cls)

        def render_grid():
            source = get_source_quadrants()
            page_size = 1 if is_mobile else 4
            total_pages = max(1, int(np.ceil(len(source) / page_size)))
            switch_state['page'] = max(0, min(switch_state['page'], total_pages - 1))
            page_start = switch_state['page'] * page_size
            display_quadrants = source[page_start:page_start + page_size]

            page_label.set_text(f'{switch_state["page"] + 1} / {total_pages}')
            btn_prev.set_visibility(total_pages > 1)
            btn_next.set_visibility(total_pages > 1)
            btn_active.classes(replace='text-[11px] font-bold rounded px-2 py-0.5 text-white bg-indigo-600' if switch_state['mode'] == 'active' else 'text-[11px] font-bold rounded px-2 py-0.5 text-slate-600 bg-white border border-slate-200')
            btn_all.classes(replace='text-[11px] font-bold rounded px-2 py-0.5 text-white bg-indigo-600' if switch_state['mode'] == 'all' else 'text-[11px] font-bold rounded px-2 py-0.5 text-slate-600 bg-white border border-slate-200')

            grid_container.clear()
            with grid_container:
                if not display_quadrants:
                    with ui.column().classes('w-full py-10 items-center justify-center text-slate-500 gap-3 bg-slate-50'):
                        ui.icon('saved_search', size='3rem', color='gray-300')
                        ui.label('当前无显著资金流向特征板块').classes('text-sm font-medium')
                    return

                n_cols = len(display_quadrants)
                col_map = {1: 'grid-cols-1', 2: 'grid-cols-2', 3: 'grid-cols-3', 4: 'grid-cols-4'}
                cols_class = col_map.get(n_cols, 'grid-cols-4')
                with ui.grid().classes(f'w-full gap-2 p-2 bg-white border-y border-slate-200 {cols_class if not is_mobile else "grid-cols-1"}'):
                    for q in display_quadrants:
                        items = attribution.get(q['key'], [])
                        display_items = items[:8] if items else []
                        theme = q['theme']
                        avg_strength = np.mean([i['strength'] for i in items]) if items else 0
                        flow_sum = sum(i['net_flow'] for i in items) if items else 0

                        with ui.column().classes('w-full p-0 h-full bg-white min-h-[220px] rounded-lg border border-slate-300 overflow-hidden relative'):
                            ui.element('div').classes(f'absolute left-0 top-0 bottom-0 w-[2px] bg-{theme}-200')
                            with ui.row().classes(f'w-full px-3 py-2 bg-{theme}-50/70 border-b border-{theme}-100 items-center justify-between'):
                                with ui.row().classes('items-center gap-2'):
                                    with ui.element('div').classes(f'w-7 h-7 rounded-md bg-white border border-{theme}-200 flex items-center justify-center'):
                                        ui.icon(q['icon'], color=theme).classes('text-base')
                                    with ui.column().classes('gap-0'):
                                        ui.label(q['title']).classes(f'text-base font-black text-{theme}-700 leading-tight')
                                        ui.label(q['desc']).classes(f'text-[10px] font-bold text-{theme}-500 leading-tight')
                                ui.label(f'{len(items)}').classes(f'text-[11px] font-black px-2 py-0.5 rounded border border-{theme}-200 text-{theme}-700 bg-white')

                            with ui.row().classes('w-full px-3 py-1 bg-white border-b border-slate-100 items-center justify-between text-[10px]'):
                                flow_cls = 'text-rose-600' if flow_sum > 0 else 'text-emerald-600'
                                density_cls = f'text-{theme}-600' if avg_strength >= 0 else 'text-slate-500'
                                ui.label(f'净流合计 {flow_sum:+.1f} 亿').classes(f'font-bold {flow_cls}')
                                ui.label(f'密度 {avg_strength:+.1f}').classes(f'font-bold {density_cls}')

                            with ui.row().classes('w-full px-3 py-1.5 bg-slate-50 border-b border-slate-100 text-[10px] text-slate-500 font-bold items-center uppercase'):
                                ui.label('板块').classes('flex-1 text-left')
                                with ui.row().classes('items-center gap-2 justify-end'):
                                    ui.label('涨跌(%)').classes('w-12 text-right')
                                    ui.label('净入(亿)').classes('w-14 text-right')
                                    ui.label('强度').classes('w-10 text-center')

                            with ui.column().classes('w-full p-0 gap-0'):
                                if not display_items:
                                    with ui.column().classes('w-full items-center justify-center gap-3 py-8'):
                                        ui.icon('inbox', size='2.4rem', color='gray-300')
                                        ui.label('暂无板块').classes('text-xs font-medium text-slate-400')
                                else:
                                    for i, item in enumerate(display_items):
                                        bg_row = 'bg-white' if i % 2 == 0 else 'bg-slate-100/70'
                                        with ui.row().classes(f'w-full items-center justify-between px-3 py-1.5 border-b border-slate-100 last:border-0 hover:bg-indigo-50/30 transition-colors {bg_row}'):
                                            ui.label(item['name']).classes('text-xs font-bold text-slate-800 flex-1 truncate pr-2')
                                            with ui.row().classes('items-center gap-2 justify-end'):
                                                c_val = item['change']
                                                c_color = 'text-rose-600' if c_val > 0 else 'text-emerald-600'
                                                ui.label(f'{c_val:+.1f}%').classes(f'text-xs font-mono font-black {c_color} w-12 text-right')
                                                n_val = item['net_flow']
                                                n_color = 'text-rose-600' if n_val > 0 else 'text-emerald-600'
                                                flow_str = f'{n_val:.0f}' if abs(n_val) >= 10 else f'{n_val:.1f}'
                                                ui.label(flow_str).classes(f'text-xs font-mono font-semibold {n_color} w-14 text-right')
                                                s_val = item['strength']
                                                s_bg = f'bg-{theme}-50 text-{theme}-700 border border-{theme}-200' if s_val > 0 else 'bg-slate-50 text-slate-700 border border-slate-200'
                                                ui.label(f'{s_val:.0f}').classes(f'text-[10px] font-mono font-black {s_bg} w-10 text-center rounded')
                                    if len(items) > 8:
                                        with ui.row().classes('w-full justify-center py-1.5 bg-slate-50 border-t border-slate-100 cursor-pointer hover:bg-indigo-50 transition-colors'):
                                            ui.label(f'查看更多 ({len(items)-8})...').classes('text-[10px] font-bold text-slate-500 hover:text-indigo-600')

        render_quick_tabs()
        render_grid()


def render_multi_day_view(radar, radar_state, df, dates, plot_func, is_mobile=False, date_value=''):
    df['资金强度'] = df.apply(lambda x: x['净流入'] / x['总成交额'] if x['总成交额'] > 0 else 0, axis=1)
    df['abs_flow'] = df['净流入'].abs()
    df_top_scatter = df.sort_values('abs_flow', ascending=False)
    total_net = df['净流入'].sum()
    pos_df = df[df['净流入'] > 0]
    neg_df = df[df['净流入'] < 0]
    pos_ratio = (len(pos_df) / len(df) * 100) if not df.empty else 0
    top_turnover_df = df.sort_values('总成交额', ascending=False).head(20)
    if '涨跌幅' in df.columns:
        avg_change = top_turnover_df['涨跌幅'].mean() if not top_turnover_df.empty else 0.0
    else:
        avg_change = 0.0
    chg_color = "rose-500" if avg_change > 0 else "emerald-500"
    top_inflow_list = df.sort_values('净流入', ascending=False).head(5)
    max_inflow = top_inflow_list.iloc[0] if not top_inflow_list.empty else None
    max_strength = df.sort_values('资金强度', ascending=False).iloc[0] if not df.empty else None

    if total_net > 0:
        status_color = "rose"
        insight_title = "多头主导"
        insight_sub = "BULLISH TREND"
        bg_gradient = "bg-gradient-to-br from-rose-50 to-white"
        border_color = "border-rose-100"
    else:
        status_color = "emerald"
        insight_title = "空头抑制"
        insight_sub = "BEARISH TREND"
        bg_gradient = "bg-gradient-to-br from-emerald-50 to-white"
        border_color = "border-emerald-100"

    with ui.grid(columns=3 if not is_mobile else 1).classes('w-full gap-4'):
        with ui.card().classes(f'w-full p-4 rounded-xl shadow-sm border {border_color} {bg_gradient} relative overflow-hidden group hover:shadow-md transition-all duration-500'):
            ui.element('div').classes('absolute -right-8 -top-8 w-32 h-32 rounded-full bg-white opacity-20 group-hover:scale-125 transition-transform duration-700')
            with ui.row().classes('items-center gap-2 mb-2'):
                ui.icon('hub', color=status_color).classes('text-lg animate-pulse')
                ui.label('智能态势洞察').classes('text-xs font-black hide-scrollbar tracking-widest text-gray-400')
                with ui.icon('help_outline', color='gray-400').classes('text-xs cursor-help'):
                    ui.tooltip('基于多空资金流向、市场参与度和板块分化程度的综合市场状态评估。').classes('text-xs')
            with ui.column().classes('gap-0'):
                ui.label(insight_title).classes(f'text-3xl md:text-4xl font-black {f"text-{status_color}-600"} tracking-tight')
                ui.label(insight_sub).classes('text-xs font-bold hide-scrollbar text-gray-400 tracking-widest -mt-1')
            flow_val_str = f"{abs(total_net):.1f} 亿"
            flow_dir = "净流入" if total_net > 0 else "净流出"
            with ui.column().classes('mt-4 gap-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.element('div').classes(f'w-1.5 h-1.5 rounded-full {f"bg-{status_color}-500"}')
                    ui.label(f'多空共识：{flow_dir} {flow_val_str}').classes('text-sm font-bold text-gray-700')
                phase_text = "极度分化" if pos_ratio < 30 else ("普盘活跃" if pos_ratio > 60 else "结构性轮动")
                with ui.row().classes('items-center gap-2'):
                    ui.element('div').classes(f'w-1.5 h-1.5 rounded-full {f"bg-{status_color}-500"}')
                    ui.label(f'演化阶段：{phase_text} ({pos_ratio:.0f}% 板块参与)').classes('text-sm font-bold text-gray-700')
            ui.label('主力主要在象限右侧“高强度区”进行火力压制。').classes('text-[11px] text-gray-400 mt-4 border-t border-gray-100 pt-3 italic')

        with ui.card().classes('w-full p-4 rounded-xl shadow-sm border border-gray-100 bg-white hover:border-indigo-200 transition-colors duration-300'):
            with ui.row().classes('items-center gap-2 mb-4'):
                ui.icon('sensors', color='indigo').classes('text-lg')
                ui.label('市场进攻脉搏').classes('text-xs font-black tracking-widest text-gray-400')
            with ui.row().classes('w-full items-end justify-between'):
                with ui.column().classes('gap-0'):
                    ui.label(f'{avg_change:+.2f}%').classes(f'text-4xl font-black text-{chg_color}')
                    with ui.row().classes('items-center gap-1'):
                        ui.label('核心板块表现').classes('text-xs font-bold text-gray-400')
                        with ui.icon('help_outline', color='gray-400').classes('text-xs cursor-help'):
                            ui.tooltip('统计成交额最高的前20个核心板块的平均涨跌幅，反映市场主流资金的赚钱效应。').classes('text-xs')
                with ui.column().classes('items-end gap-1'):
                    total_cnt = len(df)
                    with ui.row().classes('items-center gap-2'):
                        ui.label(f'{len(pos_df)}').classes('text-xs font-bold text-rose-500')
                        ui.element('div').classes(f'h-1 bg-rose-500 rounded-full').style(f'width: {(len(pos_df)/total_cnt)*40}px')
                    with ui.row().classes('items-center gap-2'):
                        ui.label(f'{len(neg_df)}').classes('text-xs font-bold text-emerald-500')
                        ui.element('div').classes(f'h-1 bg-emerald-500 rounded-full').style(f'width: {(len(neg_df)/total_cnt)*40}px')
            with ui.grid(columns=2).classes('w-full mt-6 pt-4 border-t border-gray-50 gap-4'):
                with ui.column().classes('gap-0'):
                    ui.label('统计规模').classes('text-xs text-gray-400 font-bold')
                    ui.label(f'{len(df)} 个板块').classes('text-sm font-black text-gray-700')
                with ui.column().classes('gap-0 items-end'):
                    ui.label('总成交量').classes('text-xs text-gray-400 font-bold')
                    ui.label(f'{(df["总成交额"].sum()/10000):.1f} 万亿').classes('text-sm font-black text-gray-700')

        with ui.card().classes('w-full p-4 rounded-xl shadow-sm border border-gray-100 bg-white'):
            with ui.row().classes('items-center gap-2 mb-4'):
                ui.icon('military_tech', color='amber').classes('text-lg')
                ui.label('领跑板块榜单').classes('text-xs font-black tracking-widest text-gray-400')
            if max_inflow is not None:
                with ui.row().classes('w-full items-start justify-between'):
                    with ui.column().classes('gap-0'):
                        ui.label(max_inflow["名称"]).classes('text-2xl font-black text-gray-900')
                        ui.label(f'累计流入: {max_inflow["净流入"]:.1f} 亿').classes('text-xs font-bold text-rose-500 tracking-tight')
                    ui.icon('workspace_premium', color='amber-400').classes('text-3xl')
                with ui.column().classes('w-full mt-3 space-y-1'):
                    for i, row in enumerate(top_inflow_list.iloc[1:3].itertuples()):
                        with ui.row().classes('w-full justify-between items-center bg-gray-50/50 px-2 py-1.5 rounded-lg'):
                            ui.label(f'NO.{i+2} {row.名称}').classes('text-xs font-bold text-gray-600')
                            ui.label(f'{row.净流入:+.1f} 亿').classes('text-xs font-mono text-gray-400')
                if max_strength is not None:
                    with ui.row().classes('w-full items-center gap-2 mt-3 pt-3 border-t border-dashed border-gray-100'):
                        with ui.row().classes('items-center gap-1'):
                            ui.label('效率标杆:').classes('text-xs font-black text-gray-400')
                            with ui.icon('help_outline', color='gray-300').classes('text-[10px] cursor-help'):
                                ui.tooltip('指单位成交额吸纳净流入最多的板块，代表该板块资金承接力最强。').classes('text-xs')
                        ui.label(max_strength["名称"]).classes('text-sm font-bold text-indigo-500')
                        ui.label(f'强度 {max_strength["资金强度"]*100:.1f}%').classes('text-xs bg-indigo-50 text-indigo-400 px-2 py-0.5 rounded font-bold')
            else:
                ui.label('等待数据同步...').classes('text-gray-300 text-sm italic py-8 text-center w-full')

    render_attribution_section(radar, radar_state, df, is_mobile)

    with ui.column().classes('w-full gap-6'):
        with ui.card().classes('w-full border border-gray-200 rounded-xl shadow-sm bg-white p-4 flex flex-col gap-0'):
            with ui.row().classes('w-full justify-between items-center mb-2 pb-2 border-b border-gray-200'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('bubble_chart', color='indigo').classes('text-xl')
                    ui.label('资金进攻象限 (气泡大小=成交额)').classes('text-base font-bold text-gray-800')

            with ui.element('div').classes('w-full h-[500px]'):
                fig_scatter = go.Figure()
                hover_text = [
                    f"板块: {row.名称}<br>净流入: {row.净流入:.1f}亿<br>强度: {row.资金强度*100:.1f}%<br>成交: {row.总成交额:.1f}亿<br>活跃: {row.活跃天数}天"
                    for row in df_top_scatter.itertuples()
                ]
                colors = ['#ef4444' if row.净流入 > 0 else '#10b981' for row in df_top_scatter.itertuples()]
                size_ref = df_top_scatter['总成交额'].max() if not df_top_scatter.empty else 1
                sizes = (np.sqrt(df_top_scatter['总成交额']) / np.sqrt(size_ref)) * 40 + 10
                fig_scatter.add_trace(go.Scatter(
                    x=df_top_scatter['净流入'],
                    y=df_top_scatter['资金强度'] * 100,
                    mode='markers+text',
                    text=df_top_scatter['名称'],
                    textposition="top center",
                    textfont=dict(size=11, color='rgba(0,0,0,0.7)', family="sans-serif"),
                    marker=dict(size=sizes, sizemode='diameter', color=colors, line=dict(width=1, color='white'), opacity=0.85),
                    hoverinfo='text',
                    hovertext=hover_text,
                ))
                fig_scatter.add_vline(x=0, line_width=1, line_dash="solid", line_color="rgba(0,0,0,0.05)")
                fig_scatter.add_hline(y=0, line_width=1, line_dash="solid", line_color="rgba(0,0,0,0.05)")
                fig_scatter.add_annotation(dict(x=1, y=1, xref='x domain', yref='y domain', text="🔥 主力抢筹", showarrow=False, font=dict(color='rgba(239, 68, 68, 0.15)', size=24, weight='bold'), xanchor='right', yanchor='top'))
                fig_scatter.add_annotation(dict(x=0, y=0, xref='x domain', yref='y domain', text="❄️ 减仓出货", showarrow=False, font=dict(color='rgba(16, 185, 129, 0.15)', size=24, weight='bold'), xanchor='left', yanchor='bottom'))
                fig_scatter.update_layout(
                    margin=dict(l=40, r=40, t=30, b=40),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(252, 252, 252, 1)',
                    xaxis_title='累积净流入 (亿)',
                    yaxis_title='资金强度 (%)<br><sup>计算公式: (净流入 ÷ 成交额) × 100%</sup>',
                    xaxis=dict(zeroline=False, gridcolor='#F3F4F6'),
                    yaxis=dict(zeroline=False, gridcolor='#F3F4F6'),
                    showlegend=False,
                )
                plot_func(fig_scatter).classes('w-full h-full')

        with ui.card().classes('w-full border border-gray-200 rounded-xl shadow-sm bg-white p-4 flex flex-col gap-0'):
            with ui.row().classes('w-full justify-between items-center mb-2 pb-2 border-b border-gray-200'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('analytics', color='indigo').classes('text-xl')
                    ui.label('资金流向与板块表现 (Top 20 Divergence Analysis)').classes('text-base font-bold text-gray-800')
                with ui.row().classes('items-center gap-4 text-xs text-gray-500 hidden md:flex'):
                    with ui.row().classes('items-center gap-1'):
                        ui.element('div').classes('w-3 h-3 bg-red-500 rounded-sm opacity-60')
                        ui.label('净流入 (Bar)')
                    with ui.row().classes('items-center gap-1'):
                        ui.element('div').classes('w-3 h-3 bg-emerald-500 rounded-sm opacity-60')
                        ui.label('净流出 (Bar)')
                    with ui.row().classes('items-center gap-1'):
                        ui.icon('diamond', size='xs').classes('text-gray-600')
                        ui.label('平均涨跌 (Point)')

            if '涨跌幅' not in df.columns:
                df['涨跌幅'] = 0.0
            df_in = df.sort_values('净流入', ascending=False).head(10)
            df_out = df.sort_values('净流入', ascending=True).head(10)
            df_combo = pd.concat([df_in, df_out]).drop_duplicates(subset=['名称']).sort_values('净流入', ascending=True)
            neg_count = len(df_combo[df_combo['净流入'] < 0])
            split_idx = neg_count - 0.5

            with ui.element('div').classes('w-full h-[500px]'):
                fig_combo = go.Figure()
                colors_bar = ['#ef4444' if x > 0 else '#10b981' for x in df_combo['净流入']]
                fig_combo.add_trace(go.Bar(
                    y=df_combo['名称'],
                    x=df_combo['净流入'],
                    orientation='h',
                    name='资金净流入',
                    marker_color=colors_bar,
                    opacity=0.6,
                    text=[f"{x:.1f}" for x in df_combo['净流入']],
                    textposition='outside',
                    textfont=dict(size=12, color='black', weight='bold'),
                    cliponaxis=False,
                    hoverinfo='x+y',
                ))
                colors_dot = ['#b91c1c' if x > 0 else '#047857' for x in df_combo['涨跌幅']]
                fig_combo.add_trace(go.Scatter(
                    y=df_combo['名称'],
                    x=df_combo['涨跌幅'],
                    xaxis='x2',
                    mode='markers',
                    name='平均涨跌幅',
                    marker=dict(color=colors_dot, size=10, symbol='diamond', line=dict(width=1, color='white')),
                    hovertemplate='%{y}<br>平均涨跌: %{x:.2f}%<extra></extra>',
                ))
                if 0 < neg_count < len(df_combo):
                    fig_combo.add_shape(type="line", x0=0, x1=1, xref="paper", y0=split_idx, y1=split_idx, yref="y", line=dict(color="rgba(0,0,0,0.2)", width=1, dash="longdash"))
                    fig_combo.add_annotation(x=1, y=len(df_combo)-1, xref="paper", yref="y", text="资金净流入 Top", showarrow=False, font=dict(color="#ef4444", size=12, weight="bold"), xanchor='right', yanchor='top', bgcolor="rgba(255,255,255,0.7)")
                    fig_combo.add_annotation(x=1, y=0, xref="paper", yref="y", text="资金净流出 Top", showarrow=False, font=dict(color="#10b981", size=12, weight="bold"), xanchor='right', yanchor='bottom', bgcolor="rgba(255,255,255,0.7)")
                fig_combo.update_layout(
                    margin=dict(l=20, r=20, t=40, b=20),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    barmode='overlay',
                    xaxis=dict(title=dict(text='资金净流入 (亿)', standoff=0, font=dict(size=14)), tickfont=dict(size=12), showgrid=True, gridcolor='#f3f4f6', zeroline=True, zerolinewidth=1, zerolinecolor='gray'),
                    xaxis2=dict(title=dict(text='平均涨跌幅 (%)', font=dict(color='#6b7280', size=13)), tickfont=dict(color='#6b7280', size=12), overlaying='x', side='top', showgrid=False, zeroline=False),
                    yaxis=dict(showgrid=False, tickfont=dict(size=13, color='#374151', weight='bold')),
                    showlegend=False,
                    bargap=0.3,
                )
                plot_func(fig_combo).classes('w-full h-full')

        with ui.card().classes('w-full border border-gray-200 rounded-xl shadow-sm bg-white p-0 flex flex-col gap-0'):
            with ui.row().classes('w-full justify-between items-center p-4 border-b border-gray-200'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('grid_view', color='indigo').classes('text-xl')
                    ui.label('资金流向全景透视图 (Money Flow Heatmap)').classes('text-base font-bold text-gray-800')
            df_tree = df.copy()
            df_tree['abs_turnover'] = df_tree['总成交额']
            offensive_list, defensive_list = radar.get_offensive_defensive_list()

            def get_category(name):
                if name in offensive_list:
                    return "🚀 进攻阵营"
                if name in defensive_list:
                    return "🛡️ 防守阵营"
                return "⚖️ 平衡/其他"

            df_tree['category'] = df_tree['名称'].apply(get_category)
            root_id = "全市场板块资金概览"
            cats = df_tree['category'].unique().tolist()
            ids = df_tree['名称'].tolist() + cats + [root_id]
            labels = df_tree['名称'].tolist() + cats + [root_id]
            parents = df_tree['category'].tolist() + [root_id]*len(cats) + [""]
            values = df_tree['abs_turnover'].tolist() + [0]*len(cats) + [0]
            colors = df_tree['净流入'].tolist() + [0]*len(cats) + [0]
            texts_leaves = df_tree['净流入'].apply(lambda x: f"{x:+.1f}亿").tolist()
            custom_leaves = df_tree['涨跌幅'].tolist()
            texts_branches = [""] * (len(cats) + 1)
            custom_branches = [0] * (len(cats) + 1)
            all_text = texts_leaves + texts_branches
            all_custom = custom_leaves + custom_branches

            with ui.element('div').classes('w-full h-[800px] p-2'):
                fig_tree = go.Figure(go.Treemap(
                    ids=ids,
                    labels=labels,
                    parents=parents,
                    values=values,
                    marker=dict(colors=colors, colorscale=[[0.0, 'rgb(34, 197, 94)'], [0.5, 'rgb(255, 255, 255)'], [1.0, 'rgb(239, 68, 68)']], cmid=0, showscale=False),
                    text=all_text,
                    texttemplate="<b>%{label}</b><br>%{text}",
                    hovertemplate='<b>%{label}</b><br>成交额: %{value:.1f}亿<br>净流入: %{text}<br>涨跌幅: %{customdata:.2f}%<extra></extra>',
                    customdata=all_custom,
                    textposition="middle center",
                    textfont=dict(size=14, color='black'),
                ))
                fig_tree.update_layout(margin=dict(t=10, l=10, r=10, b=10), uniformtext=dict(minsize=10, mode='hide'))
                plot_func(fig_tree).classes('w-full h-full')

            with ui.expansion('查看详细数据报表 (Data Table)', icon='table_chart').classes('w-full border-t border-gray-100 bg-gray-50'):
                with ui.column().classes('w-full p-4 gap-4'):
                    def download_csv():
                        csv_str = df.to_csv(index=False)
                        ui.download(csv_str.encode('utf-8-sig'), filename=f'fund_flow_{date_value}_{radar_state["duration"]}days.csv')

                    with ui.row().classes('w-full justify-end'):
                        ui.button('下载 CSV 数据', icon='download', on_click=download_csv).props('outline rounded color=grey-8 size=sm')

                    df_table = df.sort_values('净流入', ascending=False)
                    rows = []
                    for i, row in enumerate(df_table.itertuples(), 1):
                        intensity = row.资金强度 * 100
                        rows.append({
                            'rank': i,
                            'name': row.名称,
                            'flow': f'{row.净流入:.2f}',
                            'turnover': f'{row.总成交额:.2f}',
                            'pct': f'{row.涨跌幅:.2f}%',
                            'intensity': f'{intensity:.2f}%',
                            'days': row.活跃天数,
                        })
                    cols = [
                        {'name': 'rank', 'label': '排名', 'field': 'rank', 'sortable': True, 'align': 'center'},
                        {'name': 'name', 'label': '板块名称', 'field': 'name', 'sortable': True, 'align': 'left'},
                        {'name': 'flow', 'label': '累计净流入 (亿)', 'field': 'flow', 'sortable': True, 'align': 'right'},
                        {'name': 'pct', 'label': '平均涨跌幅', 'field': 'pct', 'sortable': True, 'align': 'right'},
                        {'name': 'turnover', 'label': '累计成交额 (亿)', 'field': 'turnover', 'sortable': True, 'align': 'right'},
                        {'name': 'intensity', 'label': '资金强度', 'field': 'intensity', 'sortable': True, 'align': 'right'},
                        {'name': 'days', 'label': '统计天数', 'field': 'days', 'sortable': True, 'align': 'center'},
                    ]
                    ui.table(columns=cols, rows=rows, pagination=10).classes('w-full bg-white shadow-sm border border-gray-200')
