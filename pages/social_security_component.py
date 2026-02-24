from nicegui import ui
from utils.social_security_fund import SocialSecurityFund
import plotly.graph_objects as go
import pandas as pd
import asyncio
import io
import math
from concurrent.futures import ThreadPoolExecutor

# Create a thread pool for IO operations
executor = ThreadPoolExecutor(max_workers=4)

def render_social_security_panel(plotly_renderer, is_mobile=False):
    """
    Render the Social Security Fund analysis panel with Fintech Fresh style.
    Features:
    - Detailed breakdown
    - Comparison with previous period
    - Full list of holdings
    """
    # Main ID for the panel to allow refreshing
    panel_id = 'social_security_panel'
    
    # Store state references
    state = {
        'df': None,
        'exited_df': None,
        'new_df': None,
        'fund_type': 'social_security'
    }

    # --- UI Components References ---
    # Stats
    stat_total_label = None
    stat_count_label = None
    stat_new_label = None
    stat_exit_label = None
    
    # Containers
    chart_container = None
    table_container = None
    distribution_chart_container = None

    def render_table(df, exited_df=None):
        
        rows = []
        # 1. Process Current Holdings
        for _, row in df.iterrows():
            change_type = row.get('持股变化', '不变')
            change_val = row.get('持股变动数值', 0)
            change_pct = row.get('持股变动比例', 0)
            
            if pd.isna(change_val): change_val = 0
            if pd.isna(change_pct): change_pct = 0
            
            change_display = "--"
            if change_type == '新进':
                 change_display = "新进"
            elif change_val != 0:
                 prefix = "+" if change_val > 0 else ""
                 change_display = f"{prefix}{change_val/10000:.1f}万 ({change_pct:.2f}%)"
            
            # Ensure '持股市值' is a float, default to 0.0 if NaN
            mv_raw_value = float(row['持股市值']) if pd.notna(row['持股市值']) else 0.0
            mv_raw_value = round(mv_raw_value / 1e8, 2)

            rows.append({
                'code': row['股票代码'],
                'name': row['股票简称'],
                'mv_raw': mv_raw_value, 
                # 'mv': f"{mv_raw_value/1e8:.2f}亿", # Unused if we use formatter
                'vol': f"{row['持股总数']/10000:.0f}万",
                'change_type': change_type,
                'change_val': change_val, 
                'change_txt': change_display
            })

        # 2. Process Exited Holdings
        if exited_df is not None and not exited_df.empty:
            for _, row in exited_df.iterrows():
                 prev_vol = row.get('持股总数', 0)
                 prev_vol = float(prev_vol) if prev_vol else 0
                 rows.append({
                    'code': row['股票代码'],
                    'name': row['股票简称'],
                    'mv_raw': 0.0, 
                    # 'mv': "0.00亿",
                    'vol': "0万",
                    'change_type': "退出",
                    'change_val': -prev_vol, 
                    'change_txt': "已清仓"
                })

        # Define Grid
        column_defs = [
            {'headerName': '代码', 'field': 'code', 'sortable': True, 'filter': True, 'width': 90, 'pinned': 'left'},
            {'headerName': '名称', 'field': 'name', 'sortable': True, 'filter': True, 'width': 100, 'pinned': 'left', 'cellStyle': {'fontWeight': 'bold'}},
            {'headerName': '持股市值(亿)', 'field': 'mv_raw', 'sortable': True, 'width': 130, 'sort': 'desc',
             'cellStyle': {'textAlign': 'right', 'color': '#4338ca', 'fontWeight': 'bold'}},
            {'headerName': '持股数量', 'field': 'vol', 'sortable': True, 'width': 120, 'cellStyle': {'textAlign': 'right'}},
            {'headerName': '变动类型', 'field': 'change_type', 'sortable': True, 'filter': True, 'width': 100,
             'cellClassRules': {
                 'text-orange-600 font-bold': "x == '新进'",
                 'text-red-600': "x == '增仓'",
                 'text-green-600': "x == '减仓'",
                 'text-gray-500 italic': "x == '退出'"
             }},
            {'headerName': '变动详情 (数量/比例)', 'field': 'change_txt', 'sortable': True, 'width': 180, 'cellStyle': {'textAlign': 'right'}},
        ]

        with table_container:
            ui.aggrid({
                'columnDefs': column_defs,
                'rowData': rows,
                'pagination': True,
                'paginationPageSize': 50,
                # 'domLayout': 'autoHeight', # Removed to ensure it fits in container with scroll
                'defaultColDef': {'resizable': True, 'filter': True}, # Removed floatingFilter
                'rowSelection': 'single',
                'animateRows': True,
            }).classes('w-full h-full border-none')

    async def load_data(force=False):
        fund_name = "社保基金" if state['fund_type'] == 'social_security' else "基本养老保险"
        if force:
            ui.notify(f'正在刷新{fund_name}数据...', type='info', position='top')
        
        try:
            ssf = SocialSecurityFund(fund_type=state['fund_type'])
            
            # 1. Fetch Current Holdings (Primary Data)
            df = await asyncio.get_running_loop().run_in_executor(executor, lambda: ssf.get_latest_holdings(force_update=force))
            state['df'] = df
            
            if df is None or df.empty:
                ui.notify(f'未能获取到{fund_name}数据', type='warning')
                # Clear UI if empty
                if stat_total_label: stat_total_label.text = "-- 亿元"
                if stat_count_label: stat_count_label.text = "-- 只"
                if chart_container: chart_container.clear()
                if table_container: table_container.clear()
                return

            # Update Basic Stats immediately
            total_mv = df['持股市值'].sum()
            count = len(df)
            
            if stat_total_label: stat_total_label.text = f"{total_mv/1e8:.2f} 亿元"
            if stat_count_label: stat_count_label.text = f"{count} 只"

            # 2. Render Charts & Table with available data
            render_charts(df)
            render_table(df)

            # 3. Fetch Comparison Data (New/Exited) in background
            loop = asyncio.get_running_loop()
            new_future = loop.run_in_executor(executor, lambda: ssf.get_new_positions())
            exit_future = loop.run_in_executor(executor, lambda: ssf.get_exited_positions())
            
            new_df, exited_df = await asyncio.gather(new_future, exit_future)
            
            state['new_df'] = new_df
            state['exited_df'] = exited_df
            
            # Update Comparison Stats
            new_count = len(new_df) if not new_df.empty else 0
            exit_count = len(exited_df) if not exited_df.empty else 0
            
            if stat_new_label: stat_new_label.text = f"{new_count} 只"
            if stat_exit_label: stat_exit_label.text = f"{exit_count} 只"
            
            # Re-render table to include exited stocks
            render_table(df, exited_df)
            
            ui.notify(f'{fund_name}数据加载完成', type='positive', position='top')

        except Exception as e:
            print(f"Error loading data: {e}") 
            ui.notify(f'加载失败: {str(e)}', type='negative')
            if chart_container:
                chart_container.clear()
                with chart_container:
                     ui.label('数据加载失败').classes('absolute-center text-red-500')

    async def change_fund_type(value):
        if state['fund_type'] == value: return
        state['fund_type'] = value
        # Trigger reload (awaiting preserves context)
        await load_data(force=False)

    def render_charts(df):
        # --- Top 10 Chart ---
        if not chart_container: return
        chart_container.clear()
        
        top_10 = df.nlargest(10, '持股市值').sort_values('持股市值', ascending=True)
        
        fig = go.Figure(go.Bar(
            x=top_10['持股市值'] / 1e8,
            y=top_10['股票简称'],
            orientation='h',
            marker=dict(
                color=top_10['持股市值'],
                colorscale='Viridis', 
                showscale=False
            ),
            text=top_10['持股市值'].apply(lambda x: f"{x/1e8:.1f}亿"),
            textposition='auto',
            hovertemplate='%{y}<br>市值: %{x:.2f}亿元<extra></extra>'
        ))

        fig.update_layout(
            margin=dict(l=20, r=20, t=30, b=20),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=350,
            xaxis=dict(showgrid=True, gridcolor='#F3F4F6', title='市值 (亿元)'),
            yaxis=dict(showgrid=False),
            font=dict(family="Roboto, sans-serif"),
            title=dict(text='重仓股 TOP 10 (按市值)', x=0.5, xanchor='center', font=dict(size=14))
        )
        
        with chart_container:
             plotly_renderer(fig).classes('w-full h-full')

        # --- Distribution Chart ---
        if not distribution_chart_container: return
        distribution_chart_container.clear()
        
        # Calculate distribution
        change_counts = df['持股变化'].value_counts()
        
        fig_pie = go.Figure(data=[go.Pie(
            labels=change_counts.index, 
            values=change_counts.values, 
            hole=.5,
            marker=dict(colors=['#F59E0B', '#10B981', '#EF4444', '#6B7280']) 
        )])
        
        fig_pie.update_layout(
            margin=dict(l=20, r=20, t=30, b=20),
            paper_bgcolor='rgba(0,0,0,0)',
            height=350,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            title=dict(text='持仓变动分布', x=0.5, xanchor='center', font=dict(size=14))
        )
        
        with distribution_chart_container:
            plotly_renderer(fig_pie).classes('w-full h-full')

    def export_to_excel():
        df = state['df']
        exited_df = state['exited_df']
        if df is None or df.empty:
            ui.notify('没有数据可导出', type='warning')
            return
        
        rows = []
        # 1. Process Current Holdings
        for _, row in df.iterrows():
            change_type = row.get('持股变化', '不变')
            change_val = row.get('持股变动数值', 0)
            change_pct = row.get('持股变动比例', 0)
            
            if pd.isna(change_val): change_val = 0
            if pd.isna(change_pct): change_pct = 0
            
            # Ensure '持股市值' is a float, default to 0.0 if NaN
            mv_raw_value = float(row['持股市值']) if pd.notna(row['持股市值']) else 0.0
            mv_raw_value = round(mv_raw_value / 1e8, 2)

            rows.append({
                'code': row['股票代码'],
                'name': row['股票简称'],
                'mv_raw': mv_raw_value, 
                'vol': row['持股总数'],  # 原始数值
                'change_type': change_type,
                'change_val': change_val,  # 原始变动数值
            })

        # 2. Process Exited Holdings
        if exited_df is not None and not exited_df.empty:
            for _, row in exited_df.iterrows():
                 prev_vol = row.get('持股总数', 0)
                 prev_vol = float(prev_vol) if prev_vol else 0
                 rows.append({
                    'code': row['股票代码'],
                    'name': row['股票简称'],
                    'mv_raw': 0.0, 
                    'vol': 0,  # 原始数值
                    'change_type': "退出",
                    'change_val': -prev_vol,  # 原始变动数值
                })
        
        df_export = pd.DataFrame(rows)
        # Rename columns to Chinese
        df_export = df_export.rename(columns={
            'code': '股票代码',
            'name': '股票简称',
            'mv_raw': '持股市值(亿)',
            'vol': '持股数量',
            'change_type': '变动类型',
            'change_val': '变动数值'
        })
        
        # Create Excel in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_export.to_excel(writer, sheet_name='社保持仓明细', index=False)
        output.seek(0)
        
        # Download
        ui.download(output.getvalue(), filename='社保持仓明细.xlsx', media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        ui.notify('Excel 文件已生成并开始下载', type='positive')

    def render_table(df, exited_df=None):
        if not table_container: return
        table_container.clear()
        
        rows = []
        # 1. Process Current Holdings
        for _, row in df.iterrows():
            change_type = row.get('持股变化', '不变')
            change_val = row.get('持股变动数值', 0)
            change_pct = row.get('持股变动比例', 0)
            
            if pd.isna(change_val): change_val = 0
            if pd.isna(change_pct): change_pct = 0
            
            change_display = "--"
            if change_type == '新进':
                 change_display = "新进"
            elif change_val != 0:
                 prefix = "+" if change_val > 0 else ""
                 change_display = f"{prefix}{change_val/10000:.1f}万 ({change_pct:.2f}%)"
            
            # Ensure '持股市值' is a float, default to 0.0 if NaN
            mv_raw_value = float(row['持股市值']) if pd.notna(row['持股市值']) else 0.0
            mv_raw_value = round(mv_raw_value / 1e8, 2)

            rows.append({
                'code': row['股票代码'],
                'name': row['股票简称'],
                'mv_raw': mv_raw_value, 
                # 'mv': f"{mv_raw_value/1e8:.2f}亿", # Unused if we use formatter
                'vol': f"{row['持股总数']/10000:.0f}万",
                'change_type': change_type,
                'change_val': change_val, 
                'change_txt': change_display
            })

        # 2. Process Exited Holdings
        if exited_df is not None and not exited_df.empty:
            for _, row in exited_df.iterrows():
                 prev_vol = row.get('持股总数', 0)
                 prev_vol = float(prev_vol) if prev_vol else 0
                 rows.append({
                    'code': row['股票代码'],
                    'name': row['股票简称'],
                    'mv_raw': 0.0, 
                    # 'mv': "0.00亿",
                    'vol': "0万",
                    'change_type': "退出",
                    'change_val': -prev_vol, 
                    'change_txt': "已清仓"
                })

        # Define Grid
        column_defs = [
            {'headerName': '代码', 'field': 'code', 'sortable': True, 'filter': True, 'width': 90, 'pinned': 'left'},
            {'headerName': '名称', 'field': 'name', 'sortable': True, 'filter': True, 'width': 100, 'pinned': 'left', 'cellStyle': {'fontWeight': 'bold'}},
            {'headerName': '持股市值(亿)', 'field': 'mv_raw', 'sortable': True, 'width': 130, 'sort': 'desc',
             'cellStyle': {'textAlign': 'right', 'color': '#4338ca', 'fontWeight': 'bold'}},
            {'headerName': '持股数量', 'field': 'vol', 'sortable': True, 'width': 120, 'cellStyle': {'textAlign': 'right'}},
            {'headerName': '变动类型', 'field': 'change_type', 'sortable': True, 'filter': True, 'width': 100,
             'cellClassRules': {
                 'text-orange-600 font-bold': "x == '新进'",
                 'text-red-600': "x == '增仓'",
                 'text-green-600': "x == '减仓'",
                 'text-gray-500 italic': "x == '退出'"
             }},
            {'headerName': '变动详情 (数量/比例)', 'field': 'change_txt', 'sortable': True, 'width': 180, 'cellStyle': {'textAlign': 'right'}},
        ]

        with table_container:
            ui.aggrid({
                'columnDefs': column_defs,
                'rowData': rows,
                'pagination': True,
                'paginationPageSize': 50,
                # 'domLayout': 'autoHeight', # Removed to ensure it fits in container with scroll
                'defaultColDef': {'resizable': True, 'filter': True}, # Removed floatingFilter
                'rowSelection': 'single',
                'animateRows': True,
            }).classes('w-full h-full border-none')

    # --- Layout Construction ---

    # 0. Header & Toggle
    with ui.row().classes('w-full justify-between items-center mb-4'):
         ui.label('国家队持仓分析').classes('text-lg font-bold text-gray-800')
         with ui.row().classes('bg-gray-100 p-1 rounded-lg'):
             ui.toggle({
                 'social_security': '社保基金', 
                 'pension': '养老金'
             }, value='social_security', on_change=lambda e: change_fund_type(e.value)) \
             .props('no-caps unelevated toggle-color=indigo text-color=grey-7').classes('shadow-none')
    
    # 1. Stats Row
    with ui.row().classes('w-full gap-4 md:gap-6 mb-6'):
        # Style helper
        def stat_card(label, icon, color, bg_gradient):
            with ui.card().classes(f'flex-1 min-w-[150px] {bg_gradient} p-4 rounded-xl shadow-sm border border-{color}-100 relative overflow-hidden'):
                ui.element('div').classes(f'absolute -right-4 -top-4 w-20 h-20 rounded-full bg-{color}-100 opacity-50')
                with ui.row().classes('items-center gap-3 relative z-10'):
                    ui.icon(icon, color=color).classes('text-3xl bg-white p-2 rounded-lg shadow-sm')
                    with ui.column().classes('gap-0'):
                        ui.label(label).classes('text-sm text-gray-500 font-medium')
                        l = ui.label('--').classes(f'text-2xl font-bold text-{color}-900')
                return l

        stat_total_label = stat_card('总持股市值', 'account_balance_wallet', 'indigo', 'bg-gradient-to-br from-indigo-50 to-white')
        stat_count_label = stat_card('持仓股票数', 'list_alt', 'teal', 'bg-gradient-to-br from-teal-50 to-white')
        stat_new_label = stat_card('本季新进', 'fiber_new', 'orange', 'bg-gradient-to-br from-orange-50 to-white')
        stat_exit_label = stat_card('本季退出', 'exit_to_app', 'red', 'bg-gradient-to-br from-red-50 to-white')

    # 2. Charts Row
    with ui.row().classes('w-full gap-6 mb-6'):
        # Left: Top 10 (Flex grow to take available space, min width to prevent squashing)
        with ui.card().classes('flex-[3] min-w-[300px] p-4 bg-white rounded-xl shadow-sm border border-gray-200'):
            chart_container = ui.element('div').classes('w-full h-[350px]')
            with chart_container:
                ui.spinner('dots', size='lg', color='primary').classes('absolute-center')
        
        # Right: Distribution (Flex grow smaller)
        with ui.card().classes('flex-[2] min-w-[300px] p-4 bg-white rounded-xl shadow-sm border border-gray-200'):
            distribution_chart_container = ui.element('div').classes('w-full h-[350px]')
            with distribution_chart_container:
                ui.spinner('dots', size='lg', color='primary').classes('absolute-center')

    # 3. Table Section
    with ui.card().classes('w-full p-0 bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden flex flex-col'):
        # Header
        with ui.row().classes('w-full px-4 py-3 border-b border-gray-100 justify-between items-center bg-gray-50/50'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('table_chart', color='indigo').classes('text-xl')
                ui.label('全部持仓明细 (含变动对比)').classes('text-base font-bold text-gray-800')
            
            with ui.row().classes('items-center gap-2'):
                # Export Button
                ui.button(icon='download', on_click=export_to_excel).props('flat round dense color=green').tooltip('导出Excel')
                # Reload Button
                ui.button(icon='refresh', on_click=lambda: load_data(force=True)).props('flat round dense color=indigo').tooltip('强制刷新')

        # Table Container
        table_container = ui.element('div').classes('w-full relative h-[600px]')
        with table_container:
             ui.spinner('dots', size='lg', color='primary').classes('absolute-center')

    # Trigger initial load
    ui.timer(0, load_data, once=True)
