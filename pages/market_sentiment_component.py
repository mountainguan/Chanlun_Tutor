from nicegui import ui
from utils.market_sentiment import MarketSentiment
from utils.index_data import IndexDataManager
from utils.macro_data import get_savings_mv_ratio_data
from pages.shibor_component import render_shibor_panel
import plotly.graph_objects as go
import pandas as pd
import asyncio
import io
import math
from concurrent.futures import ThreadPoolExecutor

# Create a thread pool for IO operations
executor = ThreadPoolExecutor(max_workers=2)

def render_market_sentiment_panel(plotly_renderer, is_mobile=False):
    # Top Layout: Info + Gauge
    # Modified for Mobile: Stack vertically on mobile (flex-col), row on PC (md:flex-row)
    # Unified gap to gap-6 for consistency
    with ui.row().classes('w-full gap-6 items-stretch flex-col md:flex-row'):
        # Info Card
        # Mobile: Compact padding (p-3), full width. PC: p-4, min-w-300
        with ui.card().classes('flex-1 w-full md:min-w-[300px] bg-white p-3 md:p-4 rounded-xl shadow-sm border border-gray-200 relative overflow-hidden'):
            # 装饰性背景
            ui.element('div').classes('absolute -right-6 -top-6 w-24 h-24 rounded-full bg-blue-50 opacity-40')
            
            with ui.row().classes('items-center mb-2 md:mb-3 justify-between'):
                with ui.row().classes('items-center scale-90 md:scale-100 origin-left'):
                    ui.icon('psychology', color='indigo').classes('text-2xl')
                    ui.label('情绪温度模型').classes('text-lg font-bold text-gray-800')
                
                # Mobile only: Toggle description
                if is_mobile:
                    with ui.button(icon='help_outline', on_click=lambda: desc_container.set_visibility(not desc_container.visible)).props('flat round dense color=grey'):
                        pass

            # Container for description (Collapsible on mobile)
            desc_classes = 'w-full'
            if is_mobile:
                 desc_wrapper = ui.column().classes('w-full transition-all duration-300')
                 desc_wrapper.set_visibility(False)
                 desc_container = desc_wrapper
            else:
                 desc_wrapper = ui.column().classes('w-full')
                 desc_container = desc_wrapper # No toggle needed on PC usually, but let's keep logic simple

            with desc_wrapper:
                 # 核心逻辑与公式
                 ui.html('<div class="text-gray-600 text-sm mb-3"><b>核心逻辑：</b>情绪由<span class="text-indigo-600 font-bold">杠杆力度</span>与<span class="text-blue-600 font-bold">成交活跃度</span>共同驱动。</div>', sanitize=False)
                 # 公式说明
                 ui.html('<div class="text-xs w-full mb-3 text-gray-600 bg-gray-100 p-2 rounded border border-gray-200 font-mono">模型公式：[(融资占比% - 4.5) &times; 7.5] + [(成交额(万亿) - 0.65) &times; 17]</div>', sanitize=False)
            
            # Legend stays visible
            with ui.row().classes('w-full gap-2 text-xs mt-2'):
                with ui.column().classes('flex-1 bg-red-50 p-2 rounded-lg border border-red-100 items-center justify-center'):
                    ui.label('>100 (高温)').classes('font-bold text-red-700')
                    ui.label('风险聚集').classes('text-red-400 scale-90')
                with ui.column().classes('flex-1 bg-gray-100 p-2 rounded-lg border border-gray-200 items-center justify-center'):
                    ui.label('0~100 (震荡)').classes('font-bold text-gray-700')
                    ui.label('正常波动').classes('text-gray-400 scale-90')
                with ui.column().classes('flex-1 bg-green-50 p-2 rounded-lg border border-green-100 items-center justify-center'):
                    ui.label('<0 (冰点)').classes('font-bold text-green-700')
                    ui.label('机会区域').classes('text-green-400 scale-90')
                    
            ui.label('数据来源：交易所/金十数据').classes('text-xs text-gray-400 mt-auto pt-2')

        # Gauge Container
        # Mobile: w-full, min-h-[280px] to ensure visibility. PC: flex-1 (share width), height stretched by sibling.
        gauge_container = ui.card().classes('flex-1 w-full md:min-w-[300px] min-h-[280px] items-center justify-center p-0 gap-0 bg-white rounded-xl shadow-sm border border-gray-200 relative')
        with gauge_container:
                ui.spinner(type='dots', size='lg', color='primary')
                ui.label('计算数据中...').classes('text-gray-400 text-sm mt-2')

    # Status Label
    status_label = ui.label('正在连接数据接口...').classes('text-lg text-indigo-600 animate-pulse font-bold')
    
    # Chart Container (Card with Header)
    chart_height_class = 'h-[440px]' if is_mobile else 'h-[520px]'
    chart_container = ui.card().classes(f'w-full {chart_height_class} border border-gray-200 rounded-xl shadow-sm bg-white p-4 flex flex-col gap-0')
    
    # Define controls ahead of time to capture reference, but place them inside card
    index_select = None
    data_type_select = None
    
    with chart_container:
        # Header Row
        # Mobile optimization: Allow wrapping
        with ui.row().classes('w-full justify-between items-center mb-2 pb-2 border-b border-gray-200 flex-wrap gap-y-2'):
                # Title Group
                with ui.row().classes('items-center gap-2'):
                    ui.icon('show_chart', color='indigo').classes('text-2xl')
                    ui.label('情绪温度趋势 (近三年)').classes('text-lg md:text-xl font-bold text-gray-800')
                
                # Actions Group
                with ui.row().classes('items-center gap-2 md:gap-4 flex-wrap justify-end flex-1'):
                    index_select = ui.select(
                        options=["上证指数", "深证成指", "创业板指", "上证50", "沪深300", "中证500"],
                        value="上证指数",
                        label="对比指数",
                        on_change=lambda e: fetch_and_draw_market()
                    ).props('dense outlined options-dense bg-white behavior=menu').classes('w-28 md:w-32 text-xs')

                    data_type_select = ui.select(
                        options=["收盘价", "指数振幅"],
                        value="收盘价",
                        label="数据类型",
                        on_change=lambda e: fetch_and_draw_market()
                    ).props('dense outlined options-dense bg-white behavior=menu').classes('w-28 md:w-32 text-xs')
                    
                    ui.button('刷新', icon='refresh', on_click=lambda: fetch_and_draw_market(force=True)) \
                        .props('flat color=indigo icon-right dense').classes('text-indigo-600 font-bold text-xs md:text-sm')

        # Plot Area
        chart_plot_area = ui.column().classes('w-full flex-1 min-h-0 relative p-0 m-0')

    # Data Table Container
    data_container = ui.column().classes('w-full hidden')
    
    # Shibor Chart Container
    # render_shibor_panel(plotly_renderer, is_mobile) -> Creates its own card, will be spaced by parent gap

    render_shibor_panel(plotly_renderer=plotly_renderer, is_mobile=is_mobile)

    # Savings Ratio Table Container
    savings_container = ui.column().classes('w-full')

    async def fetch_and_update_savings_ratio(force=False):
        if savings_container.is_deleted:
            return
        if force:
            ui.notify('正在刷新存款规模与市值比例数据...', type='info')
        
        try:
            # Pass 'force' to ensure cache refresh when requested
            savings_df = await asyncio.get_running_loop().run_in_executor(executor, lambda: get_savings_mv_ratio_data(force_update=force))
            if savings_df is not None and not savings_df.empty and not savings_container.is_deleted:
                savings_container.clear()
                with savings_container:
                    with ui.card().classes('w-full p-6 rounded-xl border border-gray-200 shadow-sm bg-white'):
                        with ui.row().classes('w-full items-center justify-between mb-4'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('account_balance', color='teal').classes('text-2xl')
                                ui.label('存款规模与A股总市值比例').classes('text-xl font-bold text-gray-800')
                            
                            with ui.row().classes('items-center gap-2'):
                                # Independent Refresh Button
                                ui.button(icon='refresh', on_click=lambda: fetch_and_update_savings_ratio(force=True)) \
                                    .props('flat color=teal round') \
                                    .tooltip('刷新存款数据')

                                # Export Button
                                def export_csv():
                                    content = savings_df.to_csv(index=False, encoding='utf-8-sig')
                                    ui.download(content.encode('utf-8-sig'), 'deposit_market_ratio.csv')
                                    ui.notify('准备导出存款比例数据', type='info')
                                    
                                ui.button('导出数据', icon='download', on_click=export_csv) \
                                    .props('flat color=teal icon-right').classes('text-teal-600')

                        # Info text
                        ui.label('该表展示了总存款、企业存款和储蓄存款相对于股市估值的倍数。比例越高，说明存款总量相对于股市体量越充裕。').classes('text-sm text-gray-500 mb-4')
                        
                        # Create table
                        # Using last 15 entries for a bit more history
                        table_data = savings_df.sort_values('月份', ascending=False).head(15).copy()
                        
                        # Convert ratios to "1 : X" format for display
                        for col in ['总存款比例', '企业存款比例', '储蓄存款比例']:
                            if col in table_data.columns:
                                table_data[col] = table_data[col].apply(lambda x: f"1 : {x:.2f}")
                                
                        rows = table_data.to_dict('records')
                        columns = [
                            {'name': '月份', 'label': '月份', 'field': '月份', 'align': 'left'},
                            {'name': '交易日期', 'label': '对比日', 'field': '交易日期', 'align': 'center'},
                            {'name': '总存款比例', 'label': '总存款 : 市值', 'field': '总存款比例', 'sortable': True, 'align': 'center', 'style': 'font-weight: bold'},
                            {'name': '企业存款比例', 'label': '企业存款 : 市值', 'field': '企业存款比例', 'sortable': True, 'align': 'center'},
                            {'name': '储蓄存款比例', 'label': '储蓄存款 : 市值', 'field': '储蓄存款比例', 'sortable': True, 'align': 'center'},
                            {'name': 'A股总市值(亿)', 'label': 'A股总市值', 'field': 'A股总市值(亿)', 'sortable': True, 'align': 'center'},
                        ]
                        
                        ui.table(columns=columns, rows=rows, pagination=15).classes('w-full shadow-none border-0')
                        
                        ui.label('注：A股总市值由当日指数收盘价与 2026-02-03 总市值锚点对比估算得出。').classes('text-xs text-gray-400 mt-2')
        except Exception as e:
            print(f"Error rendering savings table: {e}")

    async def fetch_and_draw_market(force=False):
        loop = asyncio.get_running_loop()
        ms = MarketSentiment()
        idm = IndexDataManager()
        selected_index_name = index_select.value
        
        # Add loading indicator on the chart plot area
        if not chart_plot_area.is_deleted:
            with chart_plot_area:
                ui.spinner('dots', size='lg', color='primary').classes('absolute-center z-20')

        if force:
            ui.notify(f'正在刷新 {selected_index_name} 及情绪数据...', type='info')
        
        try:
            # Parallel fetch
            temp_task = loop.run_in_executor(executor, ms.get_temperature_data, force)
            index_task = loop.run_in_executor(executor, lambda: idm.get_index_data(selected_index_name, force_refresh=force))
            
            df, df_index = await asyncio.gather(temp_task, index_task)
        
        except asyncio.CancelledError:
            print("Data fetch cancelled.")
            return
        except Exception as e:
            # Error Handling: Show notify and clean up spinner if chart exists
            ui.notify(f'系统错误: {str(e)}', type='negative')
            if not status_label.is_deleted:
                status_label.text = f'系统错误: {str(e)}'
                status_label.classes(replace='text-red-500')
            # Try to restore chart state or show error in container
            if not chart_plot_area.is_deleted:
                chart_plot_area.clear()
                with chart_plot_area:
                    ui.label('数据加载失败').classes('absolute-center text-red-500')
            return

        # Remove initial status label if it exists
        if not status_label.is_deleted:
            status_label.delete()
        
        if df is None or df.empty:
            if hasattr(ui.context.client, 'layout') and not chart_plot_area.is_deleted:
                 with chart_plot_area:
                     ui.label('无法获取大盘数据。').classes('text-red-500 font-bold')
            return
        
        # Limit data for mobile
        if is_mobile:
            df = df.tail(30)
            
        # Sync Index Data Range with Sentiment Data
        if df_index is not None and not df_index.empty and not df.empty:
            start_dt = df.index.min()
            end_dt = df.index.max()
            # Ensure df_index date is datetime
            if not pd.api.types.is_datetime64_any_dtype(df_index['date']):
                df_index['date'] = pd.to_datetime(df_index['date'])
            
            # Filter
            df_index = df_index[(df_index['date'] >= start_dt) & (df_index['date'] <= end_dt)].copy()
        
        # Gauge
        if not df.empty and not gauge_container.is_deleted:
            last_record = df.iloc[-1]
            current_temp = last_record['temperature']
            last_date_str = last_record.name.strftime('%Y-%m-%d')
            is_simulated = getattr(ms, 'is_simulated', False)
            
            fig_gauge = go.Figure(go.Indicator(
                mode = "gauge+number",
                value = current_temp,
                domain = {'x': [0.05, 0.95], 'y': [0.15, 0.85]},  # 显式控制显示区域，避免与文字重叠
                number = {
                    'font': {'size': 64, 'family': "Impact, Roboto, sans-serif"},
                    'valueformat': ".1f"
                },
                gauge = {
                    'axis': {'range': [-30, 130], 'tickwidth': 1, 'tickcolor': "#757575"},
                    'bar': {'color': "#1976D2", 'thickness': 0.6},
                    'bgcolor': "white",
                    'borderwidth': 2,
                    'bordercolor': "#EEEEEE",
                    'steps': [
                        {'range': [-30, 0], 'color': "#E0F7FA"}, 
                        {'range': [0, 100], 'color': "#F5F5F5"}, 
                        {'range': [100, 130], 'color': "#FFEBEE"} 
                    ],
                    'threshold': {
                        'line': {'color': "#D32F2F", 'width': 4}, 
                        'thickness': 0.8, 
                        'value': current_temp
                    }
                }
            ))
            fig_gauge.update_layout(
                margin=dict(l=20, r=20, t=20, b=20),
                height=260,  # 稍微增加高度
                autosize=True,
                paper_bgcolor = "rgba(0,0,0,0)",
                font = dict(family="Roboto, sans-serif")
            )
            
            if not gauge_container.is_deleted:
                gauge_container.clear()
                with gauge_container:
                    title_text = f"情绪温度 ({last_date_str})"
                    title_class = 'text-sm font-bold absolute top-2 text-gray-700 z-10'
                    if is_simulated:
                        title_text += " (预估)"
                        title_class = 'text-sm font-bold absolute top-2 text-yellow-800 bg-yellow-100 px-2 rounded z-10'
                        
                    ui.label(title_text).classes(title_class)
                    # Ensure chart takes full available space in the container
                    plotly_renderer(fig_gauge).classes('w-full h-full absolute inset-0')

        # Line Chart
        fig = go.Figure()
        
        # Background zones (Sentiment)
        fig.add_hrect(y0=100, y1=130, fillcolor="#FFEBEE", opacity=0.5, layer="below", line_width=0)
        fig.add_hrect(y0=-30, y1=0, fillcolor="#E0F7FA", opacity=0.5, layer="below", line_width=0)
        
        # --- Index Price Trace (Secondary Axis) ---
        y_axis_title = selected_index_name
        if df_index is not None and not df_index.empty:
            # Prepare data based on selection
            trace_y_data = df_index['close']
            trace_name = selected_index_name
            
            if data_type_select and data_type_select.value == "指数振幅":
                for col in ['high', 'low', 'close']:
                    if col in df_index.columns:
                        df_index[col] = pd.to_numeric(df_index[col], errors='coerce')
                
                pre_close = df_index['close'].shift(1)
                amplitude_abs = (df_index['high'] - df_index['low']) / pre_close * 100
                trace_y_data = amplitude_abs
                trace_name = f"{selected_index_name} 振幅(%)"
                y_axis_title = trace_name
            
            fig.add_trace(go.Scatter(
                x=df_index['date'], 
                y=trace_y_data,
                mode='lines',
                name=trace_name,
                line=dict(color='#CFD8DC', width=1.5),
                yaxis='y2',
                hovertemplate='%{y:.2f}<extra></extra>' 
            ))

        # Main Line
        fig.add_trace(go.Scatter(
            x=df.index, y=df['temperature'], 
            mode='lines', name='情绪温度', 
            line=dict(color='#5C6BC0', width=3, shape='spline'),
            fill='tozeroy', fillcolor='rgba(92, 107, 192, 0.05)'
        ))
        
        high_df = df[df['temperature'] > 100]
        if not high_df.empty: fig.add_trace(go.Scatter(x=high_df.index, y=high_df['temperature'], mode='markers', name='高温', marker=dict(color='#EF5350', size=8, line=dict(color='white', width=1))))
        low_df = df[df['temperature'] < 0]
        if not low_df.empty: fig.add_trace(go.Scatter(x=low_df.index, y=low_df['temperature'], mode='markers', name='冰点', marker=dict(color='#26A69A', size=8, line=dict(color='white', width=1))))
        
        try:
            first_dt = pd.to_datetime(df.index[0])
            tick0_ms = int(first_dt.timestamp() * 1000)
        except Exception:
            tick0_ms = None
        five_days_ms = 86400000 * 5
        
        xaxis_mobile = dict(
            title='日期',
            tickformat="%m-%d",
            tickangle=-45,
            hoverformat="%Y-%m-%d",
            tick0=tick0_ms,
            dtick=five_days_ms,
            tickfont=dict(size=11),
            showgrid=False,
            ticks='outside'
        )
        xaxis_desktop = dict(
            title='日期',
            dtick="M2",
            tickformat="%Y-%m",
            hoverformat="%Y-%m-%d",
            tickangle=-45,
            showgrid=True,
            gridcolor='#F3F4F6',
            ticks='outside',
            rangeslider=dict(visible=True, thickness=0.08, bgcolor='#F9FAFB')
        )

        temp_min = float(df['temperature'].min())
        temp_max = float(df['temperature'].max())
        y_min = int(math.floor(temp_min / 20.0) * 20)
        y_max = int(math.ceil(temp_max / 20.0) * 20)
        y_min = min(y_min, -40)
        y_max = max(y_max, 120)
        y_dtick = 20

        height_val = 340 if is_mobile else 460
        margin_val = dict(l=36, r=18, t=10, b=36) if is_mobile else dict(l=50, r=40, t=10, b=50)

        fig.update_layout(
            xaxis=xaxis_mobile if is_mobile else xaxis_desktop,
            yaxis=dict(
                title='温度',
                range=[y_min, y_max],
                dtick=y_dtick,
                showgrid=True,
                gridcolor='#F3F4F6',
                zeroline=True,
                zerolinecolor='#E5E7EB',
                tickformat=',d'
            ),
            yaxis2=dict(
                title=y_axis_title,
                overlaying='y',
                side='right',
                showgrid=False,
                zeroline=False
            ),
            margin=margin_val,
            height=height_val,
            hovermode='x',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family="Roboto, 'Microsoft YaHei', sans-serif"),
            showlegend=not is_mobile
        )

        fig.update_traces(hovertemplate='%{y:.2f}°', selector=dict(type='scatter'))
        
        if chart_plot_area.is_deleted: return
        chart_plot_area.clear()
        with chart_plot_area:
            plotly_renderer(fig).classes('w-full h-full')
        
        if data_container.is_deleted: return
        data_container.classes(remove='hidden')
        data_container.clear()
        with data_container:
            def export_excel_market():
                try:
                    output = io.BytesIO()
                    export_df = df.copy()
                    export_df.to_excel(output)
                    ui.download(output.getvalue(), 'market_sentiment.xlsx')
                except Exception as e: 
                    try:
                        ui.notify(f'导出失败: {e}', type='negative')
                    except RuntimeError:
                        pass

            with ui.expansion('查看大盘详细列表', icon='list_alt').classes('w-full bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm'):
                with ui.column().classes('w-full p-2'):
                    with ui.row().classes('w-full justify-between items-center mb-2'):
                        ui.label('大盘数据明细').classes('text-lg font-bold')
                        ui.button('导出Excel', icon='file_download', on_click=export_excel_market).props('small outline color=green')

                    rows = []
                    latest_idx = df.index.max()
                    is_simulated = getattr(ms, 'is_simulated', False)

                    for idx, row in df.sort_index(ascending=False).iterrows():
                        row_is_est = False
                        if 'is_simulated' in row:
                            val = row['is_simulated']
                            if isinstance(val, bool): row_is_est = val
                            elif isinstance(val, (int, float)): row_is_est = (val != 0)
                            elif isinstance(val, str): row_is_est = (val.lower() == 'true')
                        else:
                            row_is_est = (idx == latest_idx) and is_simulated
                            
                        date_str = idx.strftime('%Y-%m-%d')
                        if row_is_est:
                            date_str += " (预估)"

                        rows.append({
                            'date': date_str,
                            'temp': round(row['temperature'], 2),
                            'turnover': round(row['turnover_trillion'], 3),
                            'margin_buy': round(row['margin_buy'] / 1e8, 2) if 'margin_buy' in row else 0,
                            'margin_pct': round(row['margin_ratio_pct'], 2) if 'margin_ratio_pct' in row else 0,
                            'is_estimated': row_is_est
                        })
                    ui.table(columns=[
                            {'name': 'date', 'label': '日期', 'field': 'date', 'sortable': True, 'align': 'left'},
                            {'name': 'temp', 'label': '温度', 'field': 'temp', 'sortable': True, 'align': 'center'},
                            {'name': 'turnover', 'label': '成交(万亿)', 'field': 'turnover', 'sortable': True, 'align': 'center'},
                            {'name': 'margin_buy', 'label': '融资买入(亿)', 'field': 'margin_buy', 'sortable': True, 'align': 'center'},
                            {'name': 'margin_pct', 'label': '融资占比(%)', 'field': 'margin_pct', 'sortable': True, 'align': 'center'},
                        ], 
                        rows=rows, 
                        pagination=20
                    ).classes('w-full h-[500px] flat bordered')

    # Initial Load
    async def initial_load():
        try:
            await asyncio.gather(fetch_and_draw_market(), fetch_and_update_savings_ratio())
        except Exception as e:
            # Avoid errors if component is destroyed during load
            pass
    
    # Use timer(0) to run immediately but allow UI to render first, minimizing 'parent deleted' window
    ui.timer(0, lambda: asyncio.create_task(initial_load()), once=True)
