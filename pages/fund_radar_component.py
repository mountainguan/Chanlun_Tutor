from nicegui import ui
import plotly.graph_objects as go
from utils.fund_radar import FundRadar
from pages.fund_radar_multi_day_component import render_multi_day_view as render_fund_radar_multi_day_view
from pages.fund_radar_multi_day_component import render_attribution_section as render_fund_radar_attribution_section
from pages.fund_radar_sector_grid_component import render_sector_grid_view as render_fund_radar_sector_grid_view
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

        def render_attribution_section(df_input):
            return render_fund_radar_attribution_section(radar, radar_state, df_input, is_mobile=is_mobile)

        def render_multi_day_view(df, dates, plot_func):
            return render_fund_radar_multi_day_view(
                radar,
                radar_state,
                df,
                dates,
                plot_func,
                is_mobile=is_mobile,
                date_value=date_input.value,
            )


        def render_sector_grid_view():
            return render_fund_radar_sector_grid_view(radar)

        async def fetch_radar_data(date_val, duration, force, is_past_date):
            loop = asyncio.get_running_loop()
            if duration > 1:
                df_agg, used_dates = await loop.run_in_executor(
                    None, lambda: radar.get_multi_day_data(date_val, duration, cache_only=is_past_date)
                )
                return {'view': 'multi', 'df': df_agg, 'dates': used_dates, 'market_snap': None}
            mode = 'READ_CACHE' if is_past_date else ('FORCE_UPDATE' if force else 'READ_CACHE')
            _, df_ths, market_snap_data = await loop.run_in_executor(
                None, lambda: radar.get_data(date_val, mode=mode)
            )
            return {'view': 'single', 'df': df_ths, 'dates': None, 'market_snap': market_snap_data}

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
            
            fetch_result = await fetch_radar_data(date_val, duration, force, is_past_date)

            if fetch_result['view'] == 'multi':
                df_agg = fetch_result['df']
                used_dates = fetch_result['dates']
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



            df_ths = fetch_result['df']
            market_snap_data = fetch_result['market_snap']

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
                if not is_past_date:
                    render_sector_grid_view()

                # --- 3.5 Attribution Analysis (Moved Here) ---
                # Added check to ensure df_ths is not empty before rendering
                if not df_ths.empty:
                    render_attribution_section(df_ths)


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



