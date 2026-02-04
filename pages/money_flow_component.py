from nicegui import ui, app
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import asyncio
import pandas as pd
import json
from utils.money_flow import MoneyFlow

def render_money_flow_panel(plotly_renderer=None):
    mf = MoneyFlow()
    
    # Use provided renderer or fallback to ui.plotly
    plot_func = plotly_renderer if plotly_renderer else ui.plotly

    # State
    # Use app.storage.browser for initial loading from browser local storage
    # Note: app.storage.browser is READ-ONLY on server. We must manage writes via JS.
    
    # Initialize storage from browser (read-only snapshot at connect time)
    # Browsers store strings, so we may need to parse JSON.
    # raw_subs = app.storage.browser.get('stock_subscriptions', '[]')
    # if isinstance(raw_subs, str):
    #     try:
    #         initial_subs = json.loads(raw_subs)
    #     except:
    #         initial_subs = []
    # else:
    #     initial_subs = raw_subs if isinstance(raw_subs, list) else []

    state = {
        'selected_code': None,
        'selected_name': None,
        'time_range': '近6月',
        'subs': []  # Start empty, load later
    }
    
    def get_subs():
        return state['subs']
        
    def save_subs_to_browser():
        # Sync current state to browser LocalStorage
        js_val = json.dumps(state['subs'], ensure_ascii=False)
        # Escape for JS string
        js_cmd = f'localStorage.setItem("stock_subscriptions", {json.dumps(js_val)})'
        ui.run_javascript(js_cmd)

    def add_sub(code, name):
        subs = state['subs']
        if any(s['code'] == code for s in subs):
            return False, "已存在该股票"
        if not name:
            name = code
        subs.append({'code': code, 'name': name})
        save_subs_to_browser()
        return True, "添加成功"

    def remove_sub(code):
        subs = state['subs']
        new_subs = [s for s in subs if s['code'] != code]
        state['subs'] = new_subs
        save_subs_to_browser()
        return True

    # -- async load logic --
    async def load_subs_from_browser():
        try:
            # Read from localStorage
            data_str = await ui.run_javascript('return localStorage.getItem("stock_subscriptions")')
            if data_str:
                state['subs'] = json.loads(data_str)
                refresh_list()
        except Exception as e:
            # Maybe silenced if not on browser context yet, but should be fine inside a timer
            print(f"Error loading subs: {e}") 

    # -- UI Containers --
    # We create the structure first
    with ui.row().classes('w-full items-start gap-4'):

        # === Left Column: Subscription Management ===
        with ui.card().classes('w-80 flex-none p-4 gap-3 no-inner-shadow'):
            ui.label('我的自选股').classes('text-lg font-bold text-gray-700')
            
            # Input Area
            with ui.column().classes('w-full gap-2'):
                code_input = ui.input(placeholder='代码 (如 600000)').props('outlined dense').classes('w-full')
                name_input = ui.input(placeholder='名称 (可选)').props('outlined dense').classes('w-full')
                
                async def add_btn_click():
                    code = code_input.value.strip()
                    name = name_input.value.strip()
                    if not code:
                        ui.notify('请输入股票代码', type='warning')
                        return
                    success, msg = add_sub(code, name)
                    if success:
                        ui.notify(f'已添加 {code}')
                        code_input.value = ''
                        name_input.value = ''
                        refresh_list()
                    else:
                        ui.notify(msg, type='negative')

                ui.button('添加订阅', icon='add', on_click=add_btn_click) \
                  .props('unelevated color=indigo w-full')
            
            ui.separator()
            
            # List Area
            list_container = ui.column().classes('w-full gap-1 h-[500px] overflow-y-auto pr-2')
        
        # === Right Column: Charts ===
        with ui.column().classes('flex-grow h-full gap-4'):
            # Header
            with ui.row().classes('w-full justify-between items-center bg-white p-4 rounded-lg shadow-sm'):
                header_label = ui.label('请选择左侧股票查看资金流向').classes('text-xl font-bold text-gray-700')
                
                with ui.row().classes('items-center gap-2'):
                    # Time Range Selector
                    time_options = ['近1月', '近3月', '近6月', '近1年', '全部']
                    
                    async def on_time_range_change(e):
                        state['time_range'] = e.value
                        if state['selected_code']:
                            await render_chart(state['selected_code'], state['selected_name'])
                            
                    ui.toggle(time_options, value=state['time_range'], on_change=on_time_range_change) \
                      .props('dense color=indigo')

                    async def update_btn_click():
                        if state['selected_code']:
                            await render_chart(state['selected_code'], state['selected_name'], force=True)
                        else:
                            ui.notify('请先选择股票', type='warning')

                    ui.button('同步最新数据', icon='sync', on_click=update_btn_click) \
                      .props('outline color=indigo')

            # Chart Area
            chart_container = ui.card().classes('w-full h-[600px] p-2 no-inner-shadow')

    # -- Logic Functions --

    async def render_chart(code, name, force=False):
        chart_container.clear()
        header_label.text = f'{name} ({code}) 资金流向趋势'
        
        with chart_container:
            ui.spinner('dots').classes('absolute-center')
        
        # Fetch Data
        loop = asyncio.get_event_loop()
        # Run in executor to avoid blocking UI
        df = await loop.run_in_executor(None, mf.get_flow_data, code, force)
        
        # Apply Time Range Filter
        if df is not None and not df.empty:
            tr = state.get('time_range', '近6月')
            end_date = df.index.max()
            start_date = None
            
            if tr == '近1月':
                start_date = end_date - pd.DateOffset(months=1)
            elif tr == '近3月':
                start_date = end_date - pd.DateOffset(months=3)
            elif tr == '近6月':
                start_date = end_date - pd.DateOffset(months=6)
            elif tr == '近1年':
                start_date = end_date - pd.DateOffset(years=1)
            
            if start_date:
                df = df[df.index >= start_date]
        
        chart_container.clear()
        if df is None or df.empty:
            with chart_container:
                with ui.column().classes('w-full h-full items-center justify-center'):
                    ui.label('暂无数据或获取失败').classes('text-gray-400 text-lg')
                    ui.label('如果是新添加的股票，请点击右上角“同步最新数据”').classes('text-gray-400')
            return

        with chart_container:
            # Prepare Plotly Figure
            # Convert index to string list to simulate category axis (removes weekend gaps)
            dates = df.index.strftime('%Y-%m-%d')
            main_col = '主力净流入-净额'
            retail_col = '散户净流入-净额'
            score_col = 'retail_score'
            
            # Create a 2-row subplot (Top: Retail Count, Bottom: Money Flow)
            # Row 1 (Top): Retail Count (Most Important per user) -> Height 0.55
            # Row 2 (Bottom): Money Flow (Grouped Main & Retail) -> Height 0.45
            
            fig = make_subplots(
                rows=2, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.1,
                subplot_titles=(f'散户数量变动 (核心指标)', f'资金流向对比 (主力 vs 散户)'),
                row_heights=[0.55, 0.45]
            )
            
            # Helper for color (Red for POS, Green for NEG)
            def get_colors(series):
                return ['#ef5350' if v >= 0 else '#26a69a' for v in series]

            # --- 1. Retail Investor Count (Top) ---
            if score_col in df.columns:
                # Bar Chart for daily change
                fig.add_trace(go.Bar(
                    x=dates, y=df[score_col],
                    name='散户变动',
                    marker_color=get_colors(df[score_col]),
                    showlegend=True,
                    hovertemplate='%{y:.2f}'
                ), row=1, col=1)
                
                # Trend Line (MA5)
                if len(df) > 5:
                    ma5 = df[score_col].rolling(window=5).mean().round(2)
                    fig.add_trace(go.Scatter(
                        x=dates, y=ma5,
                        mode='lines',
                        name='5日均线',
                        line=dict(color='#FFA726', width=2),
                        opacity=0.8,
                        hovertemplate='%{y:.2f}'
                    ), row=1, col=1)

            # --- 2. Money Flow (Bottom) ---
            # Main Force
            if main_col in df.columns:
                fig.add_trace(go.Bar(
                    x=dates, y=df[main_col],
                    name='主力净流入',
                    marker_color=get_colors(df[main_col]),
                    offsetgroup=1
                ), row=2, col=1)

            # Retail
            if retail_col in df.columns:
                fig.add_trace(go.Bar(
                    x=dates, y=df[retail_col],
                    name='散户净流入',
                    marker_color=get_colors(df[retail_col]),
                    opacity=0.4,
                    offsetgroup=2
                ), row=2, col=1)

            fig.update_layout(
                margin=dict(l=50, r=20, t=40, b=40),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                hovermode='x unified',
                barmode='group' 
            )

            # Force category axis to avoid weekend gaps and ensure clean ticks
            fig.update_xaxes(type='category', tickmode='auto', nticks=10)
            
            # Format Y axes
            fig.update_yaxes(hoverformat='.2f', row=1, col=1)
            
            # Using custom renderer or ui.plotly
            plot_func(fig).classes('w-full h-full')

    def refresh_list():
        list_container.clear()
        subs = get_subs()
        
        if not subs:
            with list_container:
                ui.label('列表为空').classes('text-gray-300 text-sm')
            return

        with list_container:
            for sub in subs:
                code = sub['code']
                name = sub.get('name', code)
                
                # Check selection
                is_sel = (state['selected_code'] == code)
                bg_cls = 'bg-indigo-50 border-indigo-200' if is_sel else 'bg-white hover:bg-gray-50 border-transparent'
                
                # Item Card
                with ui.row().classes(f'w-full items-center justify-between p-3 rounded border shadow-sm cursor-pointer transition-colors {bg_cls}') as row:
                    with ui.row().classes('items-center gap-3 flex-grow'):
                        ui.icon('trending_up', color='indigo' if is_sel else 'gray').classes('text-xl')
                        with ui.column().classes('gap-0'):
                            ui.label(name).classes('font-bold text-gray-700 leading-tight')
                            ui.label(code).classes('text-xs text-gray-400')
                    
                    # Click Handler for Selection
                    async def on_select(e, c=code, n=name):
                        state['selected_code'] = c
                        state['selected_name'] = n
                        refresh_list() # Update highlight
                        await render_chart(c, n, force=False)
                    
                    row.on('click', on_select)

                    # Delete Button (stop propagation not directly available, but separate button works)
                    def perform_delete(c=code):
                        remove_sub(c)
                        if state['selected_code'] == c:
                            state['selected_code'] = None
                            chart_container.clear()
                            header_label.text = '请选择左侧股票'
                        refresh_list()
                    
                    ui.button(icon='close', on_click=lambda c=code: perform_delete(c)) \
                      .props('flat round size=sm color=gray').classes('opacity-50 hover:opacity-100')

    # Initial Render
    refresh_list()
    
    # Trigger load from client local storage
    ui.timer(0.1, load_subs_from_browser, once=True)
