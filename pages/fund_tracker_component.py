"""基金 / ETF 订阅跟踪视图层

入口：render_fund_tracker_panel(plotly_renderer, is_mobile)

交互：
- 用户通过搜索添加基金/ETF（支持代码/名称/管理人模糊搜索）
- 添加时自动从 Tushare fund_basic 读取对标指数（index_code / index_name），
  也允许用户手动覆盖
- 订阅信息持久化到浏览器 localStorage（key: fund_subscriptions）
- 顶部展示 4 大指数多周期涨跌幅（横向对比）
- 中部展示用户订阅的基金 vs 对标指数（超额收益）对比表
"""

from nicegui import ui
import json
import asyncio
import datetime
from concurrent.futures import ThreadPoolExecutor

from utils.fund_tracker import FundTracker

executor = ThreadPoolExecutor(max_workers=2)

# localStorage 键名（与 money_flow_component 风格一致）
LS_KEY_SUBS = 'fund_subscriptions_v1'

# 主题色
PRIMARY = '#6366f1'  # indigo-500
PRIMARY_DARK = '#4338ca'
SUCCESS = '#10b981'
DANGER = '#ef4444'
WARNING = '#f59e0b'
MUTED = '#94a3b8'


def render_fund_tracker_panel(plotly_renderer=None, is_mobile=False):
    """基金 / ETF 订阅跟踪面板"""
    plot_func = plotly_renderer if plotly_renderer else ui.plotly
    tracker = FundTracker()

    # 捕获当前 client，供后续异步 task 通过 client.run_javascript 发送 JS
    # （ui.context.client 在 asyncio.create_task 派生的协程里会丢失上下文）
    try:
        page_client = ui.context.client
    except RuntimeError:
        page_client = None

    # ── 视图状态 ─────────────────────────────────────
    state = {
        'subs': [],                # [{ts_code, name, index_code, index_name, added_at}]
        'period': '1d',            # 当前对比周期：1d / 5d / 20d / 60d / ytd
        'search_keyword': '',
        'search_results': [],
        'searching': False,
        'loading_perf': False,
        'perf_data': None,         # 最新一次 get_subs_performance 结果
        'auto_reload_after_add': True,
        'fund_overrides': {},      # {ts_code: [{date: 'YYYY-MM-DD', close: float, pct_chg: float}, ...]}
                                  # 由浏览器 fetch 天天基金后回填，绕过服务端
    }

    # ── UI 容器引用 ──────────────────────────────────
    search_input = None
    search_results_container = None
    sub_list_container = None
    perf_container = None
    index_compare_container = None
    refresh_btn = None
    add_dialog = None
    add_dialog_body = None
    period_buttons = {}

    # ── localStorage 读写 ───────────────────────────────

    def save_subs():
        js_val = json.dumps(state['subs'], ensure_ascii=False)
        ui.run_javascript(f'localStorage.setItem({json.dumps(LS_KEY_SUBS)}, {json.dumps(js_val)})')

    async def load_subs_from_browser():
        try:
            data_str = await ui.run_javascript(
                f'return localStorage.getItem({json.dumps(LS_KEY_SUBS)})', timeout=8.0
            )
            if data_str:
                loaded = json.loads(data_str)
                if isinstance(loaded, list):
                    state['subs'] = loaded
        except Exception as e:
            print(f'[FundTracker] load subs error: {e}')

    # ── 浏览器端天天基金 fetch（带 localStorage 缓存 1 小时） ─────────
    # 用浏览器 fetch 同源代理 /api/fund_eastmoney/{code}，避免 CORS
    # 返回 [{date: 'YYYY-MM-DD', close: float, pct_chg: float}, ...]

    # ── 操作：添加基金 ───────────────────────────────

    def add_sub(rec: dict, override_index_code: str = '', override_index_name: str = ''):
        """rec 来自 search_results 单条记录（dict）。override_* 用于用户在添加对话框里手动改对标指数。"""
        ts_code = rec.get('ts_code', '')
        if not ts_code:
            ui.notify('基金代码无效', type='negative')
            return False, '基金代码无效'
        if any(s.get('ts_code') == ts_code for s in state['subs']):
            return False, '已订阅该基金'

        # 优先用 Tushare 自带的对标指数，缺失时使用用户填的
        idx_code = (rec.get('index_code') or override_index_code or '').strip()
        idx_name = (rec.get('index_name') or override_index_name or '').strip()
        sub = {
            'ts_code': ts_code,
            'name': (rec.get('name') or ts_code).strip(),
            'index_code': idx_code,
            'index_name': idx_name,
            'management': (rec.get('management') or '').strip(),
            'fund_type': (rec.get('fund_type') or '').strip(),
            'added_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        state['subs'].append(sub)
        save_subs()
        refresh_sub_list()
        return True, '已添加'

    def remove_sub(ts_code: str):
        state['subs'] = [s for s in state['subs'] if s.get('ts_code') != ts_code]
        save_subs()
        refresh_sub_list()
        # 删除后无需立刻刷新表现（用户可能还要继续删），由用户主动刷新

    # ── 搜索 ─────────────────────────────────────

    async def do_search():
        kw = state['search_keyword'].strip()
        if not kw:
            state['search_results'] = []
            render_search_results()
            return
        state['searching'] = True
        render_search_results()
        loop = asyncio.get_running_loop()
        try:
            results = await loop.run_in_executor(executor, lambda: tracker.search_funds(kw, limit=30))
            state['search_results'] = results or []
        except Exception as e:
            state['search_results'] = []
            ui.notify(f'搜索失败: {e}', type='negative')
        state['searching'] = False
        render_search_results()

    def render_search_results():
        if search_results_container is None:
            return
        search_results_container.clear()
        with search_results_container:
            if state['searching']:
                with ui.row().classes('w-full items-center gap-2 p-3'):
                    ui.spinner('dots', size='sm', color='indigo')
                    ui.label('正在搜索…').classes('text-xs text-gray-500')
                return
            results = state['search_results']
            if not results and state['search_keyword']:
                ui.label('未找到匹配的基金 / ETF').classes('text-xs text-gray-400 px-3 py-2')
                return
            if not results:
                return

            with ui.column().classes('w-full gap-1 max-h-72 overflow-y-auto'):
                for rec in results:
                    render_search_row(rec)

    def render_search_row(rec: dict):
        """渲染一条搜索结果行。点击「添加」按钮弹出添加对话框。"""
        ts_code = rec.get('ts_code', '')
        name = (rec.get('name') or '').strip() or ts_code
        mgmt = (rec.get('management') or '').strip()
        idx_code = (rec.get('index_code') or '').strip()
        idx_name = (rec.get('index_name') or '').strip()
        fund_type = (rec.get('fund_type') or '').strip()

        is_added = any(s.get('ts_code') == ts_code for s in state['subs'])

        with ui.row().classes(
            'w-full items-center justify-between px-3 py-2 rounded-md '
            'hover:bg-indigo-50 transition-colors border border-transparent '
            'hover:border-indigo-100'
        ):
            with ui.column().classes('gap-0 flex-1 min-w-0'):
                with ui.row().classes('items-center gap-2'):
                    ui.label(name).classes('text-sm font-semibold text-gray-800 truncate')
                    if fund_type:
                        ui.chip(fund_type, color='indigo').props('dense outline square').classes('text-[10px]')
                with ui.row().classes('items-center gap-2 text-[11px] text-gray-500'):
                    ui.label(ts_code).classes('font-mono text-[11px] text-gray-500')
                    if mgmt:
                        ui.label('·').classes('text-gray-300')
                        ui.label(mgmt).classes('truncate max-w-32')
                    if idx_code:
                        ui.label('·').classes('text-gray-300')
                        ui.label(f'对标: {idx_name or idx_code}').classes('text-indigo-600 truncate max-w-40')
            if is_added:
                ui.chip('已订阅', icon='check', color='positive').props('dense square')
            else:
                ui.button('添加', icon='add',
                          on_click=lambda r=dict(rec): open_add_dialog(r)) \
                    .props('dense unelevated color=indigo').classes('text-xs')

    # ── 添加对话框（对标指数：下拉选择 + 自定义） ────────

    # 对标指数可选项：4 大指数 + 「无对标」+ 「自定义」
    _INDEX_OPTIONS = [
        {'value': '',           'label': '无对标指数（仅追踪基金自身）',  'ts_code': '',         'name': ''},
        {'value': '000001.SH',  'label': '上证指数 (000001.SH)',         'ts_code': '000001.SH','name': '上证指数'},
        {'value': '399001.SZ',  'label': '深证成指 (399001.SZ)',         'ts_code': '399001.SZ','name': '深证成指'},
        {'value': '399006.SZ',  'label': '创业板指数 (399006.SZ)',       'ts_code': '399006.SZ','name': '创业板指数'},
        {'value': '000688.SH',  'label': '科创50 (000688.SH)',           'ts_code': '000688.SH','name': '科创50'},
        {'value': '__custom__', 'label': '自定义指数…',                  'ts_code': '',         'name': ''},
    ]
    _INDEX_VALUE_TO_OPT = {o['value']: o for o in _INDEX_OPTIONS}

    def _resolve_index_selection(selected_value: str, custom_code: str, custom_name: str) -> tuple[str, str]:
        """根据下拉值解析出最终 (code, name)。"""
        if selected_value == '__custom__':
            return (custom_code.strip(), custom_name.strip())
        opt = _INDEX_VALUE_TO_OPT.get(selected_value)
        if opt is None:
            return ('', '')
        return (opt['ts_code'], opt['name'])

    def open_add_dialog(rec: dict):
        nonlocal add_dialog_body
        if add_dialog is None:
            return
        add_dialog.clear()
        with add_dialog, ui.card().classes('w-[480px] max-w-[95vw] p-0 rounded-xl overflow-hidden'):
            # 标题栏
            with ui.row().classes('w-full items-center gap-2 px-5 py-3 bg-indigo-50 border-b border-indigo-100'):
                ui.icon('add_circle', color='indigo').classes('text-xl')
                ui.label('添加订阅').classes('text-base font-bold text-indigo-700')

            add_dialog_body = ui.column().classes('w-full p-5 gap-3')

            with add_dialog_body:
                ui.label(rec.get('name') or rec.get('ts_code', '')).classes('text-lg font-bold text-gray-800')
                ui.label(rec.get('ts_code', '')).classes('text-xs font-mono text-gray-500')

                # 默认值：优先用 Tushare 自带的对标指数；若不在下拉列表中，自动落到「自定义」并预填
                pre_value = (rec.get('index_code') or '').strip()
                pre_name = (rec.get('index_name') or '').strip()
                initial_value = pre_value if pre_value in _INDEX_VALUE_TO_OPT and pre_value != '' else '__custom__' if pre_value else ''
                custom_code_input = None
                custom_name_input = None
                custom_row = None

                index_select = ui.select(
                    options={o['value']: o['label'] for o in _INDEX_OPTIONS},
                    value=initial_value,
                    label='对标指数',
                ).props('outlined dense').classes('w-full')

                def _toggle_custom():
                    show = (index_select.value == '__custom__')
                    if custom_row is not None:
                        custom_row.classes('w-full' if show else 'w-full hidden', remove='w-full hidden' if show else 'w-full')

                index_select.on('update:model-value', lambda e: _toggle_custom())

                # 自定义指数输入区（默认隐藏）
                with ui.column().classes('w-full gap-2') as custom_row:
                    custom_code_input = ui.input(
                        label='自定义指数代码',
                        value=pre_value if initial_value == '__custom__' else '',
                        placeholder='如 000300.SH / 399006.SZ'
                    ).props('outlined dense').classes('w-full')
                    custom_name_input = ui.input(
                        label='自定义指数名称',
                        value=pre_name if initial_value == '__custom__' else '',
                        placeholder='如 沪深300 / 创业板指'
                    ).props('outlined dense').classes('w-full')

                # 初始可见性
                if initial_value != '__custom__':
                    if custom_row is not None:
                        custom_row.classes('w-full hidden', remove='w-full')

                with ui.row().classes('w-full justify-end gap-2 mt-2'):
                    ui.button('取消', on_click=lambda: add_dialog.close()).props('flat color=grey')
                    ui.button('确认添加', icon='check',
                              on_click=lambda: do_confirm_add(
                                  rec,
                                  * _resolve_index_selection(
                                      index_select.value or '',
                                      custom_code_input.value if custom_code_input else '',
                                      custom_name_input.value if custom_name_input else '',
                                  )
                              )).props('unelevated color=indigo')
        # 渲染完表单再打开 dialog（NiceGUI 必须在内容就绪后 open）
        add_dialog.open()

    def do_confirm_add(rec: dict, override_code: str, override_name: str):
        ok, msg = add_sub(rec, override_index_code=override_code, override_index_name=override_name)
        if ok:
            ui.notify(msg, type='positive')
            if add_dialog:
                add_dialog.close()
            # 自动刷新表现数据 + 规模双因子总览
            if state['auto_reload_after_add']:
                asyncio.create_task(refresh_performance())
                asyncio.create_task(refresh_scale_overview())
        else:
            ui.notify(msg, type='warning')

    # ── 订阅列表 ─────────────────────────────────

    def refresh_sub_list():
        if sub_list_container is None:
            return
        sub_list_container.clear()
        with sub_list_container:
            if not state['subs']:
                with ui.column().classes('w-full items-center justify-center py-8 gap-2'):
                    ui.icon('inbox', size='40px', color='grey-4')
                    ui.label('暂无订阅').classes('text-sm text-gray-400')
                    ui.label('在上方搜索框输入代码或名称来添加').classes('text-xs text-gray-400')
                return
            with ui.column().classes('w-full gap-2 max-h-[480px] overflow-y-auto'):
                for sub in state['subs']:
                    render_sub_row(sub)

    def render_sub_row(sub: dict):
        with ui.row().classes(
            'w-full items-center justify-between px-3 py-2 rounded-md '
            'bg-white border border-gray-100 hover:border-indigo-200 hover:shadow-sm '
            'transition-all'
        ):
            with ui.column().classes('gap-0 flex-1 min-w-0'):
                with ui.row().classes('items-center gap-2'):
                    ui.label(sub.get('name') or sub.get('ts_code', '')).classes(
                        'text-sm font-semibold text-gray-800 truncate'
                    )
                with ui.row().classes('items-center gap-2 text-[11px] text-gray-500'):
                    ui.label(sub.get('ts_code', '')).classes('font-mono')
                    if sub.get('index_code'):
                        ui.label('·').classes('text-gray-300')
                        ui.label(f'对标: {sub.get("index_name") or sub.get("index_code")}').classes(
                            'text-indigo-600 truncate max-w-44'
                        )
            with ui.row().classes('items-center gap-1'):
                ui.button('规模', icon='donut_small',
                          on_click=lambda s=dict(sub): open_scale_dialog(s)) \
                    .props('flat dense no-caps color=indigo').classes('text-xs')
                ui.button(icon='delete_outline',
                          on_click=lambda c=sub.get('ts_code'): remove_sub(c)) \
                    .props('flat dense round color=grey').classes('text-gray-400 hover:text-red-500')

    # ── 规模变动双因子分析（季度） ───────────────────

    def _chg_chip(value, classes: str = ''):
        """统一渲染双因子涨跌 chip：正绿负红，None 灰。"""
        if value is None:
            ui.label('—').classes(f'{classes} text-gray-400')
            return
        try:
            v = float(value)
        except (TypeError, ValueError):
            ui.label('—').classes(f'{classes} text-gray-400')
            return
        if v > 0:
            cls, prefix = 'text-emerald-600', '+'
        elif v < 0:
            cls, prefix = 'text-rose-600', ''
        else:
            cls, prefix = 'text-gray-500', ''
        ui.label(f'{prefix}{v:.2f}%').classes(f'{classes} {cls}')

    def _flow_chip(value_yi: float, classes: str = ''):
        """渲染净申赎（亿份）chip：净申购绿色 / 净赎回红色。"""
        if value_yi is None:
            ui.label('—').classes(f'{classes} text-gray-400')
            return
        v = float(value_yi)
        if v > 0:
            cls, fmt = 'text-emerald-600', f'+{v:.2f}亿份'
        elif v < 0:
            cls, fmt = 'text-rose-600', f'-{abs(v):.2f}亿份'
        else:
            cls, fmt = 'text-gray-500', '0.00亿份'
        ui.label(fmt).classes(f'{classes} {cls}')

    def _fmt_yi(v) -> str:
        """份 → 亿份（2位小数）字符串。"""
        try:
            return f'{float(v) / 1e8:.2f}'
        except (TypeError, ValueError):
            return '—'

    scale_dialog = None
    scale_dialog_body = None

    def open_scale_dialog(sub: dict):
        """打开单只基金的季度规模变动 + 双因子分解对话框。"""
        nonlocal scale_dialog, scale_dialog_body
        if scale_dialog is None:
            scale_dialog = ui.dialog().classes('items-center')
            scale_dialog_body = ui.column().classes('w-full')

        name = sub.get('name') or sub.get('ts_code', '')
        ts_code = sub.get('ts_code', '')
        scale_dialog.clear()
        with scale_dialog, ui.card().classes('w-[820px] max-w-[96vw] p-0 rounded-xl overflow-hidden'):
            # 标题栏
            with ui.row().classes('w-full items-center justify-between px-5 py-3 bg-indigo-50 border-b border-indigo-100'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('donut_small', color='indigo').classes('text-xl')
                    with ui.column().classes('gap-0'):
                        ui.label(f'规模变动 · {name}').classes('text-base font-bold text-indigo-800')
                        ui.label(
                            f'{ts_code}  ·  数据源: 天天基金 fundf10 季度 gmbd  ·  '
                            '双因子 = 基金涨跌（净值） + 散户申赎（份额）'
                        ).classes('text-[10px] text-indigo-400 font-mono')
                ui.button(icon='close', on_click=lambda: scale_dialog.close()) \
                    .props('flat round dense color=grey').classes('text-gray-400')
            scale_dialog_body = ui.column().classes('w-full p-5 gap-4 items-center')
            with scale_dialog_body:
                ui.spinner('dots', size='md', color='indigo')
                ui.label('正在拉取季度规模数据…').classes('text-xs text-gray-400')
        scale_dialog.open()

        async def _load_and_render():
            loop = asyncio.get_running_loop()
            try:
                data = await loop.run_in_executor(
                    executor, tracker.get_fund_scale_change, ts_code
                )
            except Exception as e:
                ui.notify(f'规模数据拉取失败: {e}', type='negative')
                data = {'as_of': None, 'quarters': [], 'error': str(e)}
            if not scale_dialog or not scale_dialog_body:
                return
            scale_dialog_body.clear()
            with scale_dialog_body:
                quarters = data.get('quarters') or []
                if data.get('error') and not quarters:
                    ui.icon('error_outline', color='negative').classes('text-3xl')
                    ui.label(f'拉取失败: {data.get("error")}').classes('text-sm text-rose-500')
                    return
                if not quarters:
                    ui.icon('info', color='grey').classes('text-3xl')
                    ui.label('该基金暂无季度规模数据（可能成立时间太短）').classes(
                        'text-sm text-gray-400'
                    )
                    return

                # ── 最新一期双因子摘要卡 ──
                latest = quarters[0]
                prev = quarters[1] if len(quarters) > 1 else None
                with ui.card().classes('w-full p-4 rounded-xl border border-indigo-100 bg-indigo-50/50'):
                    with ui.row().classes('w-full items-center justify-between mb-3 flex-wrap gap-2'):
                        with ui.row().classes('items-center gap-2'):
                            ui.label(f'最新一期（{latest["date"]}）规模双因子分解').classes(
                                'text-sm font-bold text-indigo-900'
                            )
                        ui.label(f'截至 {data.get("as_of")}').classes('text-[10px] text-gray-400 font-mono')
                    with ui.grid(columns=3).classes('w-full gap-3'):
                        # 净资产总变化（结果）
                        with ui.column().classes('items-center p-3 rounded-lg bg-white border border-indigo-50 gap-1'):
                            ui.label('净资产变动（结果）').classes('text-[10px] text-gray-500')
                            _chg_chip(latest.get('cap_chg'), 'text-xl font-bold')
                            ui.label(f'{_fmt_yi(latest.get("end_nav_cap"))} 亿元').classes(
                                'text-[11px] text-gray-500 font-mono'
                            )
                        # 因子1：基金本身涨跌（净值）
                        with ui.column().classes('items-center p-3 rounded-lg bg-white border border-amber-100 gap-1'):
                            ui.label('📈 基金本身涨跌（净值因子）').classes('text-[10px] text-amber-700')
                            # 优先用真实累计净值涨跌（含分红再投资，排除分红失真）；缺时回退公式反推
                            nav_disp = latest.get('real_nav_chg')
                            _chg_chip(nav_disp if nav_disp is not None else latest.get('nav_chg'), 'text-xl font-bold')
                            nu = latest.get('real_unit_nav')
                            na = latest.get('real_ac_nav')
                            if nu is not None and na is not None:
                                nav_note = f'季末单位 {nu:.4f}｜累计 {na:.4f}'
                            else:
                                nav_note = '排除申赎后的净值变化（推算）'
                            ui.label(nav_note).classes('text-[10px] text-gray-400 font-mono')
                        # 因子2：散户申赎（份额）
                        with ui.column().classes('items-center p-3 rounded-lg bg-white border border-emerald-100 gap-1'):
                            ui.label('👥 散户申赎（份额因子）').classes('text-[10px] text-emerald-700')
                            _chg_chip(latest.get('shares_chg'), 'text-xl font-bold')
                            nf = latest.get('net_flow')
                            nf_disp = None if nf is None else nf / 1e8
                            _flow_chip(nf_disp, 'text-[11px] font-mono')
                    if prev:
                        with ui.row().classes('w-full items-center gap-1 mt-2'):
                            ui.icon('lightbulb', size='xs', color='amber-6')
                            ui.label(
                                f'解读：规模变化 ≈ (1+份额变动)×(1+净值变动)-1 → '
                                f'上期末份额 {_fmt_yi(prev.get("end_shares"))} 亿份'
                            ).classes('text-[10px] text-gray-400')

                # ── 历史季度明细表 ──
                with ui.element('div').classes('w-full overflow-x-auto rounded-lg border border-gray-200 bg-white'):
                    with ui.element('table').classes('w-full text-sm'):
                        with ui.element('thead').classes('bg-gray-50 text-gray-600'):
                            with ui.element('tr'):
                                for h in ['季度末', '申购(亿份)', '赎回(亿份)', '净申赎(亿份)',
                                          '期末份额(亿份)', '份额变动↓', '净值变动↓', '季末单位净值', '季末累计净值',
                                          '净资产变动', '期末净资产(亿)']:
                                    with ui.element('th').classes(
                                        'px-3 py-2 text-left font-semibold text-xs whitespace-nowrap'
                                    ):
                                        ui.label(h)
                        with ui.element('tbody'):
                            for q in quarters:
                                nf_yi = None if q.get('net_flow') is None else q['net_flow'] / 1e8
                                with ui.element('tr').classes(
                                    'border-t border-gray-100 hover:bg-indigo-50/40'
                                    + (' bg-indigo-50/60' if q is latest else '')
                                ):
                                    with ui.element('td').classes(
                                        'px-3 py-2 font-mono text-xs text-gray-700 whitespace-nowrap'
                                    ):
                                        ui.label(q.get('date', ''))
                                    with ui.element('td').classes('px-3 py-2 font-mono text-xs text-gray-600'):
                                        ui.label(_fmt_yi(q.get('sub_scribe')))
                                    with ui.element('td').classes('px-3 py-2 font-mono text-xs text-gray-600'):
                                        ui.label(_fmt_yi(q.get('redeem')))
                                    with ui.element('td').classes('px-3 py-2'):
                                        _flow_chip(nf_yi, 'text-xs font-mono font-semibold')
                                    with ui.element('td').classes('px-3 py-2 font-mono text-xs text-gray-700'):
                                        ui.label(_fmt_yi(q.get('end_shares')))
                                    with ui.element('td').classes('px-3 py-2'):
                                        if q is latest:
                                            with ui.row().classes('items-center gap-1'):
                                                _chg_chip(q.get('shares_chg'), 'text-xs font-mono font-semibold')
                                                ui.chip('散户因子', color='emerald').props(
                                                    'dense outline square'
                                                ).classes('text-[9px]')
                                        else:
                                            _chg_chip(q.get('shares_chg'), 'text-xs font-mono font-semibold')
                                    with ui.element('td').classes('px-3 py-2'):
                                        if q is latest:
                                            with ui.row().classes('items-center gap-1'):
                                                _chg_chip(q.get('nav_chg'), 'text-xs font-mono font-semibold')
                                                ui.chip('涨跌因子', color='amber').props(
                                                    'dense outline square'
                                                ).classes('text-[9px]')
                                        else:
                                            _chg_chip(q.get('nav_chg'), 'text-xs font-mono font-semibold')
                                    # 季末真实净值记录（单位净值 + 累计净值，以及真实涨跌）
                                    with ui.element('td').classes('px-3 py-2 whitespace-nowrap'):
                                        with ui.column().classes('gap-0'):
                                            if q.get('real_unit_nav') is not None:
                                                _chg_chip_q = None  # noop 占位
                                                ui.label(f"{q['real_unit_nav']:.4f}").classes(
                                                    'font-mono text-xs text-gray-700'
                                                )
                                                if q.get('real_unit_nav_chg') is not None:
                                                    _chg_chip(q['real_unit_nav_chg'], 'text-[10px] font-mono')
                                            else:
                                                ui.label('—').classes('text-xs text-gray-400')
                                    with ui.element('td').classes('px-3 py-2 whitespace-nowrap'):
                                        if q.get('real_ac_nav') is not None:
                                            ui.label(f"{q['real_ac_nav']:.4f}").classes(
                                                'font-mono text-xs text-gray-700'
                                            )
                                            if q.get('real_nav_chg') is not None:
                                                _chg_chip(q['real_nav_chg'], 'text-[10px] font-mono')
                                        else:
                                            ui.label('—').classes('text-xs text-gray-400')
                                    with ui.element('td').classes('px-3 py-2'):
                                        _chg_chip(q.get('cap_chg'), 'text-xs font-mono font-semibold')
                                    with ui.element('td').classes('px-3 py-2 font-mono text-xs text-gray-700'):
                                        ui.label(_fmt_yi(q.get('end_nav_cap')))
                        with ui.element('tfoot'):
                            with ui.element('tr').classes('bg-gray-50 border-t border-gray-200'):
                                with ui.element('td').props('colspan="11"').classes(
                                    'px-3 py-2 text-[10px] text-gray-400'
                                ) as td_note:
                                    ui.label(
                                        '↓ 双因子口径：份额变动 = (本期末总份额/上期末总份额)-1（散户买卖方向）；'
                                        '净值变动 = [(1+净资产变动)/(1+份额变动)]-1（推算口径）；'
                                        '季末单位/累计净值取自天天基金净值历史（含分红再投资，真实记录）'
                                    )

        asyncio.create_task(_load_and_render())

    # ── 表现对比 ─────────────────────────────────

    def set_period(period_key: str):
        state['period'] = period_key
        # 更新按钮视觉
        for k, btn in period_buttons.items():
            if k == period_key:
                btn.classes('bg-indigo-600 text-white shadow-sm', remove='text-gray-600 bg-transparent')
            else:
                btn.classes('text-gray-600 bg-transparent', remove='bg-indigo-600 text-white shadow-sm')
        asyncio.create_task(refresh_performance())

    async def _browser_fetch_fund(code6: str, client=None) -> list | None:
        """在浏览器里直接 fetch 同源代理；返回 [{date, close, pct_chg}] 或 None。

        client: 传入 ui.context.client 以保留 UI 上下文（asyncio.create_task 时必需）
        """
        js_code = (
            '(async () => {'
            '  const KEY = "fund_em_" + ' + json.dumps(code6) + ';'
            '  const TTL = 60*60*1000;'
            '  try {'
            '    const cached = localStorage.getItem(KEY);'
            '    if (cached) {'
            '      const obj = JSON.parse(cached);'
            '      if (obj && obj.ts && (Date.now()-obj.ts) < TTL && Array.isArray(obj.data) && obj.data.length) {'
            '        return obj.data;'
            '      }'
            '    }'
            '    const resp = await fetch("/api/fund_eastmoney/" + ' + json.dumps(code6) + ');'
            '    if (!resp.ok) throw new Error("HTTP " + resp.status);'
            '    const payload = await resp.json();'
            '    if (payload && payload.__error) throw new Error(payload.__error);'
            '    const arr = payload && payload.ts ? payload.ts : [];'
            '    const out = [];'
            '    for (const e of arr) {'
            '      const ts = parseInt(e.x, 10); const nav = parseFloat(e.y); const pct = parseFloat(e.equityReturn||0);'
            '      if (!ts || !nav) continue;'
            '      // 天天基金 x 是"北京时间当日 00:00"的毫秒戳，按 UTC 读取会少 8 小时、跨日错位。'
            '      // 补偿 +8h 后再按 UTC 取年月日，等价于按 Asia/Shanghai 取当日日期。'
            '      const bj = new Date(ts + 8 * 3600 * 1000);'
            '      const date = bj.getUTCFullYear() + String(bj.getUTCMonth()+1).padStart(2,"0") + String(bj.getUTCDate()).padStart(2,"0");'
            '      out.push({ date: date, close: nav, pct_chg: isNaN(pct)?0:pct });'
            '    }'
            '    try { localStorage.setItem(KEY, JSON.stringify({ ts: Date.now(), data: out })); } catch(e){}'
            '    return out;'
            '  } catch(err) {'
            '    return { __error: String(err) };'
            '  }'
            '})()'
        )
        run_fn = (client.run_javascript if client is not None else ui.run_javascript)
        try:
            result = await run_fn(js_code, timeout=15.0)
            if isinstance(result, dict) and '__error' in result:
                print(f'[FundTracker] browser fetch {code6} error: {result["__error"]}')
                return None
            if not isinstance(result, list):
                return None
            return result
        except Exception as e:
            print(f'[FundTracker] browser fetch exception: {e}')
            return None

    async def refresh_performance(force_update: bool = False):
        if perf_container is None:
            return
        if not state['subs']:
            state['perf_data'] = None
            render_performance()
            return
        state['loading_perf'] = True
        render_performance()
        # 使用面板创建时捕获的 client（page_client）；page_client 在 ui.timer 初始化时可能为 None
        client = page_client
        # 浏览器端预拉取场外 OF 基金数据（带 localStorage 缓存）
        of_subs = [s for s in state['subs'] if s.get('ts_code', '').endswith('.OF')]
        if client is not None and of_subs:
            for sub in of_subs:
                ts_code = sub.get('ts_code', '')
                code6 = ts_code.split('.')[0]
                data = await _browser_fetch_fund(code6, client=client)
                if data:
                    state['fund_overrides'][ts_code] = data
        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(
                executor,
                lambda: tracker.get_subs_performance(
                    state['subs'],
                    period_key=state['period'],
                    fund_overrides=(state.get('fund_overrides') or None) if client is not None else None,
                )
            )
            state['perf_data'] = data
        except Exception as e:
            ui.notify(f'刷新失败: {e}', type='negative')
            state['perf_data'] = None
        state['loading_perf'] = False
        render_performance()

    def render_performance():
        if perf_container is None:
            return
        perf_container.clear()
        with perf_container:
            if state['loading_perf']:
                with ui.row().classes('w-full items-center justify-center py-8 gap-2'):
                    ui.spinner('dots', size='md', color='indigo')
                    ui.label('正在拉取行情…').classes('text-sm text-gray-500')
                return
            data = state['perf_data']
            if data is None:
                if state['subs']:
                    ui.label('加载失败，请点击「刷新」重试').classes('text-sm text-gray-400 text-center py-6')
                else:
                    ui.label('添加订阅后将在此展示对比表现').classes('text-sm text-gray-400 text-center py-6')
                return
            render_performance_table(data)

    def render_performance_table(data: dict):
        as_of = data.get('as_of_date', '')
        period_key = data.get('period_key', state['period'])
        rows = data.get('rows', [])
        summary = data.get('summary', {})

        # 头部信息
        with ui.row().classes('w-full items-center justify-between mb-2 px-1 flex-wrap gap-2'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('event', size='xs', color='grey-6')
                ui.label(f'快照日期: {as_of}').classes('text-xs text-gray-500 font-mono')
            with ui.row().classes('items-center gap-3'):
                ui.label(f'基金数: {summary.get("count", 0)}').classes('text-xs text-gray-500')
                if summary.get('avg_fund_pct') is not None:
                    avg_fund = summary['avg_fund_pct']
                    ui.label('平均基金:').classes('text-xs text-gray-500')
                    pct_chip(avg_fund, 'text-sm font-bold')
                if summary.get('avg_index_pct') is not None:
                    avg_idx = summary['avg_index_pct']
                    ui.label('平均指数:').classes('text-xs text-gray-500')
                    pct_chip(avg_idx, 'text-sm font-bold')
                if summary.get('avg_excess') is not None:
                    avg_ex = summary['avg_excess']
                    ui.label('平均超额:').classes('text-xs text-gray-500')
                    pct_chip(avg_ex, 'text-sm font-bold')

        if not rows:
            ui.label('暂无数据').classes('text-sm text-gray-400 text-center py-4')
            return

        # 表格
        with ui.element('div').classes('w-full overflow-x-auto rounded-lg border border-gray-200 bg-white'):
            with ui.element('table').classes('w-full text-sm'):
                # 表头
                with ui.element('thead').classes('bg-gray-50 text-gray-600'):
                    with ui.element('tr'):
                        for h in ['基金 / ETF', '代码', '基金涨跌幅', '对标指数', '指数涨跌幅', '超额收益']:
                            with ui.element('th').classes('px-3 py-2 text-left font-semibold text-xs whitespace-nowrap'):
                                ui.label(h)
                # 表体
                with ui.element('tbody'):
                    for row in rows:
                        with ui.element('tr').classes('border-t border-gray-100 hover:bg-indigo-50/40'):
                            with ui.element('td').classes('px-3 py-2 font-medium text-gray-800 whitespace-nowrap'):
                                ui.label(row.get('fund_name') or row.get('fund_ts_code', ''))
                            with ui.element('td').classes('px-3 py-2 font-mono text-xs text-gray-500'):
                                ui.label(row.get('fund_ts_code', ''))
                            with ui.element('td').classes('px-3 py-2'):
                                pct_chip(row.get('fund_pct'), 'text-sm font-bold')
                            with ui.element('td').classes('px-3 py-2 text-xs text-indigo-600 whitespace-nowrap'):
                                ui.label(row.get('index_name') or row.get('index_code') or '—')
                            with ui.element('td').classes('px-3 py-2'):
                                pct_chip(row.get('index_pct'), 'text-sm font-bold')
                            with ui.element('td').classes('px-3 py-2'):
                                pct_chip(row.get('excess'), 'text-sm font-bold')

    def pct_chip(value, classes: str = ''):
        """统一渲染涨跌幅 chip：正绿负红，平淡灰"""
        if value is None:
            ui.label('—').classes(f'{classes} text-gray-400')
            return
        try:
            v = float(value)
        except Exception:
            ui.label('—').classes(f'{classes} text-gray-400')
            return
        if v > 0:
            color_class = 'text-emerald-600'
            prefix = '+'
        elif v < 0:
            color_class = 'text-rose-600'
            prefix = ''
        else:
            color_class = 'text-gray-500'
            prefix = ''
        ui.label(f'{prefix}{v:.2f}%').classes(f'{classes} {color_class}')

    # ── 4 大指数横向对比 ────────────────────────────

    async def refresh_index_compare():
        if index_compare_container is None:
            return
        index_compare_container.clear()
        with index_compare_container:
            with ui.row().classes('w-full items-center justify-center py-6 gap-2'):
                ui.spinner('dots', size='sm', color='indigo')
                ui.label('正在加载指数行情…').classes('text-xs text-gray-500')
        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(executor, tracker.get_indexes_compare)
            render_index_compare_cards(data)
        except Exception as e:
            index_compare_container.clear()
            with index_compare_container:
                ui.label(f'指数数据加载失败: {e}').classes('text-xs text-rose-500 text-center py-4')

    def render_index_compare_cards(data: list):
        index_compare_container.clear()
        with index_compare_container:
            # 顶部 4 张卡片（横排；移动端 2x2）
            with ui.grid(columns='responsive').classes('w-full gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4'):
                for row in data:
                    render_index_card(row)

            # 下方多周期涨跌幅对比表
            with ui.element('div').classes('w-full mt-4 overflow-x-auto rounded-lg border border-gray-200 bg-white'):
                with ui.element('table').classes('w-full text-sm'):
                    with ui.element('thead').classes('bg-gray-50 text-gray-600'):
                        with ui.element('tr'):
                            for h in ['指数', '收盘', '当日', '近5日', '近20日', '近60日', '年内']:
                                with ui.element('th').classes('px-3 py-2 text-left font-semibold text-xs'):
                                    ui.label(h)
                    with ui.element('tbody'):
                        for row in data:
                            with ui.element('tr').classes('border-t border-gray-100 hover:bg-gray-50'):
                                with ui.element('td').classes('px-3 py-2'):
                                    with ui.row().classes('items-center gap-2'):
                                        ui.element('div').classes('w-1 h-4 rounded-sm').style(
                                            f'background:{row.get("bar", "#6366f1")}'
                                        )
                                        ui.label(row.get('name', '')).classes('text-sm font-medium text-gray-800')
                                with ui.element('td').classes('px-3 py-2 font-mono text-xs text-gray-700'):
                                    if row.get('close') is not None:
                                        ui.label(f'{row["close"]:.2f}')
                                    else:
                                        ui.label('—').classes('text-gray-400')
                                with ui.element('td').classes('px-3 py-2'):
                                    pct_chip(row.get('pct_1d'), 'text-sm font-mono font-semibold')
                                with ui.element('td').classes('px-3 py-2'):
                                    pct_chip(row.get('pct_5d'), 'text-sm font-mono font-semibold')
                                with ui.element('td').classes('px-3 py-2'):
                                    pct_chip(row.get('pct_20d'), 'text-sm font-mono font-semibold')
                                with ui.element('td').classes('px-3 py-2'):
                                    pct_chip(row.get('pct_60d'), 'text-sm font-mono font-semibold')
                                with ui.element('td').classes('px-3 py-2'):
                                    pct_chip(row.get('pct_ytd'), 'text-sm font-mono font-semibold')

    def render_index_card(row: dict):
        bar = row.get('bar', PRIMARY)
        text_class = row.get('text', 'text-indigo-700')
        name = row.get('name', '')
        short = row.get('short', '')
        close = row.get('close')
        pct_1d = row.get('pct_1d')
        last_date = row.get('last_date', '')

        # 颜色判定
        if pct_1d is None:
            pct_color = 'text-gray-400'
            arrow = ''
            pct_str = '—'
        elif pct_1d > 0:
            pct_color = 'text-emerald-600'
            arrow = '▲'
            pct_str = f'+{pct_1d:.2f}%'
        elif pct_1d < 0:
            pct_color = 'text-rose-600'
            arrow = '▼'
            pct_str = f'{pct_1d:.2f}%'
        else:
            pct_color = 'text-gray-500'
            arrow = '—'
            pct_str = '0.00%'

        with ui.card().classes('w-full p-4 rounded-xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow'):
            with ui.row().classes('w-full items-center justify-between'):
                with ui.column().classes('gap-0'):
                    ui.label(name).classes(f'text-xs font-medium {text_class}')
                    ui.label(short).classes('text-[10px] text-gray-400 mt-0.5')
                ui.element('div').classes('w-1 h-8 rounded-sm').style(f'background:{bar}')
            with ui.row().classes('w-full items-end justify-between mt-2'):
                if close is not None:
                    ui.label(f'{close:.2f}').classes('text-2xl font-bold text-gray-800 font-mono')
                else:
                    ui.label('—').classes('text-2xl font-bold text-gray-400')
            with ui.row().classes('w-full items-center justify-between mt-1'):
                ui.label(f'{arrow} {pct_str}').classes(f'text-sm font-bold {pct_color}')
                if last_date:
                    ui.label(last_date).classes('text-[10px] text-gray-400 font-mono')

    # ── 主布局 ──────────────────────────────────

    add_dialog = ui.dialog().classes('items-center')

    with ui.column().classes('w-full px-2 md:px-6 py-2 gap-4'):

        # ── 顶部品牌头 ──
        with ui.card().classes('w-full p-0 rounded-2xl shadow-sm border border-indigo-100 overflow-hidden'):
            with ui.element('div').classes('w-full p-5 relative overflow-hidden').style(
                'background: linear-gradient(135deg, #eef2ff 0%, #f5f3ff 50%, #fdf4ff 100%);'
                'border-bottom: 1px solid #e0e7ff;'
            ):
                ui.element('div').classes('absolute -right-20 -top-20 w-60 h-60 rounded-full').style(
                    'background: radial-gradient(circle, rgba(99,102,241,0.18) 0%, transparent 70%);'
                )
                ui.element('div').classes('absolute -left-10 -bottom-10 w-40 h-40 rounded-full').style(
                    'background: radial-gradient(circle, rgba(168,85,247,0.14) 0%, transparent 70%);'
                )
                with ui.row().classes('w-full items-center justify-between relative z-10 flex-wrap gap-3'):
                    with ui.row().classes('items-center gap-3'):
                        with ui.element('div').classes(
                            'w-11 h-11 rounded-xl flex items-center justify-center'
                        ).style(
                            'background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);'
                            'box-shadow: 0 4px 12px rgba(99,102,241,0.3);'
                        ):
                            ui.icon('savings', color='white').classes('text-lg')
                        with ui.column().classes('gap-0'):
                            ui.html(
                                '<span style="font-size: 1.35rem; font-weight: 700; '
                                'background: linear-gradient(135deg, #4338ca 0%, #7c3aed 100%); '
                                '-webkit-background-clip: text; -webkit-text-fill-color: transparent; '
                                'background-clip: text;">基金 / ETF 订阅跟踪</span>',
                                sanitize=False
                            )
                            ui.label('数据来源：Tushare Pro（fund_basic / fund_daily / index_daily）').classes(
                                'text-[10px] text-slate-500 mt-0.5'
                            )
                    refresh_btn = ui.button('刷新数据', icon='refresh',
                                             on_click=lambda: asyncio.create_task(refresh_all())) \
                        .props('outline color=indigo-dense').classes('text-indigo-600')

        # ── 4 大指数横向对比 ──
        with ui.card().classes('w-full p-4 rounded-xl shadow-sm border border-gray-100'):
            with ui.row().classes('w-full items-center justify-between mb-3'):
                with ui.row().classes('items-center gap-2'):
                    with ui.element('div').classes('w-7 h-7 rounded-md flex items-center justify-center').style(
                        'background: linear-gradient(135deg, #6366f1 0%, #3b82f6 100%);'
                    ):
                        ui.icon('bar_chart', color='white').classes('text-sm')
                    ui.label('大盘指数横向对比').classes('text-sm font-bold text-gray-800')
                    ui.chip('上证 / 深证 / 创业板 / 科创50', color='indigo').props('dense outline square').classes(
                        'text-[10px]'
                    )
                ui.label('点击「刷新数据」可手动更新指数行情').classes('text-[10px] text-gray-400')
            index_compare_container = ui.column().classes('w-full')

        # ── 我的订阅 + 搜索 ──
        with ui.row().classes('w-full gap-4 flex-col lg:flex-row items-stretch'):
            # 左：搜索 + 列表
            with ui.card().classes('w-full lg:w-1/3 p-4 rounded-xl shadow-sm border border-gray-100'):
                with ui.row().classes('w-full items-center justify-between mb-3'):
                    with ui.row().classes('items-center gap-2'):
                        with ui.element('div').classes('w-7 h-7 rounded-md flex items-center justify-center').style(
                            'background: linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%);'
                        ):
                            ui.icon('bookmark', color='white').classes('text-sm')
                        ui.label('我的订阅').classes('text-sm font-bold text-gray-800')
                    ui.label(f'共 {len(state["subs"])} 只').classes('text-[10px] text-gray-400 font-mono')

                # 搜索输入
                with ui.row().classes('w-full items-center gap-2 mb-3'):
                    search_input = ui.input(
                        placeholder='代码 / 名称 / 管理人…',
                        on_change=lambda e: state.update(search_keyword=e.value or ''),
                    ).props('outlined dense clearable').classes('flex-1')

                    async def _on_search():
                        await do_search()
                    search_input.on('keydown.enter', lambda: asyncio.create_task(_on_search()))

                    ui.button('搜索', icon='search', on_click=lambda: asyncio.create_task(_on_search())) \
                        .props('unelevated color=indigo dense')

                # 搜索结果（折叠显示）
                with ui.row().classes('w-full items-center justify-between mb-1'):
                    ui.label('搜索结果').classes('text-xs font-semibold text-gray-500')
                    if state['search_keyword']:
                        ui.label(f'"{state["search_keyword"]}"').classes('text-[10px] text-indigo-500 font-mono truncate max-w-32')
                search_results_container = ui.column().classes('w-full mb-3 rounded-lg border border-gray-100 bg-gray-50')

                ui.separator().classes('my-2')

                sub_list_container = ui.column().classes('w-full')

            # 右：表现对比
            with ui.card().classes('w-full lg:flex-1 p-4 rounded-xl shadow-sm border border-gray-100'):
                with ui.row().classes('w-full items-center justify-between mb-3 flex-wrap gap-2'):
                    with ui.row().classes('items-center gap-2'):
                        with ui.element('div').classes('w-7 h-7 rounded-md flex items-center justify-center').style(
                            'background: linear-gradient(135deg, #10b981 0%, #059669 100%);'
                        ):
                            ui.icon('insights', color='white').classes('text-sm')
                        ui.label('基金 vs 对标指数').classes('text-sm font-bold text-gray-800')

                    # 周期切换（segmented control）
                    with ui.row().classes('bg-gray-100 rounded-full p-1 gap-1 items-center'):
                        for pd in tracker.PERIOD_DEFS:
                            key = pd['key']
                            btn = ui.button(pd['label'],
                                            on_click=lambda k=key: set_period(k)) \
                                .props('flat dense no-caps no-ripple') \
                                .classes(
                                    'px-3 py-1 rounded-full text-xs font-bold transition-all duration-200 '
                                    + ('bg-indigo-600 text-white shadow-sm'
                                       if key == state['period']
                                       else 'text-gray-600 bg-transparent hover:text-indigo-600')
                                )
                            period_buttons[key] = btn

                perf_container = ui.column().classes('w-full')

        # ── 订阅基金规模双因子总览（季度）──
        with ui.card().classes('w-full p-4 rounded-xl shadow-sm border border-gray-100'):
            with ui.row().classes('w-full items-center justify-between mb-1 flex-wrap gap-2'):
                with ui.row().classes('items-center gap-2'):
                    with ui.element('div').classes('w-7 h-7 rounded-md flex items-center justify-center').style(
                        'background: linear-gradient(135deg, #f59e0b 0%, #10b981 100%);'
                    ):
                        ui.icon('donut_small', color='white').classes('text-sm')
                    ui.label('订阅基金规模双因子（季度）').classes('text-sm font-bold text-gray-800')
                    ui.chip('基金涨跌因子 × 散户申赎因子', color='amber').props(
                        'dense outline square'
                    ).classes('text-[10px]')
                with ui.row().classes('items-center gap-2'):
                    ui.label('净值因子 = 排除申赎后的涨跌；份额因子 = 散户买卖方向').classes(
                        'text-[10px] text-gray-400'
                    )
            ui.label(
                '口径：净资产变动 ≈ (1+份额变动)×(1+净值变动) - 1 ｜ '
                '数据源：天天基金 fundf10 季度规模变动 ｜ 点击顶部「刷新数据」同步更新'
            ).classes('text-[10px] text-gray-400 mb-2')
            scale_overview_container = ui.column().classes('w-full')

        # ── 底部数据源 / 提示 ──
        with ui.row().classes('w-full items-center justify-between text-[10px] text-gray-400 px-2'):
            ui.label('💡 订阅信息保存在浏览器 localStorage 中，可在多设备分别记录自己的基金清单')
            ui.label('数据源：Tushare Pro + 天天基金')

    # ── 订阅基金规模双因子总览 ─────────────────────────

    async def refresh_scale_overview(force_update: bool = False):
        """拉取全部订阅基金的季度规模双因子并渲染总览表。

        force_update: True 时强制重新请求天天基金（绕过当日缓存），
        由顶部「刷新数据」按钮触发；页面初始化用 False 命中缓存快加载。
        """
        if scale_overview_container is None:
            return
        scale_overview_container.clear()
        with scale_overview_container:
            if not state['subs']:
                ui.label('添加订阅后将在此展示规模双因子总览').classes(
                    'text-xs text-gray-400 text-center py-4'
                )
                return
            with ui.row().classes('w-full items-center justify-center py-5 gap-2'):
                ui.spinner('dots', size='sm', color='amber-6')
                ui.label(
                    f'正在{"强制更新" if force_update else "拉取"} '
                    f'{len(state["subs"])} 只订阅基金的季度规模数据…'
                ).classes('text-xs text-gray-500')
        loop = asyncio.get_running_loop()
        started_at = asyncio.get_event_loop().time()
        try:
            data = await loop.run_in_executor(
                executor,
                lambda: tracker.get_subs_scale_change(state['subs'], force_refresh=force_update),
            )
            # 最小 loading 展示时长：接口太快时 spinner 一闪而过反而像"没刷新"，
            # 保底展示 0.8s，与其他板块的 loading 观感一致
            elapsed = asyncio.get_event_loop().time() - started_at
            min_loading = 0.8
            if elapsed < min_loading:
                await asyncio.sleep(min_loading - elapsed)
            render_scale_overview(data)
        except Exception as e:
            scale_overview_container.clear()
            with scale_overview_container:
                ui.label(f'规模数据加载失败: {e}').classes(
                    'text-xs text-rose-500 text-center py-4'
                )

    def render_scale_overview(data: dict):
        """渲染规模双因子总览表（含汇总行 + 每只基金最新一期双因子）。"""
        if scale_overview_container is None:
            return
        rows = data.get('rows') or []
        summary = data.get('summary') or {}
        scale_overview_container.clear()
        with scale_overview_container:
            if not rows:
                ui.label('暂无数据').classes('text-xs text-gray-400 text-center py-4')
                return

            # 汇总行
            with ui.row().classes('w-full items-center gap-4 mb-2 px-1 flex-wrap'):
                ui.label(f'基金数: {summary.get("count", 0)}').classes('text-xs text-gray-500')
                if summary.get('avg_nav_chg') is not None:
                    ui.label('平均「基金涨跌」:').classes('text-xs text-gray-500')
                    _chg_chip(summary['avg_nav_chg'], 'text-sm font-bold')
                if summary.get('avg_shares_chg') is not None:
                    ui.label('平均「散户申赎」:').classes('text-xs text-gray-500')
                    _chg_chip(summary['avg_shares_chg'], 'text-sm font-bold')
                if summary.get('avg_net_flow_ratio') is not None:
                    ui.label('平均净申赎比:').classes('text-xs text-gray-500')
                    _chg_chip(summary['avg_net_flow_ratio'], 'text-sm font-bold')
                # 更新时间戳：让「刷新数据」触发的重渲染可见
                ui.label(f'更新于 {datetime.datetime.now().strftime("%H:%M:%S")}').classes(
                    'text-[10px] text-gray-400 font-mono ml-auto'
                )

            with ui.element('div').classes(
                'w-full overflow-x-auto rounded-lg border border-gray-200 bg-white'
            ):
                with ui.element('table').classes('w-full text-sm'):
                    with ui.element('thead').classes('bg-gray-50 text-gray-600'):
                        with ui.element('tr'):
                            for h in ['基金', '季度末', '净资产变动', '📈 基金涨跌（净值）',
                                      '👥 散户申赎（份额）', '净申赎(亿份)', '近4季份额趋势']:
                                with ui.element('th').classes(
                                    'px-3 py-2 text-left font-semibold text-xs whitespace-nowrap'
                                ):
                                    ui.label(h)
                    with ui.element('tbody'):
                        for row in rows:
                            quarters = row.get('quarters') or []
                            latest = quarters[0] if quarters else None
                            code = row.get('ts_code', '')
                            with ui.element('tr').classes(
                                'border-t border-gray-100 hover:bg-amber-50/40'
                            ):
                                with ui.element('td').classes('px-3 py-2 whitespace-nowrap'):
                                    with ui.row().classes('items-center gap-2'):
                                        sub_item = next(
                                            (s for s in state['subs']
                                             if s.get('ts_code') == code), None
                                        )
                                        if sub_item is not None:
                                            ui.button(row.get('name') or code,
                                                      on_click=lambda s=dict(sub_item): open_scale_dialog(s)) \
                                                .props('flat dense no-caps color=indigo') \
                                                .classes('text-xs font-semibold')
                                        else:
                                            ui.label(row.get('name') or code).classes(
                                                'text-xs font-semibold text-gray-800'
                                            )
                                        ui.label(code).classes(
                                            'font-mono text-[10px] text-gray-400'
                                        )
                                with ui.element('td').classes('px-3 py-2 font-mono text-xs text-gray-500'):
                                    ui.label(row.get('as_of') or '—')
                                if latest:
                                    with ui.element('td').classes('px-3 py-2'):
                                        _chg_chip(latest.get('cap_chg'), 'text-sm font-bold')
                                    with ui.element('td').classes('px-3 py-2'):
                                        # 优先真实累计净值涨跌；缺则回退公式反推
                                        nav_disp = latest.get('real_nav_chg')
                                        _chg_chip(
                                            nav_disp if nav_disp is not None else latest.get('nav_chg'),
                                            'text-sm font-bold'
                                        )
                                    with ui.element('td').classes('px-3 py-2'):
                                        _chg_chip(latest.get('shares_chg'), 'text-sm font-bold')
                                    nf_yi = None if latest.get('net_flow') is None else latest['net_flow'] / 1e8
                                    with ui.element('td').classes('px-3 py-2'):
                                        _flow_chip(nf_yi, 'text-xs font-mono')
                                    with ui.element('td').classes('px-3 py-2'):
                                        _render_shares_trend(quarters)
                                else:
                                    with ui.element('td').props('colspan="5"').classes(
                                        'px-3 py-2 text-[10px] text-rose-400'
                                    ):
                                        ui.label(f'拉取失败: {row.get("error") or "无数据"}')

    def _render_shares_trend(quarters: list):
        """近 4 季份额变动率迷你趋势（彩色文字序列）。"""
        qs = list(reversed((quarters or [])[:4]))  # 时间正序
        chips = []
        for q in qs:
            v = q.get('shares_chg')
            if v is None:
                chips.append('<span style="color:#cbd5e1">·</span>')
            elif v >= 0:
                chips.append(f'<span style="color:#10b981;font-weight:600">+{v:.0f}%</span>')
            else:
                chips.append(f'<span style="color:#ef4444;font-weight:600">{v:.0f}%</span>')
        if not chips:
            ui.label('—').classes('text-xs text-gray-400')
            return
        ui.html(
            '<div style="display:flex;align-items:center;gap:6px;font-family:monospace;font-size:11px">'
            f'<span style="color:#94a3b8;font-size:9px">近{len(chips)}季</span>'
            + ''.join(chips) + '</div>',
            sanitize=False,
        )

    # ── 初始化流程 ────────────────────────────────

    async def init_all():
        # 1) 加载订阅
        await load_subs_from_browser()
        refresh_sub_list()
        # 2) 拉指数对比 + 订阅表现（并发）
        await asyncio.gather(
            refresh_index_compare(),
            refresh_performance(force_update=True),
        )
        # 3) 规模双因子总览（订阅非空时才拉）
        if state['subs']:
            asyncio.create_task(refresh_scale_overview())
        else:
            scale_overview_container.clear()
            with scale_overview_container:
                ui.label('添加订阅后将在此展示规模双因子总览').classes(
                    'text-xs text-gray-400 text-center py-4'
                )

    async def refresh_all():
        await asyncio.gather(
            refresh_index_compare(),
            refresh_performance(force_update=True),
            refresh_scale_overview(force_update=True),
        )

    ui.timer(0, init_all, once=True)