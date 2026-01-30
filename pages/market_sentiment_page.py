from nicegui import ui
from utils.market_sentiment import MarketSentiment
from utils.sector_sentiment import SectorSentiment
import plotly.graph_objects as go
import pandas as pd
import asyncio
import json
import uuid
import os
import sys
import subprocess
from plotly.utils import PlotlyJSONEncoder
from concurrent.futures import ThreadPoolExecutor

# Create a thread pool for IO operations
executor = ThreadPoolExecutor(max_workers=2)

def init_sentiment_page():
    @ui.page('/mood')
    def sentiment_page():
        # Inject Plotly optimization script
        ui.add_head_html('''
            <script src="/static/plotly.min.js"></script>
            <script>
                if (typeof Plotly === 'undefined') {
                    document.write('<script src="https://cdn.bootcdn.net/ajax/libs/plotly.js/3.1.1/plotly.min.js"><\/script>');
                }            
                window.renderPlotly = function(id, data, layout, config) {
                    var attempt = 0;
                    function tryRender() {
                        var el = document.getElementById(id);
                        if (el && typeof Plotly !== 'undefined') {
                            Plotly.newPlot(id, data, layout, config);
                        } else {
                            if (attempt < 10) {
                                attempt++;
                                setTimeout(tryRender, 50);
                            } else {
                                console.error('Plotly render failed: element or library not found', id);
                            }
                        }
                    }
                    tryRender();
                }
            </script>
        ''')

        # Custom Plotly render function
        def custom_plotly(fig):
            chart_id = f"chart_{uuid.uuid4().hex}"
            c = ui.element('div').props(f'id="{chart_id}"')
            if hasattr(fig, 'to_dict'):
                fig = fig.to_dict()
            data = fig.get('data', [])
            layout = fig.get('layout', {})
            config = fig.get('config', {'responsive': True, 'displayModeBar': False})
            config['responsive'] = True
            j_data = json.dumps(data, cls=PlotlyJSONEncoder)
            j_layout = json.dumps(layout, cls=PlotlyJSONEncoder)
            j_config = json.dumps(config, cls=PlotlyJSONEncoder)
            ui.run_javascript(f'window.renderPlotly("{chart_id}", {j_data}, {j_layout}, {j_config})')
            return c

        ui.page_title('情绪温度监控 - 缠论小应用')
        
        # Header
        with ui.header().classes(replace='row items-center bg-white text-gray-800 shadow-sm border-b border-gray-200 h-16 px-4') as header:
            ui.button(icon='arrow_back', on_click=lambda: ui.run_javascript('window.location.href="/"')).props('flat round color=grey-8')
            ui.label('市场情绪温度监控').classes('text-xl font-bold ml-2')
            
            ui.space() # Spacer

        # Main Layout - 使用更深的背景色增加对比，或者维持淡灰但卡片加深阴影
        with ui.column().classes('w-full items-center bg-gray-100 min-h-screen p-4'):
            
            # --- TABS: 悬浮胶囊风格 ---
            with ui.row().classes('w-full max-w-6xl justify-center mb-4'):
                with ui.tabs().classes('bg-white text-gray-500 rounded-full shadow-md p-1') \
                        .props('indicator-color="transparent" active-color="white" active-bg-color="primary" active-class="shadow-sm rounded-full bg-gradient-to-r from-blue-500 to-indigo-600 text-white"') as tabs:
                    market_tab = ui.tab('大盘温度').classes('px-8 font-bold tracking-wide transition-all')
                    sector_tab = ui.tab('板块温度').classes('px-8 font-bold tracking-wide transition-all')

            with ui.tab_panels(tabs, value=market_tab).classes('w-full max-w-6xl bg-transparent p-0'):
                
                # --- MARKET TAB ---
                with ui.tab_panel(market_tab).classes('p-0 flex flex-col items-center gap-4'):
                    # Top Layout: Info + Gauge
                    with ui.row().classes('w-full gap-4 items-stretch'):
                        # Info Card
                        with ui.card().classes('flex-1 min-w-[300px] bg-white p-4 rounded-xl shadow-md border-0 relative overflow-hidden'):
                            # 装饰性背景
                            ui.element('div').classes('absolute -right-6 -top-6 w-24 h-24 rounded-full bg-blue-50 opacity-50')
                            
                            with ui.row().classes('items-center mb-3'):
                                ui.icon('psychology', color='indigo').classes('text-2xl')
                                ui.label('情绪温度模型').classes('text-lg font-bold text-gray-800')
                            
                            ui.html('<div class="text-gray-600 text-sm mb-3"><b>核心逻辑：</b>情绪由<span class="text-indigo-600 font-bold">杠杆力度</span>与<span class="text-blue-600 font-bold">成交活跃度</span>共同驱动。</div>', sanitize=False)
                            
                            # 公式说明
                            ui.code('模型公式：[(融资占比 - 2) × 2] + [(成交额(万亿) - 0.8) × 33]').classes('text-xs w-full mb-3 text-gray-600 bg-gray-50 p-2 rounded border border-gray-200 font-mono')
                            
                            with ui.row().classes('w-full gap-2 text-xs'):
                                with ui.column().classes('flex-1 bg-red-50 p-2 rounded-lg border border-red-100 items-center justify-center'):
                                    ui.label('>100 (高温)').classes('font-bold text-red-700')
                                    ui.label('风险聚集').classes('text-red-400 scale-90')
                                with ui.column().classes('flex-1 bg-gray-50 p-2 rounded-lg border border-gray-100 items-center justify-center'):
                                    ui.label('0~100 (震荡)').classes('font-bold text-gray-700')
                                    ui.label('正常波动').classes('text-gray-400 scale-90')
                                with ui.column().classes('flex-1 bg-green-50 p-2 rounded-lg border border-green-100 items-center justify-center'):
                                    ui.label('<0 (冰点)').classes('font-bold text-green-700')
                                    ui.label('机会区域').classes('text-green-400 scale-90')
                                    
                            ui.label('数据来源：交易所/金十数据').classes('text-xs text-gray-400 mt-auto pt-2')

                        # Gauge Container
                        gauge_container = ui.card().classes('flex-1 min-w-[300px] items-center justify-center p-0 gap-0 bg-white rounded-xl shadow-md border-0 relative')
                        with gauge_container:
                             ui.spinner(type='dots', size='lg', color='primary')
                             ui.label('计算数据中...').classes('text-gray-400 text-sm mt-2')

                    # Status Label
                    status_label = ui.label('正在连接数据接口...').classes('text-lg text-indigo-600 animate-pulse font-bold')
                    
                    # Chart Container
                    chart_container = ui.card().classes('w-full max-w-6xl h-[480px] border-0 rounded-xl shadow-md bg-white p-1')
                    
                    # Data Table Container
                    data_container = ui.column().classes('w-full max-w-6xl mt-4 hidden')

                    async def fetch_and_draw_market():
                        loop = asyncio.get_running_loop()
                        ms = MarketSentiment()
                        
                        try:
                            df = await loop.run_in_executor(executor, ms.get_temperature_data)
                        except Exception as e:
                            if not status_label.is_deleted:
                                status_label.text = f'系统错误: {str(e)}'
                                status_label.classes(replace='text-red-500')
                            return

                        if status_label.is_deleted: return
                        status_label.delete()
                        
                        if df is None or df.empty:
                            if hasattr(ui.context.client, 'layout'):
                                ui.label('无法获取大盘数据。').classes('text-red-500 font-bold')
                            return
                        
                        # Warning if simulated
                        if getattr(ms, 'is_simulated', False) and not gauge_container.is_deleted:
                            with ui.row().classes('w-full justify-center bg-yellow-100 p-2 rounded mb-2 border border-yellow-300 items-center'):
                                ui.icon('warning', color='orange').classes('text-2xl mr-2')
                                ui.label('注意：当前展示的数据为模拟/估算数据。').classes('text-orange-800')

                        # Gauge
                        if not df.empty and not gauge_container.is_deleted:
                            last_record = df.iloc[-1]
                            current_temp = last_record['temperature']
                            last_date_str = last_record.name.strftime('%Y-%m-%d')
                            
                            fig_gauge = go.Figure(go.Indicator(
                                mode = "gauge+number",
                                value = current_temp,
                                gauge = {
                                    'axis': {'range': [-30, 130]},
                                    'bar': {'color': "#1976D2"},
                                    'steps': [
                                        {'range': [-30, 0], 'color': "#E0F7FA"}, 
                                        {'range': [0, 100], 'color': "#F5F5F5"}, 
                                        {'range': [100, 130], 'color': "#FFEBEE"} 
                                    ],
                                    'threshold': {'line': {'color': "#D32F2F", 'width': 4}, 'thickness': 0.75, 'value': current_temp}
                                }
                            ))
                            fig_gauge.update_layout(
                                margin=dict(l=50, r=50, t=35, b=10),
                                autosize=True,
                                paper_bgcolor = "rgba(0,0,0,0)",
                                font = dict(family="Roboto, sans-serif")
                            )
                            
                            gauge_container.clear()
                            with gauge_container:
                                ui.label(f"情绪温度 ({last_date_str})").classes('text-sm font-bold absolute top-2 text-gray-700 z-10')
                                custom_plotly(fig_gauge).classes('w-full h-full')

                        # Line Chart
                        fig = go.Figure()
                        
                        # Background zones
                        fig.add_hrect(y0=100, y1=130, fillcolor="#FFEBEE", opacity=0.5, layer="below", line_width=0)
                        fig.add_hrect(y0=-30, y1=0, fillcolor="#E0F7FA", opacity=0.5, layer="below", line_width=0)
                        
                        # Main Line (Smooth curve + thicker)
                        fig.add_trace(go.Scatter(
                            x=df.index, y=df['temperature'], 
                            mode='lines', name='情绪温度', 
                            line=dict(color='#5C6BC0', width=3, shape='spline'),
                            fill='tozeroy', fillcolor='rgba(92, 107, 192, 0.05)' # Minimal fill for area effect
                        ))
                        
                        high_df = df[df['temperature'] > 100]
                        if not high_df.empty: fig.add_trace(go.Scatter(x=high_df.index, y=high_df['temperature'], mode='markers', name='高温', marker=dict(color='#EF5350', size=8, line=dict(color='white', width=1))))
                        low_df = df[df['temperature'] < 0]
                        if not low_df.empty: fig.add_trace(go.Scatter(x=low_df.index, y=low_df['temperature'], mode='markers', name='冰点', marker=dict(color='#26A69A', size=8, line=dict(color='white', width=1))))
                        
                        fig.update_layout(
                            title=dict(text='<b>情绪温度趋势 (近三年)</b>', font=dict(size=18, color='#374151')),
                            xaxis=dict(title='日期', dtick="M2", tickformat="%Y-%m", tickangle=-45, showgrid=True, gridcolor='#F3F4F6'), 
                            yaxis=dict(title='温度', showgrid=True, gridcolor='#F3F4F6', zeroline=True, zerolinecolor='#E5E7EB'),
                            margin=dict(l=50, r=40, t=60, b=50), 
                            height=460, 
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            font=dict(family="Roboto, 'Microsoft YaHei', sans-serif")
                        )
                        chart_container.clear()
                        with chart_container:
                            custom_plotly(fig).classes('w-full h-full')
                        
                        # Market Table
                        data_container.classes(remove='hidden')
                        with data_container:
                            def export_excel_market():
                                import io
                                try:
                                    output = io.BytesIO()
                                    export_df = df.copy()
                                    export_df.to_excel(output)
                                    ui.download(output.getvalue(), 'market_sentiment.xlsx')
                                except Exception as e: 
                                    try:
                                        ui.notify(f'导出失败: {e}', type='negative')
                                    except RuntimeError:
                                        pass  # Context might be deleted

                            with ui.expansion('查看大盘详细列表', icon='list_alt').classes('w-full bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm'):
                                with ui.column().classes('w-full p-2'):
                                    with ui.row().classes('w-full justify-between items-center mb-2'):
                                        ui.label('大盘数据明细').classes('text-lg font-bold')
                                        ui.button('导出Excel', icon='file_download', on_click=export_excel_market).props('small outline color=green')

                                    rows = []
                                    for idx, row in df.sort_index(ascending=False).iterrows():
                                        rows.append({
                                            'date': idx.strftime('%Y-%m-%d'),
                                            'temp': round(row['temperature'], 2),
                                            'turnover': round(row['turnover_trillion'], 3),
                                            'margin_buy': round(row['margin_buy'] / 1e8, 2) if 'margin_buy' in row else 0,
                                            'margin_pct': round(row['margin_ratio_pct'], 2) if 'margin_ratio_pct' in row else 0
                                        })
                                    ui.aggrid({
                                        'columnDefs': [
                                            {'headerName': '日期', 'field': 'date'},
                                            {'headerName': '温度', 'field': 'temp', 'cellStyle': {'fontWeight': 'bold', 'color': '#5C6BC0'}},
                                            {'headerName': '成交(万亿)', 'field': 'turnover'},
                                            {'headerName': '融资买入(亿)', 'field': 'margin_buy'},
                                            {'headerName': '融资占比(%)', 'field': 'margin_pct'},
                                        ],
                                        'rowData': rows,
                                        'pagination': True,
                                        'defaultColDef': {'sortable': True, 'filter': True}
                                    }).classes('w-full h-[500px]')

                # --- SECTOR TAB ---
                with ui.tab_panel(sector_tab).classes('p-0 flex flex-col items-center gap-4'):
                    
                    # Info Card with Callout Style
                    with ui.card().classes('w-full  bg-white p-6 rounded-xl shadow-md border-l-4 border-l-indigo-500 border-t-0 border-r-0 border-b-0'):
                        with ui.row().classes('items-center gap-2 mb-4'):
                            ui.icon('info', color='indigo').classes('text-2xl')
                            ui.label('板块情绪温度说明').classes('text-lg font-bold text-gray-800')
                        
                        ui.html('''
                        <div class="bg-indigo-50 p-4 rounded-lg mb-4 text-sm text-indigo-900">
                            <b>📐 计算公式：</b>板块温度 = <span class="font-bold text-red-600">量能项(资金活跃度)</span> + <span class="font-bold text-blue-600">融资项(杠杆意愿)</span>
                        </div>
                        ''', sanitize=False).classes('w-full')
                        
                        with ui.grid(columns=2).classes('w-full gap-6'):
                            with ui.column().classes('p-3 bg-gray-50 rounded-lg'):
                                ui.label('量能项 (Volume)').classes('font-bold text-gray-700 text-sm mb-1')
                                ui.label('反映资金相对大盘的活跃度。').classes('text-xs text-gray-500 mb-1')
                                ui.code('公式：(板块成交/均量) ÷ (大盘成交/均量)').classes('text-xs w-full')
                            
                            with ui.column().classes('p-3 bg-gray-50 rounded-lg'):
                                ui.label('融资项 (Margin)').classes('font-bold text-gray-700 text-sm mb-1')
                                ui.label('反映杠杆资金相对大盘的激进程度。').classes('text-xs text-gray-500 mb-1')
                                ui.code('公式：(板块融资占比) - (大盘融资占比)').classes('text-xs w-full')
                        
                        ui.label('解读：温度 >0 表示强于大盘（领涨），<0 表示弱于大盘。>100 为过热，<-50 为过冷。').classes('text-xs font-bold text-indigo-800 mt-4 bg-indigo-50 inline-block px-2 py-1 rounded')

                    # Control Row & Chart Area merged
                    sector_status_label = ui.label('准备就绪').classes('hidden') # Hidden state label, controlled by logic

                    # Chart Area
                    sector_chart_container = ui.card().classes('w-full h-[750px] p-4 bg-white rounded-xl shadow-md border-0 flex flex-col')
                    
                    # Update Button reference for logic
                    update_sector_btn = None 
                    load_cache_btn = None
                    
                    # Initial Placeholder
                    with sector_chart_container:
                         with ui.column().classes('w-full h-full items-center justify-center gap-4'):
                            ui.icon('analytics', color='indigo-200').classes('text-6xl')
                            ui.label('全市场板块情绪热度').classes('text-2xl font-bold text-gray-700')
                            ui.label('请加载数据以查看分析结果').classes('text-gray-400')
                            with ui.row().classes('gap-4 mt-2'):
                                load_cache_btn = ui.button('加载缓存', on_click=lambda: load_sector_view()).props('unelevated color=indigo-6 icon=history')
                                update_sector_btn = ui.button('在线更新', on_click=lambda: update_sector_data()).props('outline color=indigo-6 icon=cloud_download')

                    # Table Area
                    sector_table_container = ui.column().classes('w-full mt-4 hidden')
                    
                    async def update_sector_data():
                        loop = asyncio.get_running_loop()
                        if update_sector_btn: update_sector_btn.disable()
                        if load_cache_btn: load_cache_btn.disable()
                        
                        sector_status_label.text = '正在更新...'
                        ui.notify('开启独立进程更新，这需要几分钟...', type='info', timeout=5000)
                        
                        try:
                            # Re-render container with loading state
                            sector_chart_container.clear()
                            with sector_chart_container:
                                with ui.column().classes('w-full h-full items-center justify-center'):
                                     ui.spinner('dots', size='xl', color='indigo')
                                     ui.label('正在从服务器获取并计算板块数据...').classes('text-indigo-500 font-bold mt-4')
                                     ui.label('这可能需要1-2分钟').classes('text-gray-400 text-sm')

                            script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'utils', 'sector_sentiment.py')
                            
                            def run_script():
                                result = subprocess.run(
                                    [sys.executable, '-u', script_path], 
                                    capture_output=True, 
                                    text=True, 
                                    cwd=os.path.dirname(os.path.dirname(__file__))
                                )
                                if result.returncode != 0:
                                    raise Exception(f"Script failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
                                return result.stdout

                            stdout = await loop.run_in_executor(None, run_script)
                            print("Update Script Output:", stdout)
                            
                            load_sector_view() 
                            
                            try:
                                ui.notify('板块数据更新成功', type='positive')
                            except RuntimeError:
                                pass  # Context might be deleted
                        except Exception as e:
                            print(f"Update failed details: {e}")
                            try:
                                ui.notify(f'更新失败: {e}', type='negative')
                            except RuntimeError:
                                pass  # Context might be deleted
                            # Restore initial state on error
                            sector_chart_container.clear()
                            with sector_chart_container:
                                with ui.column().classes('w-full h-full items-center justify-center'):
                                    ui.icon('error_outline', color='red').classes('text-6xl')
                                    ui.label('更新失败').classes('text-red-500 font-bold')
                                    ui.button('重试', on_click=lambda: update_sector_data()).props('unelevated color=red')
                        
                        if update_sector_btn: update_sector_btn.enable()
                        if load_cache_btn: load_cache_btn.enable()

                    def load_sector_view():
                        ss = SectorSentiment()
                        data = ss.get_display_data()
                        if data:
                            render_sector_view(data)
                        else:
                            try:
                                ui.notify('无缓存数据，请点击更新', type='warning')
                            except RuntimeError:
                                pass  # Context might be deleted

                    def render_sector_view(data):
                        try:
                            if not data: return
                            
                            sector_chart_container.clear()
                            sector_table_container.classes(remove='hidden')
                            
                            # Prepare Data
                            records = []
                            for k, v in data.items():
                                v['name'] = k
                                records.append(v)
                            df_s = pd.DataFrame(records)
                            
                            if df_s.empty:
                                try:
                                    ui.notify("数据为空", type='warning')
                                except RuntimeError:
                                    pass  # Context might be deleted
                                return
                            
                            # Add turnover in 100 Millions for table display
                            if 'turnover' in df_s.columns:
                                df_s['turnover_yi'] = (df_s['turnover'] / 100000000).round(2)

                            # Header inside container
                            data_date = list(data.values())[0].get("date", "未知日期")
                            
                            with sector_chart_container:
                                with ui.row().classes('w-full justify-between items-center mb-4 pb-2 border-b border-gray-100'):
                                    with ui.row().classes('items-center gap-2'):
                                        ui.icon('grid_view', color='indigo').classes('text-xl')
                                        ui.label(f'全市场板块情绪热度').classes('text-xl font-bold text-gray-800')
                                        ui.label(f'{data_date}').classes('text-sm px-2 py-0.5 bg-gray-100 rounded text-gray-500')
                                        ui.label('（注：面积大小对应成交额）').classes('text-xs text-gray-400')
                                    
                                    with ui.row().classes('items-center gap-2'):
                                        # Recapture buttons for scope
                                        nonlocal update_sector_btn, load_cache_btn
                                        load_cache_btn = ui.button('重新加载', on_click=lambda: load_sector_view()).props('flat icon=refresh color=grey').classes('text-gray-500')
                                        update_sector_btn = ui.button('更新数据', on_click=lambda: update_sector_data()).props('unelevated color=indigo icon=cloud_download')

                                # Treemap
                                # Custom Colorscale: Cold Blue -> White -> Warm Red
                                custom_colorscale = [
                                    [0.0, 'rgb(49, 54, 149)'],
                                    [0.3, 'rgb(116, 173, 209)'],
                                    [0.5, 'rgb(255, 255, 255)'],
                                    [0.7, 'rgb(244, 109, 67)'],
                                    [1.0, 'rgb(165, 0, 38)']
                                ]

                                fig = go.Figure(go.Treemap(
                                    labels = df_s['name'],
                                    parents = [""] * len(df_s),
                                    values = df_s['turnover'], 
                                    text = df_s['temperature'].apply(lambda x: f"{x:.0f}°"),
                                    marker = dict(
                                        colors = df_s['temperature'],
                                        colorscale = custom_colorscale, 
                                        cmin = -60, cmax = 120, cmid = 0,
                                        showscale = True,
                                        colorbar = dict(
                                            title='温度', 
                                            thickness=15, 
                                            len=0.8,
                                            tickfont=dict(color='#666')
                                        ),
                                        line = dict(width=2, color='#ffffff') # White borders for clean look
                                    ),
                                    hovertemplate='<b>%{label}</b><br>温度: %{color:.1f}<br>成交额: %{value}万<extra></extra>',
                                    textinfo = "label+text",
                                    textfont = dict(size=20, family="Roboto, sans-serif", color='#333'),
                                    textposition = "middle center",
                                    tiling = dict(pad=2) # Spacing inside
                                ))
                                
                                fig.update_layout(
                                    margin=dict(t=10, l=10, r=10, b=10), 
                                    height=650,
                                    paper_bgcolor='rgba(0,0,0,0)',
                                    plot_bgcolor='rgba(0,0,0,0)',
                                    font=dict(family="Roboto, 'Microsoft YaHei'")
                                )
                                
                                custom_plotly(fig).classes('w-full flex-1 min-h-0')

                            # Table
                            sector_table_container.clear()
                            with sector_table_container:
                                with ui.expansion('查看板块详细列表', icon='list').classes('w-full bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm'):
                                    with ui.column().classes('w-full p-2'):
                                        def export_sector_excel():
                                            import io
                                            try:
                                                output = io.BytesIO()
                                                # Ensure columns exist (backward compatibility)
                                                cols_map = {
                                                    'name': '板块', 'date': '日期', 'temperature': '温度', 'turnover_yi': '成交额(亿)',
                                                    'score_vol': '量能得分', 'score_margin': '融资得分'
                                                }
                                                cols = [c for c in cols_map.keys() if c in df_s.columns]
                                                export_df = df_s[cols].copy()
                                                export_df.rename(columns=cols_map, inplace=True)
                                                export_df.to_excel(output, index=False)
                                                ui.download(output.getvalue(), 'sector_sentiment.xlsx')
                                            except Exception as e: 
                                                try:
                                                    ui.notify(f'导出失败: {e}', type='negative')
                                                except RuntimeError:
                                                    pass  # Context might be deleted

                                        with ui.row().classes('w-full justify-between items-center mb-2'):
                                            ui.label('板块数据明细').classes('text-lg font-bold')
                                            ui.button('导出Excel', icon='file_download', on_click=export_sector_excel).props('small outline color=green')
                                        
                                        # Determine columns dynamically based on available keys
                                        grid_cols = [
                                            {'headerName': '板块名称', 'field': 'name', 'sortable': True, 'filter': True, 'pinned': 'left'},
                                            {'headerName': '温度', 'field': 'temperature', 'sortable': True, 'cellStyle': {'fontWeight': 'bold'}},
                                            {'headerName': '成交额(亿)', 'field': 'turnover_yi', 'sortable': True},
                                            {'headerName': '日期', 'field': 'date', 'sortable': True},
                                        ]
                                        if 'score_vol' in df_s.columns:
                                            grid_cols.insert(3, {'headerName': '量能得分', 'field': 'score_vol', 'sortable': True})
                                        if 'score_margin' in df_s.columns:
                                            grid_cols.insert(4, {'headerName': '融资得分', 'field': 'score_margin', 'sortable': True})
                                        
                                        ui.aggrid({
                                            'columnDefs': grid_cols,
                                            'rowData': df_s.to_dict('records'),
                                            'pagination': True,
                                            'paginationPageSize': 20
                                        }).classes('w-full h-[600px]')
                        except Exception as e:
                            print(f"Render sector view failed: {e}")
                            try:
                                ui.notify(f"渲染板块视图失败: {e}", type='negative')
                            except RuntimeError:
                                pass  # Context might be deleted
                            # Restore Placeholder if failed
                            sector_chart_container.clear()
                            with sector_chart_container:
                                with ui.column().classes('w-full h-full items-center justify-center gap-4'):
                                    ui.icon('error', color='red').classes('text-6xl')
                                    ui.label('渲染失败，请检查数据').classes('text-xl font-bold text-gray-700')
                                    ui.label(str(e)).classes('text-gray-400')
                                    ui.button('重试加载', on_click=lambda: load_sector_view()).props('unelevated color=indigo')


            # Start Market Fetch automatically
            async def auto_fetch_market():
                await asyncio.sleep(0.5)
                # Auto-load Sector Cache if exists
                ss = SectorSentiment()
                if os.path.exists(ss.cache_file):
                    load_sector_view()
                
                await fetch_and_draw_market()
            
            asyncio.create_task(auto_fetch_market())
