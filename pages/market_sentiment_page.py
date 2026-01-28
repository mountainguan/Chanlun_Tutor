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
        with ui.header().classes(replace='row items-center') as header:
            header.classes('bg-blue-700 text-white')
            ui.button(icon='arrow_back', on_click=lambda: ui.run_javascript('window.location.href="/"')).props('flat round color=white')
            ui.label('市场情绪温度监控').classes('text-lg font-bold ml-2')

        # Tabs
        with ui.tabs().classes('w-full text-white bg-blue-600') as tabs:
            market_tab = ui.tab('大盘温度')
            sector_tab = ui.tab('板块温度')

        with ui.tab_panels(tabs, value=market_tab).classes('w-full bg-gray-50'):
            
            # --- MARKET TAB ---
            with ui.tab_panel(market_tab).classes('p-2'):
                with ui.column().classes('w-full items-center'):
                    # Top Layout: Info + Gauge
                    with ui.row().classes('w-full max-w-6xl gap-2 mb-2 items-stretch'):
                        # Info Card
                        with ui.card().classes('flex-1 min-w-[300px] bg-white p-2 text-sm'):
                            ui.label('🌡️ 什么是情绪温度？').classes('text-base font-bold mb-1')
                            ui.html('<b>核心逻辑</b>：情绪由<b>杠杆力度</b>与<b>成交活跃度</b>驱动。<br>'
                                    '<span style="font-size:0.9em;color:#666">公式：温度 = (融资占比% - 2.0)×2 + (成交额万亿 - 0.8)×33</span>', sanitize=False).classes('mb-1 leading-tight')
                            ui.markdown(
                                '- **>100 (高温)**：情绪亢奋，注意风险\n'
                                '- **0~100 (平衡)**：正常波动区间\n'
                                '- **<0 (冰点)**：恐慌区域，可能存在机会'
                            ).classes('text-xs leading-snug mb-1')
                            ui.label('数据来源：两市成交额(网易/东财)，融资买入(金十)').classes('text-xs text-gray-400 mt-auto')

                        # Gauge Container
                        gauge_container = ui.card().classes('flex-1 min-w-[300px] items-center justify-center p-0 gap-0')
                        with gauge_container:
                             ui.label('计算中...').classes('text-gray-400 text-lg')

                    # Status Label
                    status_label = ui.label('正在连接数据接口...').classes('text-lg text-blue-600 animate-pulse')
                    
                    # Chart Container
                    chart_container = ui.column().classes('w-full max-w-6xl h-[450px] border rounded shadow-sm bg-white p-1')
                    
                    # Data Table Container
                    data_container = ui.column().classes('w-full max-w-6xl mt-6 hidden')

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
                                        {'range': [-30, 0], 'color': "#E0F2F1"}, 
                                        {'range': [0, 100], 'color': "#FAFAFA"}, 
                                        {'range': [100, 130], 'color': "#FFEBEE"} 
                                    ],
                                    'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': current_temp}
                                }
                            ))
                            fig_gauge.update_layout(margin=dict(l=25, r=25, t=10, b=20), height=160, paper_bgcolor = "rgba(0,0,0,0)")
                            
                            gauge_container.clear()
                            with gauge_container:
                                ui.label(f"昨日情绪温度").classes('text-base font-bold mt-2')
                                ui.label(f"({last_date_str})").classes('text-xs text-gray-500 mb-0')
                                custom_plotly(fig_gauge).classes('w-full h-full')

                        # Line Chart
                        fig = go.Figure()
                        fig.add_hrect(y0=100, y1=130, fillcolor="red", opacity=0.1, layer="below", line_width=0, annotation_text="高温")
                        fig.add_hrect(y0=-30, y1=0, fillcolor="green", opacity=0.1, layer="below", line_width=0, annotation_text="冰点")
                        fig.add_trace(go.Scatter(x=df.index, y=df['temperature'], mode='lines', name='情绪温度', line=dict(color='#1976D2', width=2)))
                        
                        high_df = df[df['temperature'] > 100]
                        if not high_df.empty: fig.add_trace(go.Scatter(x=high_df.index, y=high_df['temperature'], mode='markers', name='高温', marker=dict(color='red', size=5)))
                        low_df = df[df['temperature'] < 0]
                        if not low_df.empty: fig.add_trace(go.Scatter(x=low_df.index, y=low_df['temperature'], mode='markers', name='冰点', marker=dict(color='green', size=5)))
                        
                        fig.update_layout(
                            title='情绪温度趋势 (近三年)', 
                            xaxis=dict(title='日期', dtick="M1", tickformat="%Y-%m", tickangle=-45), 
                            yaxis=dict(title='温度'),
                            margin=dict(l=40, r=40, t=50, b=40), height=430, template='plotly_white'
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
                                except Exception as e: ui.notify(f'导出失败: {e}', type='negative')

                            with ui.row().classes('w-full justify-between items-center mb-2'):
                                ui.label('历史明细').classes('text-lg font-bold')
                                ui.button('导出Excel', icon='file_download', on_click=export_excel_market).props('small outline color=green')

                            with ui.expansion('查看详细数据', icon='list_alt').classes('w-full bg-white border rounded'):
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
                                        {'headerName': '温度', 'field': 'temp', 'cellStyle': {'fontWeight': 'bold'}},
                                        {'headerName': '成交(万亿)', 'field': 'turnover'},
                                        {'headerName': '融资买入(亿)', 'field': 'margin_buy'},
                                        {'headerName': '融资占比(%)', 'field': 'margin_pct'},
                                    ],
                                    'rowData': rows,
                                    'pagination': True
                                }).classes('w-full h-[500px]')

            # --- SECTOR TAB ---
            with ui.tab_panel(sector_tab).classes('p-2'):
                with ui.column().classes('w-full items-center p-2'):
                    ui.label('板块情绪热度图').classes('text-2xl font-bold mb-2')
                    ui.label('温度 = 量能项(相对放量幅度) + 融资项(相对杠杆意愿)。 0为中性(同步大盘)，>100为领涨，<0为滞涨').classes('text-sm text-gray-500 mb-4')

                    # Control Row
                    with ui.row().classes('w-full max-w-6xl justify-between items-center mb-4'):
                        sector_status_label = ui.label('准备就绪').classes('text-gray-600')
                        with ui.row().classes('gap-2'):
                           load_cache_btn = ui.button('加载缓存', on_click=lambda: load_sector_view()).props('outline icon=history')
                           update_sector_btn = ui.button('更新今日数据(耗时)', on_click=lambda: update_sector_data()).props('color=primary icon=cloud_download')

                    # Chart Area
                    sector_chart_container = ui.card().classes('w-full max-w-6xl h-[650px] p-2 bg-white')
                    with sector_chart_container:
                        ui.label('请点击“加载缓存”或“更新数据”查看热度图').classes('text-gray-400')

                    # Table Area
                    sector_table_container = ui.column().classes('w-full max-w-6xl mt-6 hidden')
                    
                    async def update_sector_data():
                        loop = asyncio.get_running_loop()
                        update_sector_btn.disable()
                        load_cache_btn.disable()
                        sector_status_label.text = '正在调用独立进程获取数据（更稳定），请稍候...'
                        ui.notify('开启独立进程更新，这需要几分钟...', type='info', timeout=5000)
                        
                        try:
                            # Use subprocess to run the update script independently
                            # This avoids threading/GIL/Network issues within the main app process
                            script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'utils', 'sector_sentiment.py')
                            
                            def run_script():
                                # Capture output to display errors if needed
                                result = subprocess.run(
                                    [sys.executable, script_path], 
                                    capture_output=True, 
                                    text=True, 
                                    cwd=os.path.dirname(os.path.dirname(__file__))
                                )
                                if result.returncode != 0:
                                    raise Exception(f"Script failed: {result.stderr}")
                                return result.stdout

                            # Run subprocess in executor to not block UI loop
                            stdout = await loop.run_in_executor(None, run_script)
                            print("Update Script Output:", stdout)
                            
                            # Reload data
                            load_sector_view() 
                            
                            sector_status_label.text = '更新完成。'
                            ui.notify('板块数据更新成功', type='positive')
                        except Exception as e:
                            sector_status_label.text = f'更新错误: {str(e)[:50]}...'
                            print(f"Update failed details: {e}")
                            ui.notify(f'更新失败: {e}', type='negative')
                        
                        update_sector_btn.enable()
                        load_cache_btn.enable()

                    def load_sector_view():
                        ss = SectorSentiment()
                        data = ss.get_display_data()
                        if data:
                            render_sector_view(data)
                            sector_status_label.text = f'已加载缓存数据。日期: {list(data.values())[0]["date"]}。'
                        else:
                            ui.notify('无缓存数据，请先点击更新', type='warning')

                    def render_sector_view(data):
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
                            ui.notify("数据为空", type='warning')
                            return

                        # Treemap
                        fig = go.Figure(go.Treemap(
                            labels = df_s['name'],
                            parents = ["全部板块"] * len(df_s),
                            values = df_s['turnover'], # Size by turnover
                            text = df_s['temperature'].apply(lambda x: f"{x:.0f}°C"),
                            marker = dict(
                                colors = df_s['temperature'],
                                colorscale = 'RdBu_r', 
                                cmin = -50, # Cold (Blue)
                                cmax = 100, # Hot (Red)
                                cmid = 0,   # Neutral
                                showscale = True,
                                colorbar = dict(title='温度')
                            ),
                            hovertemplate='<b>%{label}</b><br>温度: %{color:.1f}<br>成交额: %{value}<extra></extra>',
                            textinfo = "label+text"
                        ))
                        
                        fig.update_layout(margin=dict(t=30, l=10, r=10, b=10), height=600, title='全市场板块情绪热度 (面积=成交额, 颜色=温度)')
                        
                        with sector_chart_container:
                            custom_plotly(fig).classes('w-full h-full')

                        # Table
                        sector_table_container.clear()
                        with sector_table_container:
                            def export_sector_excel():
                                import io
                                try:
                                    output = io.BytesIO()
                                    # Ensure columns exist (backward compatibility)
                                    cols_map = {
                                        'name': '板块', 'date': '日期', 'temperature': '温度', 'turnover': '成交额',
                                        'score_vol': '量能得分', 'score_margin': '融资得分'
                                    }
                                    cols = [c for c in cols_map.keys() if c in df_s.columns]
                                    export_df = df_s[cols].copy()
                                    export_df.rename(columns=cols_map, inplace=True)
                                    export_df.to_excel(output, index=False)
                                    ui.download(output.getvalue(), 'sector_sentiment.xlsx')
                                except Exception as e: ui.notify(f'导出失败: {e}', type='negative')

                            with ui.row().classes('w-full justify-between items-center mb-2'):
                                ui.label('板块数据明细').classes('text-lg font-bold')
                                ui.button('导出Excel', icon='file_download', on_click=export_sector_excel).props('small outline color=green')
                            
                            # Determine columns dynamically based on available keys
                            grid_cols = [
                                {'headerName': '板块名称', 'field': 'name', 'sortable': True, 'filter': True, 'pinned': 'left'},
                                {'headerName': '温度', 'field': 'temperature', 'sortable': True, 'cellStyle': {'fontWeight': 'bold'}},
                                {'headerName': '成交额', 'field': 'turnover', 'sortable': True},
                                {'headerName': '日期', 'field': 'date', 'sortable': True},
                            ]
                            if 'score_vol' in df_s.columns:
                                grid_cols.insert(3, {'headerName': '量能得分', 'field': 'score_vol', 'sortable': True})
                            if 'score_margin' in df_s.columns:
                                grid_cols.insert(4, {'headerName': '融资得分', 'field': 'score_margin', 'sortable': True})
                            
                            ui.aggrid({
                                'columnDefs': grid_cols,
                                'rowData': records,
                                'pagination': True,
                                'paginationPageSize': 20
                            }).classes('w-full h-[600px]')


            # Start Market Fetch automatically
            async def auto_fetch_market():
                await asyncio.sleep(0.5)
                # Check cache for Sector view
                ss = SectorSentiment()
                if os.path.exists(ss.cache_file):
                    pass # Don't autoload to keep UI clean, or maybe we should? User can click button.
                
                await fetch_and_draw_market()
            
            asyncio.create_task(auto_fetch_market())
