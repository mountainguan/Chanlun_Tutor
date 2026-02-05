from nicegui import ui
from utils.sector_sentiment import SectorSentiment
import plotly.graph_objects as go
import pandas as pd
import asyncio
import os
import sys
import subprocess
import io

def render_sector_sentiment_panel(plotly_renderer, is_mobile=False):
    # UI Layout and Components
    
    # Redesigned: Left main column for explanations + right stats sidebar
    with ui.row().classes('w-full max-w-6xl gap-6 items-stretch min-h-[220px] flex-col md:flex-row'):
        # Left column (main content)
        with ui.column().classes('flex-1 h-full hide-on-mobile'):
            with ui.card().classes('w-full h-full flex flex-col bg-white p-4 rounded-lg shadow-md border-l-2 border-l-indigo-100 no-inner-shadow min-h-0 min-h-[450px]'):
                with ui.row().classes('items-center gap-2 mb-4'):
                    ui.icon('info', color='indigo').classes('text-2xl')
                    ui.label('板块情绪温度说明').classes('text-lg font-bold text-gray-800')

                ui.html('''
                <div class="bg-indigo-50 p-4 rounded-lg mb-4 text-sm text-indigo-900">
                    <b>📐 计算公式：</b>板块温度 = <span class="font-bold text-red-600">量能项(资金活跃度)</span> + <span class="font-bold text-blue-600">融资项(杠杆意愿)</span>
                </div>
                ''', sanitize=False).classes('w-full')

                with ui.card().classes('w-full p-4 bg-gray-50 rounded-lg flex-1 flex flex-col min-h-0'):
                    with ui.row().classes('w-full gap-4 items-stretch flex-nowrap overflow-x-auto flex-1 min-h-0'):
                        with ui.card().classes('flex-1 min-w-[320px] p-4 bg-white rounded-lg shadow-none border-0'):
                            ui.label('量能项 (Volume)').classes('font-bold text-gray-700 text-sm mb-1')
                            ui.label('反映资金相对大盘的活跃度。').classes('text-xs text-gray-500 mb-2')
                            ui.html('<div class="text-xs w-full break-words">公式： (板块成交 / 均量) ÷ (大盘成交 / 均量)</div>', sanitize=False)

                        with ui.card().classes('flex-1 min-w-[320px] p-4 bg-white rounded-lg shadow-none border-0'):
                            ui.label('融资项 (Margin)').classes('font-bold text-gray-700 text-sm mb-1')
                            ui.label('反映杠杆资金相对大盘的激进程度。').classes('text-xs text-gray-500 mb-2')
                            ui.html('<div class="text-xs w-full break-words">公式： (板块融资占比%) - (大盘融资占比%)</div>', sanitize=False)

                    with ui.row().classes('w-full gap-2 mt-3 text-xs'):
                        with ui.column().classes('flex-1 bg-red-100 p-2 rounded-lg border border-red-100 items-center justify-center'):
                            ui.label('温度 > 90：过热').classes('font-bold text-red-600')
                            ui.label('风险聚集').classes('text-red-400')
                        with ui.column().classes('flex-1 bg-indigo-50 p-2 rounded-lg border border-indigo-100 items-center justify-center'):
                            ui.label('温度 在 -20 ~ -50：较冷').classes('font-bold text-indigo-700')
                            ui.label('留意资金动向').classes('text-indigo-400')
                        with ui.column().classes('flex-1 bg-purple-50 p-2 rounded-lg border border-purple-100 items-center justify-center'):
                            ui.label('温度 < -50：过冷').classes('font-bold text-purple-700')
                            ui.label('注意板块反弹').classes('text-purple-400')

        # Right column (stats sidebar)
        with ui.column().classes('flex-1'):
            with ui.card().classes('w-full h-full p-4 bg-white rounded-lg shadow-md border-0 flex flex-col no-inner-shadow min-h-[450px]') as right_stats_card:
                ui.label('今日板块统计').classes('font-bold text-gray-700 mb-0')
                ui.label('显示当前缓存中按温度分组的板块数量与示例名称。').classes('text-xs text-gray-500 mb-1')
                right_stats_container = ui.column().classes('w-full text-sm text-gray-700 flex-1 min-h-0')
                with right_stats_container:
                    ui.label('尚未加载统计数据，请加载或更新板块数据。').classes('text-xs text-gray-400')

    # Hidden Control State
    with ui.row().classes('hidden'):
        level_select = ui.toggle({1: '一级行业', 2: '二级行业'}, value=1).props('no-caps push color=indigo')
        sector_status_label = ui.label('准备就绪').classes('hidden')

    # Chart Area
    sector_chart_container = ui.card().props('id="sector_panel_root"').classes('w-full h-auto p-4 bg-white rounded-xl shadow-md border-0 flex flex-col')
    
    # Table Area
    sector_table_container = ui.column().classes('w-full mt-4')

    # State variables
    state = {'update_btn': None, 'load_btn': None}

    # Helper for manual color interpolation
    def get_color_hex(val):
        c_blue = (49, 54, 149); c_white = (255, 255, 255); c_red = (180, 0, 0)
        try: v = float(val)
        except: return '#CCCCCC'
        def clamp(n, minn, maxn): return max(min(n, maxn), minn)
        def lerp_rgb(c1, c2, t): return (int(c1[0] + (c2[0] - c1[0]) * t), int(c1[1] + (c2[1] - c1[1]) * t), int(c1[2] + (c2[2] - c1[2]) * t))
        if v < 0:
            t = clamp(abs(v) / 60.0, 0, 1)
            rgb = lerp_rgb(c_white, c_blue, t)
        else:
            t = clamp(v / 100.0, 0, 1)
            rgb = lerp_rgb(c_white, c_red, t)
        return f'rgb({rgb[0]},{rgb[1]},{rgb[2]})'

    def load_sector_view(date=None):
        try:
            level = level_select.value
            ss = SectorSentiment(industry_level=level)
            data = ss.get_display_data()
            if data:
                render_sector_view_internal(data, target_date=date)
            else:
                ui.notify(f'无缓存数据 (Level {level})，请点击更新', type='warning')
                sector_chart_container.clear()
                with sector_chart_container:
                    # Simplified empty state
                    ui.label(f'暂无缓存 (Level {level})').classes('text-2xl font-bold text-gray-700')
                    with ui.row().classes('gap-4 mt-2'):
                        ui.button('加载缓存', on_click=lambda: load_sector_view()).props('unelevated color=indigo-6 icon=history')
                        ui.button('在线更新', on_click=lambda: update_sector_data()).props('outline color=indigo-6 icon=cloud_download')
        except RuntimeError:
            pass

    async def update_sector_data():
        try:
            loop = asyncio.get_running_loop()
            level = level_select.value
            level_name = '一级行业' if level == 1 else '二级行业'
            
            if state['update_btn']: state['update_btn'].disable()
            if state['load_btn']: state['load_btn'].disable()
            
            sector_status_label.text = '正在更新...'
            ui.notify(f'开启独立进程更新【{level_name}】，这需要几分钟...', type='info', timeout=5000)
            
            sector_chart_container.clear()
            sector_table_container.clear()
            with sector_chart_container:
                with ui.column().classes('w-full h-full items-center justify-center'):
                        ui.spinner('dots', size='xl', color='indigo')
                        ui.label(f'正在获取【{level_name}】板块数据...').classes('text-indigo-500 font-bold mt-4')

            script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'utils', 'sector_sentiment.py')
            def run_script():
                # 使用 -u 参数确保输出不被缓冲
                cmd = [sys.executable, '-u', script_path, '--level', str(level)]
                # 不捕获输出，让其直接打印到控制台，以便用户实时查看进度
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    cwd=os.path.dirname(os.path.dirname(__file__))
                )
                
                print(f"\n--- 开始更新【{level_name}】板块数据 ---", flush=True)
                for line in process.stdout:
                    print(line, end='', flush=True)
                
                process.wait()
                if process.returncode != 0:
                    raise Exception(f"板块更新脚本执行失败，退出码: {process.returncode}")
                print(f"--- 【{level_name}】板块数据更新完成 ---\n", flush=True)
                return ""

            await loop.run_in_executor(None, run_script)
            load_sector_view() 
            ui.notify('板块数据更新成功', type='positive')
        except RuntimeError:
            pass
        except Exception as e:
            try:
                ui.notify(f'更新失败: {e}', type='negative')
                load_sector_view()
            except RuntimeError:
                pass
        finally:
            try:
                if state['update_btn']: state['update_btn'].enable()
                if state['load_btn']: state['load_btn'].enable()
            except RuntimeError:
                pass

    def render_sector_view_internal(data, target_date=None):
        try:
            sector_chart_container.clear()
            sector_table_container.clear()
            available_dates = set()
            for name, rec in data.items():
                if 'history' in rec:
                    for h in rec['history']: available_dates.add(h['date'])
                elif 'latest' in rec: available_dates.add(rec['latest']['date'])
                else: available_dates.add(rec.get('date'))
            
            sorted_dates = sorted([d for d in available_dates if d], reverse=True)
            if not sorted_dates: return
            if target_date is None or target_date not in sorted_dates: target_date = sorted_dates[0]
            
            display_records = []
            for k, v in data.items():
                entry = None
                if 'history' in v:
                    matches = [h for h in v['history'] if h['date'] == target_date]
                    if matches: entry = matches[0]
                elif 'latest' in v and v['latest']['date'] == target_date: entry = v['latest']
                elif v.get('date') == target_date: entry = v
                if entry:
                    row = entry.copy(); row['name'] = k
                    if 'group' in v: row['group'] = v['group']
                    display_records.append(row)
            
            df_s = pd.DataFrame(display_records)
            if df_s.empty: return
            if 'turnover' in df_s.columns: df_s['turnover_yi'] = (df_s['turnover'] / 1e8).round(2)

            # Update sidebar stats
            try:
                right_stats_container.clear()
                overheat_list = df_s[df_s['temperature'] > 90].sort_values('temperature', ascending=False)
                cold_list = df_s[(df_s['temperature'] >= -50) & (df_s['temperature'] <= -20)].sort_values('temperature', ascending=True)
                overcold_list = df_s[df_s['temperature'] < -50].sort_values('temperature', ascending=True)
                
                with right_stats_container:
                    is_estim_sidebar = df_s['is_mock'].any() if 'is_mock' in df_s.columns else False
                    with ui.row().classes('items-center gap-1 mb-1'):
                        ui.label(f"数据日期：{target_date}").classes('text-xs text-gray-500')
                        if is_estim_sidebar:
                            ui.label('预估').classes('text-[10px] font-bold text-yellow-800 bg-yellow-100 px-1 rounded')
                    
                    with ui.row().classes('w-full gap-2 mb-1'):
                        ui.label(f'过热: {len(overheat_list)}').classes('bg-red-50 py-1 px-2 rounded-lg text-red-700 font-bold text-xs')
                        ui.label(f'较冷: {len(cold_list)}').classes('bg-blue-50 py-1 px-2 rounded-lg text-blue-700 font-bold text-xs')
                        ui.label(f'过冷: {len(overcold_list)}').classes('bg-purple-50 py-1 px-2 rounded-lg text-purple-700 font-bold text-xs')

                    def render_cat(title, items, count):
                        ui.label(f"{title} ({count})").classes('font-bold mt-1')
                        with ui.row().classes('flex-wrap gap-2 mt-1'):
                            for name in items.head(5)['name']: ui.label(name).classes('text-xs px-2 py-0.5 bg-gray-100 rounded')

                    render_cat('过热板块', overheat_list, len(overheat_list))
                    render_cat('较冷板块', cold_list, len(cold_list))
                    render_cat('过冷板块', overcold_list, len(overcold_list))
            except: pass

            with sector_chart_container:
                # Header
                with ui.row().classes('w-full justify-between items-start mb-4 pb-2 border-b border-gray-100'):
                    with ui.column().classes('gap-1'):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon('grid_view', color='indigo').classes('text-xl')
                            ui.label('全市场板块情绪热度').classes('text-xl font-bold text-gray-800')
                            with ui.row().classes('bg-gray-100 rounded-lg p-1 gap-0'):
                                cl = level_select.value
                                ui.button('一级专区', on_click=lambda: (setattr(level_select, 'value', 1), load_sector_view())).props('unelevated rounded shadow-sm color=indigo text-xs py-1 px-3' if cl==1 else 'flat rounded text-gray-500 text-xs py-1 px-3')
                                ui.button('二级专区', on_click=lambda: (setattr(level_select, 'value', 2), load_sector_view())).props('unelevated rounded shadow-sm color=indigo text-xs py-1 px-3' if cl==2 else 'flat rounded text-gray-500 text-xs py-1 px-3')
                        
                        is_estim = df_s['is_mock'].any() if 'is_mock' in df_s.columns else False
                        with ui.row().classes('items-center gap-1 ml-1'):
                            ui.label(f"{target_date}").classes('text-xs text-gray-400')
                            if is_estim:
                                ui.label('预估').classes('text-[10px] font-bold text-yellow-800 bg-yellow-100 px-1.5 rounded')
                            ui.label('（注：面积大小对应成交额）').classes('text-xs text-gray-400')
                    
                    with ui.row().classes('items-center gap-2'):
                        date_select = ui.select(options=sorted_dates, value=target_date, label="选择日期", on_change=lambda e: load_sector_view(date=e.value)).props('dense outlined options-dense bg-white').classes('w-40')
                        state['load_btn'] = ui.button(icon='refresh', on_click=lambda: load_sector_view(date=date_select.value)).props('flat color=grey')
                        state['update_btn'] = ui.button('更新数据', on_click=lambda: update_sector_data()).props('unelevated color=indigo icon=cloud_download')

                # Treemap Logic
                tm_ids = []; tm_labels = []; tm_parents = []; tm_values = []; tm_colors = []; tm_text = []; tm_textcolors = []
                has_group = 'group' in df_s.columns and df_s['group'].notna().any()

                if has_group:
                    tm_ids.append("ROOT"); tm_labels.append(""); tm_parents.append(""); tm_values.append(df_s['turnover_yi'].sum()); tm_colors.append('rgba(0,0,0,0)'); tm_textcolors.append('rgba(0,0,0,0)'); tm_text.append("")
                    for g in df_s['group'].dropna().unique():
                        sub = df_s[df_s['group'] == g]; tm_ids.append(f"G_{g}"); tm_labels.append(f"<b>{g}</b>"); tm_parents.append("ROOT"); tm_values.append(sub['turnover_yi'].sum()); tm_colors.append('rgba(0,0,0,0)'); tm_textcolors.append('#333333'); tm_text.append("")
                    for _, r in df_s.iterrows():
                        tm_ids.append(r['name']); tm_labels.append(f"<b>{r['name']}</b>"); tm_parents.append(f"G_{r['group']}" if r['group'] else "ROOT"); tm_values.append(r['turnover_yi']); tm_colors.append(get_color_hex(r['temperature'])); tm_text.append(f"{r['temperature']:.0f}°")
                        tm_textcolors.append('white' if r['temperature'] < -30 or r['temperature'] > 50 else '#333333')
                else:
                    for _, r in df_s.iterrows():
                        tm_ids.append(r['name']); tm_labels.append(f"<b>{r['name']}</b>"); tm_parents.append(""); tm_values.append(r['turnover_yi']); tm_colors.append(get_color_hex(r['temperature'])); tm_text.append(f"{r['temperature']:.0f}°")
                        tm_textcolors.append('white' if r['temperature'] < -30 or r['temperature'] > 50 else '#333333')

                fig = go.Figure(go.Treemap(
                    ids=tm_ids, labels=tm_labels, parents=tm_parents, values=tm_values, text=tm_text, branchvalues="total" if has_group else None,
                    marker=dict(colors=tm_colors, line=dict(width=1, color='white')), 
                    textfont=dict(color=tm_textcolors), 
                    texttemplate="<b>%{label}</b><br>%{text}",
                    tiling=dict(pad=1),
                    hovertemplate='<b>%{label}</b><br>成交额: %{value:.1f}亿<br>%{text}<extra></extra>'
                ))
                
                chart_height = 450 if is_mobile else 620
                fig.update_layout(margin=dict(t=10, l=0, r=0, b=0), height=chart_height, paper_bgcolor='rgba(0,0,0,0)')
                plotly_renderer(fig).classes('w-full')

            # Table (Now outside the chart container to prevent overflow)
            with sector_table_container:
                with ui.expansion('查看板块详细列表', icon='list').classes('w-full bg-white border border-gray-200 rounded-xl shadow-sm'):
                    def export():
                        try:
                            output = io.BytesIO(); df_s.round(2).to_excel(output, index=False)
                            ui.download(output.getvalue(), 'sector_sentiment.xlsx')
                        except: pass
                    with ui.row().classes('w-full justify-between items-center p-4 border-b border-gray-50'):
                        with ui.row().classes('items-center gap-2'):
                            ui.icon('table_chart', color='indigo').classes('text-xl')
                            ui.label('全市场板块热度明细').classes('font-bold text-lg')
                        ui.button('导出 Excel', icon='download', on_click=export).props('unelevated color=green-6')
                    
                    # Prepare column definitions dynamically
                    # Using 'flex' to make columns fill the available space
                    grid_cols = [
                        {'headerName': '板块名称', 'field': 'name', 'sortable': True, 'filter': True, 'pinned': 'left', 'width': 130},
                        {'headerName': '归属行业', 'field': 'group', 'sortable': True, 'filter': True, 'flex': 1, 'minWidth': 110} if 'group' in df_s.columns else None,
                        {'headerName': '情绪温度', 'field': 'temperature', 'sortable': True, 'filter': 'agNumberColumnFilter', 
                         'cellStyle': {'fontWeight': 'bold', 'textAlign': 'center'}, 'flex': 1, 'minWidth': 100,
                         'cellClassRules': {
                             'text-red-600': 'x > 90',
                             'text-red-400': 'x > 50 && x <= 90',
                             'text-blue-400': 'x < 0 && x >= -40',
                             'text-blue-700': 'x < -40',
                         }},
                        {'headerName': '量能得分', 'field': 'score_vol', 'sortable': True, 'flex': 1, 'minWidth': 100,
                         'cellClassRules': {'text-red-500': 'x > 0', 'text-blue-500': 'x <= 0'}} if 'score_vol' in df_s.columns else None,
                        {'headerName': '融资得分', 'field': 'score_margin', 'sortable': True, 'flex': 1, 'minWidth': 100,
                         'cellClassRules': {'text-red-500': 'x > 0', 'text-blue-500': 'x <= 0'}} if 'score_margin' in df_s.columns else None,
                        {'headerName': '成交(亿)', 'field': 'turnover_yi', 'sortable': True, 'flex': 1, 'minWidth': 110},
                        {'headerName': '数据状态', 'field': 'status', 'flex': 1, 'minWidth': 90} if 'is_mock' in df_s.columns else None,
                        {'headerName': '更新日期', 'field': 'date', 'sortable': True, 'flex': 1, 'minWidth': 110},
                    ]
                    
                    # Prepare data records with extra status field
                    table_rows = df_s.to_dict('records')
                    for row in table_rows:
                        if row.get('is_mock'):
                            row['status'] = '预估'
                        else:
                            row['status'] = '同步'

                    grid_cols = [c for c in grid_cols if c is not None]

                    ui.aggrid({
                        'columnDefs': grid_cols,
                        'rowData': table_rows,
                        'pagination': True,
                        'paginationPageSize': 20,
                        'defaultColDef': {
                            'resizable': True,
                            'sortable': True,
                            'filter': True,
                        },
                        'rowClassRules': {
                            'bg-red-50': 'data.temperature > 90',
                            'bg-red-100': 'data.temperature > 110', 
                            'bg-blue-50': 'data.temperature < 0',
                            'bg-purple-50': 'data.temperature < -40',
                        }
                    }).classes('w-full h-[650px]')

        except Exception as e:
            print(f"Sector Fail: {e}")

    # Initial Placeholder & Load
    with sector_chart_container:
        ui.label('请点击加载数据').classes('text-gray-400')
        with ui.row().classes('gap-4 mt-2'):
            state['load_btn'] = ui.button('加载缓存', on_click=lambda: load_sector_view()).props('unelevated color=indigo-6 icon=history')
            state['update_btn'] = ui.button('在线更新', on_click=lambda: update_sector_data()).props('outline color=indigo-6 icon=cloud_download')
    
    ui.timer(0.1, lambda: load_sector_view(), once=True)
