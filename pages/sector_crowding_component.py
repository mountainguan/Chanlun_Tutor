from nicegui import ui
from utils.sector_crowding import SectorCrowding
from utils.trading_crowding import TradingCrowding
import plotly.graph_objects as go
import pandas as pd
import asyncio
import math


# ============ 两融涨跌速度模块参数 ============
# 观察窗口（交易日数）：默认 10 个交易日 ≈ 近两周。
SPEED_WINDOWS = (3, 5, 10, 15, 20)
# 拥挤度变化超过 ±0.05pp 视为显著升温/降温，其余视为与市值增速匹配。
SPEED_CROWDING_TOL = 0.05
SPEED_SORT_LABELS = {
    'delta_ratio': '增量比（两融变化/市值变化）',
    'rzrqye_pct': '两融增速',
    'total_mv_pct': '市值增速',
    'rzrqye_chg_yi': '两融变化额',
}

# ============ 成交量 / 成交额维度参数 ============
# 前 5% 个股成交集中度：>45% 标记拥挤（与数据层 TradingCrowding.THRESHOLD 一致）
TRADING_DIM_LABELS = {'vol': '成交量', 'amount': '成交额'}
TRADING_THRESHOLD = 45.0
# 个股数少于该值的行业样本过少，前5%集中度易失真（如 1-2 只个股必为 100%），
# 不参与"拥挤"标记，界面显示"样本少"。
TRADING_MIN_STOCKS = 10


def _fmt_ratio(v):
    """增量比格式化：NaN 显示 '—'，±inf 显示 '±∞'，否则显示百分比。"""
    if v is None:
        return '—'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return '—'
    if math.isnan(f):
        return '—'
    if math.isinf(f):
        return '∞' if f > 0 else '−∞'
    return f'{f * 100:.2f}%'


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


# ============ 两融数据维度（原板块拥挤度面板） ============

def render_margin_content(plotly_renderer, is_mobile=False):
    """两融数据维度：行业两融余额/总市值拥挤度 + 三年趋势。"""
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

    # ---------- 两融涨跌速度（板块升温/降温） ----------
    speed_state = {'window': 10, 'sort_by': 'delta_ratio'}
    with ui.card().classes('w-full bg-white p-4 rounded-xl shadow-sm border border-gray-200 mt-4'):
        with ui.row().classes('items-center w-full mb-1 flex-wrap gap-2'):
            ui.icon('speed', color='orange').classes('text-xl')
            ui.label('两融涨跌速度（板块升温/降温）').classes('font-bold text-gray-800 text-base')
            ui.label('· 核心指标：增量比 = 两融变化额 ÷ 市值变化额').classes('text-xs text-gray-400')
            ui.label('').classes('flex-1')
        with ui.row().classes('items-center w-full mb-2 gap-x-3 gap-y-2 flex-wrap'):
            ui.icon('calendar_month', size='16px').classes('text-gray-500')
            ui.label('观察窗口').classes('text-xs text-gray-500 font-semibold')
            speed_window_toggle = ui.toggle(
                {w: f'{w}日' for w in SPEED_WINDOWS},
                value=10,
                on_change=lambda e: on_speed_window_change(e.value),
            ).props('dense no-caps unelevated rounded color=grey-4 toggle-color=orange-7 text-color=grey-8')
            with speed_window_toggle:
                ui.tooltip('对比近 3/5/10/15/20 个交易日的两融与市值变化，默认 10 日 ≈ 近两周')
            ui.label('默认 10 日 ≈ 近两周').classes('text-[11px] text-gray-400')
            ui.label('').classes('flex-1')
            ui.label('排序').classes('text-xs text-gray-500 font-semibold')
            speed_sort_select = ui.select(
                options=SPEED_SORT_LABELS,
                value='delta_ratio',
                on_change=lambda e: on_speed_sort_change(e.value),
            ).classes('min-w-[180px]').props('dense outlined')
            speed_meta = ui.label('').classes('text-xs text-gray-400')
        speed_summary_container = ui.element('div').classes(
            'w-full grid grid-cols-2 md:grid-cols-4 gap-3 mb-2')
        with ui.row().classes('w-full gap-4 items-stretch flex-col lg:flex-row'):
            # 左侧：行业增速明细表
            with ui.column().classes('w-full lg:w-3/5 min-w-0'):
                speed_table_container = ui.column().classes('w-full')
            # 右侧：两融增速 vs 市值增速 匹配散点图
            with ui.column().classes('w-full lg:flex-1 min-w-0'):
                speed_chart_container = ui.column().classes('w-full')

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

    # ---------- 预计算：整个面板只算一次 ----------
    # 真实瓶颈不在 CSV 读取（115ms），而是 render_index_cards 里的
    # get_index_crowding_series × 10：每个调用都用 lambda 在 groupby.agg 里做
    # weighted sum，对 ~750 日期 × 10 指数 = 4 秒纯 pandas 计算。
    # 一次面板挂载 = precompute() + precompute_all_indices()，后续 render 全 O(1) 查表。
    pre = sc.precompute()
    pre_idx = sc.precompute_all_indices()

    # ---------- 数据层：构造展示数据 ----------
    def build_display():
        if pre['df'].empty:
            return pd.DataFrame()
        latest = pre['latest_df']
        # 按当前筛选过滤
        filtered = sc.filter_industries_by_hierarchy(
            l1=filter_state['l1'],
            l2=filter_state['l2'],
            industries=latest['industry'].tolist(),
        )
        latest = latest[latest['industry'].isin(filtered)].copy()
        prev = pre['prev_df']  # Series indexed by industry

        # O(N)：用预分组好的 by_industry 代替 df[df['industry']==ind]
        rows = []
        for _, r in latest.iterrows():
            ind = r['industry']
            ser = pre['by_industry'].get(ind)
            pct_rank = sc.percentile_rank(
                ser['crowding_pct'] if ser is not None else None,
                r['crowding_pct'],
            )
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
        # 历史交易日直接用 pre['dates']，避免重复 load_history()
        history_days = len(pre['dates'])
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
            ('历史交易日', f"{history_days}",
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
        latest_date = pre['latest_date'].date() if pre['latest_date'] is not None else None
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
        # 用面板挂载时预算好的 by_industry 数据，避免每次点击都对
        # 11MB 历史做一次 O(N) 的 industry 过滤（get_industry_series）
        ser = pre['by_industry'].get(industry)
        if ser is None or ser.empty:
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
        # 直接用面板挂载时预算好的 series，不再做 10 次 groupby
        idx_latest = {}
        for code, name, scope in sc.INDEX_LIST:
            entry = pre_idx.get(code)
            if not entry:
                continue
            n, df = entry
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
            # 用面板挂载时一次算好的指数序列，避免点击卡片时重新做
            # 成分股 -> 行业加权聚合（get_index_crowding_series）
            entry = pre_idx.get(code)
            if not entry:
                return
            n2, df = entry
            if df is None or df.empty:
                return
            info = {
                'name': n2, 'df': df,
                'date': str(df.iloc[-1]['trade_date'])[:10],
                'crowding': float(df.iloc[-1]['crowding_pct']),
                'financing': float(df.iloc[-1]['financing_pct']),
            }
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

    # ---------- 两融涨跌速度：数据/渲染 ----------
    def build_speed_display():
        """按当前窗口构造行业两融/市值变化展示数据（核心：增量比）。"""
        speed_map = pre.get('margin_speed', {})
        dfw = speed_map.get(speed_state['window'])
        if dfw is None or dfw.empty:
            return pd.DataFrame()
        rows = []
        for ind, r in dfw.iterrows():
            crowding_chg = float(r['crowding_chg'])
            if crowding_chg >= SPEED_CROWDING_TOL:
                status, status_color, status_bg = '升温', '#b91c1c', '#fee2e2'
            elif crowding_chg <= -SPEED_CROWDING_TOL:
                status, status_color, status_bg = '降温', '#047857', '#d1fae5'
            else:
                status, status_color, status_bg = '匹配', '#6b7280', '#f3f4f6'
            delta_ratio = float(r['delta_ratio'])
            if math.isfinite(delta_ratio):
                delta_ratio_pct = delta_ratio * 100
            else:
                delta_ratio_pct = None
            rows.append({
                'industry': ind,
                'trade_date': str(r['trade_date'])[:10],
                'prev_date': str(r['prev_date'])[:10],
                'rzrqye_yi': float(r['rzrqye_now']) / 1e8,
                'rzrqye_chg_yi': float(r['rzrqye_chg']) / 1e8,
                'total_mv_chg_yi': float(r['total_mv_chg']) / 1e8,
                'rzrqye_pct': float(r['rzrqye_pct']),
                'total_mv_yi': float(r['total_mv_now']) / 1e8,
                'total_mv_pct': float(r['total_mv_pct']),
                'delta_ratio': delta_ratio,
                'delta_ratio_pct': delta_ratio_pct,
                'delta_ratio_text': _fmt_ratio(delta_ratio),
                'crowding_pct': float(r['crowding_pct']),
                'crowding_chg': crowding_chg,
                'status': status,
                'status_color': status_color,
                'status_bg': status_bg,
            })
        return pd.DataFrame(rows)

    def render_speed_summary(display_df):
        speed_summary_container.clear()
        if display_df.empty:
            return
        n_heat = int((display_df['status'] == '升温').sum())
        n_cool = int((display_df['status'] == '降温').sum())
        n_match = len(display_df) - n_heat - n_cool
        cards = [
            ('升温行业', f'{n_heat}', 'text-red-700 bg-red-50 border-red-200'),
            ('匹配行业', f'{n_match}', 'text-gray-700 bg-gray-100 border-gray-200'),
            ('降温行业', f'{n_cool}', 'text-emerald-700 bg-emerald-50 border-emerald-200'),
            ('观察窗口', f'{speed_state["window"]}个交易日',
             'text-indigo-700 bg-indigo-50 border-indigo-200'),
        ]
        for label, value, cls in cards:
            with speed_summary_container:
                with ui.element('div').classes(
                        f'p-2.5 rounded-lg border {cls} '
                        f'flex flex-col items-center justify-center text-center'):
                    ui.label(label).classes('text-[11px] text-gray-500')
                    ui.label(value).classes('text-base font-bold')

    def render_speed_table(display_df):
        speed_table_container.clear()
        if display_df.empty:
            with speed_table_container:
                with ui.column().classes('w-full items-center justify-center py-8 gap-2'):
                    ui.icon('query_stats', size='40px').classes('text-gray-300')
                    ui.label('历史数据不足（至少需 21 个交易日），无法计算两融/市值增速').classes(
                        'text-gray-500 font-bold text-sm')
                    ui.label('点击上方"重建三年历史"后刷新即可查看').classes('text-xs text-gray-400')
            speed_meta.text = ''
            return

        sorted_df = display_df.sort_values(
            speed_state['sort_by'], ascending=False).reset_index(drop=True)
        first = sorted_df.iloc[0]
        speed_meta.text = (
            f'对比区间 {first["prev_date"]} → {first["trade_date"]}'
            f'（{speed_state["window"]} 个交易日）'
            f'· 按{SPEED_SORT_LABELS[speed_state["sort_by"]]}降序'
        )

        head_cells = [
            ('行业', 'text-left', '14%'),
            ('增量比', 'text-right', '13%'),
            ('拥挤度%', 'text-right', '9%'),
            ('两融变化(亿)', 'text-right', '12%'),
            ('市值变化(亿)', 'text-right', '12%'),
            ('两融增速%', 'text-right', '12%'),
            ('市值增速%', 'text-right', '12%'),
            ('状态', 'text-right', '9%'),
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
            rz = float(r['rzrqye_pct'])
            mv = float(r['total_mv_pct'])
            rz_color = ('#b91c1c' if rz > 0.05
                        else ('#047857' if rz < -0.05 else '#6b7280'))
            mv_color = ('#b91c1c' if mv > 0.05
                        else ('#047857' if mv < -0.05 else '#6b7280'))
            cc = float(r['crowding_chg'])
            arrow = ('▲' if cc > 0 else ('▼' if cc < 0 else '·'))
            body_rows.append(
                f'<tr style="border-left:4px solid transparent">'
                f'<td class="px-1.5 py-2 text-xs font-semibold text-gray-800 border-b border-gray-100" '
                f'style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                f'{r["industry"]}</td>'
                f'<td class="px-1.5 py-2 text-xs border-b border-gray-100" '
                f'style="text-align:right;color:{r["status_color"]};font-weight:700;white-space:nowrap">'
                f'{r["delta_ratio_text"]}</td>'
                f'<td class="px-1.5 py-2 text-xs text-gray-600 border-b border-gray-100" '
                f'style="text-align:right;white-space:nowrap">{r["crowding_pct"]:.2f}</td>'
                f'<td class="px-1.5 py-2 text-xs border-b border-gray-100" '
                f'style="text-align:right;color:{rz_color};white-space:nowrap">'
                f'{r["rzrqye_chg_yi"]:+.1f}</td>'
                f'<td class="px-1.5 py-2 text-xs border-b border-gray-100" '
                f'style="text-align:right;color:{mv_color};white-space:nowrap">'
                f'{r["total_mv_chg_yi"]:+.1f}</td>'
                f'<td class="px-1.5 py-2 text-xs border-b border-gray-100" '
                f'style="text-align:right;color:{rz_color};font-weight:700;white-space:nowrap">'
                f'{r["rzrqye_pct"]:+.2f}</td>'
                f'<td class="px-1.5 py-2 text-xs border-b border-gray-100" '
                f'style="text-align:right;color:{mv_color};white-space:nowrap">'
                f'{r["total_mv_pct"]:+.2f}</td>'
                f'<td class="px-1.5 py-2 border-b border-gray-100" style="text-align:right;white-space:nowrap">'
                f'<span style="color:{r["status_color"]};background:{r["status_bg"]};'
                f'padding:1px 8px;border-radius:4px;font-size:10px;font-weight:600">'
                f'{arrow} {r["status"]}</span></td>'
                f'</tr>'
            )

        table_html = (
            '<div style="overflow-x:auto;max-height:480px;overflow-y:auto">'
            '<table style="width:100%;border-collapse:collapse;font-size:12px">'
            f'<thead style="background:#fafafa;position:sticky;top:0;z-index:1">'
            f'{head_html}</thead>'
            f'<tbody>{"".join(body_rows)}</tbody>'
            '</table></div>'
            '<div class="text-[10px] text-gray-400 mt-1">'
            '💡 增量比 = 两融变化额 ÷ 市值变化额（核心指标）：高于当前拥挤度% 说明边际杠杆高于平均水平。'
            '状态按拥挤度变化判定：+≥0.05pp 升温 / −≤0.05pp 降温 / 其余匹配'
            '</div>'
        )
        with speed_table_container:
            ui.html(table_html, sanitize=False)

    def render_speed_chart(display_df):
        speed_chart_container.clear()
        if display_df.empty:
            with speed_chart_container:
                with ui.column().classes('w-full h-full items-center justify-center gap-2 py-8'):
                    ui.label('暂无足够数据').classes('text-gray-400 text-sm')
            return

        top = display_df.dropna(subset=['delta_ratio_pct']).sort_values(
            'delta_ratio_pct', ascending=False).head(15)
        if top.empty:
            with speed_chart_container:
                with ui.column().classes('w-full h-full items-center justify-center gap-2 py-8'):
                    ui.label('暂无有限增量比数据').classes('text-gray-400 text-sm')
            return
        top = top.iloc[::-1]  # 增量比最高的显示在最上方

        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=top['industry'], x=top['delta_ratio_pct'], orientation='h',
            name='增量比',
            marker_color=top['status_color'].tolist(),
            customdata=top[['crowding_pct', 'status']],
            hovertemplate=('<b>%{y}</b><br>'
                           '增量比 %{x:.2f}%<br>'
                           '当前拥挤度 %{customdata[0]:.2f}%<br>'
                           '状态 %{customdata[1]}<extra></extra>'),
        ))
        fig.add_trace(go.Scatter(
            x=top['crowding_pct'], y=top['industry'], mode='markers',
            name='当前拥挤度',
            marker=dict(color='#7c3aed', size=8, symbol='diamond',
                        line=dict(color='white', width=1)),
            hovertemplate=('<b>%{y}</b><br>当前拥挤度 %{x:.2f}%<extra></extra>'),
        ))

        fig.update_layout(
            template='plotly_white',
            height=420,
            margin=dict(l=70, r=20, t=30, b=40),
            hovermode='closest',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0,
                        font=dict(size=10)),
            xaxis=dict(
                title=dict(text='增量比 %（两融变化额 ÷ 市值变化额）',
                           font=dict(color='#374151', size=10)),
                tickfont=dict(color='#374151', size=9),
                zeroline=True, zerolinecolor='#e5e7eb',
            ),
            yaxis=dict(
                title='',
                automargin=True,
            ),
            transition=dict(duration=400, easing='cubic-in-out'),
        )
        with speed_chart_container:
            plotly_renderer(fig).classes('w-full h-[420px]')

    def on_speed_window_change(value):
        speed_state['window'] = int(value)
        render_speed_module()

    def on_speed_sort_change(value):
        speed_state['sort_by'] = value
        render_speed_table(build_speed_display())

    def render_speed_module():
        """整体重渲染两融涨跌速度模块（统计卡 + 表格 + 散点图）。"""
        display_df = build_speed_display()
        render_speed_summary(display_df)
        render_speed_table(display_df)
        render_speed_chart(display_df)

    # ---------- 入口 ----------
    def load_view():
        # 数据重建/更新后：让预计算缓存读到新数据
        sc.invalidate_history_cache()
        pre.clear()
        pre.update(sc.precompute())
        pre_idx.clear()
        pre_idx.update(sc.precompute_all_indices())
        display_df = build_display()
        latest_date = pre['latest_date'].date() if pre['latest_date'] is not None else None
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
        # 两融涨跌速度（板块升温/降温）
        try:
            render_speed_module()
        except Exception as ex:
            print(f'SectorCrowding render_speed_module error: {ex}')

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


# ============ 成交量 / 成交额维度（前5%个股成交集中度） ============

def _tc_color(v):
    """根据集中度返回 (背景色, 文字色, 等级标签)。阈值 >45% 为拥挤。"""
    if v is None:
        return ('transparent', '#9ca3af', '—')
    if v > TRADING_THRESHOLD:
        return ('#fee2e2', '#b91c1c', '拥挤')
    if v >= 30:
        return ('#ffedd5', '#c2410c', '偏高')
    if v >= 20:
        return ('#f3f4f6', '#374151', '正常')
    return ('#d1fae5', '#047857', '低位')


def _tc_bar(v, vmax=60.0):
    """渲染一个紧凑的集中度色条（HTML），刻度 0~60%。"""
    if v is None:
        return ''
    pct = max(0, min(100, v / vmax * 100))
    bg, fg, _ = _tc_color(v)
    return (
        f'<div style="position:relative;width:100%;height:6px;background:#f3f4f6;'
        f'border-radius:3px;overflow:hidden;margin-top:4px;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;width:{pct:.0f}%;'
        f'background:{fg};border-radius:3px;"></div></div>'
    )


# 成交集中度面板的事件处理器。
# ui.on 会绑定到注册时所在的客户端 layout，因此必须【按客户端】注册一次，
# 否则浏览器刷新/新标签页（新客户端）后点击事件无人处理，图表不会切换。
# 渲染函数（render_chart 等）也按客户端存放，维度切换时更新为当前面板的闭包。
_tc_client_states = {}       # client.id -> {'render_chart': fn, 'render_index_chart': fn}
_tc_listener_clients = set()  # 已注册过监听器的 client.id


def _tc_current_client_id():
    try:
        return ui.context.client.id
    except Exception:
        return None


def _register_tc_listeners():
    cid = _tc_current_client_id()
    if cid is None or cid in _tc_listener_clients:
        return
    _tc_listener_clients.add(cid)

    def _on_tc_row_click(e):
        try:
            state = _tc_client_states.get(cid) or {}
            industry = e.args.get('industry') if hasattr(e, 'args') else None
            fn = state.get('render_chart')
            if industry and fn:
                fn(industry, scroll=True)
        except Exception as ex:
            print(f'TradingCrowding row click error: {ex}')

    def _on_tc_index_click(e):
        try:
            state = _tc_client_states.get(cid) or {}
            code = e.args.get('code') if hasattr(e, 'args') else None
            fn = state.get('render_index_chart')
            if code and fn:
                fn(code)
        except Exception as ex:
            print(f'TradingCrowding index click error: {ex}')

    ui.on('tc_row_click', _on_tc_row_click)
    ui.on('tc_index_click', _on_tc_index_click)


def _set_tc_client_state(cid, render_chart, render_index_chart):
    if cid is not None:
        _tc_client_states[cid] = {
            'render_chart': render_chart,
            'render_index_chart': render_index_chart,
        }


def render_trading_content(plotly_renderer, is_mobile, dimension):
    """成交量 / 成交额维度：前5%个股成交集中度（行业排行 + 指数卡片）。"""
    _register_tc_listeners()
    tc = TradingCrowding()
    sc = SectorCrowding()  # 复用行业层级筛选
    metric = 'vol' if dimension == 'vol' else 'amount'
    metric_label = TRADING_DIM_LABELS[dimension]
    metric_col = f'{metric}_concentration_pct'
    top5_col = f'top5_{metric}'
    total_col = f'total_{metric}'
    # vol: 手 → 亿手；amount: 千元 → 亿元
    unit = 1e8 if metric == 'vol' else 1e5
    unit_label = '亿手' if metric == 'vol' else '亿'
    threshold = TRADING_THRESHOLD
    progress_state = {'running': False, 'done': 0, 'total': 0,
                      'cur': '', 'msg': ''}

    # ---------- 预计算：先加载数据再建 UI ----------
    # 若数据层出错，提前失败，避免留下引用了尚未定义函数的按钮等残缺 UI。
    pre = tc.precompute()
    pre_idx = tc.precompute_indices()

    # ---------- 指标说明卡片 ----------
    with ui.card().classes('w-full bg-white p-4 rounded-xl shadow-sm border border-gray-200'):
        with ui.row().classes('items-center gap-2 w-full'):
            ui.icon('donut_small', color='orange').classes('text-2xl')
            ui.label(f'{metric_label}拥挤度说明').classes('text-lg font-bold text-gray-800')
            ui.label('数据源：Tushare Pro（日行情 T+1 发布）').classes(
                'text-xs text-gray-400 ml-auto')
        with ui.row().classes('w-full gap-4 items-stretch flex-col md:flex-row mt-2'):
            with ui.card().classes(
                    'flex-1 p-3 bg-orange-50 rounded-lg border border-orange-100 shadow-none'):
                ui.label('计算公式').classes('font-bold text-gray-700 text-sm mb-1')
                ui.html(
                    f'<div class="text-xs text-orange-800 font-mono bg-white p-2 rounded '
                    f'border border-orange-100">前5%个股{metric_label}集中度 = '
                    f'前5%个股{metric_label}合计 ÷ 板块{metric_label}合计 × 100%</div>',
                    sanitize=False)
                ui.label(f'衡量{metric_label}在该板块的聚集程度，越高说明交易越拥挤。').classes(
                    'text-xs text-gray-500 mt-2 leading-tight')
            with ui.card().classes(
                    'flex-1 p-3 bg-blue-50 rounded-lg border border-blue-100 shadow-none'):
                ui.label('数据口径').classes('font-bold text-gray-700 text-sm mb-1')
                ui.label(f'统计角度：全A市场 / 行业板块 / 指数成分股；'
                         f'前5% = ceil(个股数×5%)；集中度高于 {threshold:.0f}% 标记为拥挤；'
                         f'个股数少于 {TRADING_MIN_STOCKS} 的行业样本过少，不参与标记。'
                         ).classes('text-xs text-gray-500 leading-tight')

    # ---------- 概览统计 ----------
    stats_container = ui.element('div').classes(
        'w-full grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mt-4')

    # ---------- 主区域：左侧行业表格 + 右侧趋势图 ----------
    with ui.row().classes('w-full gap-4 items-stretch mt-4 flex-col lg:flex-row'):
        with ui.column().classes('w-full lg:w-3/5 min-w-0'):
            table_card = ui.card().classes(
                'w-full bg-white p-4 rounded-xl shadow-sm border border-gray-200')
            with table_card:
                with ui.row().classes('items-center w-full mb-1 flex-wrap gap-2'):
                    ui.icon('view_list', color='orange').classes('text-xl')
                    ui.label(f'行业{metric_label}集中度排行').classes(
                        'font-bold text-gray-800 text-base')
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
                    ui.button(icon='close', on_click=lambda: reset_filter())\
                        .props('flat dense round size=sm').classes('text-gray-500')
                    ui.label('').classes('flex-1')
                table_meta = ui.label('').classes('text-xs text-gray-400 mb-2')
                table_container = ui.column().classes('w-full')

        # ===== 右侧：趋势图 =====
        with ui.column().classes('w-full lg:flex-1 min-w-0'):
            chart_card = ui.card().props('id=trading_crowding_chart_card').classes(
                'w-full bg-white p-4 rounded-xl shadow-sm border border-gray-200 h-full')
            with chart_card:
                chart_header = ui.row().classes('items-center gap-2 w-full mb-1 flex-wrap')
                with chart_header:
                    ui.icon('show_chart', color='orange').classes('text-xl')
                    ui.label(f'行业{metric_label}集中度趋势').classes(
                        'font-bold text-gray-800')
                    selected_chip = ui.chip('未选择', icon='touch_app',
                                            color='grey-3').props('dense outline')
                    selected_chip.classes('ml-1 text-xs')
                    chart_meta = ui.label('').classes('text-xs text-gray-400 ml-auto')
                chart_hint = ui.label(
                    '👈 点击左侧任一行业行查看历史趋势').classes(
                    'text-xs text-gray-400 mb-2')
                chart_container = ui.column().classes('w-full')

    # ---------- 指数集中度卡片（全宽） ----------
    with ui.card().classes(
            'w-full bg-white p-4 rounded-xl shadow-sm border border-gray-200 mt-4'):
        with ui.row().classes('items-center w-full mb-2 flex-wrap gap-2'):
            ui.icon('insights', color='orange').classes('text-xl')
            ui.label(f'全A与主要指数{metric_label}集中度').classes(
                'font-bold text-gray-800 text-base')
            ui.label('· 点击全A或指数查看趋势').classes('text-xs text-gray-400')
            ui.label('').classes('flex-1')
            index_chart_meta = ui.label('').classes('text-xs text-gray-500')
        with ui.row().classes('w-full gap-3 flex-col lg:flex-row'):
            with ui.column().classes('w-full lg:w-2/5 min-w-0'):
                index_cards_container = ui.element('div').classes(
                    'w-full grid grid-cols-2 md:grid-cols-3 lg:grid-cols-2 gap-2')
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

    def on_l1_change(value):
        filter_state['l1'] = value
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
        if pre['df'].empty:
            return pd.DataFrame()
        latest = pre['latest_df']
        filtered = sc.filter_industries_by_hierarchy(
            l1=filter_state['l1'],
            l2=filter_state['l2'],
            industries=latest['industry'].tolist(),
        )
        latest = latest[latest['industry'].isin(filtered)].copy()
        prev = pre['prev_df']
        rows = []
        for _, r in latest.iterrows():
            ind = r['industry']
            ser = pre['by_industry'].get(ind)
            series = ser[metric_col] if ser is not None else None
            raw_conc = r[metric_col]
            conc = float(raw_conc) if not pd.isna(raw_conc) else None
            rank = SectorCrowding.percentile_rank(series, conc)
            chg = None
            if conc is not None and ind in prev.index:
                prev_val = prev.loc[ind, metric_col]
                if not pd.isna(prev_val):
                    chg = conc - float(prev_val)
            rows.append({
                'industry': ind,
                'concentration': round(conc, 2) if conc is not None else None,
                'chg': round(chg, 2) if chg is not None else None,
                'rank': round(rank, 1) if rank is not None else None,
                'top5': (float(r[top5_col]) / unit
                         if not pd.isna(r[top5_col]) else None),
                'total': (float(r[total_col]) / unit
                          if not pd.isna(r[total_col]) else None),
                'stock_count': int(r['stock_count']),
                'tiny': int(r['stock_count']) < TRADING_MIN_STOCKS,
                'flag': (conc is not None and conc > threshold
                         and int(r['stock_count']) >= TRADING_MIN_STOCKS),
            })
        return pd.DataFrame(rows)

    # ---------- 渲染层：顶部统计卡 ----------
    def render_stats(display_df, latest_date):
        stats_container.clear()
        history_days = len(pre['dates'])
        if display_df.empty:
            return
        conc_series = pd.to_numeric(display_df['concentration'], errors='coerce')
        high_count = int(display_df['flag'].sum())
        max_conc = float(conc_series.max()) if not conc_series.dropna().empty else 0.0
        all_conc = None
        all_entry = pre_idx.get('ALL')
        if all_entry and all_entry[1] is not None and not all_entry[1].empty:
            all_val = all_entry[1].iloc[-1][metric_col]
            if not pd.isna(all_val):
                all_conc = float(all_val)
        idx_high = 0
        for code, (name, sdf) in pre_idx.items():
            if code == 'ALL' or sdf is None or sdf.empty:
                continue
            last_val = sdf.iloc[-1][metric_col]
            if not pd.isna(last_val) and float(last_val) > threshold:
                idx_high += 1
        all_flag = all_conc is not None and all_conc > threshold
        cards = [
            ('数据日期', str(latest_date), 'text-orange-700 bg-orange-50 border-orange-200'),
            ('行业数', f"{len(display_df)}", 'text-blue-700 bg-blue-50 border-blue-200'),
            (f'拥挤行业(>{threshold:.0f}%)', f"{high_count}",
             'text-red-700 bg-red-50 border-red-200'),
            ('全A集中度', f'{all_conc:.2f}%' if all_conc is not None else '—',
             ('text-red-700 bg-red-50 border-red-200' if all_flag
              else 'text-indigo-700 bg-indigo-50 border-indigo-200')),
            ('最高集中度', f"{max_conc:.2f}%",
             'text-indigo-700 bg-indigo-50 border-indigo-200'),
            ('指数拥挤数', f"{idx_high}", 'text-red-700 bg-red-50 border-red-200'),
            ('历史交易日', f"{history_days}",
             'text-gray-700 bg-gray-100 border-gray-200'),
        ]
        for label, value, cls in cards:
            with stats_container:
                with ui.element('div').classes(
                        f'p-3 rounded-lg border {cls} '
                        f'flex flex-col items-center justify-center text-center'):
                    ui.label(label).classes('text-[11px] text-gray-500')
                    ui.label(value).classes('text-lg font-bold')

    # ---------- 渲染层：只重渲染表格+统计 ----------
    def render_table_only():
        display_df = build_display()
        latest_date = pre['latest_date'].date() if pre['latest_date'] is not None else None
        render_stats(display_df, latest_date)
        first_industry = display_df.iloc[0]['industry'] if not display_df.empty else None
        render_table(display_df, selected_industry=first_industry)
        if first_industry:
            cur_selected = selected_chip.text
            if cur_selected != first_industry and cur_selected not in ('未选择', ''):
                render_chart(first_industry)
            elif cur_selected in ('未选择', ''):
                render_chart(first_industry)

    # ---------- 渲染层：行业集中度表格 ----------
    def render_table(display_df, selected_industry=None):
        table_container.clear()
        if display_df.empty:
            with table_container:
                with ui.column().classes('w-full items-center justify-center py-8 gap-3'):
                    ui.icon('inbox', size='48px').classes('text-gray-300')
                    ui.label('暂无成交集中度历史数据').classes('text-gray-500 font-bold')
                    ui.label('点击"重建三年历史"或运行脚本：').classes('text-xs text-gray-400')
                    ui.code('python scripts/build_trading_crowding_history.py',
                            language='bash').classes('text-xs')
            table_meta.text = '共 0 个行业'
            return

        tiny_count = int(display_df['tiny'].sum())
        tiny_note = (f'（{tiny_count} 个行业样本过少不参与拥挤标记）'
                     if tiny_count else '')
        table_meta.text = (f'共 {len(display_df)} 个行业，按{metric_label}集中度降序'
                           f'{tiny_note}')
        sorted_df = display_df.sort_values(
            'concentration', ascending=False).reset_index(drop=True)

        head_cells = [
            ('行业', 'text-left', '18%'),
            ('集中度', 'text-right', '16%'),
            ('1月变化', 'text-right', '11%'),
            ('3年分位', 'text-right', '9%'),
            (f'前5%成交({unit_label})', 'text-right', '13%'),
            (f'板块成交({unit_label})', 'text-right', '13%'),
            ('个股数', 'text-right', '7%'),
            ('标记', 'text-right', '13%'),
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
            conc = r['concentration']
            chg = r['chg']
            rank = r['rank']
            bg, fg, level = _tc_color(conc)
            chg_color = _chg_color(chg)
            rank_color = ('#b91c1c' if (rank is not None and rank >= 80)
                          else ('#ea580c' if (rank is not None and rank >= 60)
                                else '#374151'))
            if r['tiny']:
                bg, fg, level = ('#f3f4f6', '#6b7280', '样本少')
            is_sel = (r['industry'] == selected_industry)
            row_bg = '#fff7ed' if is_sel else '#ffffff'
            row_border = ('4px solid #ea580c' if is_sel
                          else '4px solid transparent')
            chg_str = f'{chg:+.2f}' if chg is not None else '—'
            rank_str = f'{rank:.0f}' if rank is not None else '—'
            chg_arrow = ('▲' if (chg is not None and chg > 0)
                         else ('▼' if (chg is not None and chg < 0) else '·'))
            conc_str = f'{conc:.2f}%' if conc is not None else '—'
            top5_str = f'{r["top5"]:,.1f}' if r['top5'] is not None else '—'
            total_str = f'{r["total"]:,.1f}' if r['total'] is not None else '—'
            if r['tiny']:
                flag_html = (
                    '<span style="color:#6b7280;background:#f3f4f6;padding:1px 8px;'
                    'border-radius:4px;font-size:10px;font-weight:600;'
                    'white-space:nowrap">样本少</span>'
                )
            elif r['flag']:
                flag_html = (
                    '<span style="color:#b91c1c;background:#fee2e2;padding:1px 8px;'
                    'border-radius:4px;font-size:10px;font-weight:700;'
                    'white-space:nowrap">⚠ 拥挤</span>'
                )
            else:
                flag_html = (
                    '<span style="color:#374151;background:#f3f4f6;padding:1px 8px;'
                    'border-radius:4px;font-size:10px;font-weight:600;'
                    'white-space:nowrap">正常</span>'
                )
            body_rows.append(
                f'<tr class="tc-row" data-industry="{r["industry"]}" '
                f'style="background:{row_bg};cursor:pointer;transition:background 0.15s;'
                f'border-left:{row_border};" '
                f'onclick="(function(tr){{var ind=tr.getAttribute(\'data-industry\');'
                f'var c=tr.closest(\'.q-card\');if(c){{c.querySelectorAll(\'tr.tc-row\')'
                f'.forEach(function(r){{r.style.background=\'#ffffff\';'
                f'r.style.borderLeft=\'4px solid transparent\';delete r.dataset.sel;}});}}'
                f'tr.style.background=\'#fff7ed\';tr.style.borderLeft=\'4px solid #ea580c\';'
                f'tr.dataset.sel=\'true\';'
                f'var e=(window.emitEvent||emitEvent);e(\'tc_row_click\',{{industry:ind}});'
                f'}})(this)" '
                f'onmouseover="if(!this.dataset.sel)this.style.background=\'#fff7ed\'" '
                f'onmouseout="if(!this.dataset.sel)this.style.background=\'#ffffff\'">'
                f'<td class="px-1.5 py-2 text-xs font-semibold text-gray-800 '
                f'border-b border-gray-100" style="white-space:nowrap;overflow:hidden;'
                f'text-overflow:ellipsis">{r["industry"]}</td>'
                f'<td class="px-1.5 py-2 border-b border-gray-100" '
                f'style="text-align:right;white-space:nowrap">'
                f'<div style="display:flex;align-items:center;justify-content:flex-end;gap:6px">'
                f'<span style="color:{fg};font-weight:700;font-size:13px">{conc_str}</span>'
                f'<span style="font-size:10px;color:{fg};background:{bg};padding:1px 6px;'
                f'border-radius:4px;white-space:nowrap">{level}</span></div>'
                f'{_tc_bar(conc)}</td>'
                f'<td class="px-1.5 py-2 text-xs border-b border-gray-100" '
                f'style="text-align:right;color:{chg_color};font-weight:600;'
                f'white-space:nowrap">{chg_arrow} {chg_str}</td>'
                f'<td class="px-1.5 py-2 text-xs border-b border-gray-100" '
                f'style="text-align:right;color:{rank_color};white-space:nowrap">'
                f'{rank_str}%</td>'
                f'<td class="px-1.5 py-2 text-xs text-gray-600 border-b border-gray-100" '
                f'style="text-align:right;white-space:nowrap">{top5_str}</td>'
                f'<td class="px-1.5 py-2 text-xs text-gray-500 border-b border-gray-100" '
                f'style="text-align:right;white-space:nowrap">{total_str}</td>'
                f'<td class="px-1.5 py-2 text-xs text-gray-500 border-b border-gray-100" '
                f'style="text-align:right;white-space:nowrap">{r["stock_count"]}</td>'
                f'<td class="px-1.5 py-2 border-b border-gray-100" '
                f'style="text-align:right;white-space:nowrap">{flag_html}</td>'
                f'</tr>'
            )

        table_html = (
            '<div class="tc-table-wrap" style="overflow:auto;max-height:560px;'
            'border-radius:8px;border:1px solid #e5e7eb;width:100%;display:block">'
            '<table style="border-collapse:collapse;width:100%;min-width:560px;'
            'table-layout:fixed">'
            f'<thead style="background:#fafafa;position:sticky;top:0;z-index:1">'
            f'{head_html}</thead>'
            f'<tbody>{"".join(body_rows)}</tbody>'
            '</table></div>'
            f'<div class="text-[10px] text-gray-400 mt-1">'
            f'💡 前5%个股{metric_label}集中度 = 板块内{metric_label}最大的前5%个股合计 '
            f'÷ 板块{metric_label}合计；集中度高于 {threshold:.0f}% 标记为拥挤'
            '</div>'
        )

        if selected_industry:
            table_html = table_html.replace(
                f'data-industry="{selected_industry}"',
                f'data-industry="{selected_industry}" data-sel="true"',
                1,
            )

        with table_container:
            ui.html(table_html, sanitize=False)

    # ---------- 渲染层：行业集中度趋势图 ----------
    def render_chart(industry, scroll=False):
        chart_container.clear()
        ser = pre['by_industry'].get(industry)
        if ser is None or ser.empty:
            with chart_container:
                ui.label(f'行业 {industry} 暂无数据').classes('text-gray-400')
            return

        try:
            latest_val = float(ser.iloc[-1][metric_col])
            latest_date = str(ser.iloc[-1]['trade_date'])
            chg_1m = None
            if len(ser) > 22:
                chg_1m = float(ser.iloc[-1][metric_col]) - float(
                    ser.iloc[-22][metric_col])
            selected_chip.text = f'{industry}'
            selected_chip.props('color=orange-7')
            chg_str = (f'  ·  1月 {chg_1m:+.2f}pp' if chg_1m is not None else '')
            chart_meta.text = f'最新 {latest_date}  {latest_val:.2f}%{chg_str}'
        except Exception:
            selected_chip.text = industry
        chart_hint.text = ''

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=ser['trade_date'], y=ser[metric_col],
            mode='lines', name=f'{metric_label}集中度%',
            line=dict(color='#ea580c', width=2.4),
            hovertemplate=(f'%{{x|%Y-%m-%d}}<br>'
                           f'{metric_label}集中度 %{{y:.2f}}%<extra></extra>'),
        ))

        vals = ser[metric_col].dropna()
        for q, color, label in ((0.2, '#10b981', 'P20'),
                                (0.5, '#f59e0b', 'P50'),
                                (0.8, '#ef4444', 'P80')):
            qv = float(vals.quantile(q))
            fig.add_hline(y=qv, line_dash='dot', line_color=color, line_width=1,
                          annotation_text=f'{label} {qv:.2f}%',
                          annotation_position='right')
        fig.add_hline(y=threshold, line_dash='dash', line_color='#b91c1c',
                      line_width=1.4,
                      annotation_text=f'拥挤阈值 {threshold:.0f}%',
                      annotation_position='top right')

        latest_val = float(ser.iloc[-1][metric_col])
        fig.add_trace(go.Scatter(
            x=[ser.iloc[-1]['trade_date']], y=[latest_val],
            mode='markers', showlegend=False,
            marker=dict(color='#7c3aed', size=11,
                        line=dict(color='white', width=2)),
            hovertemplate=(f'最新<br>{industry}<br>'
                           f'{metric_label}集中度 {latest_val:.2f}%<extra></extra>'),
        ))

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
                rangeslider=dict(visible=True, thickness=0.06,
                                 bgcolor='#fef3c7'),
                rangeselector=dict(
                    buttons=[
                        dict(count=1, label='1月', step='month',
                             stepmode='backward'),
                        dict(count=3, label='3月', step='month',
                             stepmode='backward'),
                        dict(count=6, label='6月', step='month',
                             stepmode='backward'),
                        dict(count=1, label='1年', step='year',
                             stepmode='backward'),
                        dict(count=3, label='3年', step='year',
                             stepmode='backward'),
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
                title=dict(text=f'前5%个股{metric_label}集中度 %',
                           font=dict(color='#ea580c', size=11)),
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
                    "document.getElementById('trading_crowding_chart_card')"
                    "?.scrollIntoView({behavior:'smooth', block:'start'});"
                )
            except Exception:
                pass

    # ---------- 渲染层：指数集中度卡片 ----------
    def render_index_cards():
        index_cards_container.clear()
        idx_latest = {}
        for code, (name, sdf) in pre_idx.items():
            if sdf is None or sdf.empty:
                continue
            last = sdf.iloc[-1]
            conc = (float(last[metric_col])
                    if not pd.isna(last[metric_col]) else None)
            idx_latest[code] = {
                'name': name,
                'date': str(last['trade_date'])[:10],
                'concentration': conc,
                'coverage': (float(last['coverage'])
                             if not pd.isna(last['coverage']) else 0.0),
                'stock_count': int(last['stock_count']),
                'df': sdf,
            }
        sorted_idx = sorted(
            idx_latest.items(),
            key=lambda x: -(x[1]['concentration'] or 0))
        # 全A 置顶，独立高亮
        if 'ALL' in idx_latest:
            sorted_idx.insert(0, ('ALL', idx_latest['ALL']))
        selected_code = [None]

        for code, info in sorted_idx:
            conc = info['concentration']
            flag = conc is not None and conc > threshold
            is_all = (code == 'ALL')
            bg, fg, level = _tc_color(conc)
            cov = info['coverage']
            click_js = (
                f"(function(el){{var cards=el.parentElement.parentElement."
                f"querySelectorAll('[data-idx-code]');"
                f"cards.forEach(function(c){{c.style.background='#ffffff';"
                f"c.style.borderColor='#e5e7eb';}});"
                f"el.style.background='#fff7ed';el.style.borderColor='#ea580c';"
                f"var e=(window.emitEvent||emitEvent);"
                f"e('tc_index_click',{{code:'{code}'}});}})(this)"
            )
            card_cls = (
                'p-2.5 rounded-lg border-2 border-indigo-300 cursor-pointer '
                'hover:shadow-md transition-all bg-indigo-50/60'
                if is_all else
                'p-2.5 rounded-lg border border-gray-200 cursor-pointer '
                'hover:shadow-md transition-all bg-white'
            )
            with index_cards_container:
                with ui.element('div').classes(
                        card_cls
                ).props(f'data-idx-code={code} onclick="{click_js}"'):
                    with ui.row().classes('items-center justify-between gap-1'):
                        ui.label(info['name']).classes(
                            'font-bold text-sm text-gray-800')
                        if is_all:
                            ui.badge('⚠ 全A' if flag else '全A',
                                     color='red-7' if flag else 'indigo-7')\
                                .props('outline dense')
                        elif flag:
                            ui.badge('⚠ 拥挤', color='red-7').props('outline dense')
                        else:
                            ui.badge(level, color=(
                                'orange-7' if conc is not None and conc >= 30
                                else 'grey-6')).props('outline dense')
                    with ui.row().classes('items-end justify-between gap-1 mt-1'):
                        with ui.column().classes('gap-0'):
                            ui.label(f'{metric_label}集中度').classes(
                                'text-[10px] text-gray-500')
                            ui.label(f'{conc:.2f}%' if conc is not None else '—')\
                                .classes('text-base font-bold').style(f'color:{fg}')
                        with ui.column().classes('gap-0 items-end'):
                            ui.label('覆盖').classes('text-[10px] text-gray-500')
                            ui.label(f'{cov:.0f}%').classes('text-xs text-gray-600')
                    with ui.row().classes('items-end justify-between gap-1 mt-1'):
                        with ui.column().classes('gap-0'):
                            ui.label('个股数').classes('text-[10px] text-gray-500')
                            ui.label(f'{info["stock_count"]}').classes(
                                'text-xs font-semibold text-gray-700')
                        with ui.column().classes('gap-0 items-end'):
                            ui.label(info['date']).classes(
                                'text-[10px] text-gray-400 mt-0.5')

        if sorted_idx:
            selected_code[0] = sorted_idx[0][0]
            render_index_chart(selected_code[0])
            try:
                ui.run_javascript(f'''
                    (function(){{
                        const c = document.querySelector(
                            '[data-idx-code="{selected_code[0]}"]');
                        if (c) {{ c.style.background='#fff7ed';
                                 c.style.borderColor='#ea580c'; }}
                    }})();
                ''')
            except Exception:
                pass

    # ---------- 渲染层：指数集中度趋势图 ----------
    def render_index_chart(code):
        index_chart_container.clear()
        entry = pre_idx.get(code)
        if not entry:
            return
        name, df = entry
        if df is None or df.empty:
            with index_chart_container:
                ui.label('该指数暂无数据').classes('text-gray-400 text-sm p-4')
            return
        last = df.iloc[-1]
        conc = float(last[metric_col]) if not pd.isna(last[metric_col]) else None
        if conc is None:
            index_chart_meta.text = f'{name}  ·  暂无数据'
        else:
            index_chart_meta.text = (
                f"{name}  ·  最新 {str(last['trade_date'])[:10]}  ·  "
                f"{metric_label}集中度 {conc:.2f}%"
            )
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df['trade_date'], y=df[metric_col],
            mode='lines', name=f'{metric_label}集中度%',
            line=dict(color='#ea580c', width=2.2),
            hovertemplate=(f'%{{x|%Y-%m-%d}}<br>'
                           f'{metric_label}集中度 %{{y:.2f}}%<extra></extra>'),
        ))
        fig.add_hline(y=threshold, line_dash='dash', line_color='#b91c1c',
                      line_width=1.3,
                      annotation_text=f'拥挤阈值 {threshold:.0f}%',
                      annotation_position='right')
        if conc is not None:
            fig.add_trace(go.Scatter(
                x=[df.iloc[-1]['trade_date']], y=[conc],
                mode='markers', showlegend=False,
                marker=dict(color='#7c3aed', size=10,
                            line=dict(color='white', width=2)),
                hovertemplate=f'最新 {conc:.2f}%<extra></extra>',
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
                rangeslider=dict(visible=True, thickness=0.08,
                                 bgcolor='#fef3c7'),
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

    # ---------- 入口 ----------
    def load_view():
        tc.invalidate_history_cache()
        pre.clear()
        pre.update(tc.precompute())
        pre_idx.clear()
        pre_idx.update(tc.precompute_indices())
        display_df = build_display()
        latest_date = pre['latest_date'].date() if pre['latest_date'] is not None else None
        render_stats(display_df, latest_date)
        first_industry = display_df.iloc[0]['industry'] if not display_df.empty else None
        render_table(display_df, selected_industry=first_industry)
        if first_industry:
            render_chart(first_industry)
        try:
            render_index_cards()
        except Exception as ex:
            print(f'TradingCrowding render_index_cards error: {ex}')

    def run_build(max_days=None):
        return tc.build_history(max_days=max_days, resume=True,
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
                ui.notify(f'{metric_label}拥挤度已更新', type='positive')
            except RuntimeError:
                pass
        except RuntimeError:
            pass
        except Exception as e:
            print(f'TradingCrowding update error: {e}')
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
                return tc.build_history(
                    resume=True,
                    progress_cb=lambda d, t, c, l:
                    progress_state.update(done=d, total=t, cur=c),
                )

            added = await loop.run_in_executor(None, monitor)
            progress_state.update(done=0, total=0)
            status_label.text = f'重建完成（本次新增 {added} 个交易日）'
            load_view()
            try:
                ui.notify(f'{metric_label}拥挤度历史已就绪', type='positive')
            except RuntimeError:
                pass
        except RuntimeError:
            pass
        except Exception as e:
            print(f'TradingCrowding rebuild error: {e}')
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

    # 让本客户端的事件处理器能访问当前面板的渲染函数
    _set_tc_client_state(_tc_current_client_id(), render_chart,
                         render_index_chart)
    load_view()


# ============ 主面板：维度切换（两融 / 成交量 / 成交额） ============

def render_sector_crowding_panel(plotly_renderer, is_mobile=False):
    """板块拥挤度面板入口：顶部维度切换。"""
    _register_tc_listeners()
    with ui.column().classes('w-full gap-3'):
        with ui.card().classes(
                'w-full bg-white px-4 py-2 rounded-xl shadow-sm border border-gray-200'):
            with ui.row().classes('items-center gap-2 w-full flex-wrap'):
                ui.icon('local_fire_department', color='orange').classes('text-xl')
                ui.label('拥挤度维度').classes('font-bold text-gray-800 text-sm')
                ui.label('两融数据 / 成交量 / 成交额（前5%成交集中度）').classes(
                    'text-xs text-gray-400')
                ui.label('').classes('flex-1')
                dim_toggle = ui.toggle(
                    {'margin': '两融数据', 'vol': '成交量', 'amount': '成交额'},
                    value='margin',
                    on_change=lambda e: switch_dim(e.value),
                ).props('dense no-caps unelevated rounded color=grey-4 '
                        'toggle-color=orange-7 text-color=grey-8')

        margin_box = ui.element('div').classes('w-full')
        trading_box = ui.element('div').classes('w-full')
        with margin_box:
            render_margin_content(plotly_renderer, is_mobile)
        trading_box.set_visibility(False)

    def switch_dim(dim):
        margin_box.set_visibility(dim == 'margin')
        if dim == 'margin':
            trading_box.set_visibility(False)
            return
        try:
            trading_box.clear()
            with trading_box:
                render_trading_content(plotly_renderer, is_mobile, dim)
            trading_box.set_visibility(True)
        except Exception as ex:
            print(f'TradingCrowding panel render error: {ex}')
            try:
                ui.notify(f'成交集中度数据加载失败：{ex}', type='negative')
            except RuntimeError:
                pass
