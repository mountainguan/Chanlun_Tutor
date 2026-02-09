"""
Shibor 利率走势图组件
与上证指数叠加展示，嵌入大盘温度模块
"""

from nicegui import ui
from utils.shibor_data import ShiborDataManager, SHIBOR_TERMS
from utils.index_data import IndexDataManager
import plotly.graph_objects as go
import pandas as pd
import asyncio
import io
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=2)

# Shibor 品种颜色方案 (与官方图表对齐，使用更柔和的色彩)
TERM_COLORS = {
    "O/N": "#EF5350",   # 红
    "1W":  "#66BB6A",   # 绿
    "2W":  "#AB47BC",   # 紫
    "1M":  "#42A5F5",   # 蓝
    "3M":  "#FFA726",   # 橙
    "6M":  "#26C6DA",   # 青
    "9M":  "#8D6E63",   # 棕
    "1Y":  "#5C6BC0",   # 靛
}


# 时间区间选项
RANGE_OPTIONS = {
    "全部": None,
    "近1年": 365,
    "近半年": 183,
    "近3个月": 92,
    "近1个月": 31,
}


def render_shibor_panel(plotly_renderer, is_mobile=False):
    """渲染 Shibor 利率走势面板"""

    # ── 缓存数据避免重复请求 ──────────────────────────────────
    _cache = {'shibor_df': None, 'index_df': None}

    def export_excel():
        df = _cache.get('shibor_df')
        if df is not None and not df.empty:
            try:
                output = io.BytesIO()
                df.to_excel(output, index=False)
                ui.download(output.getvalue(), 'shibor_history.xlsx')
                ui.notify('正在导出 Shibor 历史数据...', type='info')
            except Exception as e:
                ui.notify(f'导出失败: {e}', type='negative')
        else:
            ui.notify('暂无数据可导出', type='warning')

    chart_height_class = 'h-[600px]' if is_mobile else 'h-[680px]'

    with ui.card().classes(f'w-full {chart_height_class} border border-gray-200 rounded-xl shadow-sm bg-white p-4 flex flex-col gap-0'):
        # ── Header Row ────────────────────────────────────────
        with ui.row().classes('w-full justify-between items-center mb-2 pb-2 border-b border-gray-200 flex-wrap gap-y-2'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('account_balance', color='indigo').classes('text-2xl')
                ui.label('Shibor 利率走势').classes('text-lg md:text-xl font-bold text-gray-800')

            with ui.row().classes('items-center gap-2 md:gap-4 flex-wrap justify-end flex-1'):
                term_select = ui.select(
                    options={k: f"{k} ({v})" for k, v in SHIBOR_TERMS.items()},
                    value="O/N",
                    label="Shibor品种",
                    on_change=lambda e: asyncio.create_task(redraw_chart())
                ).props('dense outlined options-dense bg-white behavior=menu').classes('w-32 md:w-40 text-xs')

                range_select = ui.select(
                    options=list(RANGE_OPTIONS.keys()),
                    value="近3个月",
                    label="时间范围",
                    on_change=lambda e: asyncio.create_task(redraw_chart())
                ).props('dense outlined options-dense bg-white behavior=menu').classes('w-24 md:w-32 text-xs')

                # 下载按钮
                ui.button(icon='download', on_click=export_excel) \
                    .props('flat color=indigo dense').tooltip('导出数据到Excel')

                ui.button('刷新', icon='refresh', on_click=lambda: asyncio.create_task(fetch_and_draw(force=True))) \
                    .props('flat color=indigo icon-right dense').classes('text-indigo-600 font-bold text-xs md:text-sm')

        # ── Plot Area ─────────────────────────────────────────
        chart_plot_area = ui.column().classes('w-full flex-1 min-h-0 relative p-0 m-0')

        # ── 说明区域 (合并到同一卡片内) ──────────────────────
        ui.separator().classes('my-2')
        with ui.column().classes('w-full gap-1 pt-1'):
            with ui.row().classes('items-start gap-3'):
                ui.icon('info_outline', color='blue-grey').classes('text-xl mt-0.5')
                with ui.column().classes('gap-1'):
                    ui.html(
                        '<div class="text-xs md:text-sm text-gray-600">'
                        '<b>Shibor</b>（Shanghai Interbank Offered Rate）是上海银行间同业拆放利率，'
                        '反映银行间市场的资金松紧程度。'
                        '<br>• <b>O/N（隔夜）</b>利率波动最大，反映短期资金面情绪；'
                        '<b>3M、1Y</b> 反映中长期利率预期。'
                        '<br>• 利率<span class="text-red-600 font-bold">快速上行</span>常意味着资金面趋紧，'
                        '利率<span class="text-green-600 font-bold">持续下行</span>表示流动性宽松。'
                        '</div>',
                        sanitize=False,
                    )
            ui.label('数据来源：中国货币网 (chinamoney.com.cn)').classes('text-[10px] text-gray-400 mt-1')

    def _apply_range_filter(df, date_col='date'):
        """根据时间范围筛选器裁剪数据"""
        range_days = RANGE_OPTIONS.get(range_select.value)
        if range_days is None or df is None or df.empty:
            return df
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=range_days)
        return df[df[date_col] >= cutoff].copy()

    async def fetch_and_draw(force=False):
        """从远程拉取数据并缓存，然后绘制"""
        loop = asyncio.get_running_loop()

        if not chart_plot_area.is_deleted:
            chart_plot_area.clear()
            with chart_plot_area:
                ui.spinner('dots', size='lg', color='primary').classes('absolute-center z-20')

        if force:
            ui.notify('正在刷新 Shibor 利率数据...', type='info')

        try:
            sdm = ShiborDataManager()
            idm = IndexDataManager()

            # 并行拉取 Shibor 和上证指数
            shibor_task = loop.run_in_executor(executor, lambda: sdm.get_shibor_data(force_refresh=force))
            index_task = loop.run_in_executor(executor, lambda: idm.get_index_data("上证指数", force_refresh=force))

            shibor_df, index_df = await asyncio.gather(shibor_task, index_task)
            _cache['shibor_df'] = shibor_df
            _cache['index_df'] = index_df

        except Exception as e:
            if not chart_plot_area.is_deleted:
                chart_plot_area.clear()
                with chart_plot_area:
                    ui.label(f'数据加载失败: {e}').classes('absolute-center text-red-500')
            return

        await redraw_chart()

    async def redraw_chart():
        """基于缓存数据 + 当前筛选条件重新绘图（无网络请求）"""
        shibor_df = _cache.get('shibor_df')
        if shibor_df is None or shibor_df.empty:
            if not chart_plot_area.is_deleted:
                chart_plot_area.clear()
                with chart_plot_area:
                    ui.label('暂无 Shibor 数据').classes('absolute-center text-gray-500 font-bold')
            return

        if not chart_plot_area.is_deleted:
            chart_plot_area.clear()
            with chart_plot_area:
                ui.spinner('dots', size='lg', color='primary').classes('absolute-center z-20')

        selected_term = term_select.value

        # ── 应用时间范围筛选 ──────────────────────────────────
        shibor_view = _apply_range_filter(shibor_df, 'date')

        # ── 构建图表 ──────────────────────────────────────────
        fig = go.Figure()

        # Shibor 利率曲线（默认 O/N）
        term = selected_term
        if term in shibor_view.columns:
            term_data = shibor_view[['date', term]].dropna(subset=[term])
            color = TERM_COLORS.get(term, '#5C6BC0')
            term_label = SHIBOR_TERMS.get(term, term)

            fig.add_trace(go.Scatter(
                x=term_data['date'],
                y=term_data[term],
                mode='lines',
                name=f'Shibor {term} ({term_label})',
                line=dict(color=color, width=2.5, shape='spline'),
                fill='tozeroy',
                fillcolor=f'rgba({_hex_to_rgb(color)}, 0.06)',
                yaxis='y',
                hovertemplate='%{x|%Y-%m-%d}<br>Shibor ' + term + ': %{y:.4f}%<extra></extra>',
            ))

        # 上证指数（副轴，始终叠加）
        df_index = _cache.get('index_df')
        show_index = df_index is not None and not df_index.empty
        if show_index:
            idx = df_index.copy()
            if not pd.api.types.is_datetime64_any_dtype(idx['date']):
                idx['date'] = pd.to_datetime(idx['date'])
            # 与当前显示的 Shibor 时间范围对齐
            idx = _apply_range_filter(idx, 'date')
            if not shibor_view.empty:
                start_dt = shibor_view['date'].min()
                end_dt = shibor_view['date'].max()
                idx = idx[(idx['date'] >= start_dt) & (idx['date'] <= end_dt)]

            if not idx.empty:
                fig.add_trace(go.Scatter(
                    x=idx['date'],
                    y=idx['close'],
                    mode='lines',
                    name='上证指数',
                    line=dict(color='#CFD8DC', width=1.5),
                    yaxis='y2',
                    hovertemplate='%{x|%Y-%m-%d}<br>上证指数: %{y:.2f}<extra></extra>',
                ))

        # ── Layout ────────────────────────────────────────────
        height_val = 340 if is_mobile else 460
        margin_val = dict(l=36, r=18, t=10, b=36) if is_mobile else dict(l=50, r=50, t=10, b=50)

        # 根据时间范围自适应 X 轴刻度
        range_days = RANGE_OPTIONS.get(range_select.value)
        if is_mobile:
            tick_fmt = "%m-%d"
            dtick_val = 86400000 * 30
        elif range_days is not None and range_days <= 31:
            tick_fmt = "%m-%d"
            dtick_val = 86400000 * 5  # 5天一格
        elif range_days is not None and range_days <= 92:
            tick_fmt = "%m-%d"
            dtick_val = 86400000 * 14  # 2周一格
        elif range_days is not None and range_days <= 183:
            tick_fmt = "%Y-%m"
            dtick_val = "M1"
        else:
            tick_fmt = "%Y-%m"
            dtick_val = "M2"

        xaxis_cfg = dict(
            title='日期',
            tickformat=tick_fmt,
            hoverformat="%Y-%m-%d",
            tickangle=-45,
            showgrid=not is_mobile,
            gridcolor='#F3F4F6',
            ticks='outside',
            dtick=dtick_val,
        )
        if not is_mobile and (range_days is None or range_days > 183):
            xaxis_cfg['rangeslider'] = dict(visible=True, thickness=0.08, bgcolor='#F9FAFB')

        fig.update_layout(
            xaxis=xaxis_cfg,
            yaxis=dict(
                title='Shibor (%)',
                showgrid=True,
                gridcolor='#F3F4F6',
                zeroline=True,
                zerolinecolor='#E5E7EB',
                tickformat='.2f',
            ),
            yaxis2=dict(
                title='上证指数',
                overlaying='y',
                side='right',
                showgrid=False,
                zeroline=False,
            ) if show_index else None,
            margin=margin_val,
            height=height_val,
            hovermode='x unified',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family="Roboto, 'Microsoft YaHei', sans-serif"),
            showlegend=not is_mobile,
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        )

        if chart_plot_area.is_deleted:
            return
        chart_plot_area.clear()
        with chart_plot_area:
            plotly_renderer(fig).classes('w-full h-full')

    # ── 首次加载 ──────────────────────────────────────────────
    ui.timer(0, lambda: asyncio.create_task(fetch_and_draw()), once=True)


def _hex_to_rgb(hex_color: str) -> str:
    """将 #RRGGBB 转为 'R, G, B' 字符串"""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"{r}, {g}, {b}"
