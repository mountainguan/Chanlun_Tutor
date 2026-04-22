from nicegui import ui
import pandas as pd
import asyncio
import datetime


def render_volume_leaders_panel(radar, date_str, is_mobile=False, plotly_renderer=None):
    """
    Render Volume Leaders Panel - showing top 100 stocks by trading volume/amount
    and their proportion of total market trading.
    Data Source: 同花顺 (stock_fund_flow_individual)
    """
    # State
    volume_state = {'force_update': False, 'loading': False}

    # Main container
    with ui.card().classes('w-full rounded-2xl shadow-lg border-0 bg-gradient-to-br from-white to-slate-50 overflow-hidden'):
        # Header
        with ui.row().classes('w-full px-6 py-4 items-center justify-between bg-white/80 backdrop-blur-sm border-b border-slate-100'):
            with ui.row().classes('items-center gap-4'):
                with ui.element('div').classes('w-12 h-12 rounded-xl bg-gradient-to-br from-rose-500 to-rose-600 flex items-center justify-center shadow-lg shadow-rose-500/30'):
                    ui.icon('insights', color='white').classes('text-2xl')
                with ui.column().classes('gap-0'):
                    ui.label('成交量主力雷达').classes('text-xl font-bold text-slate-800 tracking-tight')
                    ui.label('Top 100 股票成交额占比 | 同花顺实时数据').classes('text-xs text-slate-400')
            with ui.row().classes('items-center gap-3'):
                update_label = ui.label('').classes('text-[11px] text-slate-400 font-mono')
                refresh_btn = ui.button(icon='refresh', on_click=lambda: trigger_refresh()).props('flat dense round color=grey-6 size=sm')
                index_btn = ui.button('更新指数', on_click=lambda: trigger_index_update()).props('dense flat color=indigo-6 size=sm')
                index_status_label = ui.label('').classes('text-[10px] text-indigo-400')

        # Content area
        content = ui.column().classes('w-full p-6 gap-6')

    async def trigger_refresh():
        volume_state['force_update'] = True
        refresh_btn.props(add='loading')
        await load_data()
        refresh_btn.props(remove='loading')
        volume_state['force_update'] = False

    async def trigger_index_update():
        index_btn.props(add='loading')
        index_status_label.set_text('更新中...')
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, radar.update_index_constituents_cache)
            status = radar.get_index_cache_status()
            status_text = ' | '.join([f"{k}: {v['codes']}只" for k, v in status.items()])
            index_status_label.set_text(status_text)
        except Exception as e:
            print(f"[IndexUpdate] Error: {e}")
            index_status_label.set_text('更新失败')
        index_btn.props(remove='loading')

    async def load_data():
        if volume_state['loading']:
            return
        volume_state['loading'] = True

        content.clear()
        with content:
            with ui.column().classes('w-full items-center justify-center py-16'):
                ui.spinner(type='dots', size='3rem', color='rose')
                ui.label('正在加载成交量数据...').classes('text-slate-400 mt-4 text-sm animate-pulse')

        loop = asyncio.get_running_loop()
        try:
            df = await loop.run_in_executor(
                None, lambda: radar.get_volume_leaders(
                    date_str=date_str,
                    limit=100,
                    force_update=volume_state.get('force_update', False)
                )
            )
        except Exception as e:
            print(f"[VolumeLeaders] Load error: {e}")
            df = pd.DataFrame()

        volume_state['loading'] = False

        if content.is_deleted:
            return

        content.clear()
        with content:
            if df.empty:
                with ui.column().classes('w-full items-center justify-center py-16'):
                    ui.icon('cloud_off', size='4rem', color='slate-300')
                    ui.label('暂无法获取成交量数据').classes('text-slate-500 font-bold mt-4')
                    ui.label('数据源可能暂时不可用').classes('text-slate-400 text-sm mt-1')
                return

            # Stats Summary
            total_100_amount = df['成交额亿'].sum() if '成交额亿' in df.columns else (df['成交额'].sum() / 1e8)
            avg_turnover = df['成交额亿'].mean() if '成交额亿' in df.columns else (df['成交额'].mean() / 1e8)
            top5_pct = df.head(5)['占总成交比'].sum()
            total_net_inflow = df['净流入亿'].sum() if '净流入亿' in df.columns else (df['净流入'].sum() / 1e8)

            update_label.set_text(f"更新: {datetime.datetime.now().strftime('%H:%M:%S')}")

            # Stats cards with fintech style
            with ui.row().classes('w-full gap-4 justify-center'):
                stat_items = [
                    ('成交总额', f'{total_100_amount:.1f}亿', 'rose', 'from-rose-50 to-rose-100/50', 'rose'),
                    ('平均成交额', f'{avg_turnover:.1f}亿', 'indigo', 'from-indigo-50 to-indigo-100/50', 'indigo'),
                    ('净流入合计', f'{total_net_inflow:+.1f}亿', 'amber', 'from-amber-50 to-amber-100/50', 'amber'),
                    ('Top5占比', f'{top5_pct:.1f}%', 'emerald', 'from-emerald-50 to-emerald-100/50', 'emerald'),
                ]
                for title, val, color, bg, text_color in stat_items:
                    with ui.card().classes(f'flex-1 min-w-[140px] p-5 rounded-2xl bg-gradient-to-br {bg} border border-{color}-200/50'):
                        with ui.column().classes('items-center gap-2'):
                            ui.label(title).classes(f'text-[11px] font-semibold text-{color}-600 uppercase tracking-wider')
                            ui.label(val).classes(f'text-2xl font-black text-{color}-700')

            # Table Section with fintech styling
            with ui.card().classes('w-full rounded-2xl border border-slate-200/50 bg-white shadow-sm overflow-hidden'):
                # Table header
                with ui.row().classes('w-full px-5 py-4 items-center justify-between bg-gradient-to-r from-slate-50 to-slate-100/50 border-b border-slate-200/50'):
                    with ui.row().classes('items-center gap-3'):
                        ui.icon('table_chart', color='indigo').classes('text-xl')
                        ui.label('详细数据').classes('font-bold text-slate-700')
                    # Index filter dropdown
                    index_filter = ui.select(
                        ['全部', '沪深300', '中证500', '中证1000', '创业板', '科创50', '上证50', '深证100', '非成分股'],
                        value='全部',
                    ).props('dense outlined color=indigo size=sm')

                # Table container
                table_container = ui.column().classes('w-full')
                table_filter_state = {'filter': '全部', 'df': df}

                def render_filtered_table(filter_value, df_data):
                    table_container.clear()
                    with table_container:
                        # Apply filter
                        if filter_value == '全部':
                            filtered_df = df_data
                        elif filter_value == '非成分股':
                            filtered_df = df_data[(df_data['指数标签'].isna()) | (df_data['指数标签'] == '')]
                        else:
                            filtered_df = df_data[df_data['指数标签'].fillna('').str.contains(filter_value, na=False)]

                        # Stats bar
                        with ui.row().classes('w-full px-5 py-3 bg-slate-50/50 border-b border-slate-100 items-center justify-between'):
                            with ui.row().classes('items-center gap-4 text-xs'):
                                ui.label(f'共 {len(filtered_df)} 只').classes('text-slate-500 font-medium')
                                if filter_value != '全部':
                                    ui.label(f'| 筛选: {filter_value}').classes('text-indigo-500 font-medium')
                            with ui.row().classes('items-center gap-3 text-xs'):
                                with ui.row().classes('items-center gap-1'):
                                    ui.element('div').classes('w-2 h-2 rounded-full bg-rose-500')
                                    ui.label('涨').classes('text-slate-400')
                                with ui.row().classes('items-center gap-1'):
                                    ui.element('div').classes('w-2 h-2 rounded-full bg-emerald-500')
                                    ui.label('跌').classes('text-slate-400')

                        # Scrollable table
                        with ui.column().classes('w-full max-h-[500px] overflow-y-auto'):
                            # Header row
                            with ui.row().classes('w-full sticky top-0 bg-slate-100/90 backdrop-blur-sm z-10 py-3 px-5 border-b border-slate-200'):
                                ui.label('序号').classes('w-12 text-xs font-bold text-slate-500 text-center')
                                ui.label('代码').classes('w-20 text-xs font-bold text-slate-500 text-left')
                                ui.label('名称').classes('w-24 text-xs font-bold text-slate-500 text-left')
                                ui.label('指数标签').classes('flex-1 text-xs font-bold text-slate-500 text-left')
                                ui.label('最新价').classes('w-20 text-xs font-bold text-slate-500 text-right')
                                ui.label('涨跌幅').classes('w-20 text-xs font-bold text-slate-500 text-right')
                                ui.label('换手率').classes('w-20 text-xs font-bold text-slate-500 text-right')
                                ui.label('成交额').classes('w-24 text-xs font-bold text-slate-500 text-right')
                                ui.label('净流入').classes('w-24 text-xs font-bold text-slate-500 text-right')
                                ui.label('占比').classes('w-16 text-xs font-bold text-slate-500 text-right')

                            # Data rows
                            for _, row in filtered_df.iterrows():
                                pct = row.get('涨跌幅', 0)
                                net_in = row.get('净流入亿', 0)
                                index_tag = row.get('指数标签', '')

                                pct_color = 'text-rose-500' if pct > 0 else ('text-emerald-500' if pct < 0 else 'text-slate-400')
                                net_color = 'text-rose-500' if net_in > 0 else ('text-emerald-500' if net_in < 0 else 'text-slate-400')

                                index_tag_str = str(index_tag) if pd.notna(index_tag) else ''
                                if index_tag_str and index_tag_str != '':
                                    tags = index_tag_str.split(',')
                                else:
                                    tags = []

                                with ui.row().classes('w-full py-3 px-5 border-b border-slate-100/50 hover:bg-slate-50/50 transition-colors cursor-default'):
                                    ui.label(str(row.get('序号', ''))).classes('w-12 text-xs text-slate-400 text-center')
                                    ui.label(str(row.get('代码', ''))).classes('w-20 text-xs text-slate-600 font-mono')
                                    ui.label(str(row.get('名称', ''))).classes('w-24 text-sm text-slate-800 font-medium truncate')
                                    with ui.row().classes('flex-1 flex flex-wrap gap-1 items-center'):
                                        if tags:
                                            for t in tags:
                                                ui.label(t).classes('text-[10px] px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-600 font-semibold')
                                        else:
                                            ui.label('-').classes('text-xs text-slate-300')
                                    ui.label(f"{row.get('最新价', 0):.2f}").classes(f'w-20 text-xs text-slate-600 text-right font-mono')
                                    ui.label(f'{pct:+.2f}%').classes(f'w-20 text-xs font-bold text-right font-mono {pct_color}')
                                    ui.label(f"{row.get('换手率', 0):.2f}%").classes('w-20 text-xs text-slate-400 text-right font-mono')
                                    ui.label(f"{row.get('成交额亿', 0):.2f}亿").classes('w-24 text-xs text-slate-600 text-right font-mono')
                                    ui.label(f'{net_in:+.2f}亿').classes(f'w-24 text-xs font-bold text-right font-mono {net_color}')
                                    ui.label(f"{row.get('占总成交比', 0):.2f}%").classes('w-16 text-xs text-slate-400 text-right font-mono')

                # Initial render
                render_filtered_table('全部', df.head(100).copy())

                # Filter change handler
                def on_filter_change(e):
                    render_filtered_table(e.value, table_filter_state['df'])

                index_filter.on_value_change(on_filter_change)

    # Trigger initial load
    asyncio.ensure_future(load_data())

    return content