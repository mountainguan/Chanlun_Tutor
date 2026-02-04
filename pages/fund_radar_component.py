from nicegui import ui
import plotly.graph_objects as go
from utils.fund_radar import FundRadar
import pandas as pd
import numpy as np
import datetime

def render_fund_radar_panel(plotly_renderer=None, is_mobile=False):
    """
    Render the Fund Radar Panel with Daily Cache Mechanism.
    """
    radar = FundRadar()
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    
    # Use provided renderer or fallback to ui.plotly
    plot_func = plotly_renderer if plotly_renderer else ui.plotly
    
    # Main Container
    with ui.column().classes('w-full min-h-screen p-4 md:p-6 gap-6 functionality-container'):
        
        # 1. Header & Controls Section
        with ui.card().classes('w-full rounded-xl shadow-sm border-0 bg-white p-4'):
             with ui.row().classes('w-full items-center justify-between wrap gap-4'):
                # Left: Title
                with ui.row().classes('items-center gap-3'):
                    with ui.element('div').classes('p-2 bg-indigo-50 rounded-lg'):
                        ui.icon('radar', color='indigo').classes('text-2xl')
                    with ui.column().classes('gap-0'):
                        ui.label('主力资金雷达').classes('text-xl font-bold text-gray-800 tracking-tight')
                        ui.label('Sector Heat Radar (Sina Source)').classes('text-xs text-gray-400 font-medium')
                
                # Right: Controls (Date Picker & Refresh)
                with ui.row().classes('items-center gap-3'):
                    
                    # Date Picker Logic
                    # We can't easily restrict min/max in q-date via standard element props for simple NiceGUI date,
                    # but we can validate in logic.
                    # Default value is Today.
                    date_input = ui.input('选择日期 (Date)', value=today_str).props('outlined dense bg-white readonly').classes('w-40')
                    with date_input.add_slot('append'):
                        ui.icon('event').classes('cursor-pointer') \
                            .on('click', lambda: date_menu.open())
                        with ui.menu() as date_menu:
                            ui.date(on_change=lambda e: (date_input.set_value(e.value), date_menu.close(), update_dashboard(e.value))) \
                                .props(f'mask="YYYY-MM-DD"') # Optional: limit navigation

                    refresh_btn = ui.button('强制刷新今日数据', icon='refresh', on_click=lambda: update_dashboard(date_input.value, force=True)) \
                        .props('flat color=red').classes('font-bold bg-red-50 hover:bg-red-100')
                    
                    # Only show refresh if date is today (Client-side visibility toggle logic inside update?)
                    # Simplified: We just check inside the button handler or disable it visually?
                    # Let's bind visibility.
                    def check_refresh_visibility():
                        is_today = (date_input.value == today_str)
                        refresh_btn.set_visibility(is_today)
                    
                    date_input.on_value_change(check_refresh_visibility)

        # 2. Status & Dashboard Area
        dashboard_content = ui.column().classes('w-full gap-6')

        def update_dashboard(date_val, force=False):
            check_refresh_visibility() # Update button state
            dashboard_content.clear()
            
            with dashboard_content:
                # Loading State
                with ui.column().classes('w-full items-center justify-center py-12'):
                    ui.spinner(type='dots', size='3rem', color='indigo')
                    ui.label(f'正在加载 {date_val} 数据...').classes('text-gray-400 mt-4 animate-pulse')

            # Fetch data 
            # Note: get_sector_data_by_date handles caching internally
            df_flow, market_snap_data = radar.get_sector_data_by_date(date_val, force_refresh=force)
            
            dashboard_content.clear()
            
            with dashboard_content:
                if df_flow.empty:
                    with ui.card().classes('w-full p-8 items-center justify-center bg-white rounded-xl shadow-sm border border-gray-100'):
                        if date_val == today_str:
                             ui.icon('cloud_off', size='4rem', color='grey-4')
                             ui.label('今日暂无数据').classes('text-xl text-gray-500 font-bold mt-4')
                             ui.label('请检查网络，或尝试点击右上角“强制刷新”按钮').classes('text-gray-400')
                        else:
                             ui.icon('history_toggle_off', size='4rem', color='grey-4')
                             ui.label('历史数据未缓存').classes('text-xl text-gray-500 font-bold mt-4')
                             ui.label('该日期没有本地缓存记录，无法回溯。').classes('text-gray-400')
                    return
                
                # --- Metric Logic (Always '成交额' for Sina) ---
                metric_col = '成交额'
                is_fallback_mode = True # Always True for this pure Sina version
                
                # Ensure Types
                df_flow[metric_col] = pd.to_numeric(df_flow[metric_col], errors='coerce').fillna(0)
                if '涨跌幅' in df_flow.columns:
                    df_flow['涨跌幅'] = pd.to_numeric(df_flow['涨跌幅'], errors='coerce').fillna(0)
                else:
                    df_flow['涨跌幅'] = 0.0

                # --- 1. Top & Analysis Logic ---
                df_sorted = df_flow.sort_values(by=metric_col, ascending=False)
                top_10 = df_sorted.head(10)
                top_20 = df_sorted.head(20) # Use top 20 for charts
                
                offensive, defensive = radar.get_offensive_defensive_list()
                
                # Turnover Analysis
                avg_chg_top10 = top_10['涨跌幅'].mean()
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

                with ui.grid(columns=3 if not is_mobile else 1).classes('w-full gap-6'):
                    
                    # Card 1: Market Nature
                    with ui.card().classes(f'w-full p-4 rounded-xl shadow-sm border {border_theme} {bg_theme} relative overflow-hidden'):
                         ui.icon(icon_theme).classes('absolute -right-4 -bottom-4 text-8xl opacity-10')
                         ui.label('市场性质判定').classes('text-gray-500 text-xs font-bold uppercase tracking-wider')
                         ui.label(market_nature).classes(f'text-xl font-extrabold mt-1 {text_theme}')
                         ui.label(nature_desc).classes('text-gray-600 text-sm mt-2 leading-relaxed')

                    # Card 2: Top Sector
                    top_sector_name = top_10.iloc[0]['名称']
                    top_sector_val = top_10.iloc[0][metric_col]
                    val_str = f"{top_sector_val/1e8:.2f}亿" if top_sector_val > 1e8 else f"{top_sector_val/1e4:.0f}万"
                    
                    with ui.card().classes('w-full p-4 rounded-xl shadow-sm border border-gray-100 bg-white'):
                        with ui.row().classes('items-center justify-between w-full'):
                            ui.label('Top1 成交额').classes('text-gray-500 text-xs font-bold uppercase tracking-wider')
                            ui.icon('emoji_events', color='amber').classes('text-xl')
                        
                        ui.label(top_sector_name).classes('text-2xl font-extrabold text-gray-800 mt-1')
                        with ui.row().classes('items-center gap-1 mt-1'):
                            ui.label(val_str).classes('text-lg font-bold text-indigo-600')
                            ui.label('热度领跑').classes('text-xs bg-indigo-50 text-indigo-500 px-2 py-0.5 rounded-full')

                    # Card 3: Avg Performance
                    avg_change = top_10['涨跌幅'].mean()
                    chg_color = "red-500" if avg_change > 0 else "emerald-500"
                    sign = "+" if avg_change > 0 else ""
                    
                    with ui.card().classes('w-full p-4 rounded-xl shadow-sm border border-gray-100 bg-white'):
                        ui.label('Top10平均涨幅').classes('text-gray-500 text-xs font-bold uppercase tracking-wider')
                        with ui.row().classes('items-baseline gap-1 mt-1'):
                            ui.label(f"{sign}{avg_change:.2f}").classes(f'text-3xl font-extrabold text-{chg_color}')
                            ui.label('%').classes(f'text-lg font-bold text-{chg_color}')
                        
                        ui.label('头部板块整体表现').classes('text-gray-400 text-sm mt-1')

                # --- 4. Confrontation (Battlefield) Section (Moved to Top) ---
                # Uses market_snap_data from tuple (Fetched or Cached)
                
                if market_snap_data:
                    mkt_chg = market_snap_data.get('change_pct', 0.0)
                    with ui.card().classes('w-full p-0 rounded-xl shadow-md border-0 bg-white overflow-hidden mt-0'):
                        with ui.row().classes('w-full p-4 border-b border-gray-100 items-center justify-between'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('compare_arrows', color='indigo').classes('text-xl')
                                ui.label('多空阵营博弈 (Offense vs Defense)').classes('font-bold text-gray-800')
                            ui.label(f'上证基准: {mkt_chg:+.2f}%').classes('text-sm font-bg bg-gray-100 px-2 py-1 rounded text-gray-600')

                        df_flow['alpha'] = df_flow['涨跌幅'] - mkt_chg
                        df_off = df_flow[df_flow['名称'].isin(offensive)].sort_values(by='alpha', ascending=False).head(8).iloc[::-1]
                        df_def = df_flow[df_flow['名称'].isin(defensive)].sort_values(by='alpha', ascending=False).head(8).iloc[::-1]

                        from plotly.subplots import make_subplots
                        fig_battle = make_subplots(rows=1, cols=2, shared_yaxes=False, horizontal_spacing=0.15,
                            subplot_titles=("🛡️ 防守阵营 (Defensive)", "⚔️ 进攻阵营 (Offensive)"))
                        
                        def_text = [f"{n} ({v:+.2f}%)" for n, v in zip(df_def['名称'], df_def['涨跌幅'])]
                        fig_battle.add_trace(go.Bar(
                            y=df_def['名称'], x=df_def['alpha'], orientation='h',
                            marker_color=['#10b981' if a > 0 else '#6b7280' for a in df_def['alpha']],
                            text=def_text, textposition='auto', name='防守Alpha'
                        ), row=1, col=1)

                        off_text = [f"{n} ({v:+.2f}%)" for n, v in zip(df_off['名称'], df_off['涨跌幅'])]
                        fig_battle.add_trace(go.Bar(
                            y=df_off['名称'], x=df_off['alpha'], orientation='h',
                            marker_color=['#ef4444' if a > 0 else '#6b7280' for a in df_off['alpha']],
                            text=off_text, textposition='auto', name='进攻Alpha'
                        ), row=1, col=2)
                        
                        max_alpha = max(df_off['alpha'].abs().max() if not df_off.empty else 0, df_def['alpha'].abs().max() if not df_def.empty else 0, 3.0)
                        range_limit = max_alpha * 1.2
                        fig_battle.update_layout(
                            height=400, margin=dict(l=20, r=20, t=50, b=20), showlegend=False,
                            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                        )
                        fig_battle.update_xaxes(title_text="Alpha (%)", range=[-range_limit, range_limit], zeroline=True, zerolinewidth=2, zerolinecolor='gray')
                        plot_func(fig_battle).classes('w-full h-full min-h-[400px]')
                else:
                    # Message about missing history for Battlefield
                    with ui.row().classes('w-full justify-center p-4'):
                        reason = "今日获取失败" if date_val == today_str else "历史数据未包含大盘快照"
                        ui.label(f'多空博弈无法显示：{reason}').classes('text-gray-400 italic text-sm')

                # --- 3. Main Charts Section ---
                with ui.column().classes('w-full gap-6'):
                    
                    # Chart B: Bubble / Scatter 
                    with ui.card().classes('w-full p-0 rounded-xl shadow-md border-0 bg-white overflow-hidden'):
                        with ui.row().classes('w-full p-4 border-b border-gray-100 items-center justify-between'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('bubble_chart', color='indigo').classes('text-xl')
                                ui.label('板块全景透视 (Panorama - Top 50)').classes('font-bold text-gray-800')
                            with ui.row().classes('text-xs gap-2'):
                                ui.label('红:上涨').classes('text-red-500 font-bold')
                                ui.label('绿:下跌').classes('text-emerald-500 font-bold')

                        df_scatter = df_sorted.head(50).copy() 
                        max_val_scatter = df_scatter[metric_col].max()
                        if max_val_scatter <= 0: max_val_scatter = 1.0
                        
                        bubble_sizes = (np.sqrt(df_scatter[metric_col].replace(0, 1)) / np.sqrt(max_val_scatter)) * 45 + 15

                        fig_scatter = go.Figure()
                        min_x = (df_scatter[metric_col].min() if not df_scatter[metric_col].empty else 0) / 1e8
                        max_x = (df_scatter[metric_col].max() if not df_scatter[metric_col].empty else 1) / 1e8
                        fig_scatter.add_shape(type="line", x0=min_x, y0=0, x1=max_x, y1=0, line=dict(color="gray", width=1, dash="dash"))

                        fig_scatter.add_trace(go.Scatter(
                            x=df_scatter[metric_col] / 1e8, y=df_scatter['涨跌幅'], mode='markers+text',
                            text=df_scatter['名称'], textposition="top center",
                            marker=dict(size=bubble_sizes, sizemode='diameter',
                                color=np.where(df_scatter['涨跌幅'] > 0, '#ef4444', '#10b981'), 
                                opacity=0.7, line=dict(color='white', width=1)),
                            hovertemplate='<b>%{text}</b><br>成交: %{x:.1f}亿<br>涨跌幅: %{y:.2f}%<extra></extra>'
                        ))
                        fig_scatter.update_layout(
                            height=500, margin=dict(l=60, r=20, t=30, b=50),
                            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                            xaxis=dict(title=f"成交活跃度 (亿)", gridcolor='#F3F4F6', showgrid=True),
                            yaxis=dict(title="板块涨跌幅 (%)", gridcolor='#F3F4F6'), showlegend=False, autosize=True
                        )
                        plot_func(fig_scatter).classes('w-full h-full min-h-[500px]')

                    # Chart A: Bar Chart
                    with ui.card().classes('w-full p-0 rounded-xl shadow-md border-0 bg-white overflow-hidden'):
                        with ui.row().classes('w-full p-4 border-b border-gray-100 items-center justify-between'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('bar_chart', color='indigo').classes('text-xl')
                                ui.label(f'板块成交额热度 Top 20 (排行)').classes('font-bold text-gray-800')
                        
                        x_vals = top_20['名称'].astype(str).tolist()
                        y_vals = top_20[metric_col]
                        colors = ['#ef4444' if r > 0 else '#22c55e' for r in top_20['涨跌幅'].tolist()]

                        fig_bar = go.Figure(go.Bar(
                            x=x_vals, y=y_vals, marker_color=colors,
                            text=[f"{v/1e8:.1f}" for v in y_vals], textposition='auto',
                            texttemplate='%{text}亿' if y_vals.abs().mean() > 1e8 else '%{text}',
                            hovertemplate='%{x}<br>数值: %{y:.2f}<extra></extra>'
                        ))
                        fig_bar.update_layout(
                            height=400, margin=dict(l=40, r=20, t=20, b=80),
                            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                            yaxis=dict(gridcolor='#F3F4F6'), xaxis=dict(tickangle=-45), autosize=True, title=None
                        )
                        plot_func(fig_bar).classes('w-full h-full min-h-[400px]')

    # Auto-load today on init
    ui.timer(0.1, lambda: update_dashboard(today_str), once=True)



