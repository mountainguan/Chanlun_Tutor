from nicegui import ui
from utils.sector_crowding import SectorCrowding
import plotly.graph_objects as go
import pandas as pd
import asyncio


# ============ 视觉辅助函数 ============

def _crowding_color(v):
    """根据拥挤度返回 (背景色, 文字色, 等级标签)。"""
    if v is None:
        return ('transparent', '#9ca3af', '—')
    if v >= 4:
        return ('#fee2e2', '#b91c1c', '严重拥挤')
    if v >= 3:
        return ('#ffedd5', '#c2410c', '高拥挤')
    if v >= 2:
        return ('#fef3c7', '#b45309', '偏高')
    if v >= 1:
        return ('#f3f4f6', '#374151', '正常')
    return ('#d1fae5', '#047857', '低位')


def _chg_color(v):
    if v is None:
        return '#9ca3af'
    if v > 0.3: return '#b91c1c'
    if v > 0.1: return '#ea580c'
    if v < -0.3: return '#047857'
    if v < -0.1: return '#059669'
    return '#6b7280'


def _crowding_bar(v, vmax=6.0):
    """渲染一个紧凑的拥挤度色条（HTML）。"""
    if v is None:
        return ''
    pct = max(0, min(100, v / vmax * 100))
    bg, fg, _ = _crowding_color(v)
    return (
        f'<div style="position:relative;width:100%;height:6px;background:#f3f4f6;'
        f'border-radius:3px;overflow:hidden;margin-top:4px;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;width:{pct:.0f}%;'
        f'background:{fg};border-radius:3px;"></div></div>'
    )


# ============ 主面板 ============

def render_sector_crowding_panel(plotly_renderer, is_mobile=False):
    """板块拥挤度面板：最新排行 + 三年趋势。"""
    sc = SectorCrowding()
    progress_state = {'running': False, 'done': 0, 'total': 0, 'cur': '', 'msg': ''}
    # 行点击处理已通过内联 onclick 字符串实现，无需额外 JS 注入

    # ---------- 指标说明卡片 ----------
    with ui.card().classes('w-full bg-white p-4 rounded-xl shadow-sm border border-gray-200'):
        with ui.row().classes('items-center gap-2 w-full'):
            ui.icon('thermostat', color='orange').classes('text-2xl')
            ui.label('板块拥挤度说明').classes('text-lg font-bold text-gray-800')
            ui.label('数据源：Tushare Pro（两融明细 T+1 发布）').classes('text-xs text-gray-400 ml-auto')

        with ui.row().classes('w-full gap-4 items-stretch flex-col md:flex-row mt-2'):
            with ui.card().classes('flex-1 p-3 bg-orange-50 rounded-lg border border-orange-100 shadow-none'):
                ui.label('计算公式').classes('font-bold text-gray-700 text-sm mb-1')
                ui.html(
                    '<div class="text-xs text-orange-800 font-mono bg-white p-2 rounded border border-orange-100">'
                    '拥挤度 = 行业两融余额 ÷ 行业总市值 × 100%</div>',
                    sanitize=False)
                ui.label('衡量杠杆资金在该行业的聚集程度，越高说明两融资金越拥挤。').classes(
                    'text-xs text-gray-500 mt-2 leading-tight')
            with ui.card().classes('flex-1 p-3 bg-blue-50 rounded-lg border border-blue-100 shadow-none'):
                ui.label('数据口径').classes('font-bold text-gray-700 text-sm mb-1')
                ui.label('行业：证监会行业（同 PE 估值模块）；总市值：当日收盘口径；'
                         '历史：近三年逐交易日。').classes('text-xs text-gray-500 leading-tight')

    # ---------- 概览统计 ----------
    stats_container = ui.element('div').classes('w-full grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mt-4')

    # ---------- 主区域：左侧表格 + 右侧趋势图 ----------
    with ui.row().classes('w-full gap-4 items-stretch mt-4 flex-col lg:flex-row'):
        # ===== 左侧：自建 HTML 表格（行级点击 + 高亮 + 色条） =====
        with ui.column().classes('w-full lg:w-3/5 min-w-0'):
            table_card = ui.card().classes(
                'w-full bg-white p-4 rounded-xl shadow-sm border border-gray-200')
            with table_card:
                with ui.row().classes('items-center w-full mb-1 flex-wrap gap-2'):
                    ui.icon('view_list', color='orange').classes('text-xl')
                    ui.label('行业拥挤度排行').classes('font-bold text-gray-800 text-base')
                    ui.label('（点击行查看趋势图）').classes('text-xs text-gray-400')
                # === 行业筛选：一级板块 + 二级板块 级联下拉 ===
                with ui.row().classes('w-full gap-2 items-center flex-wrap mb-2'):
                    ui.label('一级').classes('text-xs text-gray-500 font-semibold')
                    l1_select = ui.select(
                        options=['全部'] + sc.get_industry_hierarchy()['l1_list'],
                        value='全部',
                        with_input=False,
                        on_change=lambda e: on_l1_change(e.value),
                    ).classes('min-w-[110px]').props('dense outlined dark-color=orange-7')
                    ui.label('二级').classes('text-xs text-gray-500 font-semibold ml-2')
                    l2_select = ui.select(
                        options=['全部'],
                        value='全部',
                        with_input=False,
                        on_change=lambda e: on_filter_change(),
                    ).classes('min-w-[130px]').props('dense outlined dark-color=orange-7')
                    filter_reset_btn = ui.button(icon='close', on_click=lambda: reset_filter())\
                        .props('flat dense round size=sm').classes('text-gray-500')
                    ui.label('').classes('flex-1')  # 占位
                table_meta = ui.label('').classes('text-xs text-gray-400 mb-2')
                table_container = ui.column().classes('w-full')

        # ===== 右侧：趋势图 =====
        with ui.column().classes('w-full lg:flex-1 min-w-0'):
            chart_card = ui.card().props('id=sector_crowding_chart_card').classes(
                'w-full bg-white p-4 rounded-xl shadow-sm border border-gray-200 h-full')
            with chart_card:
                chart_header = ui.row().classes('items-center gap-2 w-full mb-1 flex-wrap')
                with chart_header:
                    ui.icon('show_chart', color='orange').classes('text-xl')
                    ui.label('行业拥挤度趋势').classes('font-bold text-gray-800')
                    selected_chip = ui.chip('未选择', icon='touch_app',
                                            color='grey-3').props('dense outline')
                    selected_chip.classes('ml-1 text-xs')
                    chart_meta = ui.label('').classes('text-xs text-gray-400 ml-auto')
                chart_hint = ui.label(
                    '👈 点击左侧任一行业行查看三年趋势').classes(
                    'text-xs text-gray-400 mb-2')
                chart_container = ui.column().classes('w-full')

    # ---------- 大指数板块拥挤度信息卡（全宽） ----------
    with ui.card().classes('w-full bg-white p-4 rounded-xl shadow-sm border border-gray-200 mt-4'):
        with ui.row().classes('items-center w-full mb-2 flex-wrap gap-2'):
            ui.icon('insights', color='orange').classes('text-xl')
            ui.label('主要指数板块拥挤度').classes('font-bold text-gray-800 text-base')
            ui.label('· 点击指数查看拥挤度/融资占比趋势').classes('text-xs text-gray-400')
            ui.label('').classes('flex-1')
            index_chart_meta = ui.label('').classes('text-xs text-gray-500')
        with ui.row().classes('w-full gap-3 flex-col lg:flex-row'):
            # 左侧：指数迷你卡片列表
            with ui.column().classes('w-full lg:w-2/5 min-w-0'):
                index_cards_container = ui.element('div').classes(
                    'w-full grid grid-cols-2 md:grid-cols-3 lg:grid-cols-2 gap-2'
                )
            # 右侧：选中指数的趋势图
            with ui.column().classes('w-full lg:flex-1 min-w-0'):
                index_chart_container = ui.column().classes('w-full')

    # ---------- 操作按钮 ----------
    with ui.row().classes('w-full gap-2 mt-3'):
        update_btn = ui.button('更新到最新', icon='refresh',
                               on_click=lambda: asyncio.create_task(update_data()))
        update_btn.props('unelevated color=orange-7')
        rebuild_btn = ui.button('重建三年历史', icon='history',
                                on_click=lambda: asyncio.create_task(rebuild_history()))
        rebuild_btn.props('outline color=orange-7')
        status_label = ui.label('').classes('text-xs text-gray-500 self-center')

    # ---------- 筛选状态 ----------
    filter_state = {'l1': '全部', 'l2': '全部'}

    # ---------- 行业筛选回调 ----------
    def on_l1_change(value):
        filter_state['l1'] = value
        # 重设二级选项
        if value == '全部':
            l2_select.options = ['全部']
            l2_select.value = '全部'
        else:
            hier = sc.get_industry_hierarchy()
            l2s = ['全部'] + list(hier['l1_to_l2_to_csrc'].get(value, {}).keys())
            l2_select.options = l2s
            l2_select.value = '全部'
            l2_select.update()
        filter_state['l2'] = '全部'
        render_table_only()

    def on_filter_change():
        filter_state['l2'] = l2_select.value or '全部'
        render_table_only()

    def reset_filter():
        l1_select.value = '全部'
        l2_select.value = '全部'
        filter_state['l1'] = '全部'
        filter_state['l2'] = '全部'
        l2_select.options = ['全部']
        render_table_only()

    # ---------- 数据层：构造展示数据 ----------
    def build_display():
        df = sc.load_history()
        if df.empty:
            return pd.DataFrame()
        latest = sc.get_latest()
        # 按当前筛选过滤
        filtered = sc.filter_industries_by_hierarchy(
            l1=filter_state['l1'],
            l2=filter_state['l2'],
            industries=latest['industry'].tolist(),
        )
        latest = latest[latest['industry'].isin(filtered)].copy()
        all_dates = sorted(df['trade_date'].unique())
        prev_date = all_dates[-22] if len(all_dates) > 22 else all_dates[0]
        prev = df[df['trade_date'] == prev_date].set_index('industry')

        rows = []
        for _, r in latest.iterrows():
            ind = r['industry']
            ser = df[df['industry'] == ind]['crowding_pct']
            pct_rank = sc.percentile_rank(ser, r['crowding_pct'])
            chg = (r['crowding_pct'] - prev.loc[ind, 'crowding_pct']
                   if ind in prev.index else None)
            rows.append({
                'industry': ind,
                'crowding_pct': round(float(r['crowding_pct']), 2),
                'financing_pct': round(float(r['financing_pct']), 2),
                'short_pct': round(float(r['short_pct']), 3),
                'rzrqye_yi': round(float(r['rzrqye']) / 1e8, 1),
                'total_mv_yi': round(float(r['total_mv']) / 1e8, 0),
                'rank_pct': round(pct_rank, 1) if pct_rank is not None else None,
                'chg_1m': round(float(chg), 2) if chg is not None else None,
                'stocks': f"{int(r['margin_stock_count'])}/{int(r['stock_count'])}",
            })
        return pd.DataFrame(rows)

    # ---------- 渲染层：顶部统计卡 ----------
    def render_stats(display_df, latest_date):
        stats_container.clear()
        if display_df.empty:
            return
        total_rzrqye = display_df['rzrqye_yi'].sum()
        total_mv = display_df['total_mv_yi'].sum()
        market_ratio = total_rzrqye / total_mv * 100 if total_mv else 0
        high_count = int((display_df['crowding_pct'] >= 3).sum())
        low_count = int((display_df['crowding_pct'] < 1).sum())
        cards = [
            ('数据日期', str(latest_date), 'text-orange-700 bg-orange-50 border-orange-200'),
            ('行业数', f"{len(display_df)}", 'text-blue-700 bg-blue-50 border-blue-200'),
            ('高拥挤(≥3%)', f"{high_count}", 'text-red-700 bg-red-50 border-red-200'),
            ('低位(<1%)', f"{low_count}", 'text-emerald-700 bg-emerald-50 border-emerald-200'),
            ('全市场拥挤度', f"{market_ratio:.2f}%", 'text-indigo-700 bg-indigo-50 border-indigo-200'),
            ('历史交易日', f"{len(sc.load_history()['trade_date'].unique())}",
             'text-gray-700 bg-gray-100 border-gray-200'),
        ]
        for label, value, cls in cards:
            with stats_container:
                with ui.element('div').classes(f'p-3 rounded-lg border {cls} '
                                                f'flex flex-col items-center justify-center text-center'):
                    ui.label(label).classes('text-[11px] text-gray-500')
                    ui.label(value).classes('text-lg font-bold')

    # ---------- 渲染层：只重渲染表格+统计（不改图表） ----------
    def render_table_only():
        display_df = build_display()
        df_all = sc.load_history()
        latest_date = df_all['trade_date'].max().date() if not df_all.empty else None
        render_stats(display_df, latest_date)
        # 默认选中当前筛选下的第一个行业
        first_industry = display_df.iloc[0]['industry'] if not display_df.empty else None
        render_table(display_df, selected_industry=first_industry)
        if first_industry:
            # 只在选中行业改变时刷新图表
            cur_selected = selected_chip.text
            if cur_selected != first_industry and cur_selected not in ('未选择', ''):
                # 用户已选了一个，但该行业不在新筛选中 -> 切到第一个
                render_chart(first_industry)
            elif cur_selected in ('未选择', ''):
                render_chart(first_industry)

    # ---------- 渲染层：自建 HTML 表格（带行点击 / 选中态 / 色条） ----------
    def render_table(display_df, selected_industry=None):
        table_container.clear()
        if display_df.empty:
            with table_container:
                with ui.column().classes('w-full items-center justify-center py-8 gap-3'):
                    ui.icon('inbox', size='48px').classes('text-gray-300')
                    ui.label('暂无拥挤度历史数据').classes('text-gray-500 font-bold')
                    ui.label('点击"重建三年历史"或运行脚本：').classes('text-xs text-gray-400')
                    ui.code('python scripts/build_sector_crowding_history.py',
                            language='bash').classes('text-xs')
            table_meta.text = '共 0 个行业'
            return

        table_meta.text = f'共 {len(display_df)} 个行业，按拥挤度降序'
        sorted_df = display_df.sort_values('crowding_pct', ascending=False).reset_index(drop=True)

        head_cells = [
            ('行业', 'text-left', '17%'),
            ('拥挤度', 'text-right', '17%'),
            ('1月变化', 'text-right', '11%'),
            ('3年分位', 'text-right', '9%'),
            ('融资%', 'text-right', '8%'),
            ('两融余额(亿)', 'text-right', '13%'),
            ('总市值(亿)', 'text-right', '12%'),
            ('标的', 'text-right', '7%'),
        ]
        head_html = ''.join(
            f'<th class="px-1.5 py-2 text-[11px] font-semibold text-gray-500 '
            f'border-b border-gray-200 {align}" '
            f'style="width:{w};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
            f'{label}</th>'
            for label, align, w in head_cells
        )

        body_rows = []
        for _, r in sorted_df.iterrows():
            cp = r['crowding_pct']
            chg = r['chg_1m']
            rank = r['rank_pct']
            bg, fg, level = _crowding_color(cp)
            chg_color = _chg_color(chg)
            rank_color = ('#b91c1c' if (rank is not None and rank >= 80)
                          else ('#ea580c' if (rank is not None and rank >= 60) else '#374151'))
            is_sel = (r['industry'] == selected_industry)
            row_bg = '#fff7ed' if is_sel else '#ffffff'
            row_border = ('4px solid #ea580c' if is_sel else '4px solid transparent')
            chg_str = f'{chg:+.2f}' if chg is not None else '—'
            rank_str = f'{rank:.0f}' if rank is not None else '—'
            chg_arrow = ('▲' if (chg is not None and chg > 0)
                         else ('▼' if (chg is not None and chg < 0) else '·'))
            body_rows.append(
                f'<tr class="sc-row" data-industry="{r["industry"]}" '
                f'style="background:{row_bg};cursor:pointer;transition:background 0.15s;'
                f'border-left:{row_border};" '
                f'onclick="(function(tr){{var ind=tr.getAttribute(\'data-industry\');'
                f'var c=tr.closest(\'.q-card\');if(c){{c.querySelectorAll(\'tr.sc-row\')'
                f'.forEach(function(r){{r.style.background=\'#ffffff\';'
                f'r.style.borderLeft=\'4px solid transparent\';delete r.dataset.sel;}});}}'
                f'tr.style.background=\'#fff7ed\';tr.style.borderLeft=\'4px solid #ea580c\';'
                f'tr.dataset.sel=\'true\';'
                f'var e=(window.emitEvent||emitEvent);e(\'sc_row_click\',{{industry:ind}});'
                f'}})(this)" '
                f'onmouseover="if(!this.dataset.sel)this.style.background=\'#fff7ed\'" '
                f'onmouseout="if(!this.dataset.sel)this.style.background=\'#ffffff\'">'
                f'<td class="px-1.5 py-2 text-xs font-semibold text-gray-800 border-b border-gray-100" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                f'{r["industry"]}</td>'
                f'<td class="px-1.5 py-2 border-b border-gray-100" style="text-align:right;white-space:nowrap">'
                f'<div style="display:flex;align-items:center;justify-content:flex-end;gap:6px">'
                f'<span style="color:{fg};font-weight:700;font-size:13px">{cp:.2f}%</span>'
                f'<span style="font-size:10px;color:{fg};background:{bg};padding:1px 6px;'
                f'border-radius:4px;white-space:nowrap">{level}</span></div>'
                f'{_crowding_bar(cp)}</td>'
                f'<td class="px-1.5 py-2 text-xs border-b border-gray-100" '
                f'style="text-align:right;color:{chg_color};font-weight:600;white-space:nowrap">'
                f'{chg_arrow} {chg_str}</td>'
                f'<td class="px-1.5 py-2 text-xs border-b border-gray-100" '
                f'style="text-align:right;color:{rank_color};white-space:nowrap">{rank_str}%</td>'
                f'<td class="px-1.5 py-2 text-xs text-gray-600 border-b border-gray-100" '
                f'style="text-align:right;white-space:nowrap">{r["financing_pct"]:.2f}</td>'
                f'<td class="px-1.5 py-2 text-xs text-gray-600 border-b border-gray-100" '
                f'style="text-align:right;white-space:nowrap">{r["rzrqye_yi"]:,.1f}</td>'
                f'<td class="px-1.5 py-2 text-xs text-gray-500 border-b border-gray-100" '
                f'style="text-align:right;white-space:nowrap">{r["total_mv_yi"]:,.0f}</td>'
                f'<td class="px-1.5 py-2 text-xs text-gray-500 border-b border-gray-100" '
                f'style="text-align:right;white-space:nowrap">{r["stocks"]}</td>'
                f'</tr>'
            )

        table_html = (
            '<div class="sc-table-wrap" '
            'style="overflow:auto;max-height:560px;border-radius:8px;border:1px solid #e5e7eb;'
            'width:100%;display:block">'
            '<table style="border-collapse:collapse;width:100%;min-width:520px;table-layout:fixed">'
            f'<thead style="background:#fafafa;position:sticky;top:0;z-index:1">'
            f'{head_html}</thead>'
            f'<tbody>{"".join(body_rows)}</tbody>'
            '</table></div>'
            '<div class="text-[10px] text-gray-400 mt-1">'
            '💡 拥挤度色条直观显示该行业在 0~6% 区间的相对位置'
            '</div>'
        )

        # 给被选中的行打上 data-sel=true，方便 hover 逻辑跳过
        if selected_industry:
            table_html = table_html.replace(
                f'data-industry="{selected_industry}"',
                f'data-industry="{selected_industry}" data-sel="true"',
                1,
            )

        with table_container:
            ui.html(table_html, sanitize=False)
            # 行点击通过内联 onclick 调用全局 scHandleRowClick（已由 ui.add_body_html 注入）

    # 事件监听只在外层注册一次（render_table 内不再重复 ui.on）
    def _on_row_click(e):
        try:
            industry = e.args.get('industry') if hasattr(e, 'args') else None
            if industry:
                render_chart(industry, scroll=True)
        except Exception as ex:
            print(f'SectorCrowding row click error: {ex}')
    ui.on('sc_row_click', _on_row_click)

    # ---------- 渲染层：趋势图 ----------
    def render_chart(industry, scroll=False):
        chart_container.clear()
        ser = sc.get_industry_series(industry)
        if ser.empty:
            with chart_container:
                ui.label(f'行业 {industry} 暂无数据').classes('text-gray-400')
            return

        try:
            latest_val = float(ser.iloc[-1]['crowding_pct'])
            latest_date = str(ser.iloc[-1]['trade_date'])
            chg_1m = None
            if len(ser) > 22:
                chg_1m = float(ser.iloc[-1]['crowding_pct']) - float(ser.iloc[-22]['crowding_pct'])
            selected_chip.text = f'{industry}'
            selected_chip.props('color=orange-7')
            chg_str = (f'  ·  1月 {chg_1m:+.2f}%' if chg_1m is not None else '')
            chart_meta.text = f'最新 {latest_date}  {latest_val:.2f}%{chg_str}'
        except Exception:
            selected_chip.text = industry
        chart_hint.text = ''

        fig = go.Figure()
        # === 主图：拥挤度% + 融资占比% ===
        fig.add_trace(go.Scatter(
            x=ser['trade_date'], y=ser['crowding_pct'],
            mode='lines', name='拥挤度%',
            line=dict(color='#ea580c', width=2.4),
            hovertemplate='%{x|%Y-%m-%d}<br>拥挤度 %{y:.2f}%<extra></extra>',
        ))
        fig.add_trace(go.Scatter(
            x=ser['trade_date'], y=ser['financing_pct'],
            mode='lines', name='融资占比%',
            line=dict(color='#60a5fa', width=1.2, dash='dot'),
            hovertemplate='%{x|%Y-%m-%d}<br>融资占比 %{y:.2f}%<extra></extra>',
        ))

        vals = ser['crowding_pct'].dropna()
        for q, color, label in ((0.2, '#10b981', 'P20'), (0.5, '#f59e0b', 'P50'),
                                (0.8, '#ef4444', 'P80')):
            qv = float(vals.quantile(q))
            fig.add_hline(y=qv, line_dash='dot', line_color=color, line_width=1,
                          annotation_text=f'{label} {qv:.2f}%',
                          annotation_position='right')

        latest_val = float(ser.iloc[-1]['crowding_pct'])
        fig.add_hline(y=latest_val, line_dash='dash', line_color='#7c3aed',
                      line_width=1.2,
                      annotation_text=f'最新 {latest_val:.2f}%',
                      annotation_position='top right')

        fig.add_trace(go.Scatter(
            x=[ser.iloc[-1]['trade_date']], y=[latest_val],
            mode='markers', showlegend=False,
            marker=dict(color='#7c3aed', size=11, line=dict(color='white', width=2)),
            hovertemplate=f'最新<br>{industry}<br>拥挤度 {latest_val:.2f}%<extra></extra>',
        ))

        # 计算默认可见范围：能拿到三年数据则默认看近 6 个月，
        # 用户可通过底部 rangeslider 拖动查看全部历史
        x_min = ser['trade_date'].min()
        x_max = ser['trade_date'].max()
        try:
            x_max_dt = pd.to_datetime(x_max)
            default_start = x_max_dt - pd.DateOffset(months=6)
            if pd.to_datetime(x_min) > default_start:
                default_start = pd.to_datetime(x_min)
        except Exception:
            default_start = None

        fig.update_layout(
            template='plotly_white',
            height=480,
            margin=dict(l=55, r=20, t=50, b=10),
            hovermode='x unified',
            legend=dict(
                orientation='h',
                yanchor='top', y=-0.12, x=0.5, xanchor='center',
                groupclick='toggleitem',
                tracegroupgap=8,
                bgcolor='rgba(255,255,255,0.0)',
                bordercolor='#e5e7eb',
                borderwidth=0,
                font=dict(size=11),
            ),
            xaxis=dict(
                title='',
                type='date',
                rangeslider=dict(visible=True, thickness=0.06, bgcolor='#fef3c7'),
                rangeselector=dict(
                    buttons=[
                        dict(count=1, label='1月', step='month', stepmode='backward'),
                        dict(count=3, label='3月', step='month', stepmode='backward'),
                        dict(count=6, label='6月', step='month', stepmode='backward'),
                        dict(count=1, label='1年', step='year', stepmode='backward'),
                        dict(count=3, label='3年', step='year', stepmode='backward'),
                        dict(step='all', label='全部'),
                    ],
                    bgcolor='#fff7ed',
                    activecolor='#ea580c',
                    bordercolor='#e5e7eb',
                    font=dict(size=10),
                    x=0, y=1.10, xanchor='left', yanchor='top',
                ),
                range=[default_start, x_max] if default_start is not None else None,
            ),
            yaxis=dict(
                title=dict(text='占行业总市值 %', font=dict(color='#ea580c', size=11)),
                tickfont=dict(color='#ea580c', size=10),
                side='left',
            ),
            transition=dict(duration=500, easing='cubic-in-out'),
        )
        with chart_container:
            plotly_renderer(fig).classes('w-full h-[480px]')

        if scroll:
            try:
                ui.run_javascript(
                    "document.getElementById('sector_crowding_chart_card')"
                    "?.scrollIntoView({behavior:'smooth', block:'start'});"
                )
            except Exception:
                pass

    # ---------- 指数板块卡片渲染 ----------
    def _crowding_color_for_value(v):
        if v is None:
            return ('#f3f4f6', '#9ca3af', '—')
        if v >= 4:
            return ('#fee2e2', '#b91c1c', '严重')
        if v >= 3:
            return ('#ffedd5', '#c2410c', '高')
        if v >= 2:
            return ('#fef3c7', '#b45309', '偏高')
        if v >= 1:
            return ('#f3f4f6', '#374151', '正常')
        return ('#d1fae5', '#047857', '低位')

    def render_index_cards():
        """渲染 10 个大指数的迷你卡片（最新拥挤度/融资占比）。"""
        index_cards_container.clear()
        # 缓存各指数的最新数据
        idx_latest = {}
        for code, name, scope in sc.INDEX_LIST:
            n, df = sc.get_index_crowding_series(code, scope=scope)
            if df is None or df.empty:
                continue
            last = df.iloc[-1]
            idx_latest[code] = {
                'name': n or name,
                'date': str(last['trade_date'])[:10],
                'crowding': float(last['crowding_pct']),
                'financing': float(last['financing_pct']),
                'coverage': float(last['coverage']),
                'df': df,
            }
        # 按拥挤度降序排
        sorted_idx = sorted(idx_latest.items(), key=lambda x: -x[1]['crowding'])
        selected_code = [None]  # 用 list 包装闭包变量

        for code, info in sorted_idx:
            cp = info['crowding']
            fp = info['financing']
            cov = info['coverage']
            # 计算 3 年分位
            rank_pct = sc.percentile_rank(info['df']['crowding_pct'], cp)
            rank_pct_str = f'{rank_pct:.0f}%' if rank_pct is not None else '—'
            rank_color = ('#b91c1c' if (rank_pct is not None and rank_pct >= 80)
                          else ('#ea580c' if (rank_pct is not None and rank_pct >= 60) else '#374151'))
            bg, fg, level = _crowding_color_for_value(cp)
            with index_cards_container:
                # 内联 onclick：emitEvent 在 nicegui 客户端上下文直接可用
                click_js = (
                    f"(function(el){{var cards=el.parentElement.parentElement.querySelectorAll('[data-idx-code]');"
                    f"cards.forEach(function(c){{c.style.background='#ffffff';c.style.borderColor='#e5e7eb';}});"
                    f"el.style.background='#fff7ed';el.style.borderColor='#ea580c';"
                    f"var e=(window.emitEvent||emitEvent);"
                    f"e('sc_index_click',{{code:'{code}'}});}})(this)"
                )
                with ui.element('div').classes(
                    f'p-2.5 rounded-lg border border-gray-200 cursor-pointer '
                    f'hover:shadow-md transition-all bg-white'
                ).props(f'data-idx-code={code} onclick="{click_js}"'):
                    with ui.row().classes('items-center justify-between gap-1'):
                        ui.label(info['name']).classes('font-bold text-sm text-gray-800')
                        ui.badge(level, color='orange-7' if cp >= 3 else (
                            'red-7' if cp >= 4 else 'grey-6')).props('outline dense')
                    with ui.row().classes('items-end justify-between gap-1 mt-1'):
                        with ui.column().classes('gap-0'):
                            ui.label('拥挤度').classes('text-[10px] text-gray-500')
                            ui.label(f'{cp:.2f}%').classes(
                                f'text-base font-bold').style(f'color:{fg}')
                        with ui.column().classes('gap-0 items-end'):
                            ui.label('融资占比').classes('text-[10px] text-gray-500')
                            ui.label(f'{fp:.2f}%').classes('text-sm font-semibold text-blue-700')
                    with ui.row().classes('items-end justify-between gap-1 mt-1'):
                        with ui.column().classes('gap-0'):
                            ui.label('3年分位').classes('text-[10px] text-gray-500')
                            ui.label(rank_pct_str).classes(
                                'text-xs font-semibold').style(f'color:{rank_color}')
                        with ui.column().classes('gap-0 items-end'):
                            ui.label('覆盖').classes('text-[10px] text-gray-500')
                            ui.label(f'{cov:.0f}%').classes('text-xs text-gray-600')
                    ui.label(info['date']).classes(
                        'text-[10px] text-gray-400 mt-0.5')

        # 默认选中拥挤度最高的
        if sorted_idx:
            selected_code[0] = sorted_idx[0][0]
            render_index_chart(selected_code[0], idx_latest)
            # 高亮默认卡片
            try:
                ui.run_javascript(f'''
                    (function(){{
                        const c = document.querySelector('[data-idx-code="{selected_code[0]}"]');
                        if (c) {{ c.style.background='#fff7ed'; c.style.borderColor='#ea580c'; }}
                    }})();
                ''')
            except Exception:
                pass

    def render_index_chart(code, idx_latest=None):
        """渲染指定指数的拥挤度/融资占比 趋势图。"""
        index_chart_container.clear()
        if idx_latest is None:
            for c, n, s in sc.INDEX_LIST:
                if c == code:
                    n2, df = sc.get_index_crowding_series(c, scope=s)
                    if df is not None and not df.empty:
                        info = {
                            'name': n2 or n, 'df': df,
                            'date': str(df.iloc[-1]['trade_date'])[:10],
                            'crowding': float(df.iloc[-1]['crowding_pct']),
                            'financing': float(df.iloc[-1]['financing_pct']),
                        }
                        break
            else:
                return
        else:
            info = idx_latest.get(code)
        if not info or info['df'].empty:
            with index_chart_container:
                ui.label('该指数暂无数据').classes('text-gray-400 text-sm p-4')
            return
        df = info['df']
        index_chart_meta.text = (
            f"{info['name']}  ·  最新 {info['date']}  ·  "
            f"拥挤度 {info['crowding']:.2f}%  ·  融资占比 {info['financing']:.2f}%"
        )
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df['trade_date'], y=df['crowding_pct'],
            mode='lines', name='拥挤度%',
            line=dict(color='#ea580c', width=2.2),
            hovertemplate='%{x|%Y-%m-%d}<br>拥挤度 %{y:.2f}%<extra></extra>',
        ))
        fig.add_trace(go.Scatter(
            x=df['trade_date'], y=df['financing_pct'],
            mode='lines', name='融资占比%',
            line=dict(color='#60a5fa', width=1.2, dash='dot'),
            hovertemplate='%{x|%Y-%m-%d}<br>融资占比 %{y:.2f}%<extra></extra>',
        ))
        fig.add_trace(go.Scatter(
            x=[df.iloc[-1]['trade_date']], y=[info['crowding']],
            mode='markers', showlegend=False,
            marker=dict(color='#7c3aed', size=10, line=dict(color='white', width=2)),
            hovertemplate=f"最新 {info['crowding']:.2f}%<extra></extra>",
        ))
        fig.update_layout(
            template='plotly_white',
            height=320,
            margin=dict(l=50, r=20, t=30, b=30),
            hovermode='x unified',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0,
                        font=dict(size=10)),
            xaxis=dict(
                title='',
                type='date',
                rangeslider=dict(visible=True, thickness=0.08, bgcolor='#fef3c7'),
            ),
            yaxis=dict(
                title=dict(text='占比 %', font=dict(color='#ea580c', size=10)),
                tickfont=dict(color='#ea580c', size=9),
                side='left',
            ),
            transition=dict(duration=400, easing='cubic-in-out'),
        )
        with index_chart_container:
            plotly_renderer(fig).classes('w-full h-[320px]')

    def _on_index_click(e):
        try:
            code = e.args.get('code') if hasattr(e, 'args') else None
            if code:
                render_index_chart(code)
        except Exception as ex:
            print(f'SectorCrowding index click error: {ex}')

    ui.on('sc_index_click', _on_index_click)

    # ---------- 入口 ----------
    def load_view():
        df = sc.load_history()
        display_df = build_display()
        latest_date = df['trade_date'].max().date() if not df.empty else None
        render_stats(display_df, latest_date)
        first_industry = display_df.iloc[0]['industry'] if not display_df.empty else None
        render_table(display_df, selected_industry=first_industry)
        if first_industry:
            render_chart(first_industry)
        # 指数板块卡片
        try:
            render_index_cards()
        except Exception as ex:
            print(f'SectorCrowding render_index_cards error: {ex}')

    def run_build(max_days=None):
        return sc.build_history(max_days=max_days, resume=True,
                                progress_cb=lambda d, t, c, l:
                                progress_state.update(done=d, total=t, cur=c))

    async def update_data():
        if progress_state['running']:
            try:
                ui.notify('已有任务在运行，请稍候', type='warning')
            except RuntimeError:
                pass
            return
        try:
            update_btn.disable()
            status_label.text = '正在更新到最新交易日...'
            progress_state['running'] = True
            loop = asyncio.get_running_loop()
            added = await loop.run_in_executor(None, lambda: run_build(max_days=10))
            status_label.text = f'更新完成（新增 {added} 个交易日）'
            load_view()
            try:
                ui.notify('板块拥挤度已更新', type='positive')
            except RuntimeError:
                pass
        except RuntimeError:
            pass
        except Exception as e:
            print(f'SectorCrowding update error: {e}')
            try:
                ui.notify(f'更新失败: {e}', type='negative')
            except RuntimeError:
                pass
        finally:
            progress_state['running'] = False
            try:
                update_btn.enable()
            except RuntimeError:
                pass

    async def rebuild_history():
        if progress_state['running']:
            try:
                ui.notify('已有任务在运行，请稍候', type='warning')
            except RuntimeError:
                pass
            return
        try:
            rebuild_btn.disable()
            update_btn.disable()
            progress_state['running'] = True
            status_label.text = '正在构建三年历史（约需 10-20 分钟），可在服务器日志查看进度...'
            loop = asyncio.get_running_loop()

            def monitor():
                return sc.build_history(
                    resume=True,
                    progress_cb=lambda d, t, c, l:
                    progress_state.update(done=d, total=t, cur=c),
                )

            added = await loop.run_in_executor(None, monitor)
            progress_state.update(done=0, total=0)
            status_label.text = f'重建完成（本次新增 {added} 个交易日）'
            load_view()
            try:
                ui.notify('三年历史数据已就绪', type='positive')
            except RuntimeError:
                pass
        except RuntimeError:
            pass
        except Exception as e:
            print(f'SectorCrowding rebuild error: {e}')
            try:
                ui.notify(f'重建失败: {e}', type='negative')
            except RuntimeError:
                pass
        finally:
            progress_state['running'] = False
            try:
                rebuild_btn.enable()
                update_btn.enable()
            except RuntimeError:
                pass

    load_view()
