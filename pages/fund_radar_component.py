from nicegui import ui, app
import plotly.graph_objects as go
from utils.fund_radar import FundRadar
from utils.sector_grid_logic import get_sector_grid_data
from utils.sector_analysis import sector_analyzer
import pandas as pd
import numpy as np
import datetime
import asyncio
import os

def render_fund_radar_panel(plotly_renderer=None, is_mobile=False):
    """
    Render the Fund Radar Panel with Daily Cache Mechanism.
    """
    radar = FundRadar()
    
    # Default state for the component
    radar_state = {'duration': 1}
    
    # Ensure Today is based on China Time (UTC+8)
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    cn_now = utc_now + datetime.timedelta(hours=8)
    today_str = cn_now.strftime('%Y-%m-%d')

    # Define 2026 Trading Days Logic (复用 FundRadar 的节假日表)
    def get_2026_trading_days():
        start_date = datetime.date(2026, 1, 1)
        end_date = datetime.date(2026, 12, 31)
        valid_days = set() # Use set for O(1) lookup
        valid_days_list = [] # For return
        
        curr = start_date
        while curr <= end_date:
            # 非周末 + 非节假日 = 交易日
            if curr.weekday() < 5 and not FundRadar.is_holiday(curr):
                date_str = curr.strftime('%Y/%m/%d')
                valid_days.add(date_str)
                valid_days_list.append(date_str)
            curr += datetime.timedelta(days=1)
        return valid_days, valid_days_list

    trading_days_set, trading_days_2026 = get_2026_trading_days()

    # Determine default selected date (find latest valid trading day)
    check_date = cn_now.date()
    # Limit check loop to avoid infinite loops, check max 30 days back
    for _ in range(30):
        if check_date.strftime('%Y/%m/%d') in trading_days_set:
            break
        check_date -= datetime.timedelta(days=1)
    
    today_str = check_date.strftime('%Y-%m-%d')
    # Update cn_now to reflect the selected date roughly (though cn_now usage below might just be for 'is today' checks)
    # Actually logic below uses today_str for initial state

    # Use provided renderer or fallback to ui.plotly
    plot_func = plotly_renderer if plotly_renderer else ui.plotly

    # Main Container
    # Modified: px-0 on mobile (was px-2), gap-4 on mobile
    with ui.column().classes('w-full px-0 md:px-6 py-0 gap-4 md:gap-6 functionality-container'):

        # 1. Header & Controls Section
        with ui.card().classes('w-full rounded-xl shadow-sm border border-gray-200 bg-white p-3 md:p-4'):
             with ui.row().classes('w-full items-center justify-between wrap gap-y-3 gap-x-4'):
                # Left: Title & Duration Toggle
                with ui.row().classes('items-center gap-3'):
                    with ui.element('div').classes('p-2 bg-indigo-50 rounded-lg'):
                        ui.icon('radar', color='indigo').classes('text-2xl')
                    with ui.column().classes('gap-0'):
                        with ui.row().classes('items-center gap-3'):
                            ui.label('主力资金雷达').classes('text-lg md:text-xl font-bold text-gray-800 tracking-tight')
                            # Duration Toggle: Redesigned as segmented buttons (pill style)
                            duration_container = ui.row().classes('bg-gray-100 rounded-lg p-1 gap-1 items-center')
                        
                        with ui.row().classes('items-center gap-2'):
                            ui.label('Sector Heat Radar (Multi-Day)').classes('text-xs text-gray-400 font-medium hidden md:block')
                            last_update_label = ui.label('').classes('text-[10px] text-indigo-400 bg-indigo-50 px-1.5 rounded-full font-mono')

                # Right: Controls (Date Picker & Refresh)
                with ui.row().classes('items-center gap-2 flex-wrap justify-end flex-1'):

                    # Date Picker Logic
                    date_input = ui.input('选择日期', value=today_str).props('outlined dense bg-white readonly').classes('w-32 md:w-40 text-sm')
                    with date_input.add_slot('append'):
                        ui.icon('event').classes('cursor-pointer') \
                            .on('click', lambda: date_menu.open())
                        with ui.menu() as date_menu:
                            ui.date(value=today_str, on_change=lambda e: (date_input.set_value(e.value), date_menu.close())) \
                                .props(f'mask="YYYY-MM-DD" :options="{trading_days_2026}"')

                    refresh_btn = ui.button('强制刷新', icon='refresh', on_click=lambda: update_dashboard(date_input.value, force=True)) \
                        .props('flat color=red dense').classes('font-bold bg-red-50 hover:bg-red-100 text-xs md:text-sm')

                    # Visibility Logic
                    def check_refresh_visibility():
                        if refresh_btn.is_deleted: return
                        # Allow refresh if it is "today" OR the latest available trading day
                        # A simple logic is: allow refresh if date is today (logic might need adjust for holidays)
                        # Actually original logic: is_today = (date_input.value == today_str) 
                        # Now today_str is the 'latest trading day'. 
                        # But wait, 'today_str' is just the initial value. 
                        # We want to allow refresh if the selected date IS essentially the real today (or last trading day).
                        # Let's keep it simple: enable refresh button if date equals our auto-calculated 'today_str'
                        # which is the "latest trading day relative to real time".
                        
                        is_current_target = (date_input.value == today_str)
                        refresh_btn.set_visibility(is_current_target)
                    
                    # Update Duration Options - now always show multi-day options
                    # since THS direct API doesn't require daily cache accumulation
                    def update_duration_options(date_val):
                        if duration_container.is_deleted: return
                        
                        # 判断是否为历史回溯模式（非最新交易日）
                        is_history_mode = (date_val != today_str)
                        
                        if is_history_mode:
                            # 历史回溯模式：隐藏多日选项，强制使用单日
                            possible_options = [(1, '1天')]
                            # 如果当前处于多日模式，强制切回单日（注意：这里不直接触发 set_duration 避免死循环，
                            # 而是修改 state，UI 刷新由后续逻辑保证，或者在切换日期时本就会重置视图）
                            if radar_state['duration'] != 1:
                                radar_state['duration'] = 1
                        else:
                            # 最新交易日：显示所有选项
                            possible_options = [
                                (1, '1天'),
                                (3, '3天'),
                                (5, '5天'),
                                (10, '10天'),
                                (20, '20天'),
                            ]
                        
                        options = {d: label for d, label in possible_options}
                        
                        if radar_state['duration'] not in options:
                            radar_state['duration'] = 1
                            
                        duration_container.clear()
                        # 仅在有多个选项时才渲染（或者始终渲染1天以保持布局，但根据需求这里只显示可用的）
                        # 如果是历史模式，为了提示用户，可以显示一个静态标签或者仅仅显示“1天”按钮
                        with duration_container:
                            if is_history_mode:
                                # 历史模式下，显示一个提示或置灰的单日按钮
                                ui.label('历史快照').classes('text-xs text-gray-400 font-bold px-2')
                            else:
                                for d, lbl in options.items():
                                    is_active = (radar_state['duration'] == d)
                                    # Capture d in closure
                                    ui.button(lbl, on_click=lambda val=d: set_duration(val)) \
                                        .props(f'flat dense no-caps size=sm {"color=indigo" if is_active else "text-color=grey-7"}') \
                                        .classes(f'px-2 md:px-3 rounded-md transition-all {"bg-white shadow-sm font-bold" if is_active else "hover:bg-gray-200"} text-xs')

                    async def set_duration(val):
                        radar_state['duration'] = val
                        update_duration_options(date_input.value)
                        await update_dashboard(date_input.value)

                    # Event Listeners
                    async def on_date_change():
                        check_refresh_visibility()
                        update_duration_options(date_input.value)
                        await update_dashboard(date_input.value)

                    date_input.on_value_change(on_date_change)

                    # Init
                    check_refresh_visibility()
                    update_duration_options(today_str)

        # 2. Status & Dashboard Area
        dashboard_content = ui.column().classes('w-full gap-6')

        def render_multi_day_view(df, dates, plot_func):
             """
             Render multi-day aggregated view with enhanced tech-minimalist styling.
             """
             # Pre-calculations
             df['资金强度'] = df.apply(lambda x: x['净流入'] / x['总成交额'] if x['总成交额'] > 0 else 0, axis=1)
             
             # Filter logic
             df['abs_flow'] = df['净流入'].abs()
             df_top_scatter = df.sort_values('abs_flow', ascending=False)
             # Removed limit to show all sectors
             # if len(df_top_scatter) > 50:
             #     df_top_scatter = df_top_scatter.head(50)
             
             # Stats
             total_net = df['净流入'].sum()
             pos_df = df[df['净流入'] > 0]
             neg_df = df[df['净流入'] < 0]
             pos_ratio = (len(pos_df) / len(df) * 100) if not df.empty else 0
             avg_strength = df['资金强度'].mean()
             
             # Calculate Core Sector Performance (Avg Change of top 20 by turnover) for multi-day
             top_turnover_df = df.sort_values('总成交额', ascending=False).head(20)
             if '涨跌幅' in df.columns:
                 avg_change = top_turnover_df['涨跌幅'].mean() if not top_turnover_df.empty else 0.0
             else:
                 avg_change = 0.0
             chg_color = "rose-500" if avg_change > 0 else "emerald-500"

             # Leaders
             top_inflow_list = df.sort_values('净流入', ascending=False).head(5)
             max_inflow = top_inflow_list.iloc[0] if not top_inflow_list.empty else None
             max_strength = df.sort_values('资金强度', ascending=False).iloc[0] if not df.empty else None
             
             # Market Sentiment Color Mapping
             if total_net > 0:
                 status_color = "rose" # Tailwind color name for Indigo/Rose mix
                 status_hex = "#f43f5e"
                 insight_title = "多头主导"
                 insight_sub = "BULLISH TREND"
                 bg_gradient = "bg-gradient-to-br from-rose-50 to-white"
                 border_color = "border-rose-100"
             else:
                 status_color = "emerald"
                 status_hex = "#10b981"
                 insight_title = "空头抑制"
                 insight_sub = "BEARISH TREND"
                 bg_gradient = "bg-gradient-to-br from-emerald-50 to-white"
                 border_color = "border-emerald-100"

             with ui.grid(columns=3 if not is_mobile else 1).classes('w-full gap-4'):

                # Card 1: AI Insight Specialist (Glass/Gradient Tech Style)
                with ui.card().classes(f'w-full p-4 rounded-xl shadow-sm border {border_color} {bg_gradient} relative overflow-hidden group hover:shadow-md transition-all duration-500'):
                        # Tech background element
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

                # Card 2: Market Pulse (Minimalist Tech Meter)
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
                        
                        # Distribution Visualizer
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

                # Card 3: Sector Alpha (Minimalist Leaderboard)
                with ui.card().classes('w-full p-4 rounded-xl shadow-sm border border-gray-100 bg-white'):
                    with ui.row().classes('items-center gap-2 mb-4'):
                        ui.icon('military_tech', color='amber').classes('text-lg')
                        ui.label('领跑板块榜单').classes('text-xs font-black tracking-widest text-gray-400')
                    
                    if max_inflow is not None:
                        # Top 1 Section
                        with ui.row().classes('w-full items-start justify-between'):
                            with ui.column().classes('gap-0'):
                                ui.label(max_inflow["名称"]).classes('text-2xl font-black text-gray-900')
                                ui.label(f'累计流入: {max_inflow["净流入"]:.1f} 亿').classes('text-xs font-bold text-rose-500 tracking-tight')
                            ui.icon('workspace_premium', color='amber-400').classes('text-3xl')

                        # Top 2 & 3 List
                        with ui.column().classes('w-full mt-3 space-y-1'):
                            for i, row in enumerate(top_inflow_list.iloc[1:3].itertuples()):
                                with ui.row().classes('w-full justify-between items-center bg-gray-50/50 px-2 py-1.5 rounded-lg'):
                                    ui.label(f'NO.{i+2} {row.名称}').classes('text-xs font-bold text-gray-600')
                                    ui.label(f'{row.净流入:+.1f} 亿').classes('text-xs font-mono text-gray-400')
                        
                        # Efficiency Badge
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

             # 2. Advanced Scatter Plot (Quadrant Analysis)
             with ui.column().classes('w-full gap-6'):  
                with ui.card().classes('w-full border border-gray-200 rounded-xl shadow-sm bg-white p-4 flex flex-col gap-0'):
                      with ui.row().classes('w-full justify-between items-center mb-2 pb-2 border-b border-gray-200'):
                           with ui.row().classes('items-center gap-2'):
                                ui.icon('bubble_chart', color='indigo').classes('text-xl')
                                ui.label('资金进攻象限 (气泡大小=成交额)').classes('text-base font-bold text-gray-800')
                      
                      plot_h = 'h-[500px]' 
                      with ui.element('div').classes(f'w-full {plot_h}'):
                          fig_scatter = go.Figure()
                          
                          # Hover template
                          hover_text = [
                              f"板块: {row.名称}<br>净流入: {row.净流入:.1f}亿<br>强度: {row.资金强度*100:.1f}%<br>成交: {row.总成交额:.1f}亿<br>活跃: {row.活跃天数}天"
                              for row in df_top_scatter.itertuples()
                          ]
                          
                          # Determine colors based on Net Inflow (Red for positive, Green for negative)
                          colors = ['#ef4444' if row.净流入 > 0 else '#10b981' for row in df_top_scatter.itertuples()]
                          
                          # Size calculation (Adjusted for better visuals)
                          size_ref = df_top_scatter['总成交额'].max() if not df_top_scatter.empty else 1
                          sizes = (np.sqrt(df_top_scatter['总成交额']) / np.sqrt(size_ref)) * 40 + 10

                          fig_scatter.add_trace(go.Scatter(
                              x=df_top_scatter['净流入'],
                              y=df_top_scatter['资金强度'] * 100,
                              mode='markers+text',
                              text=df_top_scatter['名称'],
                              textposition="top center",
                              textfont=dict(size=11, color='rgba(0,0,0,0.7)', family="sans-serif"), 
                              marker=dict(
                                  size=sizes, 
                                  sizemode='diameter',
                                  color=colors,
                                  line=dict(width=1, color='white'),
                                  opacity=0.85
                              ),
                              hoverinfo='text',
                              hovertext=hover_text
                          ))
                          
                          # Quadrant Lines
                          fig_scatter.add_vline(x=0, line_width=1, line_dash="solid", line_color="rgba(0,0,0,0.05)")
                          fig_scatter.add_hline(y=0, line_width=1, line_dash="solid", line_color="rgba(0,0,0,0.05)")
                          
                          # Background Watermark Annotations (Matching Image 1 Style)
                          quad_anns = [
                              dict(x=1, y=1, xref='x domain', yref='y domain', text="🔥 主力抢筹", showarrow=False, 
                                   font=dict(color='rgba(239, 68, 68, 0.15)', size=24, weight='bold'), xanchor='right', yanchor='top'),
                              dict(x=0, y=0, xref='x domain', yref='y domain', text="❄️ 减仓出货", showarrow=False, 
                                   font=dict(color='rgba(16, 185, 129, 0.15)', size=24, weight='bold'), xanchor='left', yanchor='bottom')
                          ]
                          for ann in quad_anns:
                              fig_scatter.add_annotation(ann)

                          fig_scatter.update_layout(
                              margin=dict(l=40,r=40,t=30,b=40),
                              paper_bgcolor='rgba(0,0,0,0)',
                              plot_bgcolor='rgba(252, 252, 252, 1)', 
                              xaxis_title='累积净流入 (亿)',
                              yaxis_title='资金强度 (%)<br><sup>计算公式: (净流入 ÷ 成交额) × 100%</sup>',
                              xaxis=dict(zeroline=False, gridcolor='#F3F4F6'),
                              yaxis=dict(zeroline=False, gridcolor='#F3F4F6'),
                              showlegend=False
                          )
                          plot_func(fig_scatter).classes('w-full h-full')
                 
                # 3. Combined Analysis Chart (Divergence & Flow)
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
                     
                     # Data Prep
                     # Ensure we have '涨跌幅'
                     if '涨跌幅' not in df.columns:
                         df['涨跌幅'] = 0.0
                     
                     df_in = df.sort_values('净流入', ascending=False).head(10)
                     df_out = df.sort_values('净流入', ascending=True).head(10)
                     df_combo = pd.concat([df_in, df_out]).drop_duplicates(subset=['名称']).sort_values('净流入', ascending=True)
                     
                     # Calculate visual separator position (between negative and positive)
                     neg_count = len(df_combo[df_combo['净流入'] < 0])
                     split_idx = neg_count - 0.5

                     with ui.element('div').classes('w-full h-[500px]'):
                         fig_combo = go.Figure()

                         # Trace 1: Net Inflow (Bars)
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
                             hoverinfo='x+y'
                         ))

                         # Trace 2: Price Change (Markers)
                         # Use secondary x-axis
                         # Red diamond for Up, Green diamond for Down
                         colors_dot = ['#b91c1c' if x > 0 else '#047857' for x in df_combo['涨跌幅']]
                         fig_combo.add_trace(go.Scatter(
                             y=df_combo['名称'],
                             x=df_combo['涨跌幅'],
                             xaxis='x2',
                             mode='markers',
                             name='平均涨跌幅',
                             marker=dict(color=colors_dot, size=10, symbol='diamond', line=dict(width=1, color='white')), 
                             hovertemplate='%{y}<br>平均涨跌: %{x:.2f}%<extra></extra>'
                         ))

                         # Add Separator Line & Annotations
                         if 0 < neg_count < len(df_combo):
                             fig_combo.add_shape(type="line", 
                                x0=0, x1=1, xref="paper",
                                y0=split_idx, y1=split_idx, yref="y",
                                line=dict(color="rgba(0,0,0,0.2)", width=1, dash="longdash")
                             )
                             # Zone Labels
                             fig_combo.add_annotation(x=1, y=len(df_combo)-1, xref="paper", yref="y",
                                text="资金净流入 Top", showarrow=False, font=dict(color="#ef4444", size=12, weight="bold"), xanchor='right', yanchor='top',
                                bgcolor="rgba(255,255,255,0.7)")
                             fig_combo.add_annotation(x=1, y=0, xref="paper", yref="y",
                                text="资金净流出 Top", showarrow=False, font=dict(color="#10b981", size=12, weight="bold"), xanchor='right', yanchor='bottom',
                                bgcolor="rgba(255,255,255,0.7)")

                         # Highlight Divergence (Optional Annotation)?
                         # Keep it clean for now.

                         fig_combo.update_layout(
                             margin=dict(l=20,r=20,t=40,b=20),
                             paper_bgcolor='rgba(0,0,0,0)',
                             plot_bgcolor='rgba(0,0,0,0)',
                             barmode='overlay',
                             xaxis=dict(
                                 title=dict(text='资金净流入 (亿)', standoff=0, font=dict(size=14)),
                                 tickfont=dict(size=12),
                                 showgrid=True, 
                                 gridcolor='#f3f4f6', # Very light
                                 zeroline=True, zerolinewidth=1, zerolinecolor='gray'
                             ),
                             xaxis2=dict(
                                 title=dict(text='平均涨跌幅 (%)', font=dict(color='#6b7280', size=13)),
                                 tickfont=dict(color='#6b7280', size=12),
                                 overlaying='x', 
                                 side='top',
                                 showgrid=False,
                                 zeroline=False
                             ),
                             yaxis=dict(
                                 showgrid=False,
                                 tickfont=dict(size=13, color='#374151', weight='bold') # Dark gray, bold-ish look
                             ),
                             showlegend=False,
                             bargap=0.3
                         )
                         plot_func(fig_combo).classes('w-full h-full')

                # 4. Detailed Data & Panorama (Treemap + Table)
                with ui.card().classes('w-full border border-gray-200 rounded-xl shadow-sm bg-white p-0 flex flex-col gap-0'):
                     # Header
                     with ui.row().classes('w-full justify-between items-center p-4 border-b border-gray-200'):
                           with ui.row().classes('items-center gap-2'):
                                ui.icon('grid_view', color='indigo').classes('text-xl')
                                ui.label('资金流向全景透视图 (Money Flow Heatmap)').classes('text-base font-bold text-gray-800')

                     # Data Prep for Treemap
                     df_tree = df.copy()
                     df_tree['abs_turnover'] = df_tree['总成交额']
                     
                     # 1. Categorize Sectors
                     offensive_list, defensive_list = radar.get_offensive_defensive_list()
                     def get_category(name):
                        if name in offensive_list: return "🚀 进攻阵营"
                        if name in defensive_list: return "🛡️ 防守阵营"
                        return "⚖️ 平衡/其他"

                     df_tree['category'] = df_tree['名称'].apply(get_category)
                     
                     # 2. Build Hierarchy Nodes
                     # Root
                     root_id = "全市场板块资金概览"
                     
                     # Categories
                     cats = df_tree['category'].unique().tolist()
                     
                     # Leaves (Sectors) - Parent is their Category
                     ids = df_tree['名称'].tolist() + cats + [root_id]
                     labels = df_tree['名称'].tolist() + cats + [root_id]
                     parents = df_tree['category'].tolist() + [root_id]*len(cats) + [""]
                     
                     # Values (Turnover)
                     # Leaves have real turnover. Groups/Root = 0 (Plotly sums children)
                     values = df_tree['abs_turnover'].tolist() + [0]*len(cats) + [0]
                     
                     # Colors (Net Inflow)
                     # Leaves have real inflow. Groups/Root = 0 (or let Plotly aggregate? Plotly Treemap implies color aggregation if unspecified? 
                     # No, we must provide color for all nodes if we use array)
                     colors = df_tree['净流入'].tolist() + [0]*len(cats) + [0]
                     
                     # Text/CustomData
                     # Leaves
                     texts_leaves = df_tree['净流入'].apply(lambda x: f"{x:+.1f}亿").tolist()
                     custom_leaves = df_tree['涨跌幅'].tolist()
                     
                     # Branch/Root Text (Optional)
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
                            marker=dict(
                                colors=colors,
                                # Custom Red-White-Green scale
                                colorscale=[
                                    [0.0, 'rgb(34, 197, 94)'],   # Green (Outflow)
                                    [0.5, 'rgb(255, 255, 255)'], # White
                                    [1.0, 'rgb(239, 68, 68)']    # Red (Inflow)
                                ],
                                cmid=0,
                                showscale=False
                            ),
                            text=all_text,
                            texttemplate="<b>%{label}</b><br>%{text}",
                            hovertemplate='<b>%{label}</b><br>成交额: %{value:.1f}亿<br>净流入: %{text}<br>涨跌幅: %{customdata:.2f}%<extra></extra>',
                            customdata=all_custom,
                            textposition="middle center",
                            textfont=dict(size=14, color='black')
                         ))
                         
                         fig_tree.update_layout(
                            margin=dict(t=10, l=10, r=10, b=10),
                            uniformtext=dict(minsize=10, mode='hide')
                         )
                         plot_func(fig_tree).classes('w-full h-full')

                     # Collapsible Data Table
                     with ui.expansion('查看详细数据报表 (Data Table)', icon='table_chart').classes('w-full border-t border-gray-100 bg-gray-50'):
                        with ui.column().classes('w-full p-4 gap-4'):
                             # Download Button
                             def download_csv():
                                 csv_str = df.to_csv(index=False)
                                 ui.download(csv_str.encode('utf-8-sig'), filename=f'fund_flow_{date_input.value}_{radar_state["duration"]}days.csv')
                             
                             with ui.row().classes('w-full justify-end'):
                                 ui.button('下载 CSV 数据', icon='download', on_click=download_csv).props('outline rounded color=grey-8 size=sm')

                             # Table
                             df_table = df.sort_values('净流入', ascending=False)
                             rows = []
                             for i, row in enumerate(df_table.itertuples(), 1):
                                 intensity = row.资金强度 * 100 
                                 flows = row.日均趋势 if hasattr(row, '日均趋势') else []
                                 
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


        def render_sector_grid_view():
            """
            Render the 3-column sector grid view (similar to Tonghuashun structure).
            """
            try:
                # Get data for last 6 days
                dates, grid_data = get_sector_grid_data(radar.cache_dir, days=6)
                if not dates:
                    return

                with ui.card().classes('w-full border border-gray-200 rounded-xl shadow-sm bg-white p-0 flex flex-col gap-0 mt-4'):
                    # Header
                    with ui.row().classes('w-full justify-between items-center p-3 border-b border-gray-200 bg-gray-50/50'):
                        with ui.column().classes('gap-0'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('grid_view', color='indigo').classes('text-lg')
                                ui.label('核心板块资金流向雷达 (Core Sector Flow Radar)').classes('text-sm font-bold text-gray-800')
                                
                                # Last Update Time Label
                                last_analysis_time = ui.label('').classes('text-[10px] text-gray-400 font-mono ml-2')
                                
                            ui.label('备注：2.24日开始，净流入为主力净流入，之前为全口径净流入').classes('text-[10px] text-gray-400 transform scale-90 origin-left ml-7')
                        
                        with ui.row().classes('items-center gap-4'):
                            # Refresh Button for Sector Analysis
                            btn_refresh_analysis = ui.button('刷新分析', icon='refresh', on_click=lambda: run_analysis(force=True)) \
                                .props('flat dense size=sm color=indigo').classes('text-xs font-bold')
                            
                            # Legend
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

                    # Detail Dialog (Interactive Logic)
                    detail_dialog = ui.dialog().classes('w-full')
                    with detail_dialog, ui.card().classes('w-full max-w-5xl p-6 rounded-2xl shadow-xl bg-white'):
                        # Header
                        with ui.row().classes('w-full justify-between items-start mb-6'):
                             with ui.row().classes('items-end gap-4'):
                                 detail_title = ui.label('板块详情').classes('text-3xl font-black text-gray-900 tracking-tight')
                                 # Price & Change Placeholder
                                 detail_price = ui.label('').classes('text-2xl font-bold font-mono')
                                 detail_change = ui.label('').classes('text-lg font-bold px-2 py-0.5 rounded-lg')
                                 detail_subtitle = ui.label('').classes('text-sm text-gray-400 font-bold mb-1')
                             ui.button(icon='close', on_click=detail_dialog.close).props('flat round dense color=grey size=lg')
                        
                        # Content Container
                        detail_content = ui.column().classes('w-full gap-6')

                    def show_sector_detail(name):
                        detail_title.set_text(name)
                        # Reset placeholders
                        detail_price.set_text('')
                        detail_change.set_text('')
                        detail_change.classes(remove='bg-red-50 text-red-600 bg-green-50 text-green-600')
                        
                        detail_content.clear()
                        detail_dialog.open()
                        
                        # Async fetch data
                        async def load_detail():
                             with detail_content:
                                 ui.spinner(type='dots', size='3rem', color='indigo')
                             
                             # Fetch analysis
                             res = await asyncio.get_event_loop().run_in_executor(None, lambda: sector_analyzer.analyze(name))
                             
                             # Update Header Data
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
                                 # 1. Top Cards (Short & Mid-Long)
                                 with ui.grid(columns=2).classes('w-full gap-6'):
                                     # Short Term Card
                                     with ui.card().classes('p-5 rounded-2xl border border-gray-100 bg-gradient-to-br from-gray-50 to-white shadow-sm relative overflow-hidden group hover:shadow-md transition-all'):
                                         ui.icon('bolt', color='gray-200').classes('absolute -right-4 -bottom-4 text-8xl opacity-20 rotate-12 group-hover:scale-110 transition-transform')
                                         ui.label('短线机会 (Short Term)').classes('text-sm font-black text-gray-400 uppercase tracking-widest mb-3')
                                         ui.label(res['short_term']['status']).classes(f"text-3xl font-black tracking-tight {res['short_term']['color']}")
                                         with ui.row().classes('items-center gap-2 mt-2'):
                                             ui.icon('info', size='xs', color='gray-400')
                                             ui.label(res['short_term']['signal']).classes('text-sm text-gray-600 font-medium')
                                         
                                     # Mid-Long Term Card
                                     with ui.card().classes('p-5 rounded-2xl border border-gray-100 bg-gradient-to-br from-gray-50 to-white shadow-sm relative overflow-hidden group hover:shadow-md transition-all'):
                                         ui.icon('trending_up', color='gray-200').classes('absolute -right-4 -bottom-4 text-8xl opacity-20 rotate-12 group-hover:scale-110 transition-transform')
                                         ui.label('中线趋势 (Medium Term)').classes('text-sm font-black text-gray-400 uppercase tracking-widest mb-3')
                                         ui.label(res['mid_long_term']['status']).classes(f"text-3xl font-black tracking-tight {res['mid_long_term']['color']}")
                                         with ui.row().classes('items-center gap-2 mt-2'):
                                             ui.icon('analytics', size='xs', color='gray-400')
                                             ui.label(res['mid_long_term']['signal']).classes('text-sm text-gray-600 font-medium')

                                 # 2. Indicators Grid
                                 with ui.card().classes('w-full p-6 rounded-2xl border border-gray-100 shadow-sm'):
                                     ui.label('技术指标透视 (Technical Indicators)').classes('text-base font-black text-gray-800 mb-6 pb-3 border-b border-gray-100 w-full')
                                     
                                     with ui.grid(columns=4).classes('w-full gap-8'):
                                         # MACD
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
                                         
                                         # RSI
                                         with ui.column().classes('gap-2'):
                                             ui.label('RSI (14) 强弱').classes('text-xs font-bold text-gray-400 uppercase')
                                             rsi_val = res['last_rsi']
                                             rsi_color = 'text-red-500' if rsi_val > 70 else ('text-green-500' if rsi_val < 30 else 'text-gray-800')
                                             
                                             with ui.row().classes('items-baseline gap-1'):
                                                 ui.label(f"{rsi_val:.1f}").classes(f"text-3xl font-black {rsi_color} leading-none")
                                                 ui.label('/ 100').classes('text-xs text-gray-400 font-bold')
                                             
                                             # Visual Bar
                                             with ui.element('div').classes('w-full h-2 bg-gray-100 rounded-full overflow-hidden mt-1 relative'):
                                                 # Zones
                                                 ui.element('div').classes('absolute left-0 top-0 h-full bg-green-100 w-[30%]')
                                                 ui.element('div').classes('absolute right-0 top-0 h-full bg-red-100 w-[30%]')
                                                 # Value
                                                 bar_color = 'bg-red-500' if rsi_val > 70 else ('bg-green-500' if rsi_val < 30 else 'bg-indigo-500')
                                                 ui.element('div').classes(f'h-full {bar_color} transition-all duration-500').style(f'width: {rsi_val}%')

                                         # Bollinger
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
                                         
                                         # MA Alignment
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

                                 # 3. Chan Lun Structure
                                 with ui.card().classes('w-full p-6 rounded-2xl border border-gray-100 bg-gradient-to-r from-indigo-50 to-white shadow-sm'):
                                     ui.label('缠论结构分析 (Chan Lun Structure)').classes('text-base font-black text-indigo-900 mb-4 pb-2 border-b border-indigo-100 w-full')
                                     
                                     with ui.row().classes('w-full gap-8'):
                                         # Left: Current Status
                                         with ui.column().classes('flex-1 gap-2'):
                                             ui.label('当前笔状态').classes('text-xs font-bold text-indigo-400 uppercase')
                                             ui.label(res['chan_info']['text']).classes(f"text-2xl font-black {res['chan_info']['color']}")
                                             ui.label(res['summary']).classes('text-sm text-gray-600 font-medium leading-relaxed mt-2 bg-white/50 p-3 rounded-lg border border-indigo-50')
                                         
                                         # Right: Recent Bi List
                                         with ui.column().classes('flex-1 gap-2'):
                                             ui.label('近期笔走势 (Recent Strokes)').classes('text-xs font-bold text-indigo-400 uppercase')
                                             if res['bi_points']:
                                                 # Show last 5 points reversed
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

                        # Start async load
                        run_in_bg(load_detail)

                    def run_in_bg(task):
                        asyncio.create_task(task())

                    # Grid Content - Single Column List View (User Requested)
                    with ui.column().classes('w-full gap-0 border-t border-gray-200'):
                        
                        # 1. Main Table Header
                        with ui.row().classes('w-full bg-gray-100 border-b border-gray-200 h-8 items-center gap-0'):
                            ui.label('板块').classes('w-24 pl-4 text-[11px] font-bold text-gray-500')
                            # Added Analysis Columns
                            ui.label('短线机会').classes('w-24 text-center text-[11px] font-bold text-gray-500 border-l border-gray-200')
                            ui.label('中线趋势').classes('w-24 text-center text-[11px] font-bold text-gray-500 border-l border-gray-200')
                            ui.label('缠论结构').classes('w-24 text-center text-[11px] font-bold text-gray-500 border-l border-gray-200')
                            ui.label('MACD').classes('w-20 text-center text-[11px] font-bold text-gray-500 border-l border-gray-200')
                            ui.label('RSI').classes('w-12 text-center text-[11px] font-bold text-gray-500 border-l border-gray-200')
                            ui.label('布林').classes('w-16 text-center text-[11px] font-bold text-gray-500 border-l border-gray-200')
                            
                            for d in dates:
                                ui.label(d).classes('flex-1 text-center text-[11px] font-bold text-gray-500 border-l border-gray-200')

                        # 2. Render Rows
                        all_rows = [] # Store row objects to control visibility
                        analysis_targets = [] # Store elements to update
                        sector_count = 0
                        INITIAL_SHOW_COUNT = 15 # Increased slightly

                        # Iterate through grid_data (preserves insertion order from logic file)
                        for category, sectors in grid_data.items():
                            if not sectors: continue

                            # Category Header Row
                            cat_row = ui.row().classes('w-full bg-indigo-50 border-y border-indigo-100 py-1.5 px-4 items-center')
                            with cat_row:
                                ui.label(category).classes('text-[11px] font-black text-indigo-800 tracking-widest')
                            
                            all_rows.append({'row': cat_row, 'type': 'category'})
                            
                            # Sector Rows
                            for sector in sectors:
                                s_row = ui.row().classes('w-full border-b border-gray-100 h-9 items-center gap-0 hover:bg-gray-50 transition-colors group')
                                with s_row:
                                    # Name
                                    with ui.row().classes('w-24 pl-4 h-full items-center border-r border-gray-100'):
                                        ui.label(sector['name']).classes('text-[11px] font-bold text-gray-700 truncate')
                                    
                                    # Analysis Placeholders
                                    
                                    # Short Term
                                    with ui.row().classes('w-24 h-full items-center justify-center border-r border-gray-100 px-1'):
                                        lbl_short = ui.label('-').classes('text-[10px] text-gray-400')
                                        
                                    # Mid-Long Term
                                    with ui.row().classes('w-24 h-full items-center justify-center border-r border-gray-100 px-1'):
                                        lbl_mid = ui.label('-').classes('text-[10px] text-gray-400')

                                    # Chan Lun Structure (Top/Bottom Fenxing)
                                    with ui.row().classes('w-24 h-full items-center justify-center border-r border-gray-100 px-1'):
                                        lbl_chan = ui.label('-').classes('text-[10px] text-gray-400')
                                        
                                    # MACD
                                    with ui.row().classes('w-20 h-full items-center justify-center border-r border-gray-100 px-1'):
                                        lbl_macd = ui.label('-').classes('text-[10px] text-gray-400')
                                    
                                    # RSI
                                    with ui.row().classes('w-12 h-full items-center justify-center border-r border-gray-100 px-1'):
                                        lbl_rsi = ui.label('-').classes('text-[10px] text-gray-400')

                                    # Bollinger
                                    with ui.row().classes('w-16 h-full items-center justify-center border-r border-gray-100 px-1'):
                                        lbl_boll = ui.label('-').classes('text-[10px] text-gray-400')

                                    analysis_targets.append({
                                        'name': sector['name'],
                                        'short': lbl_short,
                                        'mid': lbl_mid,
                                        'chan': lbl_chan,
                                        'macd': lbl_macd,
                                        'rsi': lbl_rsi,
                                        'boll': lbl_boll
                                    })
                                    
                                    # Click to Open Detail
                                    def open_detail(name=sector['name']):
                                        show_sector_detail(name)
                                        
                                    # Make Name Clickable
                                    s_row.on('click', open_detail)
                                    s_row.classes('cursor-pointer')

                                    # Date Cells
                                    for day_data in sector['history']:
                                        with ui.row().classes(f'flex-1 h-full items-center justify-center {day_data["color_class"]} border-r border-gray-100 px-1 relative'):
                                            ui.label(day_data['status']).classes('text-[11px] font-bold leading-none')
                                            # Tooltip
                                            ui.tooltip(f"{day_data['date']} {sector['name']}\n净流入: {day_data['inflow']:.1f}亿\n成交额: {day_data['turnover']:.1f}亿\n强度: {day_data['ratio']:.1f}%").classes('text-xs bg-gray-800 text-white shadow-lg whitespace-pre-line')
                                
                                all_rows.append({'row': s_row, 'type': 'sector'})
                                sector_count += 1
                        
                        # 3. Visibility Logic
                        visible_sectors = 0
                        hidden_row_elements = []
                        
                        for item in all_rows:
                            if visible_sectors >= INITIAL_SHOW_COUNT:
                                item['row'].set_visibility(False)
                                hidden_row_elements.append(item['row'])
                            
                            if item['type'] == 'sector':
                                visible_sectors += 1
                        
                        # 4. Expand/Collapse Button
                        if hidden_row_elements:
                            with ui.row().classes('w-full justify-center py-3 bg-gray-50 border-t border-gray-200 cursor-pointer hover:bg-gray-100 transition-colors') as btn_container:
                                icon = ui.icon('expand_more', color='gray-500').classes('text-xl transition-transform duration-300')
                                lbl = ui.label(f'展开剩余 {sector_count - INITIAL_SHOW_COUNT} 个板块').classes('text-xs font-bold text-gray-500')
                                
                                is_expanded = {'val': False}
                                
                                def toggle_grid():
                                    is_expanded['val'] = not is_expanded['val']
                                    for r in hidden_row_elements:
                                        r.set_visibility(is_expanded['val'])
                                    
                                    if is_expanded['val']:
                                        lbl.set_text('收起列表')
                                        icon.classes(remove='rotate-0', add='rotate-180')
                                    else:
                                        lbl.set_text(f'展开剩余 {sector_count - INITIAL_SHOW_COUNT} 个板块')
                                        icon.classes(remove='rotate-180', add='rotate-0')
                                
                                btn_container.on('click', toggle_grid)
                        
                        # 5. Background Analysis Task
                        async def run_analysis(force=False):
                            # Update timestamp label
                            cn_now = datetime.datetime.now() + datetime.timedelta(hours=8)
                            # Actually, server is likely local, so datetime.now() might be correct if timezone is set.
                            # But safe to use UTC+8 explicit if needed. 
                            # Assuming system time is correct or we use utcnow
                            # Let's use simple now() for display if running locally in China, 
                            # or use the logic from earlier:
                            # utc_now = datetime.datetime.now(datetime.timezone.utc)
                            # cn_now = utc_now + datetime.timedelta(hours=8)
                            # But 'datetime' is imported at top level.
                            # Re-use logic:
                            utc_now = datetime.datetime.now(datetime.timezone.utc)
                            cn_now = utc_now + datetime.timedelta(hours=8)
                            time_str = cn_now.strftime('%H:%M:%S')
                            
                            if not last_analysis_time.is_deleted:
                                last_analysis_time.set_text(f"最后刷新: {time_str}")
                                
                            if force:
                                ui.notify('正在强制刷新板块分析数据...', type='info', position='top')
                                # Disable button temporarily?
                                if not btn_refresh_analysis.is_deleted:
                                    btn_refresh_analysis.disable()

                            # Prioritize visible sectors? 
                            # Since analysis_targets follows the grid order, the first INITIAL_SHOW_COUNT are visible.
                            # We just iterate linearly.
                            
                            for target in analysis_targets:
                                if s_row.is_deleted: return # Stop if component destroyed
                                
                                # Use run_in_executor to avoid blocking event loop during network requests
                                try:
                                    # If force is True, we pass it to fetch_history inside analyze?
                                    # Need to update SectorAnalyzer.analyze to accept force_update
                                    # Or call fetch_history with force first.
                                    # Actually SectorAnalyzer.analyze doesn't take force arg in current impl.
                                    # We can modify SectorAnalyzer to handle it, or call fetch_history explicitly.
                                    # Let's modify the lambda to handle it.
                                    
                                    def analyze_wrapper(name, force_flag):
                                        if force_flag:
                                            # Force fetch first
                                            sector_analyzer.fetch_history(name, force_update=True)
                                        return sector_analyzer.analyze(name)

                                    res = await asyncio.get_event_loop().run_in_executor(
                                        None, 
                                        lambda: analyze_wrapper(target['name'], force)
                                    )
                                    
                                    # Update UI
                                    # 1. Short Term
                                    target['short'].set_text(res['short_term']['status'])
                                    target['short'].classes(replace=f"text-[10px] font-bold {res['short_term']['color']}")
                                    target['short'].tooltip(res['short_term']['signal'])
                                    
                                    # 2. Mid-Long Term
                                    target['mid'].set_text(res['mid_long_term']['status'])
                                    target['mid'].classes(replace=f"text-[10px] font-bold {res['mid_long_term']['color']}")
                                    target['mid'].tooltip(res['mid_long_term']['signal'])

                                    # 3. Chan Structure
                                    target['chan'].set_text(res['chan_info']['text'])
                                    target['chan'].classes(replace=f"text-[10px] font-bold {res['chan_info']['color']}")
                                    # Enhanced Tooltip for Chan
                                    chan_tooltip = f"{res['summary']}\nRSI: {res['last_rsi']}\n{res['boll_info']['text']}\n{res['breakout_info']['text']}"
                                    target['chan'].tooltip(chan_tooltip).classes('whitespace-pre-line')
                                    
                                    # 4. MACD
                                    target['macd'].set_text(res['macd_info']['text'])
                                    target['macd'].classes(replace=f"text-[10px] font-bold {res['macd_info']['color']}")

                                    # 5. RSI
                                    target['rsi'].set_text(str(int(res['last_rsi'])))
                                    if res['last_rsi'] > 70:
                                        target['rsi'].classes(replace='text-[10px] text-red-500 font-bold')
                                    elif res['last_rsi'] < 30:
                                        target['rsi'].classes(replace='text-[10px] text-green-500 font-bold')
                                    else:
                                        target['rsi'].classes(replace='text-[10px] text-gray-500')

                                    # 6. Bollinger
                                    # Always show text
                                    target['boll'].set_text(res['boll_info']['text'])
                                    target['boll'].classes(replace=f"text-[10px] font-bold {res['boll_info']['color']}")
                                    
                                    # Yield to event loop to keep UI responsive
                                    await asyncio.sleep(0.05)
                                    
                                except Exception as e:
                                    print(f"Analysis error for {target['name']}: {e}")
                                    target['short'].set_text('Error')
                            
                            if force:
                                if not btn_refresh_analysis.is_deleted:
                                    btn_refresh_analysis.enable()
                                ui.notify('板块分析数据刷新完成', type='positive', position='top')
                        
                        # Start analysis after a short delay
                        ui.timer(0.5, run_analysis, once=True)

            except Exception as e:
                print(f"Error rendering sector grid: {e}")
                ui.label(f"Error loading sector grid: {str(e)}").classes('text-red-500 text-xs p-4')

        async def update_dashboard(date_val, force=False):
            if dashboard_content.is_deleted: return
            check_refresh_visibility() # Update button state
            dashboard_content.clear()
            
            # 判断是否为过去的日期（非当前最新交易日）
            is_past_date = (date_val != today_str)
            
            # 过去日期不触发在线数据获取，仅查询本地缓存
            if is_past_date and force:
                force = False  # 过去日期强制取消强制刷新
            
            # Determine duration
            duration = radar_state['duration']

            with dashboard_content:
                # Loading State
                with ui.column().classes('w-full items-center justify-center py-12'):
                    ui.spinner(type='dots', size='3rem', color='indigo')
                    if is_past_date:
                        ui.label(f'正在查询 {date_val} 本地缓存数据...').classes('text-gray-400 mt-4 animate-pulse')
                    elif duration > 1:
                        ui.label(f'正在从同花顺获取 {duration} 天累计数据...').classes('text-gray-400 mt-4 animate-pulse')
                        ui.label('首次加载需约10秒（并行获取90个行业历史成交额）').classes('text-xs text-gray-300 mt-1')
                    else:
                        ui.label(f'正在加载 {date_val} 数据...').classes('text-gray-400 mt-4 animate-pulse')
            
            loop = asyncio.get_running_loop()

            # --- Multi Data Logic ---
            if duration > 1:
                df_agg, used_dates = await loop.run_in_executor(
                    None, lambda: radar.get_multi_day_data(date_val, duration, cache_only=is_past_date)
                )
                
                if dashboard_content.is_deleted: return
                dashboard_content.clear()
                with dashboard_content:
                    if df_agg.empty:
                        with ui.card().classes('w-full p-8 items-center justify-center bg-white rounded-xl shadow-sm border border-gray-200'):
                             if is_past_date:
                                 ui.icon('history', size='4rem', color='amber-4')
                                 ui.label('回溯日期未缓存任何数据').classes('text-xl text-gray-500 font-bold mt-4')
                                 ui.label(f'{date_val} 无本地缓存数据，历史日期仅支持查看已缓存的数据。').classes('text-gray-400 text-sm mt-2')
                                 ui.label('提示：只有在当天盘中/收盘后加载过的日期才会有缓存数据。').classes('text-gray-400 text-xs mt-1')
                             else:
                                 ui.icon('cloud_off', size='4rem', color='grey-4')
                                 ui.label('数据源暂时不可用').classes('text-xl text-gray-500 font-bold mt-4')
                                 ui.label('同花顺API解析异常，可能是网站结构变更。请稍后重试或联系开发者。').classes('text-gray-400 text-sm mt-2')
                                 ui.label('建议：尝试单日数据，或等待数据源修复。').classes('text-gray-400 text-xs mt-1')
                    else:
                        render_multi_day_view(df_agg, used_dates, plot_func)
                return

            # --- Single Day Logic (Original) ---



            # Fetch data 
            # Returns: Sina DF (Amount), THS DF (Net Inflow), Market Snapshot
            # 过去日期仅读缓存，当天日期根据force决定模式
            if is_past_date:
                mode = 'READ_CACHE'
            else:
                mode = 'FORCE_UPDATE' if force else 'READ_CACHE'
            loop = asyncio.get_running_loop()
            
            # Request data (Ignore Sina/Flow data, only use THS)
            _, df_ths, market_snap_data = await loop.run_in_executor(
                None, lambda: radar.get_data(date_val, mode=mode)
            )

            # Update Last Updated Label
            if market_snap_data and 'update_time' in market_snap_data:
                if not last_update_label.is_deleted:
                    last_update_label.set_text(f"最后刷新: {market_snap_data['update_time']}")
                    last_update_label.set_visibility(True)
            else:
                if not last_update_label.is_deleted:
                    last_update_label.set_visibility(False)

            if dashboard_content.is_deleted: return
            dashboard_content.clear()

            with dashboard_content:
                # Strictly check THS data
                if df_ths.empty:
                    with ui.card().classes('w-full p-8 items-center justify-center bg-white rounded-xl shadow-sm border border-gray-200'):
                         if is_past_date:
                             ui.icon('history', size='4rem', color='amber-4')
                             ui.label('回溯日期未缓存任何数据').classes('text-xl text-gray-500 font-bold mt-4')
                             ui.label(f'{date_val} 无本地缓存数据，历史日期仅支持查看已缓存的数据。').classes('text-gray-400 text-sm mt-2')
                             ui.label('提示：只有在当天盘中/收盘后加载过的日期才会有缓存数据。').classes('text-gray-400 text-xs mt-1')
                         else:
                             ui.icon('cloud_off', size='4rem', color='grey-4')
                             ui.label('数据源暂时不可用').classes('text-xl text-gray-500 font-bold mt-4')
                             ui.label('同花顺API解析异常，可能是网站结构变更。请稍后重试或联系开发者。').classes('text-gray-400 text-sm mt-2')
                             ui.label('建议：尝试强制刷新，或等待数据源修复。').classes('text-gray-400 text-xs mt-1')
                    return

                # --- Metric Logic (THS Only) ---
                metric_col = '总成交额' # Use THS column name

                # Ensure Types for THS DF
                # Data is normalized to '亿' in utils if > 1e5, but let's be safe
                df_ths['净流入'] = pd.to_numeric(df_ths['净流入'], errors='coerce').fillna(0)
                
                if '总成交额' not in df_ths.columns and '成交额' in df_ths.columns:
                     df_ths['总成交额'] = df_ths['成交额']
                
                if '总成交额' in df_ths.columns:
                     df_ths['总成交额'] = pd.to_numeric(df_ths['总成交额'], errors='coerce').fillna(0)
                else:
                     df_ths['总成交额'] = 0.0

                if '涨跌幅' in df_ths.columns:
                    df_ths['涨跌幅'] = pd.to_numeric(df_ths['涨跌幅'], errors='coerce').fillna(0)
                else:
                    df_ths['涨跌幅'] = 0.0
                
                # Calculate Net Ratio
                df_ths['净占比'] = (df_ths['净流入'] / df_ths['总成交额'].replace(0, 1)) * 100

                # Prepare standard views
                # Leaderboard / Charts will use this unified DF
                df_flow = df_ths # Alias for compatibility with existing variable names below if needed, or replace usages
                
                # Sorted by Turnover for Panorama/Bubble size
                df_sorted = df_ths.sort_values(by='总成交额', ascending=False)
                top_10 = df_sorted.head(10)
                top_20 = df_sorted.head(20)
                
                # Create Combined DF for Leaderboard (Logic simplified: it's just df_ths)
                df_leader = df_ths

                offensive, defensive = radar.get_offensive_defensive_list()

                # Turnover / Market Nature Analysis 
                analysis_df = top_10

                avg_chg_top10 = analysis_df['涨跌幅'].mean() if not analysis_df.empty else 0.0
                if avg_chg_top10 > 1.0:
                    market_nature = "放量上攻 (Strong)"
                    nature_desc = "板块普遍放量上涨，交投活跃，多头主导。"
                    nature_color = "red"
                elif avg_chg_top10 < -1.0:
                    market_nature = "放量下杀 (Panic)"
                    nature_desc = "高成交换手下大幅下跌，恐慌盘涌出。"
                    nature_color = "green" 
                else:
                    market_nature = "分歧震荡 (Divergence)"
                    nature_desc = "高成交板块涨跌互现，市场分歧巨大。"
                    nature_color = "yellow"

                # Define Color Classes
                if nature_color == "red":
                    bg_theme = "bg-red-50"
                    text_theme = "text-red-600"
                    icon_theme = "trending_up"
                    border_theme = "border-red-100"
                elif nature_color == "green":
                    bg_theme = "bg-emerald-50"
                    text_theme = "text-emerald-600"
                    icon_theme = "trending_down" if "下杀" in market_nature else "shield"
                    border_theme = "border-emerald-100"
                else:
                    bg_theme = "bg-amber-50"
                    text_theme = "text-amber-600"
                    icon_theme = "shuffle"
                    border_theme = "border-amber-100"

                # --- 2. KPI Cards Row ---
                # Notification for Historical Data
                if date_val != today_str:
                     with ui.row().classes('w-full bg-blue-50 border border-blue-200 rounded-lg p-3 items-center gap-3 animate-fade-in'):
                        ui.icon('history', color='blue').classes('text-xl')
                        ui.label(f'正在回溯历史数据快照：{date_val}').classes('text-blue-800 text-sm font-medium')

                # Calculate stats for the new style
                total_net = df_ths['净流入'].sum() if not df_ths.empty else 0
                pos_count = len(df_flow[df_flow['涨跌幅'] > 0]) if not df_flow.empty else 0
                total_count = len(df_flow) if not df_flow.empty else 1
                pos_ratio = (pos_count / total_count) * 100
                

                with ui.grid(columns=3 if not is_mobile else 1).classes('w-full gap-6'):

                    # Card 1: AI Insight Specialist (Screenshot 1 Style)
                    # Use existing nature_color logic to map to status colors
                    if nature_color == "red":
                        status_color = "rose"
                        bg_gradient = "bg-gradient-to-br from-rose-50 to-white"
                        border_color = "border-rose-100"
                    elif nature_color == "green":
                        status_color = "emerald"
                        bg_gradient = "bg-gradient-to-br from-emerald-50 to-white"
                        border_color = "border-emerald-100"
                    else:
                        status_color = "amber"
                        bg_gradient = "bg-gradient-to-br from-amber-50 to-white"
                        border_color = "border-amber-100"

                    with ui.card().classes(f'w-full p-3 rounded-xl shadow-sm border {border_color} {bg_gradient} relative overflow-hidden group hover:shadow-md transition-all duration-500'):
                        ui.element('div').classes('absolute -right-8 -top-8 w-24 h-24 rounded-full bg-white opacity-20 group-hover:scale-125 transition-transform duration-700')
                        
                        with ui.row().classes('items-center gap-2 mb-1'):
                            ui.icon('psychology', color=status_color).classes('text-lg')
                            ui.label('智能态势洞察').classes('text-xs font-black tracking-widest text-gray-400')
                            with ui.icon('help_outline', color='gray-400').classes('text-xs cursor-help'):
                                ui.tooltip('基于多空资金流向、市场参与度和板块分化程度的综合市场状态评估。').classes('text-xs')
                        
                        with ui.column().classes('gap-0'):
                            ui.label(market_nature.split(' ')[0]).classes(f'text-3xl md:text-4xl font-black {f"text-{status_color}-600"} tracking-tight')
                            ui.label(market_nature.split(' ')[1] if ' ' in market_nature else "MARKET TREND").classes('text-xs font-bold text-gray-300 tracking-widest -mt-1')
                        
                        with ui.column().classes('mt-2 gap-1.5'):
                            with ui.row().classes('items-center gap-1.5'):
                                ui.element('div').classes(f'w-1.5 h-1.5 rounded-full bg-{status_color}-500')
                                ui.label(f'多空共识：{abs(total_net):.1f}亿 {"净流入" if total_net > 0 else "净流出"}').classes('text-sm font-bold text-gray-700')
                            
                            with ui.row().classes('items-center gap-1.5'):
                                ui.element('div').classes(f'w-1.5 h-1.5 rounded-full bg-{status_color}-500')
                                ui.label(f'演化阶段：{nature_desc.split("，")[0]} ({pos_ratio:.0f}%参与)').classes('text-sm font-bold text-gray-700 font-tight')

                        ui.label(nature_desc.split("，")[1] if "，" in nature_desc else nature_desc).classes('text-xs text-gray-400 mt-2 border-t border-gray-100 pt-2 italic')

                    # Card 2: Market Pulse (Screenshot 1 Style)
                    avg_change = analysis_df['涨跌幅'].mean() if not analysis_df.empty else 0
                    chg_color = "rose-500" if avg_change > 0 else "emerald-500"
                    
                    with ui.card().classes('w-full p-3 rounded-xl shadow-sm border border-gray-100 bg-white hover:border-indigo-200 transition-colors duration-300'):
                        with ui.row().classes('items-center gap-2 mb-2'):
                            ui.icon('sensors', color='indigo').classes('text-lg')
                            ui.label('市场进攻脉搏').classes('text-xs font-black tracking-widest text-gray-400')
                        
                        with ui.row().classes('w-full items-end justify-between'):
                            with ui.column().classes('gap-0'):
                                ui.label(f'{avg_change:+.2f}%').classes(f'text-4xl font-black text-{chg_color}')
                                with ui.row().classes('items-center gap-1'):
                                    ui.label('核心板块表现').classes('text-xs font-bold text-gray-400')
                                    with ui.icon('help_outline', color='gray-400').classes('text-xs cursor-help'):
                                        ui.tooltip('统计成交额最高的前10个核心板块的平均涨跌幅，反映市场主流资金的赚钱效应。').classes('text-xs')
                            
                            # Small bars for positive/negative balance
                            with ui.column().classes('items-end gap-1'):
                                with ui.row().classes('items-center gap-2'):
                                    ui.label(f'{pos_count}').classes('text-xs font-black text-rose-500')
                                    ui.element('div').classes(f'h-1 bg-rose-500 rounded-full').style(f'width: {(pos_count/total_count)*40 if total_count > 0 else 0}px')
                                with ui.row().classes('items-center gap-2'):
                                    neg_count = total_count - pos_count
                                    ui.label(f'{neg_count}').classes('text-xs font-black text-emerald-500')
                                    ui.element('div').classes(f'h-1 bg-emerald-500 rounded-full').style(f'width: {(neg_count/total_count)*40 if total_count > 0 else 0}px')

                        with ui.grid(columns=2).classes('w-full mt-3 pt-3 border-t border-gray-50 gap-2'):
                            with ui.column().classes('gap-0'):
                                ui.label('统计规模').classes('text-xs text-gray-400 font-bold uppercase')
                                ui.label(f'{total_count} 个板块').classes('text-sm font-black text-gray-700')
                            with ui.column().classes('gap-0 items-end'):
                                total_vol = df_flow[metric_col].sum() if not df_flow.empty else 0
                                ui.label('总成交额').classes('text-xs text-gray-400 font-bold uppercase')
                                ui.label(f'{total_vol/1e4:.1f}万亿' if total_vol > 1e4 else f'{total_vol:.1f}亿').classes('text-sm font-black text-gray-700')

                    # Card 3: Sector Alpha/Leaderboard (Screenshot 1 Style)
                    with ui.card().classes('w-full p-3 rounded-xl shadow-sm border border-gray-100 bg-white'):
                        with ui.row().classes('items-center gap-2 mb-2'):
                            ui.icon('military_tech', color='amber').classes('text-lg')
                            ui.label('领跑板块榜单').classes('text-xs font-black tracking-widest text-gray-400')
                        
                        # Use Combined Leader Data
                        top_list = df_leader.sort_values(by=metric_col, ascending=False).head(3)
                        
                        if not top_list.empty:
                            max_sector = top_list.iloc[0]
                            # Top 1 Section
                            with ui.row().classes('w-full items-start justify-between'):
                                with ui.column().classes('gap-0'):
                                    ui.label(max_sector["名称"]).classes('text-3xl font-black text-gray-900 tracking-tighter')
                                    with ui.row().classes('items-center gap-2 mt-0.5'):
                                        ui.label(f'成交:{max_sector[metric_col]:.1f}亿').classes('text-xs font-bold text-gray-400')
                                        if pd.notnull(max_sector.get('净流入')):
                                            inf = max_sector['净流入']
                                            color = "rose-500" if inf > 0 else "emerald-500"
                                            ui.label(f'主力:{inf:+.1f}亿').classes(f'text-xs font-black text-{color}')
                                ui.icon('workspace_premium', color='amber-400').classes('text-4xl line-height-0')

                            # Top 2 & 3 List
                            with ui.column().classes('w-full mt-2 space-y-1'):
                                for i, row in enumerate(top_list.iloc[1:3].itertuples()):
                                    with ui.row().classes('w-full justify-between items-center bg-gray-50/50 px-2 py-1 rounded-lg'):
                                        with ui.column().classes('gap-0'):
                                            ui.label(f'NO.{i+2} {row.名称}').classes('text-xs font-extrabold text-gray-600')
                                            ui.label(f'成交:{getattr(row, metric_col):.1f}亿').classes('text-[11px] text-gray-400')
                                        
                                        if hasattr(row, '净流入') and pd.notnull(row.净流入):
                                            color_sub = "rose-500" if row.净流入 > 0 else "emerald-500"
                                            ui.label(f'{row.净流入:+.1f}亿').classes(f'text-xs font-bold text-{color_sub}')
                            
                            # Efficiency Badge (Fallback if not multi-day)
                            if not df_ths.empty:
                                best_ratio = df_ths.sort_values(by='净占比', ascending=False).iloc[0]
                                with ui.row().classes('w-full items-center justify-between mt-2 pt-2 border-t border-dashed border-gray-100'):
                                    with ui.row().classes('items-center gap-1'):
                                        ui.label('最强强度:').classes('text-xs font-black text-gray-400 uppercase')
                                        ui.label(best_ratio["名称"]).classes('text-sm font-bold text-indigo-400')
                                    ui.label(f'{best_ratio["净占比"]:+.1f}%').classes('text-xs bg-indigo-50 text-indigo-400 px-1.5 py-0.5 rounded font-mono font-bold')
                        else:
                            ui.label('暂无成交数据').classes('text-gray-300 text-sm italic py-8 text-center w-full')


                # --- 3. Sector Grid View (Tonghuashun Style) ---
                render_sector_grid_view()


                # --- 4. Confrontation (Battlefield) Section (Moved to Top) ---
                # Uses market_snap_data from tuple (Fetched or Cached)

                if market_snap_data:
                    mkt_chg = market_snap_data.get('change_pct', 0.0)
                    with ui.card().classes('w-full p-0 rounded-xl shadow-sm border border-gray-200 bg-white overflow-hidden'):
                        with ui.row().classes('w-full p-3 border-b border-gray-200 items-center justify-between'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('compare_arrows', color='indigo').classes('text-xl')
                                ui.label('多空阵营博弈 (Offense vs Defense)').classes('font-bold text-gray-800 text-base')
                            ui.label(f'上证基准: {mkt_chg:+.2f}%').classes('text-xs font-bold bg-gray-50 px-2 py-1 rounded text-gray-500')

                        df_flow['alpha'] = df_flow['涨跌幅'] - mkt_chg
                        
                        # Calculate Camp Averages
                        df_off_all = df_flow[df_flow['名称'].isin(offensive)]
                        df_def_all = df_flow[df_flow['名称'].isin(defensive)]
                        df_bal_all = df_flow[~df_flow['名称'].isin(offensive + defensive)]
                        
                        avg_off = df_off_all['alpha'].mean() if not df_off_all.empty else 0
                        avg_def = df_def_all['alpha'].mean() if not df_def_all.empty else 0
                        avg_bal = df_bal_all['alpha'].mean() if not df_bal_all.empty else 0

                        # Select Display Data (Limit to 8 for clarity)
                        df_off = df_off_all.sort_values(by='alpha', ascending=False).head(8).iloc[::-1]
                        df_def = df_def_all.sort_values(by='alpha', ascending=False).head(8).iloc[::-1]
                        df_bal = df_bal_all.sort_values(by='alpha', ascending=False).head(8).iloc[::-1]

                        from plotly.subplots import make_subplots
                        b_rows = 3 if is_mobile else 1
                        b_cols = 1 if is_mobile else 3
                        
                        titles = (
                            f"🛡️ 防守阵营 (Avg:{avg_def:+.1f}%)", 
                            f"⚖️ 平衡/轮动 (Avg:{avg_bal:+.1f}%)", 
                            f"🚀 进攻阵营 (Avg:{avg_off:+.1f}%)"
                        )

                        fig_battle = make_subplots(rows=b_rows, cols=b_cols, shared_yaxes=False, 
                                                 horizontal_spacing=0.05, vertical_spacing=0.08,
                                                 subplot_titles=titles)

                        # Bar colors & Styling
                        def add_camp_trace(fig, df, row, col, name):
                            colors = ['#ef4444' if a > 0 else '#10b981' for a in df['alpha']]
                            text = [f"<b>{n}</b> ({v:+.2f}%)" for n, v in zip(df['名称'], df['涨跌幅'])]
                            fig.add_trace(go.Bar(
                                y=df['名称'], x=df['alpha'], orientation='h',
                                marker_color=colors,
                                marker_line=dict(width=1, color='rgba(255,255,255,0.5)'),
                                text=text, textposition='outside', 
                                textfont=dict(size=11, color='#374151'),
                                name=name,
                                showlegend=False,
                                cliponaxis=False
                            ), row=row, col=col)

                        add_camp_trace(fig_battle, df_def, 1, 1, '防守Alpha')
                        add_camp_trace(fig_battle, df_bal, 2 if is_mobile else 1, 1 if is_mobile else 2, '平衡Alpha')
                        add_camp_trace(fig_battle, df_off, 3 if is_mobile else 1, 1 if is_mobile else 3, '进攻Alpha')

                        max_alpha = max(
                            df_flow['alpha'].abs().max() if not df_flow.empty else 0, 
                            3.0
                        )
                        range_limit = max_alpha * 1.5 # Extra room for labels

                        # Enhance sections with background colors (Subtle Gradients)
                        # Define colors
                        bg_colors = ["rgba(16, 185, 129, 0.03)", "rgba(245, 158, 11, 0.03)", "rgba(239, 68, 68, 0.03)"]
                        for i in range(3):
                            r = i + 1 if is_mobile else 1
                            c = 1 if is_mobile else i + 1
                            # Plotly uses 'x', 'x2', 'x3'... (no 'x1')
                            ax_id = f"{i + 1}" if i > 0 else ""
                            fig_battle.add_shape(type="rect", xref=f"x{ax_id} domain", yref=f"y{ax_id} domain", 
                                               x0=0, y0=0, x1=1, y1=1,
                                               fillcolor=bg_colors[i], layer="below", line_width=0, row=r, col=c)

                        fig_battle.update_layout(
                            height=700 if is_mobile else 420, 
                            margin=dict(l=10, r=40, t=40, b=10), 
                            showlegend=False,
                            plot_bgcolor='rgba(255,255,255,1)', paper_bgcolor='rgba(0,0,0,0)',
                            font=dict(size=12)
                        )

                        # Enhanced Titles Styling
                        if len(fig_battle.layout.annotations) >= 3:
                            title_colors = ['#10b981', '#f59e0b', '#ef4444']
                            for i, color in enumerate(title_colors):
                                fig_battle.layout.annotations[i].update(font=dict(size=14, color=color, weight='bold'))

                        fig_battle.update_xaxes(title_text="Alpha (%)" if not is_mobile else "", range=[-range_limit, range_limit], 
                                              zeroline=True, zerolinewidth=1, zerolinecolor='rgba(0,0,0,0.3)',
                                              gridcolor='rgba(0,0,0,0.04)', tickfont=dict(size=10))
                        fig_battle.update_yaxes(showticklabels=False, zeroline=False, gridcolor='rgba(0,0,0,0.02)')
                        
                        plot_func(fig_battle).classes(f'w-full {"h-[900px]" if is_mobile else "h-[460px]"}')

                else:
                    # Message about missing history for Battlefield
                    with ui.row().classes('w-full justify-center p-4'):
                        reason = "今日获取失败" if date_val == today_str else "历史数据未包含大盘快照"
                        ui.label(f'多空博弈无法显示：{reason}').classes('text-gray-400 italic text-sm')

                # --- NEW SECTION: THS Deep Insight Analysis (Merged & Redesigned) ---
                if not df_ths.empty:
                    # 1. Data Processing
                    df_ths_clean = df_ths.copy()
                    df_ths_clean['净占比'] = (df_ths_clean['净流入'] / (df_ths_clean['总成交额'].replace(0, 1))) * 100
                    df_ths_clean['abs_inflow'] = df_ths_clean['净流入'].abs()

                    # Lists Logic
                    accumulating = df_ths_clean[ (df_ths_clean['涨跌幅'] < 0) & (df_ths_clean['净流入'] > 0) ].sort_values('净占比', ascending=False).head(6)
                    distributing = df_ths_clean[ (df_ths_clean['涨跌幅'] > 0) & (df_ths_clean['净流入'] < 0) ].sort_values('净占比', ascending=True).head(6)

                    # --- Unified Insight Panel ---
                    with ui.card().classes('w-full p-0 rounded-xl shadow-sm border border-gray-200 bg-white overflow-hidden'):
                        # Panel Header
                        with ui.row().classes('w-full px-4 py-3 border-b border-gray-200 items-center justify-between bg-gray-50/50'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('psychology', color='indigo').classes('text-xl')
                                ui.label('资金深度博弈透视 (Deep Market Insight)').classes('font-bold text-gray-800 text-sm md:text-base')
                            
                            # Legend / Controls
                            with ui.row().classes('items-center gap-3 text-xs'):
                                with ui.row().classes('items-center gap-1'):
                                    ui.element('div').classes('w-2 h-2 rounded-full bg-red-500')
                                    ui.label('主力做多')
                                with ui.row().classes('items-center gap-1'):
                                    ui.element('div').classes('w-2 h-2 rounded-full bg-emerald-500')
                                    ui.label('主力做空')

                        # Content Grid (Chart vs Lists)
                        with ui.grid(columns=12).classes('w-full'):
                            
                            # LEFT COLUMN: CHART (Span 9 on desktop)
                            with ui.column().classes('col-span-12 lg:col-span-9 p-1 relative border-r border-gray-100'):
                                # Chart Controls Overlay
                                with ui.row().classes('absolute top-2 right-2 z-10 gap-2 opacity-80 hover:opacity-100 transition-opacity'):
                                     ui.label('Y轴: 净占比').classes('text-[10px] text-indigo-500 bg-indigo-50 px-1.5 py-0.5 rounded border border-indigo-100 cursor-help') \
                                        .tooltip('净占比 = 净流入 / 总成交额')

                                fig_map = go.Figure()
                                # Add Quadrant Backgrounds/Lines
                                fig_map.add_hline(y=0, line_width=1, line_dash="solid", line_color="rgba(0,0,0,0.08)")
                                fig_map.add_vline(x=0, line_width=1, line_dash="solid", line_color="rgba(0,0,0,0.08)")


                                colors = ['#ef4444' if x > 0 else '#10b981' for x in df_ths_clean['净流入']]
                                size_ref = df_ths_clean['abs_inflow'].max() if df_ths_clean['abs_inflow'].max() > 0 else 1
                                # Tuned size factor: Slightly reduce max bubble size to improve readability
                                sizes = (np.sqrt(df_ths_clean['abs_inflow']) / np.sqrt(size_ref)) * 30 + 5

                                fig_map.add_trace(go.Scatter(
                                    x=df_ths_clean['涨跌幅'],
                                    y=df_ths_clean['净占比'],
                                    mode='markers+text',
                                    text=df_ths_clean['名称'],
                                    textposition='top center',
                                    textfont=dict(size=10, color='rgba(0,0,0,0.7)'),
                                    marker=dict(size=sizes, color=colors, opacity=0.8, line=dict(width=1, color='white')),
                                    hovertemplate='<b>%{text}</b><br>涨跌: %{x:.2f}%<br>净占比: %{y:.2f}%<br>净流入: %{customdata:.2f}亿<extra></extra>',
                                    customdata=df_ths_clean['净流入']
                                ))

                                # Quadrant Annotations
                                quad_anns = [
                                    dict(x=1, y=1, xref='x domain', yref='y domain', text="🔥 强力做多", showarrow=False, font=dict(color='rgba(239, 68, 68, 0.15)', size=24, weight='bold'), xanchor='right', yanchor='top'),
                                    dict(x=0, y=1, xref='x domain', yref='y domain', text="🛡️ 逆势吸筹", showarrow=False, font=dict(color='rgba(245, 158, 11, 0.15)', size=24, weight='bold'), xanchor='left', yanchor='top'),
                                    dict(x=1, y=0, xref='x domain', yref='y domain', text="⚠️ 拉高出货", showarrow=False, font=dict(color='rgba(16, 185, 129, 0.15)', size=24, weight='bold'), xanchor='right', yanchor='bottom'),
                                    dict(x=0, y=0, xref='x domain', yref='y domain', text="❄️ 合力做空", showarrow=False, font=dict(color='rgba(107, 114, 128, 0.15)', size=24, weight='bold'), xanchor='left', yanchor='bottom')
                                ]
                                for ann in quad_anns:
                                    fig_map.add_annotation(ann)

                                fig_map.update_layout(
                                    height=750, margin=dict(l=40, r=40, t=30, b=40),
                                    plot_bgcolor='white', paper_bgcolor='white',
                                    xaxis=dict(title="板块涨跌幅 (%)", zeroline=False, gridcolor='#F3F4F6', showgrid=True),
                                    yaxis=dict(title="主力资金净占比 (%)", zeroline=False, gridcolor='#F3F4F6', showgrid=True),
                                    showlegend=False
                                )
                                plot_func(fig_map).classes('w-full h-full min-h-[700px]')

                            # RIGHT COLUMN: LISTS (Span 3 on desktop)
                            with ui.column().classes('col-span-12 lg:col-span-3 bg-white flex flex-col h-full'):
                                
                                # Helper for List Item
                                def render_list_item(row, type_color, is_accum=True):
                                    with ui.row().classes('w-full items-center justify-between py-2 px-3 hover:bg-gray-50 transition-colors border-b border-gray-100 last:border-0'):
                                        # Name & Code/Tag
                                        with ui.row().classes('items-center gap-2'):
                                            # Mini Bar
                                            ui.element('div').classes(f'w-1 h-3 rounded-full bg-{type_color}-500')
                                            with ui.column().classes('gap-0'):
                                                # Truncated name logic if too long
                                                display_name = row['名称']
                                                ui.label(display_name).classes('font-bold text-gray-800 text-sm leading-tight')
                                                # Small badge for intensity
                                                intensity = abs(row['净占比'])
                                                ui.label(f'强度 {intensity:.1f}').classes('text-[10px] text-gray-400')
                                        
                                        # Data numbers
                                        with ui.column().classes('items-end gap-0'):
                                            flow_sign = "+" if row['净流入'] > 0 else ""
                                            ui.label(f'{flow_sign}{row["净流入"]:.1f}亿').classes(f'text-{type_color}-600 font-bold font-mono text-sm leading-tight')
                                            
                                            change_sign = "+" if row['涨跌幅'] > 0 else ""
                                            change_color = 'red' if row['涨跌幅'] > 0 else 'green' # Standard CN colors
                                            # Specific logic: Accumulation (Down) -> Green text, Divergence (Up) -> Red text
                                            
                                            ui.label(f'{change_sign}{row["涨跌幅"]:.2f}%').classes(f'text-{change_color}-500 font-mono text-xs')

                                # 1. Accumulation List (Top Half)
                                # Increased max-height to match new chart height roughly (700px total -> ~320px each)
                                with ui.column().classes('w-full flex-1 p-0 border-b border-gray-100'):
                                    with ui.row().classes('w-full p-3 bg-amber-50/30 border-l-4 border-amber-400 items-center justify-between'):
                                        with ui.row().classes('items-center gap-2'):
                                            ui.icon('vertical_align_bottom', color='amber-600').classes('text-sm')
                                            ui.label('隐形吸筹 (跌势入资)').classes('font-bold text-gray-800 text-xs tracking-wider')
                                        ui.label('资金流入 > 0 | 指数 < 0').classes('text-[10px] text-gray-400 scale-90 origin-right')
                                    
                                    with ui.column().classes('w-full p-0 gap-0 overflow-y-auto max-h-[320px] scrollbar-thin'):
                                        if not accumulating.empty:
                                            for _, row in accumulating.iterrows():
                                                render_list_item(row, 'rose', is_accum=True)
                                        else:
                                            with ui.row().classes('w-full justify-center py-6'):
                                                ui.label('当前无明显吸筹板块').classes('text-gray-400 text-xs italic')

                                # 2. Divergence List (Bottom Half)
                                with ui.column().classes('w-full flex-1 p-0'):
                                    with ui.row().classes('w-full p-3 bg-emerald-50/30 border-l-4 border-emerald-400 items-center justify-between'):
                                        with ui.row().classes('items-center gap-2'):
                                            ui.icon('warning_amber', color='emerald-600').classes('text-sm')
                                            ui.label('背离警示 (涨势出货)').classes('font-bold text-gray-800 text-xs tracking-wider')
                                        ui.label('资金流入 < 0 | 指数 > 0').classes('text-[10px] text-gray-400 scale-90 origin-right')
                                    
                                    with ui.column().classes('w-full p-0 gap-0 overflow-y-auto max-h-[320px] scrollbar-thin'):
                                        if not distributing.empty:
                                            for _, row in distributing.iterrows():
                                                render_list_item(row, 'emerald', is_accum=False)
                                        else:
                                            with ui.row().classes('w-full justify-center py-6'):
                                                ui.label('当前无明显背离板块').classes('text-gray-400 text-xs italic')

                # --- 3. Main Charts Section ---
                # Unified Spacing: removed mt-2 to match parent gap-6
                with ui.column().classes('w-full gap-6'):

                    # Chart B: Bubble / Scatter 
                    with ui.card().classes('w-full p-0 rounded-xl shadow-sm border border-gray-200 bg-white overflow-hidden'):
                        with ui.row().classes('w-full p-2 border-b border-gray-200 items-center justify-between px-3'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('bubble_chart', color='indigo').classes('text-xl')
                                ui.label('板块全景透视 (Panorama)').classes('font-bold text-gray-800 text-sm')
                            with ui.row().classes('text-xs gap-2'):
                                ui.label('红:上涨').classes('text-rose-500 font-bold')
                                ui.label('绿:下跌').classes('text-emerald-500 font-bold')

                        df_scatter = df_sorted.head(50).copy() 
                        max_val_scatter = df_scatter[metric_col].max()
                        if max_val_scatter <= 0: max_val_scatter = 1.0

                        bubble_sizes = (np.sqrt(df_scatter[metric_col].replace(0, 1)) / np.sqrt(max_val_scatter)) * 35 + 10

                        fig_scatter = go.Figure()
                        min_x = (df_scatter[metric_col].min() if not df_scatter[metric_col].empty else 0)
                        max_x = (df_scatter[metric_col].max() if not df_scatter[metric_col].empty else 1)
                        fig_scatter.add_shape(type="line", x0=min_x, y0=0, x1=max_x, y1=0, line=dict(color="gray", width=1, dash="dash"))

                        fig_scatter.add_trace(go.Scatter(
                            x=df_scatter[metric_col], y=df_scatter['涨跌幅'], mode='markers+text',
                            text=df_scatter['名称'], textposition="top center",
                            marker=dict(size=bubble_sizes, sizemode='diameter',
                                color=np.where(df_scatter['涨跌幅'] > 0, '#ef4444', '#10b981'), 
                                opacity=0.7, line=dict(color='white', width=1)),
                            hovertemplate='<b>%{text}</b><br>成交: %{x:.1f}亿<br>涨跌幅: %{y:.2f}%<extra></extra>'
                        ))
                        fig_scatter.update_layout(
                            height=400, margin=dict(l=60, r=20, t=10, b=40),
                            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                            xaxis=dict(title=f"成交活跃度 (亿)", gridcolor='#F3F4F6', showgrid=True),
                            yaxis=dict(title="板块涨跌幅 (%)", gridcolor='#F3F4F6'), showlegend=False, autosize=True
                        )
                        plot_func(fig_scatter).classes('w-full h-full min-h-[500px]')

                    # Chart A: Bar Chart
                    with ui.card().classes('w-full p-0 rounded-xl shadow-md border-0 bg-white overflow-hidden'):
                        with ui.row().classes('w-full p-3 border-b border-gray-200 items-center justify-between px-3'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('bar_chart', color='indigo').classes('text-xl')
                                ui.label(f'板块成交额热度 Top 20').classes('font-bold text-gray-800 text-sm')

                        x_vals = top_20['名称'].astype(str).tolist()
                        y_vals = top_20[metric_col]
                        colors = ['#ef4444' if r > 0 else '#22c55e' for r in top_20['涨跌幅'].tolist()]

                        fig_bar = go.Figure(go.Bar(
                            x=x_vals, y=y_vals, marker_color=colors,
                            text=[f"{v:.1f}亿" for v in y_vals], textposition='auto',
                            hovertemplate='%{x}<br>数值: %{y:.2f}亿<extra></extra>'
                        ))
                        fig_bar.update_layout(
                            height=350, margin=dict(l=40, r=20, t=10, b=60),
                            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                            yaxis=dict(gridcolor='#F3F4F6', tickfont=dict(size=11)), 
                            xaxis=dict(tickangle=-45, tickfont=dict(size=11)), 
                            autosize=True, title=None
                        )
                        plot_func(fig_bar).classes('w-full h-full min-h-[350px]')

    # --- Auto-load logic ---
    async def auto_load_logic():
        # Determine if "First Open" of the day for this client session
        client_key = f"fr_visited_{today_str}"
        
        # Read from localStorage via JS since app.storage.browser is problematic in callbacks
        # and standardizing with Money Flow module's approach.
        is_first_visit = False
        try:
            # 增加超时时间并捕获异常，防止因网络不稳定导致的崩溃
            stored_val = await ui.run_javascript(f'return localStorage.getItem("{client_key}")', timeout=10.0)
            is_first_visit = (stored_val != "true")
        except Exception as e:
            print(f"[FundRadar] Warning: localStorage check timeout or error: {e}. Defaulting to cached data.")
            is_first_visit = False

        mode_force = False
        if is_first_visit:
            # First time today: Force refresh as per requirement
            print(f"[FundRadar] First visit detected for {today_str}. Force refreshing...")
            # Write to localStorage
            ui.run_javascript(f'localStorage.setItem("{client_key}", "true")')
            mode_force = True
        
        await update_dashboard(today_str, force=mode_force)

    # Run init logic
    ui.timer(0, auto_load_logic, once=True)

    # --- Client-Side Poller (Reflect Background Updates) ---
    # Disabled to prevent interrupting user analysis
    # async def poll_for_monitor():
    #     # Poll cache to reflect backend updates (Monitor visual)
    #     # Checks every minute. force=False ensures we ONLY read cache, never fetch.
    #     if date_input.is_deleted: return
    #     if date_input.value == today_str:
    #         await update_dashboard(today_str, force=False)

    # ui.timer(60, poll_for_monitor)



