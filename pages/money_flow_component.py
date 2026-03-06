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
        'indicator': '散户数量',
        'assistant_period': 'day',
        'kline_window': '近60个',
        'render_ticket': 0,
        'subs': [],  # Start empty, load later
        'groups': ['默认']
    }
    
    def get_subs():
        return state['subs']
    
    def save_groups_to_browser():
        js_val = json.dumps(state['groups'], ensure_ascii=False)
        js_cmd = f'localStorage.setItem("stock_groups", {json.dumps(js_val)})'
        ui.run_javascript(js_cmd)

    def save_subs_to_browser():
        # Sync current state to browser LocalStorage
        js_val = json.dumps(state['subs'], ensure_ascii=False)
        # Escape for JS string
        js_cmd = f'localStorage.setItem("stock_subscriptions", {json.dumps(js_val)})'
        ui.run_javascript(js_cmd)
        save_groups_to_browser() # sync groups too

    def add_sub(code, name, group='默认'):
        subs = state['subs']
        if any(s['code'] == code for s in subs):
            return False, "已存在该股票"
        if not name:
            name = code
            
        # Add group if explicit new
        if group not in state['groups']:
            state['groups'].append(group)
            
        subs.append({'code': code, 'name': name, 'group': group})
        save_subs_to_browser() # saves both
        return True, "添加成功"

    def remove_sub(code):
        subs = state['subs']
        new_subs = [s for s in subs if s['code'] != code]
        state['subs'] = new_subs
        save_subs_to_browser()
        return True
    
    def get_groups():
        return state['groups']

    # -- async load logic --
    async def load_subs_from_browser():
        try:
            # Read from localStorage
            data_str = await ui.run_javascript('return localStorage.getItem("stock_subscriptions")')
            if data_str:
                state['subs'] = json.loads(data_str)
            
            # Read Groups
            groups_str = await ui.run_javascript('return localStorage.getItem("stock_groups")')
            if groups_str:
                state['groups'] = json.loads(groups_str)
            else:
                # Migration: infer
                inferred = set(s.get('group', '默认') for s in state['subs'])
                inferred.add('默认')
                state['groups'] = sorted(list(inferred))
                save_groups_to_browser()
            
            # Ensure '默认' exists and is first if feasible, or just exists
            if '默认' not in state['groups']:
                state['groups'].insert(0, '默认')
                
            refresh_list()
        except Exception as e:
            # Maybe silenced if not on browser context yet, but should be fine inside a timer
            print(f"Error loading subs: {e}")  


    # -- Logic Manager Functions --
    # Dialog for Group Management
    group_dialog = ui.dialog().classes('w-96')
    
    def open_group_manager():
        groups = get_groups()
        group_dialog.clear()
        with group_dialog, ui.card().classes('w-[500px] p-4 flex flex-col gap-4'):
             with ui.row().classes('w-full items-center justify-between'):
                 ui.label('分组管理').classes('text-xl font-bold text-gray-800')
                 ui.button(icon='close', on_click=group_dialog.close).props('flat round dense')
             
             # Add New Group Section
             with ui.row().classes('w-full items-center gap-2 bg-blue-50 p-2 rounded-lg'):
                 new_group_input = ui.input(placeholder='新分组名称').props('dense outlined bg-white').classes('flex-grow')
                 def add_new_group():
                     name = new_group_input.value.strip()
                     if not name: return
                     if name in state['groups']:
                         ui.notify('分组已存在', type='warning')
                         return
                     state['groups'].append(name)
                     save_groups_to_browser()
                     ui.notify(f'已添加分组: {name}') # Move notify before UI update/clear
                     refresh_list()
                     open_group_manager()
                 ui.button('新建', icon='add', on_click=add_new_group).props('unelevated dense color=primary')
                 
             ui.separator()

             if not groups or (len(groups) == 1 and groups[0] == '默认'):
                 ui.label('暂无自定义分组').classes('text-gray-400 italic')
             
             with ui.column().classes('w-full gap-2 max-h-[400px] overflow-y-auto p-1'):
                 for g in groups:
                     # Skip default
                     if g == '默认': 
                         continue 

                     with ui.card().classes('w-full p-2 bg-gray-50 border border-gray-200'):
                        with ui.row().classes('w-full items-center gap-2'):
                            # Edit Mode State
                            name_input = ui.input(value=g).props('dense outlined').classes('flex-grow')
                            
                            def rename_group(old, new_input):
                                new_name = new_input.value.strip()
                                if not new_name or new_name == old: return
                                if new_name in state['groups']:
                                     ui.notify('分组名已存在', type='warning')
                                     return
                                
                                # Update subs
                                for s in state['subs']:
                                    if s.get('group') == old:
                                        s['group'] = new_name
                                
                                # Update groups list (replace in place to keep order)
                                idx = state['groups'].index(old)
                                state['groups'][idx] = new_name
                                
                                save_subs_to_browser() # saves both
                                ui.notify(f'已重命名: {old} -> {new_name}') # Move notify before refresh
                                refresh_list() # refresh main list
                                open_group_manager() # refresh dialog

                            ui.button(icon='save', on_click=lambda o=g, i=name_input: rename_group(o, i)) \
                                .props('flat round dense color=primary').classes('opacity-80 hover:opacity-100') \
                                .tooltip('保存重命名')

                            def delete_group_action(target_group):
                                count = 0
                                for s in state['subs']:
                                    if s.get('group') == target_group:
                                        s['group'] = '默认'
                                        count += 1
                                
                                if target_group in state['groups']:
                                    state['groups'].remove(target_group)
                                    
                                save_subs_to_browser()
                                ui.notify(f'已删除分组"{target_group}"，{count}个股票移至"默认"') # Move notify up
                                refresh_list()
                                open_group_manager()

                            ui.button(icon='delete', on_click=lambda t=g: delete_group_action(t)) \
                                .props('flat round dense color=red').classes('opacity-80 hover:opacity-100') \
                                .tooltip('删除分组 (股票移至默认)')

        group_dialog.open()

    # -- UI Containers --
    # We create the structure first
    # Modified for Mobile: Stack vertically
    with ui.row().classes('w-full items-stretch gap-6 flex-col md:flex-row md:flex-nowrap'):

        # === Left Column: Subscription Management ===
        # Modified: Full width on mobile, fixed width on PC. Height auto on mobile (scrollable list inside limitation?), fixed on PC.
        with ui.card().classes('w-full md:w-[320px] flex-none p-4 gap-4 bg-white rounded-xl shadow-sm border border-gray-200 h-auto md:h-[600px] flex flex-col'):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label('我的自选股').classes('text-xl font-bold text-gray-800 tracking-tight')
                ui.button(icon='settings', on_click=open_group_manager).props('flat round dense color=grey-7').tooltip('管理分组')
            
            # Input Area
            with ui.column().classes('w-full gap-3 bg-gray-50 p-3 rounded-lg border border-gray-200'):
                ui.label('添加新股票').classes('text-xs font-bold text-gray-500 uppercase tracking-wider')
                code_input = ui.input(placeholder='代码 (如 600000)').props('outlined dense bg-white').classes('w-full')
                name_input = ui.input(placeholder='名称 (可选)').props('outlined dense bg-white').classes('w-full')
                
                # Auto-fetch name logic
                async def on_code_changed(e):
                    val = e.value
                    if val and len(val) >= 6 and val.isdigit():
                        # Try fetch
                        loop = asyncio.get_event_loop()
                        name = await loop.run_in_executor(None, mf.get_stock_name, val)
                        if name:
                            name_input.value = name
                            ui.notify(f'已识别: {name}', type='positive', position='top')
                
                code_input.on('blur', lambda: on_code_changed(code_input))
                code_input.on('keyup.enter', lambda: on_code_changed(code_input))
                
                # Group Selection with Create new option
                # Use a standard select but allow selecting from state['groups']
                # But NiceGUI select dynamic options binding is tricky.
                # Let's use a function to get options
                
                group_select = ui.select(options=state['groups'], value='默认', label='分组', with_input=True, new_value_mode='add-unique') \
                    .props('outlined dense bg-white use-input hide-selected fill-input behavior="menu"') \
                    .classes('w-full')
                
                # Bind options to always reflect state['groups'] (Removed explicit bind_prop call to avoid attribute errors)
                # Instead, we will manually update options in refresh_list()

                async def add_btn_click():
                    code = code_input.value.strip()
                    name = name_input.value.strip()
                    group = group_select.value.strip() if group_select.value else '默认'
                    
                    if not code:
                        ui.notify('请输入股票代码', type='warning')
                        return
                    success, msg = add_sub(code, name, group)
                    if success:
                        ui.notify(f'已添加 {code}')
                        code_input.value = ''
                        name_input.value = ''
                        refresh_list()
                    else:
                        ui.notify(msg, type='negative')

                ui.button('添加订阅', icon='add', on_click=add_btn_click) \
                  .props('unelevated color=primary text-color=white w-full rounded-lg') \
                  .classes('shadow-sm font-bold')
            
            ui.separator().classes('bg-gray-100')
            
            # List Area
            # Mobile: Limit max height to avoid being too long
            list_container = ui.column().classes('w-full gap-1 flex-1 overflow-y-auto pr-2 custom-scrollbar max-h-[300px] md:max-h-full')
        
        # === Right Column: Charts ===
        # Mobile: Lower height or auto
        with ui.column().classes('flex-grow h-auto md:h-auto gap-4 min-w-0'):
            # Header
            with ui.row().classes('w-full justify-between items-center bg-white p-4 rounded-xl shadow-sm border border-gray-200 flex-none gap-4 md:flex-nowrap'):
                with ui.row().classes('items-center gap-3 flex-shrink-0'):
                    ui.icon('analytics', color='primary').classes('text-3xl')
                    header_label = ui.label('请选择左侧股票查看个股医生指标').classes('text-2xl font-bold text-gray-800 tracking-tight')
                
                controls_container = ui.row().classes('items-center gap-2 flex-nowrap overflow-x-auto custom-scrollbar pb-1')
            
            with controls_container:
                # Time Range Selector - Chip style
                time_options = ['近1月', '近3月', '近6月', '近1年', '全部']
                period_options = [
                    ('week', '周线'),
                    ('day', '日线'),
                    ('5m', '5分钟'),
                    ('15m', '15分钟'),
                    ('30m', '30分钟'),
                    ('60m', '60分钟'),
                    ('120m', '120分钟'),
                ]

                async def set_time_range(val):
                    state['time_range'] = val
                    render_header_controls()
                    if state['selected_code']:
                        await render_chart(state['selected_code'], state['selected_name'])

                async def set_indicator(val):
                    state['indicator'] = val
                    render_header_controls()
                    if state['selected_code']:
                        await render_chart(state['selected_code'], state['selected_name'])

                async def set_period(val):
                    state['assistant_period'] = val
                    render_header_controls()
                    if state['selected_code']:
                        await render_chart(state['selected_code'], state['selected_name'])

                def render_indicator_controls():
                    with ui.row().classes('bg-slate-100 rounded-full p-1 gap-1 border border-slate-200'):
                        for opt in ['散户数量', '买卖助手']:
                            is_active = (state['indicator'] == opt)
                            btn_cls = 'bg-white text-slate-800 shadow-sm' if is_active else 'text-slate-500 hover:text-slate-700'
                            ui.button(opt, on_click=lambda o=opt: set_indicator(o)) \
                                .props(f'flat dense no-caps size=sm') \
                                .classes(f'px-4 rounded-full transition-all font-bold {btn_cls}')

                def render_period_controls():
                    with ui.row().classes('bg-slate-100 rounded-full p-1 gap-1 border border-slate-200'):
                        for key, label in period_options:
                            is_active = (state['assistant_period'] == key)
                            btn_cls = 'bg-white text-slate-800 shadow-sm' if is_active else 'text-slate-500 hover:text-slate-700'
                            ui.button(label, on_click=lambda p=key: set_period(p)) \
                                .props(f'flat dense no-caps size=sm') \
                                .classes(f'px-3 rounded-full transition-all font-bold {btn_cls}')

                def render_time_controls():
                    with ui.row().classes('bg-slate-100 rounded-full p-1 gap-1 border border-slate-200'):
                        for opt in time_options:
                            is_active = (state['time_range'] == opt)
                            btn_cls = 'bg-white text-slate-800 shadow-sm' if is_active else 'text-slate-500 hover:text-slate-700'
                            ui.button(opt, on_click=lambda o=opt: set_time_range(o)) \
                                .props(f'flat dense no-caps size=sm') \
                                .classes(f'px-3 rounded-full transition-all font-bold {btn_cls}')

                def render_sync_btn():
                    async def update_btn_click():
                        if state['selected_code']:
                            await render_chart(state['selected_code'], state['selected_name'], force=True)
                        else:
                            ui.notify('请先选择股票', type='warning')
                    ui.button('同步最新', icon='sync', on_click=update_btn_click) \
                    .props('outline color=primary size=sm rounded-lg')

                def render_header_controls():
                    controls_container.clear()
                    with controls_container:
                        render_indicator_controls()
                        if state['indicator'] == '买卖助手':
                            render_period_controls()
                            render_sync_btn()
                        else:
                            render_time_controls() # 散户数量仍使用时间跨度
                            render_sync_btn()
                
                # Initial Render
                render_header_controls()

            # Chart Area
            chart_container = ui.card().classes('w-full flex-grow p-2 no-inner-shadow')


    # -- Logic Functions --
    
    async def render_chart(code, name, force=False):
        if chart_container.is_deleted or header_label.is_deleted: return
        state['render_ticket'] = state.get('render_ticket', 0) + 1
        current_ticket = state['render_ticket']
        chart_container.clear()
        header_label.text = f'{name} ({code}) {state["indicator"]}趋势'
        
        with chart_container:
            ui.spinner('dots').classes('absolute-center')
        
        loop = asyncio.get_event_loop()
        df = None
        if state['indicator'] == '散户数量':
            df = await loop.run_in_executor(None, mf.get_flow_data, code, force)
            if current_ticket != state.get('render_ticket'):
                return
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

        if chart_container.is_deleted: return
        chart_container.clear()
        if state['indicator'] == '散户数量' and (df is None or df.empty):
            with chart_container:
                with ui.column().classes('w-full h-full items-center justify-center'):
                    ui.label('暂无数据或获取失败').classes('text-gray-400 text-lg')
                    ui.label('如果是新添加的股票，请点击右上角“同步最新数据”').classes('text-gray-400')
            return

        with chart_container:
            main_col = '主力净流入-净额'
            retail_col = '小单净流入-净额'
            score_col = 'retail_score'

            def get_colors(series):
                return ['#ef5350' if v >= 0 else '#26a69a' for v in series]

            if state['indicator'] == '散户数量':
                dates = df.index.strftime('%Y-%m-%d')
                fig = make_subplots(
                    rows=2, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.1,
                    subplot_titles=('散户数量变动 (纯小单过滤)', '资金流向对比 (主力 vs 小单散户)'),
                    row_heights=[0.55, 0.45]
                )

                if score_col in df.columns:
                    fig.add_trace(go.Bar(
                        x=dates.tolist(), y=df[score_col].fillna(0).tolist(),
                        name='散户变动',
                        marker_color=get_colors(df[score_col].fillna(0)),
                        showlegend=True,
                        hovertemplate='%{y:.2f}'
                    ), row=1, col=1)

                    if len(df) > 5:
                        ma5 = df[score_col].rolling(window=5).mean().round(2).fillna(0)
                        fig.add_trace(go.Scatter(
                            x=dates.tolist(), y=ma5.tolist(),
                            mode='lines',
                            name='5日均线',
                            line=dict(color='#FFA726', width=2),
                            opacity=0.8,
                            hovertemplate='%{y:.2f}'
                        ), row=1, col=1)

                if main_col in df.columns:
                    fig.add_trace(go.Bar(
                        x=dates.tolist(), y=df[main_col].fillna(0).tolist(),
                        name='主力净流入',
                        marker_color=get_colors(df[main_col].fillna(0)),
                        offsetgroup=1
                    ), row=2, col=1)

                if retail_col in df.columns:
                    fig.add_trace(go.Bar(
                        x=dates.tolist(), y=df[retail_col].fillna(0).tolist(),
                        name='纯散户(小单)净流入',
                        marker_color=get_colors(df[retail_col].fillna(0)),
                        opacity=0.4,
                        offsetgroup=2
                    ), row=2, col=1)

                # 浅色金融科技风配色方案
                COLOR_BG = '#ffffff'
                COLOR_GRID = '#f1f5f9'
                COLOR_TEXT = '#475569'

                fig.update_layout(
                    margin=dict(l=40, r=15, t=38, b=20),
                    paper_bgcolor=COLOR_BG,
                    plot_bgcolor=COLOR_BG,
                    showlegend=True,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="left",
                        x=0,
                        bgcolor='rgba(255,255,255,0.8)',
                        bordercolor=COLOR_GRID,
                        borderwidth=0,
                        font=dict(size=10, color=COLOR_TEXT)
                    ),
                    hovermode='x unified',
                    barmode='group',
                    font=dict(family="Roboto, 'Segoe UI', 'Microsoft YaHei', sans-serif", color=COLOR_TEXT, size=11)
                )
                
                common_axis_config = dict(
                    showgrid=True,
                    gridcolor=COLOR_GRID,
                    gridwidth=1,
                    zeroline=False,
                    showline=True,
                    linecolor=COLOR_GRID,
                    mirror=True,
                    tickfont=dict(color=COLOR_TEXT, size=10)
                )
                
                fig.update_xaxes(**common_axis_config, type='category', tickmode='auto', nticks=8)
                fig.update_yaxes(**common_axis_config, hoverformat='.2f', row=1, col=1)
                fig.update_yaxes(**common_axis_config, hoverformat='.2f', row=2, col=1)
            else:
                period = state.get('assistant_period', 'day')
                kline_df = await loop.run_in_executor(None, mf.get_kline_data, code, period, force)
                if current_ticket != state.get('render_ticket'):
                    return
                if kline_df is None or kline_df.empty:
                    with ui.column().classes('w-full h-full items-center justify-center'):
                        ui.label('买卖助手暂无可用K线').classes('text-gray-400 text-lg')
                    return

                end_dt = kline_df.index.max()
                # if pd.notna(end_dt):
                #    kline_df = kline_df[kline_df.index >= (end_dt - pd.Timedelta(days=180))]

                # Calculate on FULL data first for accurate Chan Lun structures
                assistant = await loop.run_in_executor(None, mf.build_buy_sell_assistant, kline_df)
                if current_ticket != state.get('render_ticket'):
                    return
                kdf = assistant.get('kline', pd.DataFrame())
                analysis = assistant.get('analysis', {})
                if kdf is None or kdf.empty:
                    with ui.column().classes('w-full h-full items-center justify-center'):
                        ui.label('买卖助手计算失败').classes('text-gray-400 text-lg')
                    return

                # Map bi_points to real indices in FULL kdf
                raw_bi_points = analysis.get('bi_points', [])
                valid_bi_points = []
                if not kdf.empty:
                    # Create a map for faster lookup if needed, but get_loc is fast for DatetimeIndex
                    for p in raw_bi_points:
                        try:
                            p_dt = pd.to_datetime(p['date'])
                            # Ensure we find the exact index
                            if p_dt in kdf.index:
                                p['real_idx'] = kdf.index.get_loc(p_dt)
                                valid_bi_points.append(p)
                        except:
                            continue
                raw_bi_points = valid_bi_points

                if not kdf.empty:
                    _closes = pd.to_numeric(kdf.get('close'), errors='coerce').ffill().bfill()
                    kdf['boll_mid'] = _closes.rolling(window=20, min_periods=2).mean().ffill().bfill()
                    _std = _closes.rolling(window=20, min_periods=2).std().fillna(0)
                    kdf['boll_upper'] = kdf['boll_mid'] + 2 * _std
                    kdf['boll_lower'] = kdf['boll_mid'] - 2 * _std

                # Slice for display AFTER calculation
                bar_count = 180

                start_idx = 0
                full_len = len(kdf)
                if bar_count and full_len > bar_count:
                    start_idx = full_len - bar_count
                    kdf = kdf.iloc[-bar_count:]

                date_fmt = '%Y-%m-%d' if period in ['day', 'week'] else '%Y-%m-%d %H:%M'
                x_labels = kdf.index.strftime(date_fmt)

                # Filter and Format bi_points to match visible x-axis
                bi_points = []
                if not kdf.empty:
                    # 1. Add boundary crossing point (interpolation)
                    if start_idx > 0 and raw_bi_points:
                        for i in range(len(raw_bi_points) - 1):
                            p1 = raw_bi_points[i]
                            p2 = raw_bi_points[i+1]
                            idx1 = p1.get('real_idx', -1)
                            idx2 = p2.get('real_idx', -1)
                            
                            # Check if segment crosses start_idx
                            if idx1 < start_idx and idx2 >= start_idx:
                                # Interpolate price at start_idx
                                if idx2 != idx1:
                                    ratio = (start_idx - idx1) / (idx2 - idx1)
                                    price_at_start = p1['price'] + ratio * (p2['price'] - p1['price'])
                                    
                                    # Add virtual start point at the first visible date
                                    start_date_str = kdf.index[0].strftime(date_fmt)
                                    bi_points.append({
                                        'date': start_date_str,
                                        'price': price_at_start,
                                        'type': 'virtual'
                                    })
                                break

                    # 2. Add visible points
                    for p in raw_bi_points:
                        if p.get('real_idx', -1) >= start_idx:
                            p_copy = p.copy()
                            p_dt = pd.to_datetime(p['date'])
                            p_copy['date'] = p_dt.strftime(date_fmt) # Update to match x_labels format
                            bi_points.append(p_copy)

                macd_hist = pd.to_numeric(kdf.get('macd_hist'), errors='coerce').fillna(0)
                dif = pd.to_numeric(kdf.get('dif'), errors='coerce').fillna(0)
                dea = pd.to_numeric(kdf.get('dea'), errors='coerce').fillna(0)
                boll_mid = kdf.get('boll_mid', pd.Series(0, index=kdf.index))
                boll_upper = kdf.get('boll_upper', pd.Series(0, index=kdf.index))
                boll_lower = kdf.get('boll_lower', pd.Series(0, index=kdf.index))
                macd_colors = ['#ef4444' if v >= 0 else '#10b981' for v in macd_hist]
                gc_mask = kdf.get('golden_cross', pd.Series(False, index=kdf.index)).fillna(False).values
                dc_mask = kdf.get('dead_cross', pd.Series(False, index=kdf.index)).fillna(False).values
                last_date = kdf.index.max()
                gap_days = (pd.Timestamp.now().normalize() - pd.Timestamp(last_date).normalize()).days if pd.notna(last_date) else 0

                # 浅色金融科技风配色方案
                COLOR_UP = '#ef4444'     # 红色 (涨)
                COLOR_DOWN = '#22c55e'   # 绿色 (跌)
                COLOR_MA5 = '#f59e0b'    # 橙色
                COLOR_MA10 = '#3b82f6'   # 蓝色
                COLOR_MA20 = '#8b5cf6'   # 紫色
                COLOR_MA30 = '#ec4899'   # 粉色
                COLOR_MA60 = '#64748b'   # 灰色
                COLOR_BI = '#94a3b8'     # 笔 (Slate-400)
                COLOR_BG = '#ffffff'     # 背景纯白
                COLOR_GRID = '#f1f5f9'   # 网格极淡 (Slate-100)
                COLOR_TEXT = '#475569'   # 文本 (Slate-600)

                fig = make_subplots(
                    rows=2, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.05, # 压缩主副图间距
                    row_heights=[0.75, 0.25] # 主副图区域分配，因为底部还有滑块被单独计算
                )
                
                visible_macd = []
                visible_boll = []

                def _add_trace(trace, row, col, kind='all'):
                    fig.add_trace(trace, row=row, col=col)
                    if kind == 'all':
                        visible_macd.append(True)
                        visible_boll.append(True)
                    elif kind == 'macd':
                        visible_macd.append(True)
                        visible_boll.append(False)
                        fig.data[-1].visible = True
                    elif kind == 'boll':
                        visible_macd.append(False)
                        visible_boll.append(True)
                        fig.data[-1].visible = False
                
                # 1. K线图
                _add_trace(go.Candlestick(
                    x=x_labels,
                    open=kdf['open'],
                    high=kdf['high'],
                    low=kdf['low'],
                    close=kdf['close'],
                    increasing_line_color=COLOR_UP,
                    decreasing_line_color=COLOR_DOWN,
                    increasing_fillcolor=COLOR_UP,
                    decreasing_fillcolor=COLOR_DOWN,
                    name='K线'
                ), row=1, col=1)

                # 2. 均线
                _add_trace(go.Scatter(x=x_labels, y=kdf['ma5'], mode='lines', line=dict(color=COLOR_MA5, width=1), name='MA5'), row=1, col=1)
                _add_trace(go.Scatter(x=x_labels, y=kdf['ma10'], mode='lines', line=dict(color=COLOR_MA10, width=1), name='MA10'), row=1, col=1)
                _add_trace(go.Scatter(x=x_labels, y=kdf['ma20'], mode='lines', line=dict(color=COLOR_MA20, width=1), name='MA20'), row=1, col=1)
                _add_trace(go.Scatter(x=x_labels, y=kdf['ma30'], mode='lines', line=dict(color=COLOR_MA30, width=1), name='MA30'), row=1, col=1)
                _add_trace(go.Scatter(x=x_labels, y=kdf['ma60'], mode='lines', line=dict(color=COLOR_MA60, width=1.2, dash='dot'), name='MA60'), row=1, col=1)

                # 3. 缠论笔与分型
                # bi_points already filtered and formatted above
                if len(bi_points) >= 2:
                    # Dates are already formatted to match x_labels
                    bi_x = [p['date'] for p in bi_points]
                    bi_y = [p['price'] for p in bi_points]
                    # 笔线
                    _add_trace(go.Scatter(
                        x=bi_x,
                        y=bi_y,
                        mode='lines+markers',
                        line=dict(color=COLOR_BI, width=1.5, dash='solid'), # 笔改为实线更清晰，或保留虚线
                        marker=dict(size=4, color=COLOR_BI),
                        name='缠论笔',
                        opacity=0.8
                    ), row=1, col=1)
                    
                    # 顶底分型
                    top_x = [p['date'] for p in bi_points if p.get('type') == 'top']
                    top_y = [p['price'] for p in bi_points if p.get('type') == 'top']
                    bot_x = [p['date'] for p in bi_points if p.get('type') == 'bottom']
                    bot_y = [p['price'] for p in bi_points if p.get('type') == 'bottom']
                    
                    if top_x:
                        _add_trace(go.Scatter(
                            x=top_x, y=top_y, mode='markers',
                            marker=dict(size=6, color=COLOR_DOWN, symbol='circle-open', line=dict(width=1.5)),
                            name='顶分型', showlegend=False
                        ), row=1, col=1)
                    if bot_x:
                        _add_trace(go.Scatter(
                            x=bot_x, y=bot_y, mode='markers',
                            marker=dict(size=6, color=COLOR_UP, symbol='circle-open', line=dict(width=1.5)),
                            name='底分型', showlegend=False
                        ), row=1, col=1)

                # 4. 买卖点标记
                buy_mask = kdf['buy_signal'].fillna(False).values
                sell_mask = kdf['sell_signal'].fillna(False).values
                
                # 增强买卖点显示
                if buy_mask.any():
                    _add_trace(go.Scatter(
                        x=x_labels[buy_mask],
                        y=kdf['buy_y'][buy_mask],
                        mode='markers+text',
                        marker=dict(
                            size=16, 
                            color=COLOR_UP, 
                            symbol='triangle-up',
                            line=dict(width=1, color='white')
                        ),
                        text=['<b>买</b>'] * int(buy_mask.sum()),
                        textfont=dict(color=COLOR_UP, size=14), # 字体加大加粗
                        textposition='bottom center', # 文字在图标下方
                        name='买点'
                    ), row=1, col=1)
                if sell_mask.any():
                    _add_trace(go.Scatter(
                        x=x_labels[sell_mask],
                        y=kdf['sell_y'][sell_mask],
                        mode='markers+text',
                        marker=dict(
                            size=16, 
                            color=COLOR_DOWN, 
                            symbol='triangle-down',
                            line=dict(width=1, color='white')
                        ),
                        text=['<b>卖</b>'] * int(sell_mask.sum()),
                        textfont=dict(color=COLOR_DOWN, size=14), # 字体加大加粗
                        textposition='top center', # 文字在图标上方
                        name='卖点'
                    ), row=1, col=1)

                # 5. 副图指标（MACD）
                _add_trace(go.Bar(
                    x=x_labels,
                    y=macd_hist,
                    marker_color=macd_colors,
                    name='MACD柱',
                    marker_line_width=0, # 去掉柱子边框
                    hovertemplate='%{y:.3f}<extra></extra>'
                ), row=2, col=1, kind='macd')
                _add_trace(go.Scatter(x=x_labels, y=dif, mode='lines', line=dict(color=COLOR_MA10, width=1.5), name='DIF'), row=2, col=1, kind='macd')
                _add_trace(go.Scatter(x=x_labels, y=dea, mode='lines', line=dict(color=COLOR_MA5, width=1.5), name='DEA'), row=2, col=1, kind='macd')

                if gc_mask.any():
                    _add_trace(go.Scatter(
                        x=x_labels[gc_mask], y=dif[gc_mask], mode='markers',
                        marker=dict(color=COLOR_UP, size=6, symbol='diamond'),
                        name='金叉', showlegend=False
                    ), row=2, col=1, kind='macd')
                if dc_mask.any():
                    _add_trace(go.Scatter(
                        x=x_labels[dc_mask], y=dif[dc_mask], mode='markers',
                        marker=dict(color=COLOR_DOWN, size=6, symbol='diamond'),
                        name='死叉', showlegend=False
                    ), row=2, col=1, kind='macd')

                # 副图指标（布林线）
                # 使用自定义Bar伪造K线，完全避开 Plotly 底层 Candlestick 组件在控制隐藏时引发的 Margin 塌陷 Bug
                kline_colors = ['rgba(239,68,68,0.7)' if c >= o else 'rgba(34,197,94,0.7)' for c, o in zip(kdf['close'], kdf['open'])]
                body_y = [max(abs(c - o), 0.01) for c, o in zip(kdf['close'], kdf['open'])] # 保证十字星也有极小的一点高度
                body_base = [min(c, o) for c, o in zip(kdf['close'], kdf['open'])]
                
                # 辅助K线：影线 (High-Low)
                _add_trace(go.Bar(
                    x=x_labels, y=kdf['high'] - kdf['low'], base=kdf['low'],
                    marker_color=kline_colors, width=0.1, # 细线
                    name='K线(辅)影线', showlegend=False, hoverinfo='skip'
                ), row=2, col=1, kind='boll')
                
                # 辅助K线：实体 (Open-Close)
                _add_trace(go.Bar(
                    x=x_labels, y=body_y, base=body_base,
                    marker_color=kline_colors, width=0.6, # 宽条
                    name='K线(辅)实体', showlegend=False, hoverinfo='skip'
                ), row=2, col=1, kind='boll')

                _add_trace(go.Scatter(
                    x=x_labels, y=boll_upper, mode='lines', line=dict(color=COLOR_MA20, width=1.5), name='BOLL上轨'
                ), row=2, col=1, kind='boll')
                _add_trace(go.Scatter(
                    x=x_labels, y=boll_mid, mode='lines', line=dict(color=COLOR_MA60, width=1.3), name='BOLL中轨'
                ), row=2, col=1, kind='boll')
                _add_trace(go.Scatter(
                    x=x_labels, y=boll_lower, mode='lines', line=dict(color=COLOR_MA10, width=1.5), name='BOLL下轨'
                ), row=2, col=1, kind='boll')

                # 6. Layout 布局优化
                fig.update_layout(
                    height=600, # 强制图表总高度固定为600px（主图70%, 副图25%, 留些给图例和间距）
                    margin=dict(l=10, r=10, t=30, b=10),
                    paper_bgcolor=COLOR_BG,
                    plot_bgcolor=COLOR_BG,
                    hovermode='x unified',
                    xaxis_rangeslider_visible=False,
                    xaxis2_rangeslider_visible=True, # 开启副图自带的滑块 (5%)
                    # 图例样式
                    legend=dict(
                        orientation='h',
                        yanchor='bottom', y=1.02,
                        xanchor='left', x=0,
                        bgcolor='rgba(255,255,255,0.8)',
                        bordercolor=COLOR_GRID,
                        borderwidth=0,
                        font=dict(size=10, color=COLOR_TEXT),
                        itemwidth=30
                    ),
                    font=dict(family="Roboto, 'Segoe UI', 'Microsoft YaHei', sans-serif", color=COLOR_TEXT, size=11),
                    # 构建主副图中间的切换按钮
                    updatemenus=[
                        dict(
                            type="buttons",
                            direction="right",
                            active=0,
                            x=0.01,
                            y=0.258, # 精确定位在主副图之间（无遮挡）
                            xanchor="left",
                            yanchor="middle",
                            pad={"r": 10, "t": 0, "b": 0},
                            showactive=True,
                            buttons=list([
                                dict(
                                    label="MACD",
                                    method="update",
                                    args=[
                                        {"visible": visible_macd},
                                        {"yaxis2.autorange": True}
                                    ]
                                ),
                                dict(
                                    label="BOLL",
                                    method="update",
                                    args=[
                                        {"visible": visible_boll},
                                        {"yaxis2.autorange": True}
                                    ]
                                )
                            ]),
                            bgcolor="#F8FAFC",
                            bordercolor="#E2E8F0",
                            font=dict(color="#475569", size=11)
                        )
                    ],
                    # 分隔线
                    shapes=[
                        dict(
                            type='line', xref='paper', yref='paper',
                            x0=0, x1=1, y0=0.26, y1=0.26, # 主副图分隔
                            line=dict(color=COLOR_GRID, width=1)
                        )
                    ]
                )
                
                # 滑块范围及副图设置
                fig.update_xaxes(
                    rangeslider=dict(
                        visible=True,
                        thickness=0.06, # 占据约5%-6%的高度
                        bgcolor="#F8FAFC",
                        bordercolor="#E2E8F0"
                    ),
                    row=2, col=1
                )
                
                # 坐标轴优化
                common_axis_config = dict(
                    showgrid=True,
                    gridcolor=COLOR_GRID,
                    gridwidth=1,
                    showline=True,
                    linecolor=COLOR_GRID,
                    mirror=True,
                    tickfont=dict(color=COLOR_TEXT, size=10)
                )

                # 计算默认可见区间 (最后 60 个)，供 rangeslider 使用
                total_points = len(x_labels)
                default_range = [max(0, total_points - 60 - 0.5), total_points - 1 + 0.5] if total_points > 0 else None

                fig.update_xaxes(**common_axis_config, zeroline=False, type='category', tickmode='auto', nticks=8, range=default_range)
                fig.update_yaxes(**common_axis_config, zeroline=False, row=1, col=1)
                fig.update_yaxes(**common_axis_config, zeroline=True, zerolinecolor=COLOR_GRID, row=2, col=1)

                # 移除主图X轴标签（因为共享）
                fig.update_xaxes(showticklabels=False, row=1, col=1)

            chart_container.clear()
            
            if state['indicator'] == '散户数量':
                # 散户数量模式：全屏图表
                with ui.card().classes('w-full p-0 shadow-sm border border-slate-100 rounded-xl overflow-hidden').style('height: 600px;'):
                     plot_func(fig).classes('w-full h-full')
            else:
                # 买卖助手模式：左图右分析布局，强制给定高度
                with ui.row().classes('w-full gap-3 items-stretch no-wrap').style('height: 600px;'):
                    # 左侧：图表 (占据大部分空间)
                    with ui.card().classes('flex-grow h-full min-w-0 p-0 shadow-sm border border-slate-100 rounded-xl overflow-hidden relative'):
                        plot_func(fig).classes('w-full h-full z-0')
                    
                    # 右侧：缠论分析面板 (固定宽度)
                    with ui.card().classes('w-80 h-full p-4 shadow-sm border border-slate-100 rounded-xl bg-white overflow-y-auto flex-shrink-0 flex flex-col gap-3'):
                         ui.label(f'{name} ({code})').classes('text-lg font-bold text-slate-800 leading-tight')
                         
                         # 1. 核心结论
                         with ui.row().classes('items-center gap-2'):
                             status_color = 'text-red-500' if '上涨' in analysis.get('structure', '') else 'text-green-500' if '下跌' in analysis.get('structure', '') else 'text-slate-500'
                             ui.label(analysis.get('structure', '未知结构')).classes(f'text-xl font-black {status_color}')
                             ui.badge(analysis.get('ma_alignment', '均线缠绕'), color='blue' if analysis.get('ma_alignment')=='多头排列' else 'grey').props('outline')

                         ui.separator().classes('my-1')
                         
                         # 2. 关键点位
                         with ui.grid(columns=2).classes('w-full gap-2'):
                             def info_item(label, value, color='slate-700'):
                                 with ui.column().classes('gap-0'):
                                     ui.label(label).classes('text-xs text-slate-400')
                                     ui.label(str(value)).classes(f'text-sm font-bold text-{color}')
                             
                             info_item('支撑位', analysis.get('support_price', '-'), 'red-500')
                             info_item('压力位', analysis.get('pressure_price', '-'), 'green-500')
                             info_item('RSI', analysis.get('rsi', '-'), 'purple-500')
                             info_item('MACD', analysis.get('macd', '-'), 'slate-700')

                         # 3. 操作区间
                         with ui.column().classes('w-full bg-slate-50 p-3 rounded-lg gap-1 border border-slate-100'):
                             ui.label('操作建议区间').classes('text-xs font-bold text-slate-500 mb-1')
                             with ui.row().classes('w-full justify-between items-center'):
                                 ui.label('低吸区').classes('text-xs text-slate-400')
                                 ui.label(analysis.get('buy_zone', '-')).classes('text-xs font-mono font-bold text-red-500')
                             with ui.row().classes('w-full justify-between items-center'):
                                 ui.label('高抛区').classes('text-xs text-slate-400')
                                 ui.label(analysis.get('sell_zone', '-')).classes('text-xs font-mono font-bold text-green-500')
                             with ui.row().classes('w-full justify-between items-center'):
                                 ui.label('风控线').classes('text-xs text-slate-400')
                                 ui.label(analysis.get('risk_line', '-')).classes('text-xs font-mono font-bold text-slate-700')

                         ui.separator().classes('my-1')

                         # 4. 详细策略
                         ui.label('策略建议').classes('text-sm font-bold text-slate-700')
                         with ui.column().classes('gap-2'):
                             for i, plan in enumerate(analysis.get('action_plan', [])):
                                 with ui.row().classes('items-start gap-2'):
                                     ui.label(str(i+1)+'.').classes('text-xs font-bold text-slate-400 mt-0.5')
                                     ui.label(plan).classes('text-xs text-slate-600 leading-relaxed')
                         
                         # 底部提示
                         ui.element('div').classes('flex-grow')
                         ui.label(f'更新时间: {last_date}').classes('text-xs text-slate-300 text-center w-full')

    def refresh_list():
        # Update group select options
        group_select.options = state['groups']
        group_select.update()

        list_container.clear()
        subs = get_subs()
        
        if not subs:
            with list_container:
                ui.label('列表为空').classes('text-gray-400 text-sm italic p-2')
            return

        groups = get_groups()
        
        # Determine which group is currently "active" if selection exists, to auto-expand
        # Or just expand all by default
        
        with list_container:
            for group in groups:
                # Filter subs for this group
                group_subs = [s for s in subs if s.get('group', '默认') == group]
                if not group_subs:
                    continue
                
                with ui.expansion(group, icon='folder').props('expand-separator default-opened dense header-class="text-gray-800 font-bold bg-gray-50 rounded-lg"').classes('w-full border-none mb-2 shadow-sm rounded-lg overflow-hidden'):
                    with ui.column().classes('w-full gap-1 p-1 bg-white'):
                        for sub in group_subs:
                            code = sub['code']
                            name = sub.get('name', code)
                            
                            # Check selection
                            is_sel = (state['selected_code'] == code)
                            
                            # Styling
                            bg_cls = 'bg-blue-50 border-blue-200 shadow-inner' if is_sel else 'bg-transparent hover:bg-gray-50 border-transparent'
                            text_cls = 'text-blue-900' if is_sel else 'text-gray-700'
                            
                            # Item Card
                            with ui.row().classes(f'w-full items-center justify-between p-2 rounded-md border cursor-pointer transition-all {bg_cls}') as row:
                                with ui.row().classes('items-center gap-3 flex-grow min-w-0'):
                                    # Color coded icon
                                    icon_color = 'primary' if is_sel else 'grey-5'
                                    ui.icon('trending_up', color=icon_color).classes('text-lg')
                                    with ui.column().classes('gap-0 min-w-0 flex-1'):
                                        ui.label(name).classes(f'font-bold {text_cls} leading-tight truncate w-full text-sm')
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
                                        header_label.text = '请选择左侧股票查看个股医生指标'
                                    refresh_list()
                                
                                ui.button(icon='close', on_click=lambda c=code: perform_delete(c)) \
                                .props('flat round size=xs color=grey-4').classes('opacity-60 hover:opacity-100 hover:text-red-500')

    # Initial Render
    refresh_list()
    
    # Trigger load from client local storage
    ui.timer(0, load_subs_from_browser, once=True)
