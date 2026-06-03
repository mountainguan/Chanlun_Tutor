from nicegui import ui
import plotly.graph_objects as go
import pandas as pd
import asyncio
import datetime
import io
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)


# 全部指数定义（与 data/指数样本调整名单.xlsx 的「所属指数」列保持一致）
# 单一来源：筛选下拉、对比柱状图、详细统计卡片都从这里取，避免遗漏
INDEX_DEFS = [
    {'name': '上证50指数',     'short': '上证50', 'bar': '#6366f1', 'bg': 'bg-indigo-50',  'text': 'text-indigo-700',  'border': 'border-indigo-200'},
    {'name': '上证180指数',    'short': '上证180', 'bar': '#ec4899', 'bg': 'bg-pink-50',   'text': 'text-pink-700',   'border': 'border-pink-200'},
    {'name': '上证380指数',    'short': '上证380', 'bar': '#f59e0b', 'bg': 'bg-amber-50',  'text': 'text-amber-700',  'border': 'border-amber-200'},
    {'name': '科创50指数',     'short': '科创50',  'bar': '#10b981', 'bg': 'bg-emerald-50', 'text': 'text-emerald-700', 'border': 'border-emerald-200'},
    {'name': '创业板指数',     'short': '创业板',  'bar': '#ef4444', 'bg': 'bg-rose-50',   'text': 'text-rose-700',   'border': 'border-rose-200'},
    {'name': '创业板50指数',   'short': '创业板50', 'bar': '#f43f5e', 'bg': 'bg-red-50',    'text': 'text-red-700',    'border': 'border-red-200'},
    {'name': '深证100指数',    'short': '深证100', 'bar': '#0ea5e9', 'bg': 'bg-sky-50',    'text': 'text-sky-700',    'border': 'border-sky-200'},
    {'name': '深证成份指数',   'short': '深证成份', 'bar': '#8b5cf6', 'bg': 'bg-violet-50', 'text': 'text-violet-700', 'border': 'border-violet-200'},
]


def render_pe_tracker_panel(plotly_renderer, is_mobile=False):
    """指数成分股PE估值跟踪面板 - 清新金融科技风格"""

    # State
    state = {
        'df': None,
        'selected_index': 'all',
        'selected_action': 'all',
        'selected_level': 'all',
        'selected_percentile': 'all',  # 历史PE分位档位筛选
        'selected_level_view': '低估',  # 估值分布区点击的档位
        'expanded_percentile_band': None,  # 图2 档位内联展开状态
        'table_level_filter': None,  # 图3 档位徽章联动筛选
        'loading': False,
    }

    # UI References
    insight_label = None
    chart_container = None
    table_container = None

    async def load_data(force=False):
        """加载数据"""
        if state['loading']:
            return

        state['loading'] = True

        if chart_container:
            chart_container.clear()
            with chart_container:
                _render_loading_state()

        try:
            from utils.pe_tracker import PETracker
            tracker = PETracker()

            loop = asyncio.get_running_loop()
            df = await loop.run_in_executor(executor, lambda: tracker.get_all_data(force_update=force))

            state['df'] = df

            if df.empty:
                ui.notify('未能获取到数据', type='warning')
                state['loading'] = False
                return

            update_insights(df)
            render_charts(df)
            render_table(df)

            ui.notify('PE数据加载完成', type='positive', position='top')

        except Exception as e:
            print(f"[PETracker] Load error: {e}")
            ui.notify(f'加载失败: {str(e)}', type='negative')

        state['loading'] = False

    def _render_loading_state():
        with ui.column().classes('w-full items-center justify-center py-16'):
            ui.spinner('dots', size='xl', color='indigo')
            ui.label('正在获取PE估值数据...').classes('text-slate-500 mt-4 text-sm')
            ui.label('首次加载可能需要10-20秒').classes('text-slate-400 text-xs mt-1')

    def update_insights(df):
        """更新核心洞察（基于行业历史PE分位判断估值温度）"""
        if df.empty or insight_label is None:
            return

        # PE有效（>0）的样本
        valid = df[df['动态PE'] > 0]
        if valid.empty:
            insight_label.text = '暂无有效数据'
            return

        # 调入 vs 调出的PE中位数对比（保留：直观展示调整方向）
        in_pe = valid[valid['调入调出'] == '调入']['动态PE'].median() if not valid[valid['调入调出'] == '调入'].empty else 0
        out_pe = valid[valid['调入调出'] == '调出']['动态PE'].median() if not valid[valid['调入调出'] == '调出'].empty else 0

        # 整体市场温度：基于中位历史PE分位
        pct_valid = valid[valid['PE分位'].notna()]
        if pct_valid.empty:
            # 缓存未构建时的兜底：退回用绝对PE中位数
            median_pe = valid['动态PE'].median()
            if median_pe < 15:
                market_temp, temp_color = '低估', 'emerald'
            elif median_pe < 30:
                market_temp, temp_color = '合理', 'sky'
            elif median_pe < 50:
                market_temp, temp_color = '偏高', 'amber'
            else:
                market_temp, temp_color = '高估', 'rose'
            temp_metric = f'中位PE {median_pe:.1f}倍'
            low_pct_label = f'低估(<15) {len(valid[valid["动态PE"]<15])/len(valid)*100:.0f}%'
            high_pct_label = f'高估(>50) {len(valid[valid["动态PE"]>50])/len(valid)*100:.0f}%'
        else:
            median_pct = pct_valid['PE分位'].median()
            if median_pct < 30:
                market_temp, temp_color = '低估', 'emerald'
            elif median_pct < 55:
                market_temp, temp_color = '偏低', 'sky'
            elif median_pct < 75:
                market_temp, temp_color = '偏高', 'amber'
            else:
                market_temp, temp_color = '高估', 'rose'
            temp_metric = f'中位分位 {median_pct:.0f}%'
            # 分位档位比例
            n = len(pct_valid)
            low_count = len(pct_valid[pct_valid['PE分位'] < 20])
            high_count = len(pct_valid[pct_valid['PE分位'] >= 80])
            low_pct_label = f'低估(<20%) {low_count/n*100:.0f}%'
            high_pct_label = f'高估(≥80%) {high_count/n*100:.0f}%'

        # 生成洞察文本
        insight_text = (
            f'当前{temp_metric}，{market_temp}区间 | '
            f'{low_pct_label}，{high_pct_label}'
        )

        if out_pe > 0 and in_pe > 0:
            diff = out_pe - in_pe
            if diff > 5:
                insight_text += f' | 调出股票PE({out_pe:.1f})高于调入({in_pe:.1f})，符合"高估替换"逻辑'
            elif diff < -5:
                insight_text += f' | 调出股票PE({out_pe:.1f})低于调入({in_pe:.1f})，指数调入更高估值标的'

        # 缓存缺失提示
        if pct_valid.empty:
            insight_text += ' | ⚠️ 历史PE分位缓存未生成，请运行 python scripts/build_sector_pe_history.py'

        insight_label.text = insight_text

    def filter_data():
        """根据筛选条件过滤数据"""
        df = state['df']
        if df is None or df.empty:
            return pd.DataFrame()

        filtered = df.copy()

        if state['selected_index'] != 'all':
            filtered = filtered[filtered['所属指数'] == state['selected_index']]

        if state['selected_action'] != 'all':
            filtered = filtered[filtered['调入调出'] == state['selected_action']]

        # 估值档位筛选
        if state['selected_level'] != 'all':
            if state['selected_level'] == '低估':
                filtered = filtered[(filtered['动态PE'] > 0) & (filtered['动态PE'] < 15)]
            elif state['selected_level'] == '合理':
                filtered = filtered[(filtered['动态PE'] >= 15) & (filtered['动态PE'] < 30)]
            elif state['selected_level'] == '偏高':
                filtered = filtered[(filtered['动态PE'] >= 30) & (filtered['动态PE'] < 50)]
            elif state['selected_level'] == '高估':
                filtered = filtered[filtered['动态PE'] >= 50]

        # 行业历史PE分位筛选（替换原 PE溢价率 筛选）
        if state['selected_percentile'] != 'all':
            pct_valid = filtered['PE分位'].notna()
            if state['selected_percentile'] == '低估':
                filtered = filtered[pct_valid & (filtered['PE分位'] < 20)]
            elif state['selected_percentile'] == '偏低':
                filtered = filtered[pct_valid & (filtered['PE分位'] >= 20) & (filtered['PE分位'] < 50)]
            elif state['selected_percentile'] == '偏高':
                filtered = filtered[pct_valid & (filtered['PE分位'] >= 50) & (filtered['PE分位'] < 80)]
            elif state['selected_percentile'] == '高估':
                filtered = filtered[pct_valid & (filtered['PE分位'] >= 80)]

        return filtered

    def render_charts(df):
        """渲染图表"""
        if not chart_container or df.empty:
            return

        chart_container.clear()

        # 准备数据
        pe_filtered = df[(df['动态PE'] > 0) & (df['动态PE'] <= 500)]
        pe_values = pe_filtered['动态PE'].tolist()

        with chart_container:
            # ====== 调入 vs 调出 对比图表 ======
            with ui.card().classes('w-full p-6 bg-white rounded-2xl shadow-sm border border-slate-100 mb-4'):
                ui.label('调入 vs 调出 估值对比').classes('text-base font-bold text-slate-800 mb-1')
                ui.label('直观展示本次指数调整的估值变化方向').classes('text-xs text-slate-400 mb-4')

                with ui.row().classes('w-full gap-6 items-stretch flex-col md:flex-row'):
                    # 调入侧
                    _render_action_card('调入', df, 'emerald', 'trending_flat', 'arrow_downward', '低估值标的进入')
                    # 调出侧
                    _render_action_card('调出', df, 'rose', 'trending_down', 'arrow_upward', '高估值标的退出')

                # 指数调整逻辑提示
                with ui.element('div').classes('w-full mt-4 p-3 rounded-lg bg-slate-50 border border-slate-200'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('lightbulb', size='sm', color='amber')
                        ui.label(_generate_logic_text(df)).classes('text-xs text-slate-600')

            # ====== 指数PE分布对比 + 估值分布 ======
            with ui.row().classes('w-full gap-4 flex-col lg:flex-row mb-4 items-stretch'):
                with ui.card().classes('flex-1 p-5 bg-white rounded-2xl shadow-sm border border-slate-100 flex flex-col'):
                    with ui.row().classes('w-full items-center justify-between mb-1'):
                        ui.label('各指数估值水平对比').classes('text-sm font-bold text-slate-700')
                        ui.badge('误差线 = Q1~Q3', color='slate').props('dense outline')
                    ui.label('中位数PE越高表示该指数整体估值越贵').classes('text-xs text-slate-400 mb-3')

                    _render_index_comparison(df)

                    # 下方添加指数详细统计
                    _render_index_stats(df)

                with ui.card().classes('flex-1 p-5 bg-white rounded-2xl shadow-sm border border-slate-100 flex flex-col'):
                    with ui.row().classes('w-full items-center justify-between mb-1'):
                        ui.label('估值分布区间').classes('text-sm font-bold text-slate-700')
                        ui.badge('点击档位查看股票', color='indigo').props('dense outline')
                    ui.label('低估/合理/偏高三档划分').classes('text-xs text-slate-400 mb-3')

                    _render_pe_distribution(df)
                    # 股票列表
                    _render_level_stocks(df)

            # ====== PE分位分析（基于行业历史） ======
            with ui.card().classes('w-full p-6 bg-white rounded-2xl shadow-sm border border-slate-100'):
                with ui.row().classes('w-full items-center justify-between mb-1'):
                    ui.label('行业历史PE分位分布').classes('text-base font-bold text-slate-800')
                    ui.badge('分位 = 当前PE在所属申万一级行业过去N年日频PE序列中的位置', color='indigo').props('outline')
                ui.label('<20% 偏低估 | 20-50% 偏低 | 50-80% 偏高 | ≥80% 高估').classes('text-xs text-slate-400 mb-4')

                _render_percentile_distribution(df)

    def _render_action_card(action, df, color, icon_name, trend_icon, hint_text):
        """渲染调入/调出对比卡片"""
        action_data = df[(df['调入调出'] == action) & (df['动态PE'] > 0)]
        if action_data.empty:
            return

        count = len(action_data)
        median_pe = action_data['动态PE'].median()
        avg_pe = action_data['动态PE'].mean()
        # 板块PE中位数
        sector_pe = action_data['板块PE'].median()

        # 估值档位
        if median_pe < 15:
            level = '低估'
            level_color = 'emerald'
        elif median_pe < 30:
            level = '合理'
            level_color = 'sky'
        elif median_pe < 50:
            level = '偏高'
            level_color = 'amber'
        else:
            level = '高估'
            level_color = 'rose'

        color_map = {
            'emerald': {
                'bg': 'bg-gradient-to-br from-emerald-50 to-white',
                'border': 'border-emerald-200',
                'text': 'text-emerald-700',
                'accent': 'bg-emerald-500',
            },
            'rose': {
                'bg': 'bg-gradient-to-br from-rose-50 to-white',
                'border': 'border-rose-200',
                'text': 'text-rose-700',
                'accent': 'bg-rose-500',
            },
        }
        c = color_map[color]

        with ui.card().classes(f'flex-1 p-5 {c["bg"]} rounded-xl border {c["border"]} relative overflow-hidden'):
            # 装饰圆
            ui.element('div').classes(f'absolute -right-6 -top-6 w-24 h-24 rounded-full {c["accent"]} opacity-10')

            with ui.column().classes('relative z-10 gap-3'):
                # 标题行
                with ui.row().classes('items-center gap-2'):
                    ui.icon(icon_name, size='sm').classes(c['text'])
                    ui.label(action).classes(f'text-sm font-bold {c["text"]}')
                    ui.badge(level, color=level_color).props('dense')

                # 主数值
                with ui.row().classes('items-baseline gap-1'):
                    ui.label(f'{median_pe:.1f}').classes(f'text-4xl font-bold {c["text"]}')
                    ui.label('倍').classes('text-sm text-slate-500')

                # 副指标
                with ui.row().classes('w-full gap-4 mt-1'):
                    with ui.column().classes('gap-0'):
                        ui.label('平均PE').classes('text-[10px] text-slate-400')
                        ui.label(f'{avg_pe:.1f}').classes('text-sm font-bold text-slate-700')

                    with ui.column().classes('gap-0'):
                        ui.label('板块PE').classes('text-[10px] text-slate-400')
                        ui.label(f'{sector_pe:.1f}' if sector_pe > 0 else '—').classes('text-sm font-bold text-slate-700')

                    with ui.column().classes('gap-0'):
                        ui.label('数量').classes('text-[10px] text-slate-400')
                        ui.label(f'{count}只').classes('text-sm font-bold text-slate-700')

                # 提示
                ui.separator().classes('my-1')
                with ui.row().classes('items-center gap-1'):
                    ui.icon(trend_icon, size='xs').classes(c['text'])
                    ui.label(hint_text).classes('text-[11px] text-slate-500')

    def _render_index_comparison(df):
        """指数估值对比 - 柱状图（中位数 + Q1/Q3范围）"""
        indices = [d['name'] for d in INDEX_DEFS]
        colors = [d['bar'] for d in INDEX_DEFS]

        # 计算统计数据
        medians = []
        q1s = []
        q3s = []
        counts = []
        labels = []
        bar_colors = []

        for i, idx_name in enumerate(indices):
            idx_data = df[(df['所属指数'] == idx_name) & (df['动态PE'] > 0) & (df['动态PE'] <= 200)]['动态PE']
            if not idx_data.empty:
                medians.append(idx_data.median())
                q1s.append(idx_data.quantile(0.25))
                q3s.append(idx_data.quantile(0.75))
                counts.append(len(idx_data))
                labels.append(idx_name.replace('指数', ''))
                bar_colors.append(colors[i])

        if not medians:
            ui.label('暂无指数对比数据').classes('text-slate-400 text-sm py-8')
            return

        fig = go.Figure()

        # 添加Q1-Q3范围（误差棒形式）
        fig.add_trace(go.Bar(
            x=labels,
            y=medians,
            marker_color=bar_colors,
            text=[f'{m:.1f}' for m in medians],
            textposition='outside',
            textfont=dict(size=14, color='#1e293b', family='ui-monospace, monospace'),
            error_y=dict(
                type='data',
                symmetric=False,
                array=[q3 - m for q3, m in zip(q3s, medians)],
                arrayminus=[m - q1 for m, q1 in zip(medians, q1s)],
                color='#94a3b8',
                thickness=2,
                width=8,
            ),
            hovertemplate='<b>%{x}</b><br>中位数PE: %{y:.1f}<br>样本数: %{customdata}<extra></extra>',
            customdata=counts,
        ))

        # 添加参考线
        fig.add_hline(y=15, line_dash="dot", line_color="#22c55e", line_width=1,
                      annotation_text="低估线(15)", annotation_position="right",
                      annotation_font_size=10, annotation_textangle=-90)
        fig.add_hline(y=30, line_dash="dot", line_color="#f59e0b", line_width=1,
                      annotation_text="合理线(30)", annotation_position="right",
                      annotation_font_size=10, annotation_textangle=-90)
        fig.add_hline(y=50, line_dash="dot", line_color="#ef4444", line_width=1,
                      annotation_text="高估线(50)", annotation_position="right",
                      annotation_font_size=10, annotation_textangle=-90)

        fig.update_layout(
            margin=dict(l=10, r=80, t=20, b=30),
            height=280,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            yaxis=dict(
                showgrid=True, gridcolor='#f1f5f9',
                title=dict(text='动态PE', font=dict(size=11)),
                range=[0, max(medians) * 1.4 if max(medians) > 0 else 50],
            ),
            xaxis=dict(title='', tickfont=dict(size=12, color='#475569')),
            showlegend=False,
            bargap=0.5,
        )

        chart_div = ui.element('div').classes('w-full relative').style('height: 240px')
        with chart_div:
            plotly_renderer(fig).classes('w-full absolute inset-0')

        # 下方添加图例说明
        with ui.row().classes('w-full justify-center gap-4 mt-1 text-[10px] text-slate-500'):
            ui.label('柱顶 = 中位数PE').classes('')
            with ui.row().classes('items-center gap-1'):
                ui.element('div').classes('w-3 h-0.5 bg-slate-400')
                ui.label('误差线 = Q1~Q3区间（50%数据）')

    def _render_index_stats(df):
        """指数详细统计"""
        indices = [d['name'] for d in INDEX_DEFS]
        colors = {d['name']: d for d in INDEX_DEFS}
        # 默认配色（兜底）
        default_color = INDEX_DEFS[0]

        with ui.column().classes('w-full gap-2 mt-3'):
            for idx_name in indices:
                idx_data = df[(df['所属指数'] == idx_name) & (df['动态PE'] > 0)]
                if idx_data.empty:
                    continue

                median_pe = idx_data['动态PE'].median()
                max_pe = idx_data['动态PE'].max()
                min_pe = idx_data['动态PE'].min()
                count = len(idx_data)
                c = colors.get(idx_name, default_color)

                # 估值档位
                if median_pe < 15:
                    badge_text = '低估'
                    badge_color = 'emerald'
                elif median_pe < 30:
                    badge_text = '合理'
                    badge_color = 'sky'
                elif median_pe < 50:
                    badge_text = '偏高'
                    badge_color = 'amber'
                else:
                    badge_text = '高估'
                    badge_color = 'rose'

                with ui.row().classes(f'w-full items-center gap-2 p-2 rounded-lg {c["bg"]} border {c["border"]}'):
                    # 指数名称
                    ui.label(idx_name.replace('指数', '')).classes(f'text-xs font-bold {c["text"]} min-w-[50px]')

                    # 档位标签
                    ui.badge(badge_text, color=badge_color).props('dense')

                    # 中位数
                    with ui.column().classes('flex-1 items-center gap-0'):
                        ui.label('中位数').classes('text-[9px] text-slate-400')
                        ui.label(f'{median_pe:.1f}').classes(f'text-sm font-bold {c["text"]}').style('font-family: ui-monospace, monospace')

                    # 范围
                    with ui.column().classes('flex-1 items-center gap-0'):
                        ui.label('区间').classes('text-[9px] text-slate-400')
                        ui.label(f'{min_pe:.0f}~{max_pe:.0f}').classes('text-xs text-slate-600').style('font-family: ui-monospace, monospace')

                    # 数量
                    with ui.column().classes('items-end gap-0'):
                        ui.label('样本').classes('text-[9px] text-slate-400')
                        ui.label(f'{count}只').classes('text-xs font-medium text-slate-600')

    def _render_pe_distribution(df):
        """PE估值分布图（区间统计）"""
        valid = df[(df['动态PE'] > 0) & (df['动态PE'] <= 500)]
        if valid.empty:
            ui.label('暂无数据').classes('text-slate-400 text-sm py-8')
            return

        # 区间统计
        ranges = [
            ('低估', 0, 15, '#10b981', 'bg-emerald-500'),
            ('合理', 15, 30, '#3b82f6', 'bg-blue-500'),
            ('偏高', 30, 50, '#f59e0b', 'bg-amber-500'),
            ('高估', 50, 500, '#ef4444', 'bg-rose-500'),
        ]

        total = len(valid)
        with ui.column().classes('w-full gap-2'):
            for name, low, high, color, bg_class in ranges:
                count = len(valid[(valid['动态PE'] >= low) & (valid['动态PE'] < high if high < 200 else valid['动态PE'] >= low)])
                pct = count / total * 100
                is_selected = state['selected_level_view'] == name

                # 可点击的档位行
                with ui.element('div').classes(
                    f'w-full p-2 rounded-lg cursor-pointer transition-all {"ring-2 ring-indigo-400 bg-indigo-50/50" if is_selected else "hover:bg-slate-50"} border border-transparent'
                ).on('click', lambda n=name: on_level_view_change(n)):
                    with ui.column().classes('w-full gap-1'):
                        with ui.row().classes('w-full items-center justify-between'):
                            with ui.row().classes('items-center gap-2'):
                                ui.element('div').classes(f'w-3 h-3 rounded-full {bg_class}')
                                ui.label(f'{name}（{low}-{high if high < 200 else "+"}）').classes(f'text-sm font-medium {"text-indigo-700" if is_selected else "text-slate-700"}')
                                if is_selected:
                                    ui.icon('check_circle', size='xs', color='indigo')
                            with ui.row().classes('items-center gap-2'):
                                ui.label(f'{count}只').classes('text-xs text-slate-500')
                                ui.label(f'{pct:.0f}%').classes(f'text-sm font-bold').style(f'color: {color}')

                        # 进度条
                        with ui.element('div').classes('w-full h-2 bg-slate-100 rounded-full overflow-hidden'):
                            ui.element('div').classes(f'h-full {bg_class} transition-all').style(f'width: {pct}%')

            # 提示
            ui.separator().classes('my-1')
            with ui.row().classes('items-center gap-2'):
                ui.icon('info', size='xs', color='slate')
                ui.label(f'共 {total} 只有效PE数据').classes('text-[10px] text-slate-400')

    def _render_level_stocks(df):
        """渲染选中档位的股票列表"""
        level = state['selected_level_view']
        ranges = {
            '低估': (0, 15),
            '合理': (15, 30),
            '偏高': (30, 50),
            '高估': (50, 500),
        }
        low, high = ranges.get(level, (0, 15))

        # 获取该档位股票
        if high >= 500:
            level_stocks = df[(df['动态PE'] >= low) & (df['动态PE'] > 0)]
        else:
            level_stocks = df[(df['动态PE'] >= low) & (df['动态PE'] < high) & (df['动态PE'] > 0)]

        # 按PE升序
        level_stocks = level_stocks.sort_values('动态PE').head(8)

        # 档位主题色
        color_map = {
            '低估': {'text': 'text-emerald-600', 'bg': 'bg-emerald-50', 'border': 'border-emerald-200', 'icon': 'trending_down'},
            '合理': {'text': 'text-sky-600', 'bg': 'bg-sky-50', 'border': 'border-sky-200', 'icon': 'balance'},
            '偏高': {'text': 'text-amber-600', 'bg': 'bg-amber-50', 'border': 'border-amber-200', 'icon': 'trending_up'},
            '高估': {'text': 'text-rose-600', 'bg': 'bg-rose-50', 'border': 'border-rose-200', 'icon': 'warning'},
        }
        c = color_map[level]

        with ui.element('div').classes(f'w-full mt-3 p-3 rounded-xl {c["bg"]} border {c["border"]}'):
            with ui.row().classes('w-full items-center justify-between mb-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon(c['icon'], size='xs').classes(c['text'])
                    ui.label(f'{level}档位').classes(f'text-xs font-bold {c["text"]}')
                ui.label(f'共{len(df[(df["动态PE"] >= low) & (df["动态PE"] < high if high < 500 else df["动态PE"] >= low) & (df["动态PE"] > 0)])}只').classes('text-[10px] text-slate-500')

            if level_stocks.empty:
                with ui.row().classes('w-full justify-center py-4'):
                    ui.label('该档位暂无股票').classes('text-xs text-slate-400')
            else:
                with ui.column().classes('w-full gap-1'):
                    for _, stock in level_stocks.iterrows():
                        pe = stock.get('动态PE', 0)
                        action = stock.get('调入调出', '')
                        action_color = {'调入': 'text-emerald-600', '调出': 'text-rose-600', '备选': 'text-amber-600'}.get(action, 'text-slate-500')

                        with ui.row().classes('w-full items-center gap-2 py-1.5 px-2 rounded hover:bg-white/50 transition-colors'):
                            # 名称
                            ui.label(stock.get('股票名称', '')).classes('text-xs font-bold text-slate-700 flex-1 truncate')
                            # 状态
                            ui.label(action).classes(f'text-[10px] {action_color} font-medium min-w-[24px]')
                            # PE
                            ui.label(f'{pe:.1f}').classes(f'text-xs font-bold {c["text"]} tabular-nums').style('font-family: ui-monospace, monospace')

    def _render_percentile_distribution(df):
        """PE历史分位分布 - 按行业历史PE分位档位统计（替换原 PE溢价率分布）"""
        pct_valid = df[df['PE分位'].notna()]
        if pct_valid.empty:
            with ui.column().classes('w-full items-center justify-center py-8 gap-2'):
                ui.icon('analytics', size='2rem', color='slate-300')
                ui.label('行业历史PE分位缓存未生成').classes('text-slate-500 text-sm')
                ui.label('请在终端运行：python scripts/build_sector_pe_history.py').classes('text-slate-400 text-xs font-mono')
            return

        # 4档分位（与 PETracker.PERCENTILE_LEVELS 对齐）
        ranges = [
            ('低估', 0, 20,  '#10b981', 'bg-emerald-500', 'text-emerald-700'),
            ('偏低', 20, 50, '#3b82f6', 'bg-blue-500',    'text-blue-700'),
            ('偏高', 50, 80, '#f59e0b', 'bg-amber-500',   'text-amber-700'),
            ('高估', 80, 100,'#ef4444', 'bg-rose-500',    'text-rose-700'),
        ]

        total = len(pct_valid)
        with ui.column().classes('w-full gap-2'):
            for name, low, high, color, bg_class, text_class in ranges:
                level_stocks = pct_valid[(pct_valid['PE分位'] >= low) & (pct_valid['PE分位'] < high)]
                count = len(level_stocks)
                pct = count / total * 100

                with ui.element('div').classes(
                    f'w-full p-3 rounded-lg cursor-pointer transition-all hover:bg-slate-50 hover:shadow-sm border border-transparent hover:border-slate-200'
                ).on('click', lambda n=name, l=low, h=high, s=level_stocks: show_percentile_detail(n, l, h, s)):
                    with ui.column().classes('w-full gap-1'):
                        with ui.row().classes('w-full items-center justify-between'):
                            with ui.row().classes('items-center gap-2'):
                                ui.element('div').classes(f'w-3 h-3 rounded-full {bg_class}')
                                ui.label(f'{name}（{low}%-{high if high<100 else "100%"}）').classes(f'text-sm font-medium {text_class}')
                                ui.icon('chevron_right', size='xs', color='slate-400')
                            with ui.row().classes('items-center gap-2'):
                                ui.label(f'{count}只').classes('text-xs text-slate-600')
                                ui.label(f'{pct:.0f}%').classes('text-sm font-bold').style(f'color: {color}')

                        # 进度条
                        with ui.element('div').classes('w-full h-2 bg-slate-100 rounded-full overflow-hidden'):
                            ui.element('div').classes(f'h-full {bg_class} transition-all').style(f'width: {pct}%')

            # 提示
            ui.separator().classes('my-2')
            with ui.row().classes('items-center gap-2'):
                ui.icon('info', size='xs', color='slate')
                ui.label(f'共 {total} 只股票有分位数据 | 点击档位查看明细').classes('text-[11px] text-slate-400')

    def show_percentile_detail(name, low, high, stocks):
        """显示分位档位详情弹窗（替换原 PE溢价率 弹窗）"""
        color_map = {
            '低估': 'emerald',
            '偏低': 'blue',
            '偏高': 'amber',
            '高估': 'rose',
        }
        color = color_map.get(name, 'slate')

        with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl'):
            # 标题栏
            with ui.row().classes('w-full items-center justify-between p-4 border-b border-slate-100'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('list_alt', color=color).classes('text-xl')
                    with ui.column().classes('gap-0'):
                        ui.label(name).classes(f'text-lg font-bold text-{color}-700')
                        ui.label(f'PE分位 {low}% ~ {high}% | 共 {len(stocks)} 只股票').classes('text-xs text-slate-500')
                ui.button(icon='close', on_click=dialog.close).props('flat round dense')

            # 表格
            with ui.element('div').classes('w-full p-4 max-h-[500px] overflow-auto'):
                if stocks.empty:
                    ui.label('该档位暂无股票').classes('text-slate-400 text-sm py-8 text-center')
                else:
                    rows = []
                    for _, row in stocks.iterrows():
                        pe_dynamic = row.get('动态PE', 0)
                        pe_pct = row.get('PE分位', None)
                        if pe_pct is None or (hasattr(pd, 'isna') and pd.isna(pe_pct)):
                            pct_color = '#94a3b8'
                            pct_display = '—'
                        else:
                            if pe_pct >= 80:
                                pct_color = '#dc2626'
                            elif pe_pct >= 50:
                                pct_color = '#f59e0b'
                            elif pe_pct >= 20:
                                pct_color = '#3b82f6'
                            else:
                                pct_color = '#16a34a'
                            pct_display = round(float(pe_pct), 1)

                        action = row.get('调入调出', '')
                        action_colors = {'调入': '#059669', '调出': '#dc2626', '备选': '#d97706'}

                        rows.append({
                            'code': row.get('股票编码', ''),
                            'name': row.get('股票名称', ''),
                            'action': action,
                            'action_color': action_colors.get(action, '#64748b'),
                            'index': row.get('所属指数', '').replace('指数', ''),
                            'sector_name': row.get('所属板块', ''),
                            'pe_dynamic': round(pe_dynamic, 2) if pe_dynamic else 0,
                            'pe_percentile': pct_display,
                            'pct_color': pct_color,
                        })

                    def _sort_key(x):
                        v = x['pe_percentile']
                        return v if isinstance(v, (int, float)) else -1
                    rows.sort(key=_sort_key, reverse=True)

                    column_defs = [
                        {'headerName': '代码', 'field': 'code', 'width': 85, 'pinned': 'left',
                         'cellStyle': {'fontWeight': '500'}},
                        {'headerName': '名称', 'field': 'name', 'width': 90, 'pinned': 'left',
                         'cellStyle': {'fontWeight': '600'}},
                        {'headerName': '状态', 'field': 'action', 'width': 65,
                         'cellRenderer': "function(params) { return '<span style=\"color:'+params.data.action_color+';font-weight:600\">'+params.value+'</span>'; }"},
                        {'headerName': '指数', 'field': 'index', 'width': 70, 'cellStyle': {'fontSize': '12px'}},
                        {'headerName': '所属板块', 'field': 'sector_name', 'width': 100, 'cellStyle': {'fontSize': '12px'}},
                        {'headerName': '个股PE', 'field': 'pe_dynamic', 'width': 80,
                         'cellStyle': {'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600'}},
                        {'headerName': 'PE分位', 'field': 'pe_percentile', 'width': 95, 'sort': 'desc',
                         'cellRenderer': "function(params) { if(params.value==='—') return '<span style=\"color:#94a3b8;font-family:monospace\">—</span>'; return '<span style=\"color:'+params.data.pct_color+';font-weight:600;font-family:monospace\">'+params.value.toFixed(1)+'%</span>'; }"},
                    ]

                    ui.aggrid({
                        'columnDefs': column_defs,
                        'rowData': rows,
                        'defaultColDef': {'resizable': True},
                        'rowSelection': 'single',
                        'animateRows': True,
                        'suppressCellFocus': True,
                    }).classes('w-full h-[420px]')

        dialog.open()

    def _generate_logic_text(df):
        """生成指数调整逻辑提示"""
        valid = df[df['动态PE'] > 0]
        in_data = valid[valid['调入调出'] == '调入']
        out_data = valid[valid['调入调出'] == '调出']

        if in_data.empty or out_data.empty:
            return '本次调整涉及调入和调出两类股票，可对比其估值差异。'

        in_pe = in_data['动态PE'].median()
        out_pe = out_data['动态PE'].median()
        diff_pct = (out_pe - in_pe) / in_pe * 100

        if diff_pct > 30:
            return f'本次调整呈现"高剔低纳"特征：调出标的估值({out_pe:.1f})显著高于调入({in_pe:.1f})，差{diff_pct:.0f}%。'
        elif diff_pct < -30:
            return f'本次调整方向相反：调入标的({in_pe:.1f})估值反而高于调出({out_pe:.1f})，差{abs(diff_pct):.0f}%。'
        else:
            return f'本次调整的估值差异较小：调入({in_pe:.1f})与调出({out_pe:.1f})中位数PE接近。'

    def render_table(df=None):
        """渲染表格"""
        if not table_container:
            return

        table_container.clear()

        if df is None:
            df = filter_data()

        if df.empty:
            with table_container:
                with ui.column().classes('w-full items-center justify-center py-16'):
                    ui.icon('inbox', size='3rem', color='slate-300')
                    ui.label('暂无数据').classes('text-slate-400 mt-2')
            return

        # 准备表格数据
        rows = []
        for _, row in df.iterrows():
            pe_dynamic = row.get('动态PE', 0)
            sector_pe = row.get('板块PE', 0)

            # 估值档位（按绝对PE值，与行业历史分位档位互为补充）
            level = '—'
            level_bg = '#f1f5f9'
            level_color = '#64748b'
            if pe_dynamic > 0:
                if pe_dynamic < 15:
                    level = '低估'
                    level_bg = '#dcfce7'
                    level_color = '#15803d'
                elif pe_dynamic < 30:
                    level = '合理'
                    level_bg = '#dbeafe'
                    level_color = '#1d4ed8'
                elif pe_dynamic < 50:
                    level = '偏高'
                    level_bg = '#fef3c7'
                    level_color = '#b45309'
                else:
                    level = '高估'
                    level_bg = '#fee2e2'
                    level_color = '#b91c1c'

            action = row.get('调入调出', '')
            action_styles = {
                '调入': {'color': '#059669', 'bg': '#ecfdf5', 'border': '#a7f3d0'},
                '调出': {'color': '#dc2626', 'bg': '#fef2f2', 'border': '#fecaca'},
                '备选': {'color': '#d97706', 'bg': '#fffbeb', 'border': '#fde68a'},
            }
            action_style = action_styles.get(action, {'color': '#64748b', 'bg': '#f8fafc', 'border': '#e2e8f0'})

            # PB 规范化：缺失/0 → None（与下方 pe_pct 块同模式）
            pb_raw = row.get('PB', None)
            pb_val = round(float(pb_raw), 2) if (pb_raw is not None and pb_raw > 0) else None

            # 历史PE分位（None 时显示 '—'，并打灰色）
            pe_pct = row.get('PE分位', None)
            if pe_pct is None or (hasattr(pd, 'isna') and pd.isna(pe_pct)):
                pct_color = '#94a3b8'
                pct_display = '—'
                pct_level = '—'
                pct_level_bg = '#f1f5f9'
                pct_level_color = '#94a3b8'
            else:
                pct_val = float(pe_pct)
                if pct_val >= 80:
                    pct_color = '#dc2626'
                    pct_level, pct_level_bg, pct_level_color = '高估', '#fee2e2', '#b91c1c'
                elif pct_val >= 50:
                    pct_color = '#f59e0b'
                    pct_level, pct_level_bg, pct_level_color = '偏高', '#fef3c7', '#b45309'
                elif pct_val >= 20:
                    pct_color = '#3b82f6'
                    pct_level, pct_level_bg, pct_level_color = '偏低', '#dbeafe', '#1d4ed8'
                else:
                    pct_color = '#16a34a'
                    pct_level, pct_level_bg, pct_level_color = '低估', '#dcfce7', '#15803d'
                pct_display = round(pct_val, 1)

            rows.append({
                'code': row.get('股票编码', ''),
                'name': row.get('股票名称', ''),
                'index': row.get('所属指数', '').replace('指数', ''),
                'action': action,
                'price': f"{row.get('最新价', 0):.2f}",
                'pe_dynamic': round(pe_dynamic, 2) if pe_dynamic else 0,
                'level': level,
                'level_bg': level_bg,
                'level_color': level_color,
                'sector_name': row.get('所属板块', ''),
                'sector_pe': round(sector_pe, 2) if sector_pe else 0,
                'pe_percentile': pct_display,
                'pct_color': pct_color,
                'pct_level': pct_level,
                'pct_level_bg': pct_level_bg,
                'pct_level_color': pct_level_color,
                'pb': pb_val,
                'market_cap': round(row.get('总市值', 0) / 1e8, 2) if row.get('总市值', 0) else 0,
                'action_color': action_style['color'],
                'action_bg': action_style['bg'],
            })

        column_defs = [
            {'headerName': '代码', 'field': 'code', 'sortable': True, 'filter': True, 'width': 85, 'pinned': 'left',
             'cellStyle': {'fontWeight': '500', 'fontSize': '13px'},
             'headerClass': 'pe-grid-header'},
            {'headerName': '名称', 'field': 'name', 'sortable': True, 'filter': True, 'width': 90, 'pinned': 'left',
             'cellStyle': {'fontWeight': '600', 'fontSize': '13px'},
             'headerClass': 'pe-grid-header'},
            {'headerName': '指数', 'field': 'index', 'sortable': True, 'filter': True, 'width': 70,
             'cellStyle': {'fontSize': '12px', 'color': '#64748b'},
             'headerClass': 'pe-grid-header'},
            {'headerName': '状态', 'field': 'action', 'sortable': True, 'filter': True, 'width': 65,
             'cellRenderer': "function(params) { return '<span style=\"background:'+params.data.action_bg+';color:'+params.data.action_color+';padding:3px 8px;border-radius:4px;font-size:12px;font-weight:600\">'+params.value+'</span>'; }",
             'headerClass': 'pe-grid-header'},
            {'headerName': '最新价', 'field': 'price', 'sortable': True, 'width': 75,
             'cellStyle': {'textAlign': 'right', 'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace', 'fontSize': '13px'},
             'headerClass': 'pe-grid-header'},
            {'headerName': '动态PE', 'field': 'pe_dynamic', 'sortable': True, 'width': 80, 'sort': 'asc',
             'cellStyle': {'textAlign': 'right', 'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace', 'fontWeight': '600', 'fontSize': '13px'},
             'headerClass': 'pe-grid-header'},
            {'headerName': '档位', 'field': 'level', 'sortable': True, 'filter': True, 'width': 70,
             'cellRenderer': "function(params) { return '<span style=\"background:'+params.data.level_bg+';color:'+params.data.level_color+';padding:3px 8px;border-radius:4px;font-size:12px;font-weight:600\">'+params.value+'</span>'; }",
             'headerClass': 'pe-grid-header'},
            {'headerName': '所属板块', 'field': 'sector_name', 'sortable': True, 'filter': True, 'width': 100,
             'cellStyle': {'fontSize': '12px', 'color': '#475569'},
             'headerClass': 'pe-grid-header'},
            {'headerName': '板块PE', 'field': 'sector_pe', 'sortable': True, 'width': 80,
             'cellStyle': {'textAlign': 'right', 'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace', 'color': '#6366f1', 'fontWeight': '500', 'fontSize': '13px'},
             'headerClass': 'pe-grid-header'},
            {'headerName': 'PE分位', 'field': 'pe_percentile', 'sortable': True, 'width': 90, 'sort': 'desc',
             'cellRenderer': "function(params) { if(params.value==='\u2014') return '<span style=\"color:#94a3b8;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,monospace;font-size:13px\">\u2014</span>'; var color = params.data.pct_color; return '<span style=\"color:'+color+';font-weight:600;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,monospace;font-size:13px\">'+params.value.toFixed(1)+'%</span>'; }",
             'headerClass': 'pe-grid-header'},
            {'headerName': '档位', 'field': 'pct_level', 'sortable': True, 'filter': True, 'width': 70,
             'cellRenderer': "function(params) { return '<span style=\"background:'+params.data.pct_level_bg+';color:'+params.data.pct_level_color+';padding:3px 8px;border-radius:4px;font-size:12px;font-weight:600\">'+params.value+'</span>'; }",
             'headerClass': 'pe-grid-header'},
            {'headerName': 'PB', 'field': 'pb', 'sortable': True, 'width': 65,
             'cellStyle': {'textAlign': 'right', 'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace', 'fontSize': '13px'},
             'cellRenderer': "function(params) { if(params.value === null || params.value === undefined) return '<span style=\"color:#94a3b8\">—</span>'; return params.value.toFixed(2); }",
             'headerClass': 'pe-grid-header',
             'headerTooltip': '市净率 PB = 股价 / 每股净资产（数据缺失显示 —）'},
            {'headerName': '总市值(亿)', 'field': 'market_cap', 'sortable': True, 'width': 100,
             'cellStyle': {'textAlign': 'right', 'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace', 'fontSize': '13px'},
             'headerClass': 'pe-grid-header'},
        ]

        with table_container:
            ui.aggrid({
                'columnDefs': column_defs,
                'rowData': rows,
                'pagination': True,
                'paginationPageSize': 50,
                'defaultColDef': {'resizable': True, 'filter': True, 'sortable': True},
                'rowSelection': 'single',
                'animateRows': True,
                'suppressCellFocus': True,
            }).classes('w-full h-full border-none pe-table').style('font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;')

        # 添加表头样式
        ui.add_head_html('''
            <style>
            .pe-table .ag-header {
                background: linear-gradient(90deg, #eef2ff 0%, #f5f3ff 100%) !important;
                border-bottom: 2px solid #c7d2fe !important;
            }
            .pe-table .ag-header-cell-text {
                font-size: 12px !important;
                font-weight: 700 !important;
                color: #4338ca !important;
                letter-spacing: 0.025em !important;
            }
            .pe-table .ag-row {
                border-bottom: 1px solid #f1f5f9 !important;
            }
            .pe-table .ag-row:hover {
                background-color: #f8fafc !important;
            }
            .pe-table .ag-cell {
                display: flex !important;
                align-items: center !important;
                line-height: 1.5 !important;
            }
            .pe-table .ag-paging-panel {
                font-size: 12px !important;
                color: #475569 !important;
            }
            </style>
        ''')

    def on_index_change(value):
        state['selected_index'] = value
        filtered = filter_data()
        update_insights(filtered)
        render_charts(filtered)
        render_table(filtered)

    def on_action_change(value):
        state['selected_action'] = value
        filtered = filter_data()
        update_insights(filtered)
        render_charts(filtered)
        render_table(filtered)

    def on_level_change(value):
        state['selected_level'] = value
        filtered = filter_data()
        update_insights(filtered)
        render_charts(filtered)
        render_table(filtered)

    def on_percentile_change(value):
        state['selected_percentile'] = value
        filtered = filter_data()
        update_insights(filtered)
        render_charts(filtered)
        render_table(filtered)

    def on_level_view_change(level):
        state['selected_level_view'] = level
        filtered = filter_data()
        render_charts(filtered)

    def export_to_excel():
        """导出成分股明细到Excel"""
        df = filter_data()
        if df.empty:
            ui.notify('没有数据可导出', type='warning')
            return

        # 获取当前日期
        data_date = datetime.datetime.now().strftime('%Y-%m-%d')

        # 准备导出数据
        export_df = df[['股票编码', '股票名称', '所属指数', '调入调出', '最新价',
                        '动态PE', '静态PE', '所属板块', '板块PE', 'PE分位',
                        'PB', '总市值']].copy()

        # 添加估值档位列
        def get_level(pe):
            if pe <= 0:
                return '无效'
            elif pe < 15:
                return '低估'
            elif pe < 30:
                return '合理'
            elif pe < 50:
                return '偏高'
            else:
                return '高估'

        export_df['估值档位'] = export_df['动态PE'].apply(get_level)
        export_df['数据日期'] = data_date
        export_df['总市值(亿)'] = (export_df['总市值'] / 1e8).round(2)
        export_df = export_df.drop('总市值', axis=1)

        # 重排列顺序
        export_df = export_df[['数据日期', '股票编码', '股票名称', '所属指数', '调入调出',
                               '最新价', '动态PE', '估值档位', '静态PE',
                               '所属板块', '板块PE', 'PE分位', 'PB', '总市值(亿)']]

        # 创建Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            export_df.to_excel(writer, sheet_name='成分股PE明细', index=False)
        output.seek(0)

        filename = f'成分股PE估值明细_{data_date}.xlsx'
        ui.download(output.getvalue(), filename=filename,
                    media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        ui.notify(f'已导出 {len(export_df)} 条数据', type='positive')

    # ========== UI Layout ==========

    # 顶部统一卡片 - 包含标题、洞察、筛选
    with ui.card().classes('w-full p-0 mb-4 rounded-2xl shadow-sm border border-slate-100 overflow-hidden'):
        # 头部标题区 - 浅色背景
        with ui.element('div').classes('w-full p-5 relative overflow-hidden').style(
            'background: linear-gradient(135deg, #eef2ff 0%, #f5f3ff 50%, #fdf4ff 100%); border-bottom: 1px solid #e0e7ff;'
        ):
            # 装饰圆
            ui.element('div').classes('absolute -right-20 -top-20 w-60 h-60 rounded-full').style(
                'background: radial-gradient(circle, rgba(99,102,241,0.15) 0%, transparent 70%);'
            )
            ui.element('div').classes('absolute -left-10 -bottom-10 w-40 h-40 rounded-full').style(
                'background: radial-gradient(circle, rgba(168,85,247,0.12) 0%, transparent 70%);'
            )

            with ui.row().classes('w-full items-center justify-between relative z-10 flex-wrap gap-3'):
                with ui.row().classes('items-center gap-3'):
                    with ui.element('div').classes('w-11 h-11 rounded-xl flex items-center justify-center').style(
                        'background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); box-shadow: 0 4px 12px rgba(99,102,241,0.3);'
                    ):
                        ui.icon('analytics', color='white').classes('text-lg')
                    with ui.column().classes('gap-0'):
                        ui.html('<span style="font-size: 1.35rem; font-weight: 700; background: linear-gradient(135deg, #4338ca 0%, #7c3aed 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">指数成分股PE估值跟踪</span>', sanitize=False)
                        ui.label('数据来源：Tushare Pro').classes('text-[10px] text-slate-500 mt-0.5')

                # 修复按钮颜色 - 使用Quasar color prop
                ui.button('刷新数据', icon='refresh', on_click=lambda: load_data(force=True))\
                    .props('outline color=indigo-dense').classes('text-indigo-600')

        # 核心洞察+筛选 合并区
        with ui.element('div').classes('w-full p-4 bg-white'):
            # 核心洞察
            with ui.row().classes('w-full items-center gap-3 mb-3 p-3 rounded-lg').style('background: linear-gradient(90deg, #eef2ff 0%, #f5f3ff 100%); border: 1px solid #e0e7ff;'):
                with ui.element('div').classes('w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0').style(
                    'background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);'
                ):
                    ui.icon('auto_awesome', color='white').classes('text-sm')
                ui.label('核心洞察').classes('text-[10px] text-indigo-600 font-bold tracking-wider uppercase')
                insight_label = ui.label('正在分析数据...').classes('text-sm text-slate-700 font-medium flex-1')

            # 筛选条件
            with ui.row().classes('w-full items-center gap-3 flex-wrap'):
                with ui.row().classes('items-center gap-1'):
                    ui.icon('tune', size='xs', color='slate-400')
                    ui.label('筛选').classes('text-xs font-medium text-slate-500')

                # 指数下拉：从 INDEX_DEFS 动态生成，保持与基础数据一致
                index_options = {'all': '全部指数'}
                index_options.update({d['name']: d['short'] for d in INDEX_DEFS})
                ui.select(
                    index_options,
                    value='all',
                    on_change=lambda e: on_index_change(e.value)
                ).props('dense outlined').classes('w-32 text-xs')

                ui.select(
                    {'all': '全部状态', '调入': '调入', '调出': '调出', '备选': '备选'},
                    value='all',
                    on_change=lambda e: on_action_change(e.value)
                ).props('dense outlined').classes('w-24 text-xs')

                ui.select(
                    {'all': '全部估值', '低估': '低估(<15)', '合理': '合理(15-30)', '偏高': '偏高(30-50)', '高估': '高估(>50)'},
                    value='all',
                    on_change=lambda e: on_level_change(e.value)
                ).props('dense outlined').classes('w-28 text-xs')

                ui.select(
                    {'all': '全部分位', '低估': '低估(<20%)', '偏低': '偏低(20-50%)', '偏高': '偏高(50-80%)', '高估': '高估(≥80%)'},
                    value='all',
                    on_change=lambda e: on_percentile_change(e.value)
                ).props('dense outlined').classes('w-28 text-xs')

    # 图表区域
    chart_container = ui.column().classes('w-full gap-4')

    # 表格区域
    with ui.card().classes('w-full p-0 bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden'):
        # 表格标题 - 优化字体
        with ui.row().classes('w-full px-5 py-4 border-b border-slate-100 justify-between items-center').style(
            'background: linear-gradient(90deg, #f8fafc 0%, #f1f5f9 100%);'
        ):
            with ui.row().classes('items-center gap-3'):
                with ui.element('div').classes('w-8 h-8 rounded-lg flex items-center justify-center').style(
                    'background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);'
                ):
                    ui.icon('table_chart', color='white').classes('text-base')
                with ui.column().classes('gap-0'):
                    ui.html('<span style="font-size: 1.05rem; font-weight: 700; color: #1e293b; letter-spacing: 0.025em;">成分股估值明细</span>', sanitize=False)
                    with ui.row().classes('items-center gap-1'):
                        ui.icon('event', size='2.5px', color='slate')
                        ui.label(f'数据日期: {datetime.datetime.now().strftime("%Y-%m-%d")}').classes('text-[10px] text-slate-500')

            # 导出按钮 - 与页面其他按钮风格一致（outline）
            ui.button('导出Excel', icon='file_download', on_click=export_to_excel)\
                .props('outline color=emerald dense').classes('text-emerald-600')

        # 表格容器 - 初始化占位，加载后由 render_table 填充
        table_container = ui.element('div').classes('w-full relative h-[640px]')
        with table_container:
            with ui.column().classes('w-full items-center justify-center py-16'):
                ui.spinner('dots', size='lg', color='indigo')
                ui.label('正在加载明细数据...').classes('text-slate-400 text-sm mt-2')

    # 触发加载
    ui.timer(0, load_data, once=True)
