import asyncio
import io
import pandas as pd
from nicegui import ui
from utils.national_team import NationalTeamSelector


def render_national_team_panel(plotly_renderer=None, is_mobile=False):
    selector = NationalTeamSelector()
    state = {
        'days': 5,
        'fund_type': 'social_security',
        'df': pd.DataFrame(),
        'meta': {},
    }

    with ui.card().classes('w-full border border-gray-200 rounded-xl shadow-sm bg-white p-4 flex flex-col gap-3'):
        with ui.row().classes('w-full items-center justify-between gap-4'):
            with ui.column().classes('gap-0'):
                ui.label('国家队股票筛选').classes('text-lg md:text-xl font-bold text-gray-800 tracking-tight')
                ui.label('联动主力资金雷达，聚焦国家队持仓与缠论提示').classes('text-xs text-gray-400')
            with ui.row().classes('items-center gap-2'):
                last_update_label = ui.label('').classes('text-[10px] text-indigo-400 bg-indigo-50 px-1.5 rounded-full font-mono')

        with ui.row().classes('w-full items-center justify-between gap-3 flex-wrap'):
            with ui.row().classes('items-center gap-2'):
                duration_container = ui.row().classes('bg-gray-100 rounded-lg p-1 gap-1 items-center')
                fund_toggle = ui.toggle(
                    {'social_security': '社保基金', 'pension': '养老金'},
                    value=state['fund_type'],
                    on_change=lambda e: change_fund_type(e.value),
                ).props('no-caps unelevated toggle-color=indigo text-color=grey-7').classes('shadow-none')
            with ui.row().classes('items-center gap-2'):
                refresh_btn = ui.button('同步最新数据', icon='refresh', on_click=lambda: load_data(force=True)) \
                    .props('outline color=indigo size=sm') \
                    .classes('text-indigo-600')

        stats_container = ui.row().classes('w-full gap-3 flex-wrap')
        table_container = ui.column().classes('w-full gap-4')

    def update_duration_options():
        options = [(3, '3天'), (5, '5天'), (10, '10天')]
        duration_container.clear()
        with duration_container:
            for d, lbl in options:
                is_active = (state['days'] == d)
                ui.button(lbl, on_click=lambda val=d: set_duration(val)) \
                    .props(f'flat dense no-caps size=sm {"color=indigo" if is_active else "text-color=grey-7"}') \
                    .classes(f'px-2 md:px-3 rounded-md transition-all {"bg-white shadow-sm font-bold" if is_active else "hover:bg-gray-200"} text-xs')

    def render_stats(df):
        stats_container.clear()
        total = len(df)
        sectors = df['同花顺行业'].nunique() if '同花顺行业' in df.columns else 0
        above_all = df[(df['站上MA5'] == '是') & (df['站上MA10'] == '是') & (df['站上MA20'] == '是')].shape[0]
        items = [
            ('筛选结果', f'{total} 只', 'folder_special', 'indigo', 'bg-indigo-50'),
            ('涉及板块', f'{sectors} 个', 'hub', 'teal', 'bg-teal-50'),
            ('强势结构', f'{above_all} 只', 'trending_up', 'rose', 'bg-rose-50'),
        ]
        with stats_container:
            for title, val, icon, color, bg in items:
                with ui.card().classes(f'p-3 rounded-lg border border-gray-100 {bg}'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon(icon, color=color).classes('text-lg')
                        with ui.column().classes('gap-0'):
                            ui.label(title).classes('text-xs text-gray-500 font-bold')
                            ui.label(val).classes('text-sm font-black text-gray-700')

    def download_excel():
        df = state['df']
        if df is None or df.empty:
            ui.notify('暂无可下载数据', type='warning')
            return
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='国家队股票筛选', index=False)
        output.seek(0)
        ui.download(output.getvalue(), filename='国家队股票筛选.xlsx', media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        ui.notify('Excel 文件已生成并开始下载', type='positive')

    def render_table():
        table_container.clear()
        df = state['df']
        if df is None or df.empty:
            with table_container:
                with ui.card().classes('w-full p-6 items-center justify-center bg-white rounded-xl shadow-sm border border-gray-200'):
                    ui.icon('info', size='2rem', color='grey-4')
                    ui.label('暂无符合条件的国家队股票').classes('text-gray-500 text-sm mt-2')
            return
        render_stats(df)
        with table_container:
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('筛选明细').classes('text-sm font-bold text-gray-700')
                ui.button('导出Excel', icon='file_download', on_click=download_excel).props('small outline color=green')
            rows = []
            for _, row in df.iterrows():
                rows.append({
                    'code': row.get('股票代码'),
                    'name': row.get('股票简称'),
                    'industry': row.get('同花顺行业'),
                    'sector_flow': row.get('板块净流入(亿)', 0),
                    'mv': row.get('持股市值(亿)', 0),
                    'price': row.get('最新价') if pd.notna(row.get('最新价')) else None,
                    'ma5': row.get('MA5') if pd.notna(row.get('MA5')) else None,
                    'ma10': row.get('MA10') if pd.notna(row.get('MA10')) else None,
                    'ma20': row.get('MA20') if pd.notna(row.get('MA20')) else None,
                    'above5': row.get('站上MA5'),
                    'above10': row.get('站上MA10'),
                    'above20': row.get('站上MA20'),
                    'hint': row.get('缠论提示'),
                })
            
            # Format function for numeric columns
            fmt_num = 'value => (value !== null && value !== undefined) ? Number(value).toFixed(2) : "--"'
            
            cols = [
                {'name': 'code', 'label': '股票代码', 'field': 'code', 'sortable': True, 'align': 'left'},
                {'name': 'name', 'label': '股票简称', 'field': 'name', 'sortable': True, 'align': 'left'},
                {'name': 'industry', 'label': '同花顺行业', 'field': 'industry', 'sortable': True, 'align': 'left'},
                {'name': 'sector_flow', 'label': '板块净流入(亿)', 'field': 'sector_flow', 'sortable': True, 'align': 'right', ':format': fmt_num},
                {'name': 'mv', 'label': '持股市值(亿)', 'field': 'mv', 'sortable': True, 'align': 'right', ':format': fmt_num},
                {'name': 'price', 'label': '最新价', 'field': 'price', 'sortable': True, 'align': 'right', ':format': fmt_num},
                {'name': 'ma5', 'label': 'MA5', 'field': 'ma5', 'sortable': True, 'align': 'right', ':format': fmt_num},
                {'name': 'ma10', 'label': 'MA10', 'field': 'ma10', 'sortable': True, 'align': 'right', ':format': fmt_num},
                {'name': 'ma20', 'label': 'MA20', 'field': 'ma20', 'sortable': True, 'align': 'right', ':format': fmt_num},
                {'name': 'above5', 'label': '站上MA5', 'field': 'above5', 'sortable': True, 'align': 'center'},
                {'name': 'above10', 'label': '站上MA10', 'field': 'above10', 'sortable': True, 'align': 'center'},
                {'name': 'above20', 'label': '站上MA20', 'field': 'above20', 'sortable': True, 'align': 'center'},
                {'name': 'hint', 'label': '缠论提示', 'field': 'hint', 'sortable': True, 'align': 'left'},
            ]
            ui.table(columns=cols, rows=rows, pagination={'rowsPerPage': 10, 'sortBy': 'mv', 'descending': True}).classes('w-full bg-white shadow-sm border border-gray-200')

    async def load_data(force=False):
        stats_container.clear()
        table_container.clear()
        
        progress_info = {'text': '正在筛选国家队股票...'}
        
        with table_container:
            with ui.row().classes('items-center gap-2'):
                ui.spinner(type='dots', size='2rem', color='indigo')
                lbl = ui.label('正在筛选国家队股票...').classes('text-xs text-gray-400')
            
            # Timer to update UI from progress_info
            timer = ui.timer(0.1, lambda: lbl.set_text(progress_info['text']))
        
        def progress_callback(current, total, message):
            progress_info['text'] = message
            print(f"[NationalTeam] {message}")

        loop = asyncio.get_running_loop()
        try:
            df, meta = await loop.run_in_executor(
                None,
                lambda: selector.get_selection(
                    days=state['days'],
                    fund_type=state['fund_type'],
                    force_update=force,
                    progress_callback=progress_callback
                ),
            )
        finally:
            timer.cancel()
            
        state['df'] = df
        state['meta'] = meta
        if meta and meta.get('updated_at'):
            last_update_label.set_text(f"最后刷新: {meta.get('updated_at')}")
            last_update_label.set_visibility(True)
        else:
            last_update_label.set_visibility(False)
        render_table()

    async def set_duration(val):
        state['days'] = val
        update_duration_options()
        await load_data(force=False)

    async def change_fund_type(val):
        state['fund_type'] = val
        await load_data(force=False)

    update_duration_options()
    ui.timer(0.1, lambda: asyncio.create_task(load_data(force=False)), once=True)
