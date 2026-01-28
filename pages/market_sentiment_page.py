from nicegui import ui
from utils.market_sentiment import MarketSentiment
import plotly.graph_objects as go
import pandas as pd
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Create a thread pool for IO operations
executor = ThreadPoolExecutor(max_workers=2)

def init_sentiment_page():
    @ui.page('/mood')
    def sentiment_page():
        # 设置页面标题
        ui.page_title('大盘情绪温度 - 缠论小应用')
        
        # 顶部导航栏 (可选，保持与主应用一致的风格，这里简单弄一个返回)
        with ui.header().classes(replace='row items-center') as header:
            header.classes('bg-blue-700 text-white')
            ui.button(icon='arrow_back', on_click=lambda: ui.run_javascript('window.location.href="/"')).props('flat round color=white')
            ui.label('大盘情绪温度监控').classes('text-lg font-bold ml-2')

        with ui.column().classes('w-full items-center p-2'):
            # 顶部布局：左侧科普，右侧仪表盘
            with ui.row().classes('w-full max-w-6xl gap-2 mb-2 items-stretch'):
                # 左侧：科普介绍 (50%)
                with ui.card().classes('flex-1 min-w-[300px] bg-gray-50 p-2 text-sm'):
                    ui.label('🌡️ 什么是情绪温度？').classes('text-base font-bold mb-1')
                    ui.html('<b>核心逻辑</b>：情绪由<b>杠杆力度</b>与<b>成交活跃度</b>驱动。<br>'
                            '<span style="font-size:0.9em;color:#666">公式：温度 = (融资占比% - 2.0)×2 + (成交额万亿 - 0.8)×33</span>', sanitize=False).classes('mb-1 leading-tight')
                    
                    ui.markdown(
                        '- **>100 (高温)**：情绪亢奋，注意风险\n'
                        '- **0~100 (平衡)**：正常波动区间\n'
                        '- **<0 (冰点)**：恐慌区域，可能存在机会'
                    ).classes('text-xs leading-snug mb-1')
                    
                    ui.label('数据来源：两市成交额(网易/东财)，融资买入(金十)').classes('text-xs text-gray-400 mt-auto')

                # 右侧：仪表盘容器 (50%)
                gauge_container = ui.card().classes('flex-1 min-w-[300px] items-center justify-center p-0 gap-0')
                with gauge_container:
                     ui.label('计算中...').classes('text-gray-400 text-lg')

            # 状态提示
            status_label = ui.label('正在连接数据接口，请稍候...').classes('text-lg text-blue-600 animate-pulse')
            
            # 图表容器
            chart_container = ui.column().classes('w-full max-w-6xl h-[450px] border rounded shadow-sm bg-white p-1')
            
            # 数据表格容器
            data_container = ui.column().classes('w-full max-w-6xl mt-6 hidden')

            async def fetch_and_draw():
                loop = asyncio.get_running_loop()
                ms = MarketSentiment()
                
                # 在线程池中运行耗时的网络请求
                try:
                    df = await loop.run_in_executor(executor, ms.get_temperature_data)
                except Exception as e:
                    status_label.text = f'系统错误: {str(e)}'
                    status_label.classes(replace='text-red-500')
                    return

                status_label.delete()
                
                if df is None or df.empty:
                    ui.label('无法获取足够的数据进行计算。请检查网络连接或稍后再试。').classes('text-red-500 font-bold text-xl')
                    # 提供一个刷新按钮
                    ui.button('重试', on_click=lambda: ui.run_javascript('window.location.reload()')).props('color=primary')
                    return
                
                # 检查是否是模拟数据并发出警告
                if getattr(ms, 'is_simulated', False):
                    with ui.row().classes('w-full justify-center bg-yellow-100 p-2 rounded mb-2 border border-yellow-300 items-center'):
                        ui.icon('warning', color='orange').classes('text-2xl mr-2')
                        ui.label('注意：由于外部API访问受限，当前展示的数据包含模拟/估算成分，仅供展示页面功能。').classes('text-orange-800')

                # --- 仪表盘 (最新一天的温度) ---
                if not df.empty:
                    last_record = df.iloc[-1]
                    current_temp = last_record['temperature']
                    last_date_str = last_record.name.strftime('%Y-%m-%d')
                    
                    fig_gauge = go.Figure(go.Indicator(
                        mode = "gauge+number",
                        value = current_temp,
                        # title = {'text': f"昨日情绪温度<br><span style='font-size:0.8em;color:gray'>({last_date_str})</span>"},
                        gauge = {
                            # 调整范围以适应新算法
                            'axis': {'range': [-30, 130]},
                            'bar': {'color': "#1976D2"},
                            'steps': [
                                {'range': [-30, 0], 'color': "#E0F2F1"},   # 恐慌
                                {'range': [0, 100], 'color': "#FAFAFA"},    # 常温
                                {'range': [100, 130], 'color': "#FFEBEE"}   # 高温
                            ],
                            'threshold': {
                                'line': {'color': "red", 'width': 4},
                                'thickness': 0.75,
                                'value': current_temp
                            }
                        }
                    ))
                    fig_gauge.update_layout(
                        margin=dict(l=25, r=25, t=10, b=20),
                        height=160,
                        paper_bgcolor = "rgba(0,0,0,0)",
                        font = {'family': "Arial"}
                    )
                    
                    gauge_container.clear()
                    with gauge_container:
                        ui.label(f"昨日情绪温度").classes('text-base font-bold mt-2')
                        ui.label(f"({last_date_str})").classes('text-xs text-gray-500 mb-0')
                        ui.plotly(fig_gauge).classes('w-full h-full')

                # --- 绘图 (趋势图) ---
                fig = go.Figure()
                
                # 背景色块 (标记区域)
                fig.add_hrect(y0=100, y1=130, fillcolor="red", opacity=0.1, layer="below", line_width=0, annotation_text="高温区 (>100)", annotation_position="top left")
                fig.add_hrect(y0=-30, y1=0, fillcolor="green", opacity=0.1, layer="below", line_width=0, annotation_text="冰点区 (<0)", annotation_position="bottom left")

                # 主轴：情绪温度 (蓝色)
                fig.add_trace(go.Scatter(
                    x=df.index, 
                    y=df['temperature'], 
                    mode='lines', 
                    name='情绪温度',
                    line=dict(color='#1976D2', width=2),
                ))

                # 超过 100 的部分标记 (红色 Marker)
                high_df = df[df['temperature'] > 100]
                if not high_df.empty:
                    fig.add_trace(go.Scatter(
                        x=high_df.index,
                        y=high_df['temperature'],
                        mode='markers',
                        name='高温点',
                        marker=dict(color='red', size=5)
                    ))
                
                # 低于 0 的部分标记 (绿色 Marker)
                low_df = df[df['temperature'] < 0]
                if not low_df.empty:
                    fig.add_trace(go.Scatter(
                        x=low_df.index,
                        y=low_df['temperature'],
                        mode='markers',
                        name='冰点点',
                        marker=dict(color='green', size=5)
                    ))
                
                fig.update_layout(
                    title=dict(text='情绪温度趋势 (近三年)', x=0.5),
                    template='plotly_white',
                    xaxis=dict(
                        title='日期',
                        dtick="M1",             # 强制每一个月一个刻度
                        tickformat="%Y-%m",     # 格式化显示
                        tickangle=-45,          # 倾斜防止重叠
                        showgrid=True,           # 显示网格线
                        gridwidth=1,
                        gridcolor='rgba(200, 200, 200, 0.3)'
                    ),
                    yaxis=dict(title='情绪温度', range=[-30, 130]),
                    hovermode='x unified',
                    margin=dict(l=40, r=40, t=50, b=40),
                    height=430
                )
                
                # 清空容器并添加图表
                chart_container.clear()
                with chart_container:
                    ui.plotly(fig).classes('w-full h-full')
                
                # --- 数据表格 ---
                data_container.classes(remove='hidden')
                with data_container:
                    # 导出功能
                    def export_excel():
                        import io
                        try:
                            output = io.BytesIO()
                            # 整理导出数据
                            export_df = df.copy()
                            export_df.index.name = '日期'
                            export_df = export_df.rename(columns={
                                'temperature': '情绪温度',
                                'turnover_trillion': '成交额(万亿)', 
                                'margin_buy': '融资买入额',
                                'margin_ratio_pct': '融资占比(%)'
                            })
                            # 选择并排序显示列
                            cols = ['情绪温度', '成交额(万亿)', '融资买入额', '融资占比(%)']
                            # 确保列存在
                            valid_cols = [c for c in cols if c in export_df.columns]
                            
                            export_df[valid_cols].to_excel(output)
                            ui.download(output.getvalue(), 'market_sentiment.xlsx')
                        except Exception as e:
                            ui.notify(f'导出失败: {e}', type='negative')

                    with ui.row().classes('w-full justify-between items-center mb-2'):
                        ui.label('历史数据明细').classes('text-lg font-bold text-gray-700')
                        ui.button('导出Excel', icon='file_download', on_click=export_excel).props('small outline color=green')

                    with ui.expansion('查看详细历史数据', icon='list_alt').classes('w-full bg-white border rounded'):
                        # 准备表格数据
                        rows = []
                        # 按日期倒序
                        df_rev = df.sort_index(ascending=False)
                        for idx, row in df_rev.iterrows():
                            # 根据温度给个颜色
                            temp = row['temperature']
                            temp_color = 'green' if temp < -20 else ('red' if temp > 100 else 'black')
                            
                            rows.append({
                                'date': idx.strftime('%Y-%m-%d'),
                                'temp': round(row['temperature'], 2),
                                'turnover': round(row['turnover_trillion'], 3),
                                'margin_buy': round(row['margin_buy'] / 1e8, 2) if 'margin_buy' in row else 0, # 亿元
                                'margin_pct': round(row['margin_ratio_pct'], 2)
                            })
                            
                        ui.aggrid({
                            'columnDefs': [
                                {'headerName': '日期', 'field': 'date', 'sortable': True, 'filter': True},
                                {'headerName': '情绪温度', 'field': 'temp', 'sortable': True, 'cellStyle': {'color': 'blue', 'fontWeight': 'bold'}},
                                {'headerName': '两市成交额(万亿)', 'field': 'turnover', 'sortable': True},
                                {'headerName': '融资买入额(亿)', 'field': 'margin_buy', 'sortable': True},
                                {'headerName': '融资占比(%)', 'field': 'margin_pct', 'sortable': True},
                            ],
                            'rowData': rows,
                            'pagination': True,
                            'paginationPageSize': 20,
                            # 'domLayout': 'autoHeight', # 移除自适应高度，改用固定高度以确保容器正常包裹
                            'defaultColDef': {'flex': 1, 'resizable': True}
                        }).classes('w-full h-[600px]') # 设定固定高度，确保边框能正确包裹内容，若超出则内部滚动

            # 启动加载
            ui.timer(0.1, fetch_and_draw, once=True)
