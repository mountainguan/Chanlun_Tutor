from nicegui import ui
import plotly.graph_objects as go
from utils.fund_radar import FundRadar
import pandas as pd
import numpy as np

def render_fund_radar_panel(plotly_renderer=None, is_mobile=False):
    """
    Render the Fund Radar Panel with High-End Dashboard Design.
    """
    radar = FundRadar()
    
    # Use provided renderer or fallback to ui.plotly
    plot_func = plotly_renderer if plotly_renderer else ui.plotly
    
    # Main Container with gray background for dashboard feel
    with ui.column().classes('w-full min-h-screen p-4 md:p-6 gap-6 functionality-container'):
        
        # 1. Header & Controls Section
        # Using a clean white card for the control bar
        with ui.card().classes('w-full rounded-xl shadow-sm border-0 bg-white p-4'):
             with ui.row().classes('w-full items-center justify-between wrap gap-4'):
                # Left: Title
                with ui.row().classes('items-center gap-3'):
                    with ui.element('div').classes('p-2 bg-indigo-50 rounded-lg'):
                        ui.icon('radar', color='indigo').classes('text-2xl')
                    with ui.column().classes('gap-0'):
                        ui.label('主力资金雷达').classes('text-xl font-bold text-gray-800 tracking-tight')
                        ui.label('Main Force Radar').classes('text-xs text-gray-400 font-medium')
                
                # Right: Controls
                with ui.row().classes('items-center gap-3'):
                    days_select = ui.select(
                        {'0': '今日 (实时)', '3': '3日 (资金流)', '5': '5日 (资金流)', '10': '10日 (资金流)'}, 
                        value='0', 
                    ).props('outlined dense bg-white').classes('w-40')
                    
                    analyze_btn = ui.button('分析资金流向', icon='analytics', on_click=lambda: update_dashboard(int(days_select.value))) \
                        .props('flat color=indigo').classes('font-bold bg-indigo-50 hover:bg-indigo-100')

        # 2. Status & Dashboard Area
        dashboard_content = ui.column().classes('w-full gap-6')

        def update_dashboard(days):
            dashboard_content.clear()
            
            with dashboard_content:
                # Loading State
                with ui.column().classes('w-full items-center justify-center py-12'):
                    ui.spinner(type='dots', size='3rem', color='indigo')
                    ui.label('正如雷达扫描般获取数据...').classes('text-gray-400 mt-4 animate-pulse')

            # Fetch data 
            df_flow = radar.get_sector_flow_ranking(days)
            
            dashboard_content.clear()
            
            with dashboard_content:
                if df_flow.empty:
                    with ui.card().classes('w-full p-8 items-center justify-center bg-white rounded-xl shadow-sm border border-gray-100'):
                        ui.icon('cloud_off', size='4rem', color='grey-4')
                        ui.label('暂无数据回应').classes('text-xl text-gray-500 font-bold mt-4')
                        ui.label('请检查网络连接或稍后再试').classes('text-gray-400')
                    return
                
                # --- Mode Detection ---
                has_net_flow = '主力净流入-净额' in df_flow.columns
                is_fallback_mode = not has_net_flow
                metric_col = '主力净流入-净额' if has_net_flow else '成交额'
                
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
                top_names = top_10['名称'].tolist()
                
                off_count = sum(1 for n in top_names if n in offensive)
                def_count = sum(1 for n in top_names if n in defensive)
                
                market_nature = "未知"
                nature_desc = ""
                nature_color = "gray"
                
                if not is_fallback_mode:
                    if off_count > def_count:
                        market_nature = "进攻态势 (Offensive)"
                        nature_desc = "主力资金大幅流入科技/成长板块，市场攻击欲望较强。"
                        nature_color = "red"
                    elif def_count > off_count:
                        market_nature = "防守态势 (Defensive)"
                        nature_desc = "主力资金回流权重/红利板块，避险情绪升温。"
                        nature_color = "green" # Green means defensive strategy
                    else:
                        market_nature = "轮动僵持 (Rotation)"
                        nature_desc = "资金流向分散，多空博弈焦灼。"
                        nature_color = "yellow"
                else:
                    # Turnover Analysis
                    avg_chg_top10 = top_10['涨跌幅'].mean()
                    if avg_chg_top10 > 1.0:
                        market_nature = "放量上攻 (Strong)"
                        nature_desc = "板块普遍放量上涨，交投活跃，多头主导。"
                        nature_color = "red"
                    elif avg_chg_top10 < -1.0:
                        market_nature = "放量下杀 (Panic)"
                        nature_desc = "高成交换手下大幅下跌，恐慌盘涌出。"
                        nature_color = "green" # Green usually means down
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
                if is_fallback_mode:
                     with ui.row().classes('w-full bg-orange-50 border border-orange-200 rounded-lg p-3 items-center gap-3 animate-fade-in'):
                        ui.icon('warning', color='orange').classes('text-xl')
                        ui.label('当前处于接口降级模式：由于主力资金数据不可用，系统已自动切换至【成交额热度】分析算法。').classes('text-orange-800 text-sm font-medium')

                with ui.grid(columns=3 if not is_mobile else 1).classes('w-full gap-6'):
                    
                    # Card 1: Market Nature
                    with ui.card().classes(f'w-full p-4 rounded-xl shadow-sm border {border_theme} {bg_theme} relative overflow-hidden'):
                         # Decorator
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
                            ui.label(f'Top1 {"净流入" if not is_fallback_mode else "成交额"}').classes('text-gray-500 text-xs font-bold uppercase tracking-wider')
                            ui.icon('emoji_events', color='amber').classes('text-xl')
                        
                        ui.label(top_sector_name).classes('text-2xl font-extrabold text-gray-800 mt-1')
                        with ui.row().classes('items-center gap-1 mt-1'):
                            ui.label(val_str).classes('text-lg font-bold text-indigo-600')
                            ui.label('强度领跑').classes('text-xs bg-indigo-50 text-indigo-500 px-2 py-0.5 rounded-full')

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

                # --- 3. Main Charts Section ---
                # Vertical Stack for Full Width Charts
                with ui.column().classes('w-full gap-6'):
                    
                    # Chart A: Bar Chart
                    with ui.card().classes('w-full p-0 rounded-xl shadow-md border-0 bg-white overflow-hidden'):
                        # Header
                        with ui.row().classes('w-full p-4 border-b border-gray-100 items-center justify-between'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('bar_chart', color='indigo').classes('text-xl')
                                ui.label(f'{"主力净流入" if not is_fallback_mode else "板块成交额热度"} Top 20 (排行)').classes('font-bold text-gray-800')
                            ui.button(icon='more_horiz').props('flat round size=sm color=grey')

                        # Chart
                        # Use Top 20 for wider view
                        x_vals = top_20['名称'].astype(str).tolist()
                        y_vals = top_20[metric_col]
                        
                        # Colors
                        if is_fallback_mode:
                            colors = ['#ef4444' if r > 0 else '#22c55e' for r in top_20['涨跌幅'].tolist()]
                        else:
                            colors = ['#ef4444' if v > 0 else '#22c55e' for v in y_vals.tolist()]
                            
                        fig_bar = go.Figure(go.Bar(
                            x=x_vals, y=y_vals, marker_color=colors,
                            text=[f"{v/1e8:.1f}" for v in y_vals], textposition='auto',
                            texttemplate='%{text}亿' if y_vals.abs().mean() > 1e8 else '%{text}',
                            hovertemplate='%{x}<br>数值: %{y:.2f}<extra></extra>'
                        ))
                        fig_bar.update_layout(
                            height=400, margin=dict(l=40, r=20, t=20, b=80),
                            plot_bgcolor='rgba(0,0,0,0)',
                            paper_bgcolor='rgba(0,0,0,0)',
                            yaxis=dict(gridcolor='#F3F4F6'),
                            xaxis=dict(tickangle=-45),
                            autosize=True,
                            title=None
                        )
                        plot_func(fig_bar).classes('w-full h-full min-h-[400px]')

                    # Chart B: Bubble / Scatter
                    with ui.card().classes('w-full p-0 rounded-xl shadow-md border-0 bg-white overflow-hidden'):
                         # Header
                        with ui.row().classes('w-full p-4 border-b border-gray-100 items-center justify-between'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('bubble_chart' if is_fallback_mode else 'show_chart', color='indigo').classes('text-xl')
                                ui.label('板块全景透视 (Panorama - Top 50)').classes('font-bold text-gray-800')
                            # Legend
                            with ui.row().classes('text-xs gap-2'):
                                ui.label('红:上涨').classes('text-red-500 font-bold')
                                ui.label('绿:下跌').classes('text-emerald-500 font-bold')
                                ui.label('气泡大小:成交活跃度').classes('text-gray-400')

                        if is_fallback_mode:
                            # Scatter Map
                            df_scatter = df_sorted.head(50).copy() # Top 50
                            
                            # Refined Bubble Sizing
                            # Using Sqrt Scale relative to Max for better visual differentiation
                            max_val = df_scatter[metric_col].max()
                            if max_val > 0:
                                # Normalize 0.1 to 1.0, then scale to pixel size 15 to 60
                                bubble_sizes = (np.sqrt(df_scatter[metric_col]) / np.sqrt(max_val)) * 45 + 15
                            else:
                                bubble_sizes = 20

                            fig_scatter = go.Figure()
                            
                            # Add Zero Lines
                            fig_scatter.add_shape(type="line", x0=df_scatter[metric_col].min(), y0=0, x1=df_scatter[metric_col].max(), y1=0,
                                line=dict(color="gray", width=1, dash="dash"))

                            fig_scatter.add_trace(go.Scatter(
                                x=df_scatter[metric_col],
                                y=df_scatter['涨跌幅'],
                                mode='markers+text',
                                text=df_scatter['名称'],
                                textposition="top center",
                                marker=dict(
                                    size=bubble_sizes,
                                    sizemode='diameter',
                                    color=np.where(df_scatter['涨跌幅'] > 0, '#ef4444', '#10b981'), # Red/Emerald
                                    opacity=0.7,
                                    line=dict(color='white', width=1)
                                ),
                                hovertemplate='<b>%{text}</b><br>成交额: %{x:.2f}<br>涨跌幅: %{y:.2f}%<extra></extra>'
                            ))
                            
                            fig_scatter.update_layout(
                                height=500, margin=dict(l=60, r=20, t=30, b=50),
                                plot_bgcolor='rgba(0,0,0,0)',
                                paper_bgcolor='rgba(0,0,0,0)',
                                xaxis=dict(title=f"成交活跃度 ({metric_col})", gridcolor='#F3F4F6', showgrid=True),
                                yaxis=dict(title="板块涨跌幅 (%)", gridcolor='#F3F4F6'),
                                showlegend=False,
                                autosize=True
                            )
                            plot_func(fig_scatter).classes('w-full h-full min-h-[500px]')
                        else:
                             # RS Placeholder styling
                             with ui.column().classes('w-full h-[380px] items-center justify-center bg-gray-50'):
                                 ui.icon('science', size='3rem', color='gray-300')
                                 ui.label('RS相对强度模型持续跟踪中...').classes('text-gray-400 mt-2')


