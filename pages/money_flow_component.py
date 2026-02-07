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
    with ui.row().classes('w-full items-stretch gap-6 flex-col md:flex-row'):

        # === Left Column: Subscription Management ===
        # Modified: Full width on mobile, fixed width on PC. Height auto on mobile (scrollable list inside limitation?), fixed on PC.
        with ui.card().classes('w-full md:w-[320px] flex-none p-4 gap-4 bg-white rounded-xl shadow-sm border border-gray-200 h-auto md:h-[700px] flex flex-col'):
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
        with ui.column().classes('flex-grow h-[500px] md:h-[700px] gap-4 min-w-0'):
            # Header
            with ui.row().classes('w-full justify-between items-center bg-white p-5 rounded-xl shadow-sm border border-gray-200 flex-none'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('analytics', color='primary').classes('text-3xl')
                    header_label = ui.label('请选择左侧股票查看资金流向').classes('text-2xl font-bold text-gray-800 tracking-tight')
                
                with ui.row().classes('items-center gap-3'):
                    # Time Range Selector - Chip style
                    time_options = ['近1月', '近3月', '近6月', '近1年', '全部']
                    
                    async def set_time_range(val):
                        # Simple re-render of this specific UI part is tricky in NiceGUI loops, 
                        # so we rely on the header container being static and state being dynamic?
                        # Actually, toggling button style requires re-rendering the button group.
                        # For simplicity, we just update state and chart, button style might lag unless we wrap buttons in a clearable container.
                        state['time_range'] = val
                        # Re-render buttons (a bit hacky but works for instant feedback)
                        header_controls.clear()
                        with header_controls:
                            render_time_controls()
                            render_sync_btn()
                        
                        if state['selected_code']:
                            await render_chart(state['selected_code'], state['selected_name'])

                    header_controls = ui.row().classes('items-center gap-3')
                    
                    def render_time_controls():
                        with ui.row().classes('bg-gray-100 rounded-lg p-1 gap-1'):
                            for opt in time_options:
                                is_active = (state['time_range'] == opt)
                                ui.button(opt, on_click=lambda o=opt: set_time_range(o)) \
                                    .props(f'flat dense no-caps size=sm {"color=primary" if is_active else "text-color=grey-8"}') \
                                    .classes(f'px-3 rounded-md transition-all {"bg-white shadow-sm font-bold" if is_active else "hover:bg-gray-200"}')

                    def render_sync_btn():
                        async def update_btn_click():
                            if state['selected_code']:
                                await render_chart(state['selected_code'], state['selected_name'], force=True)
                            else:
                                ui.notify('请先选择股票', type='warning')
                        ui.button('同步最新', icon='sync', on_click=update_btn_click) \
                        .props('outline color=primary size=sm rounded-lg')

                    with header_controls:
                        render_time_controls()
                        render_sync_btn()

            # Chart Area
            chart_container = ui.card().classes('w-full flex-grow p-2 no-inner-shadow')


    # -- Logic Functions --
    
    async def render_chart(code, name, force=False):
        if chart_container.is_deleted or header_label.is_deleted: return
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
        
        if chart_container.is_deleted: return
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
                                        header_label.text = '请选择左侧股票'
                                    refresh_list()
                                
                                ui.button(icon='close', on_click=lambda c=code: perform_delete(c)) \
                                .props('flat round size=xs color=grey-4').classes('opacity-60 hover:opacity-100 hover:text-red-500')

    # Initial Render
    refresh_list()
    
    # Trigger load from client local storage
    ui.timer(0, load_subs_from_browser, once=True)
