from nicegui import ui, app
import plotly.graph_objects as go
from utils.fund_radar import FundRadar
import pandas as pd
import numpy as np
import datetime
import asyncio

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

    # Define 2026 Trading Days Logic
    def get_2026_trading_days():
        # Closed weekdays (public holidays)
        holidays_2026 = {
            (1, 1), (1, 2),                          # 元旦
            (2, 16), (2, 17), (2, 18), (2, 19), (2, 20), (2, 23), # 春节
            (4, 6),                                  # 清明
            (5, 1), (5, 4), (5, 5),                  # 劳动节
            (6, 19),                                 # 端午
            (9, 25),                                 # 中秋
            (10, 1), (10, 2), (10, 5), (10, 6), (10, 7) # 国庆
        }
        
        start_date = datetime.date(2026, 1, 1)
        end_date = datetime.date(2026, 12, 31)
        valid_days = set() # Use set for O(1) lookup
        valid_days_list = [] # For return
        
        curr = start_date
        while curr <= end_date:
            # Keep weekday if not in holidays
            # 0=Mon, 4=Fri, 5=Sat, 6=Sun
            if curr.weekday() < 5 and (curr.month, curr.day) not in holidays_2026:
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
                    
                    # Update Duration Options based on Cache
                    def update_duration_options(date_val):
                        available_dates = radar.get_available_cache_dates()
                        try:
                            if date_val in available_dates:
                                idx = available_dates.index(date_val)
                                available_count = idx + 1
                            elif date_val == today_str: 
                                available_count = available_dates.index(date_val) + 1 if date_val in available_dates else 1
                            else:
                                available_count = 0 
                        except:
                            available_count = 0

                        # Map display labels to days following "Money Flow" style
                        possible_options = [
                            (1, '1天'),
                            (3, '3天'),
                            (5, '5天'),
                            (10, '10天'),
                            (20, '20天'),
                            (60, '60天')
                        ]
                        
                        options = {}
                        for d, label in possible_options:
                            # Show if only 1 day or enough data exists
                            if d == 1 or available_count >= d:
                                options[d] = label
                        
                        if radar_state['duration'] not in options:
                            radar_state['duration'] = 1
                            
                        duration_container.clear()
                        with duration_container:
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
             if len(df_top_scatter) > 50:
                 df_top_scatter = df_top_scatter.head(50)
             
             # Stats
             total_net = df['净流入'].sum()
             pos_df = df[df['净流入'] > 0]
             neg_df = df[df['净流入'] < 0]
             pos_ratio = (len(pos_df) / len(df) * 100) if not df.empty else 0
             avg_strength = df['资金强度'].mean()
             
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
                            ui.label(f'{avg_strength:+.3f}').classes(f'text-4xl font-black {"text-rose-500" if avg_strength > 0 else "text-emerald-500"}')
                            with ui.row().classes('items-center gap-1'):
                                ui.label('平均进攻强度').classes('text-xs font-bold text-gray-400')
                                with ui.icon('help_outline', color='gray-400').classes('text-xs cursor-help'):
                                    ui.tooltip('该指标衡量资金流入成交额的效率，正值越高代表进攻欲望越强。').classes('text-xs')
                        
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
                                ui.label(f'强度 {max_strength["资金强度"]:.3f}').classes('text-xs bg-indigo-50 text-indigo-400 px-2 py-0.5 rounded font-bold')
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
                              f"板块: {row.名称}<br>净流入: {row.净流入:.1f}亿<br>强度: {row.资金强度:.3f}<br>成交: {row.总成交额:.1f}亿<br>活跃: {row.活跃天数}天"
                              for row in df_top_scatter.itertuples()
                          ]
                          
                          # Determine colors based on Net Inflow (Red for positive, Green for negative)
                          colors = ['#ef4444' if row.净流入 > 0 else '#10b981' for row in df_top_scatter.itertuples()]
                          
                          # Size calculation (Adjusted for better visuals)
                          size_ref = df_top_scatter['总成交额'].max() if not df_top_scatter.empty else 1
                          sizes = (np.sqrt(df_top_scatter['总成交额']) / np.sqrt(size_ref)) * 40 + 10

                          fig_scatter.add_trace(go.Scatter(
                              x=df_top_scatter['净流入'],
                              y=df_top_scatter['资金强度'],
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
                              yaxis_title='资金强度 (净流入/成交额)',
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


        async def update_dashboard(date_val, force=False):
            check_refresh_visibility() # Update button state
            dashboard_content.clear()
            
            # Determine duration
            duration = radar_state['duration']

            with dashboard_content:
                # Loading State
                with ui.column().classes('w-full items-center justify-center py-12'):
                    ui.spinner(type='dots', size='3rem', color='indigo')
                    ui.label(f'正在加载 {date_val} (过去{duration}天) 数据...').classes('text-gray-400 mt-4 animate-pulse')
            
            loop = asyncio.get_running_loop()

            # --- Multi Data Logic ---
            if duration > 1:
                df_agg, used_dates = await loop.run_in_executor(
                    None, lambda: radar.get_multi_day_data(date_val, duration)
                )
                
                dashboard_content.clear()
                with dashboard_content:
                    if df_agg.empty:
                        with ui.card().classes('w-full p-8 items-center justify-center bg-white rounded-xl shadow-sm border border-gray-200'):
                             ui.icon('history_edu', size='4rem', color='grey-4')
                             ui.label(f'过去 {duration} 天数据不足').classes('text-xl text-gray-500 font-bold mt-4')
                             ui.label('请尝试选择更近的日期或单日视图').classes('text-gray-400')
                    else:
                        render_multi_day_view(df_agg, used_dates, plot_func)
                return

            # --- Single Day Logic (Original) ---


            # Fetch data 
            # Returns: Sina DF (Amount), THS DF (Net Inflow), Market Snapshot
            # Use 'FORCE_UPDATE' if force is True, else 'READ_CACHE'
            mode = 'FORCE_UPDATE' if force else 'READ_CACHE'
            loop = asyncio.get_running_loop()
            df_flow, df_ths, market_snap_data = await loop.run_in_executor(
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
                if df_flow.empty and df_ths.empty:
                    with ui.card().classes('w-full p-8 items-center justify-center bg-white rounded-xl shadow-sm border border-gray-200'):
                        if date_val == today_str:
                             ui.icon('cloud_off', size='4rem', color='grey-4')
                             ui.label('今日暂无数据').classes('text-xl text-gray-500 font-bold mt-4')
                             ui.label('请检查网络，或尝试点击右上角“强制刷新”按钮').classes('text-gray-400')
                        else:
                             ui.icon('history_toggle_off', size='4rem', color='grey-4')
                             ui.label('历史数据未缓存').classes('text-xl text-gray-500 font-bold mt-4')
                             ui.label('该日期没有本地缓存记录，无法回溯。').classes('text-gray-400')
                    return

                # --- Metric Logic (Sina / Default) ---
                metric_col = '成交额'

                # Ensure Types for Sina DF
                if not df_flow.empty:
                    # Data is now normalized to '亿' (100M) by FundRadar class
                    df_flow[metric_col] = pd.to_numeric(df_flow[metric_col], errors='coerce').fillna(0)
                    
                    if '涨跌幅' in df_flow.columns:
                        df_flow['涨跌幅'] = pd.to_numeric(df_flow['涨跌幅'], errors='coerce').fillna(0)
                    else:
                        df_flow['涨跌幅'] = 0.0

                    df_sorted = df_flow.sort_values(by=metric_col, ascending=False)
                    top_10 = df_sorted.head(10)
                    top_20 = df_sorted.head(20)
                else:
                     df_flow = pd.DataFrame(columns=['名称', '涨跌幅', metric_col])
                     df_sorted = df_flow
                     top_10 = df_flow
                     top_20 = df_flow

                # Ensure Types for THS DF (Net Inflow)
                if not df_ths.empty:
                     df_ths['净流入'] = pd.to_numeric(df_ths['净流入'], errors='coerce').fillna(0)
                     if '总成交额' in df_ths.columns:
                         df_ths['总成交额'] = pd.to_numeric(df_ths['总成交额'], errors='coerce').fillna(0)
                     df_ths['涨跌幅'] = pd.to_numeric(df_ths['涨跌幅'], errors='coerce').fillna(0)
                     # Calculate Main Force Net Inflow Ratio
                     df_ths['净占比'] = (df_ths['净流入'] / df_ths['总成交额'].replace(0, 1)) * 100

                # Create Combined DF for Leaderboard (Join Sina Turnover + THS Inflow)
                if not df_flow.empty and not df_ths.empty:
                    df_leader = pd.merge(df_flow, df_ths[['名称', '净流入', '净占比']], on='名称', how='left')
                elif not df_flow.empty:
                    df_leader = df_flow.copy()
                    df_leader['净流入'] = np.nan
                    df_leader['净占比'] = np.nan
                else:
                    df_leader = df_ths.copy()
                    if metric_col not in df_leader.columns: df_leader[metric_col] = df_leader.get('总成交额', 0)

                offensive, defensive = radar.get_offensive_defensive_list()

                # Turnover / Market Nature Analysis (Preferred Source: Sina for Money Flow)
                analysis_df = top_10 if not top_10.empty else (df_ths.head(10) if not df_ths.empty else pd.DataFrame())
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
                
                with ui.grid(columns=3 if not is_mobile else 1).classes('w-full gap-3 md:gap-4 px-1'):

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


                # --- 4. Confrontation (Battlefield) Section (Moved to Top) ---
                # Uses market_snap_data from tuple (Fetched or Cached)

                if market_snap_data:
                    mkt_chg = market_snap_data.get('change_pct', 0.0)
                    with ui.card().classes('w-full p-0 rounded-xl shadow-sm border border-gray-200 bg-white overflow-hidden mt-3'):
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
                # --- NEW SECTION: THS Deep Insight Analysis ---
                if not df_ths.empty:
                    # 1. Data Processing & Derived Metrics
                    # Note: Data is already normalized to '亿' by FundRadar
                    df_ths_clean = df_ths.copy()

                    # Avoid division by zero
                    df_ths_clean['净占比'] = (df_ths_clean['净流入'] / (df_ths_clean['总成交额'].replace(0, 1))) * 100

                    # Sort by absolute inflow impact for bubble size
                    df_ths_clean['abs_inflow'] = df_ths_clean['净流入'].abs()

                    # Filter for visualization noise reduction (keep top 80% by volume or just all non-tiny)
                    # df_ths_viz = df_ths_clean[df_ths_clean['总成交额'] > (max_turnover * 0.02)] 

                    with ui.card().classes('w-full p-0 rounded-xl shadow-sm border border-gray-200 bg-white overflow-hidden'):
                        with ui.row().classes('w-full p-4 border-b border-gray-200 items-center justify-between'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('psychology', color='indigo').classes('text-xl')
                                ui.label('主力动向四象限 (Main Force Intent Map)').classes('font-bold text-gray-800')
                            with ui.row().classes('items-center gap-2 text-xs text-gray-500'):
                                ui.label('X轴: 市场涨跌').classes('px-2 py-0.5 bg-gray-100 rounded')
                                with ui.row().classes('items-center gap-1 px-2 py-0.5 bg-indigo-50 text-indigo-500 rounded cursor-help'):
                                    ui.label('Y轴: 主力净占比')
                                    ui.icon('info', size='14px')
                                    ui.tooltip('主力净占比 = (主力净流入 / 总成交额) * 100%。反映单位成交量中主力介入的“密度”，比单纯的金额更能剔除盘子大小的影响。').classes('text-xs')

                        # Prepare Quadrant Data
                        # Q1: Up + Inflow (Bullish Consensus)
                        # Q2: Down + Inflow (Hidden Accumulation)
                        # Q3: Down + Outflow (Panic/Bearish)
                        # Q4: Up + Outflow (Divergence/Distribution)

                        fig_map = go.Figure()

                        # Add Quadrant Backgrounds/Lines
                        fig_map.add_hline(y=0, line_width=1, line_dash="solid", line_color="rgba(0,0,0,0.1)")
                        fig_map.add_vline(x=0, line_width=1, line_dash="solid", line_color="rgba(0,0,0,0.1)")

                        # Plot Scatter
                        # Color: Red for Inflow, Green for Outflow
                        colors = ['#ef4444' if x > 0 else '#10b981' for x in df_ths_clean['净流入']]

                        # Size: Based on 'abs_inflow' (Actual money amount impact)
                        # Normalize check
                        size_ref = df_ths_clean['abs_inflow'].max() if df_ths_clean['abs_inflow'].max() > 0 else 1
                        sizes = (np.sqrt(df_ths_clean['abs_inflow']) / np.sqrt(size_ref)) * 30 + 8

                        fig_map.add_trace(go.Scatter(
                            x=df_ths_clean['涨跌幅'],
                            y=df_ths_clean['净占比'],
                            mode='markers+text',
                            text=df_ths_clean['名称'],
                            textposition='top center',
                            textfont=dict(size=10, color='rgba(0,0,0,0.6)'),
                            marker=dict(
                                size=sizes,
                                color=colors,
                                opacity=0.7,
                                line=dict(width=1, color='white')
                            ),
                            hovertemplate='<b>%{text}</b><br>涨跌: %{x:.2f}%<br>主力净占比: %{y:.2f}%<br>净流入额: %{customdata:.2f}亿<extra></extra>',
                            customdata=df_ths_clean['净流入']
                        ))

                        # Annotations for Quadrants (Generic)
                        quad_anns = [
                            dict(x=1, y=1, xref='x domain', yref='y domain', text="🔥 强力做多", showarrow=False, font=dict(color='rgba(239, 68, 68, 0.2)', size=20, weight='bold'), xanchor='right', yanchor='top'),
                            dict(x=0, y=1, xref='x domain', yref='y domain', text="🛡️ 逆势吸筹", showarrow=False, font=dict(color='rgba(245, 158, 11, 0.2)', size=20, weight='bold'), xanchor='left', yanchor='top'),
                            dict(x=1, y=0, xref='x domain', yref='y domain', text="⚠️ 拉高出货", showarrow=False, font=dict(color='rgba(16, 185, 129, 0.2)', size=20, weight='bold'), xanchor='right', yanchor='bottom'),
                            dict(x=0, y=0, xref='x domain', yref='y domain', text="❄️ 合力做空", showarrow=False, font=dict(color='rgba(107, 114, 128, 0.2)', size=20, weight='bold'), xanchor='left', yanchor='bottom')
                        ]
                        for ann in quad_anns:
                            fig_map.add_annotation(ann)

                        fig_map.update_layout(
                            height=550, margin=dict(l=40, r=40, t=20, b=40),
                            plot_bgcolor='rgba(252,252,252,1)', paper_bgcolor='rgba(0,0,0,0)',
                            xaxis=dict(title="板块涨跌幅 (%)", zeroline=False, gridcolor='#F3F4F6'),
                            yaxis=dict(title="主力资金净占比 (%)", zeroline=False, gridcolor='#F3F4F6'),
                            showlegend=False
                        )
                        plot_func(fig_map).classes('w-full h-full min-h-[550px]')

                    # 2. Insight Cards (Divergence & Accumulation)
                    # Accumulation: Down > 0 (or just negative) AND Inflow > 0
                    # Rank by Inflow Ratio (Density of buying)
                    accumulating = df_ths_clean[ (df_ths_clean['涨跌幅'] < 0) & (df_ths_clean['净流入'] > 0) ].sort_values('净占比', ascending=False).head(5)

                    # Distribution: Up > 0 AND Inflow < 0
                    # Rank by Outflow Intensity
                    distributing = df_ths_clean[ (df_ths_clean['涨跌幅'] > 0) & (df_ths_clean['净流入'] < 0) ].sort_values('净占比', ascending=True).head(5)

                    if not accumulating.empty or not distributing.empty:
                        with ui.grid(columns=2 if not is_mobile else 1).classes('w-full gap-3 mt-2'):
                            # Accumulation List
                            with ui.card().classes('w-full p-2 rounded-xl shadow-sm border border-amber-50 bg-amber-50/50'):
                                with ui.row().classes('items-center gap-2 mb-1'):
                                    ui.icon('vertical_align_bottom', color='amber').classes('text-lg')
                                    with ui.column().classes('gap-0'):
                                        ui.label('隐形吸筹榜 (Accumulation)').classes('font-black text-gray-800 text-xs uppercase')
                                        ui.label('下跌但主力净流入').classes('text-xs text-gray-400')

                                if not accumulating.empty:
                                    for _, row in accumulating.iterrows():
                                        with ui.row().classes('w-full items-center justify-between py-1.5 border-b border-amber-100 last:border-0'):
                                            ui.label(row['名称']).classes('font-bold text-gray-700 text-sm')
                                            with ui.row().classes('gap-2 items-center'):
                                                ui.label(f"{row['涨跌幅']:.2f}%").classes('text-emerald-500 font-mono text-xs')
                                                ui.label(f"{row['净流入']:.1f}亿").classes('text-rose-500 font-black text-sm')
                                else:
                                    ui.label('暂无明显数据').classes('text-gray-400 text-xs italic')

                            # Distribution List
                            with ui.card().classes('w-full p-2 rounded-xl shadow-sm border border-emerald-50 bg-emerald-50/50'):
                                with ui.row().classes('items-center gap-2 mb-1'):
                                    ui.icon('warning', color='emerald').classes('text-lg')
                                    with ui.column().classes('gap-0'):
                                        ui.label('背离警示榜 (Divergence)').classes('font-black text-gray-800 text-xs uppercase')
                                        ui.label('上涨但主力净流出').classes('text-xs text-gray-400')

                                if not distributing.empty:
                                    for _, row in distributing.iterrows():
                                        with ui.row().classes('w-full items-center justify-between py-1.5 border-b border-emerald-100 last:border-0'):
                                            ui.label(row['名称']).classes('font-bold text-gray-700 text-sm')
                                            with ui.row().classes('gap-2 items-center'):
                                                ui.label(f"+{row['涨跌幅']:.2f}%").classes('text-rose-500 font-mono text-xs')
                                                ui.label(f"{abs(row['净流入']):.1f}亿").classes('text-emerald-500 font-black text-sm')
                                else:
                                    ui.label('暂无明显数据').classes('text-gray-400 text-xs italic')
                # --- 3. Main Charts Section ---
                with ui.column().classes('w-full gap-4 mt-2'):

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
    ui.timer(0.1, auto_load_logic, once=True)

    # --- Client-Side Poller (Reflect Background Updates) ---
    async def poll_for_monitor():
        # Poll cache to reflect backend updates (Monitor visual)
        # Checks every minute. force=False ensures we ONLY read cache, never fetch.
        if date_input.value == today_str:
            await update_dashboard(today_str, force=False)

    ui.timer(60, poll_for_monitor)



