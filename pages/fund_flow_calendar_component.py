from nicegui import ui
from utils.sector_grid_logic import get_sector_flow_history
import datetime
import asyncio


async def render_fund_flow_calendar(sector_name, cache_dir):
    flow_hist = await asyncio.get_event_loop().run_in_executor(
        None, lambda: get_sector_flow_history(sector_name, cache_dir, days=365)
    )
    if not flow_hist:
        return

    parsed_hist = []
    for item in flow_hist:
        try:
            item_date = datetime.datetime.strptime(str(item.get('date', '')), '%Y-%m-%d').date()
        except Exception:
            continue
        parsed_hist.append({
            'date': item_date,
            'ratio': float(item.get('ratio', 0) or 0),
            'inflow': float(item.get('inflow', 0) or 0),
        })

    if not parsed_hist:
        return

    latest_day = max(parsed_hist, key=lambda x: x['date'])
    latest_date = latest_day['date']
    flow_by_date = {item['date']: item for item in parsed_hist}
    month_keys = sorted({(item['date'].year, item['date'].month) for item in parsed_hist})
    view_state = {'year': latest_date.year, 'month': latest_date.month, 'metric': 'ratio'}
    cn_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    today_date = cn_now.date()

    with ui.card().classes('w-full p-3 md:p-4 rounded-2xl border border-indigo-100 bg-gradient-to-br from-slate-50 via-white to-indigo-50/40 shadow-sm'):
        with ui.row().classes('w-full items-center justify-between gap-2'):
            with ui.row().classes('items-center gap-2'):
                ui.icon('calendar_month', color='indigo').classes('text-base')
                ui.label('主力资金流入日历').classes('text-sm md:text-base font-black text-slate-800 tracking-tight')
            ui.label(f"最近更新 {latest_date.strftime('%Y-%m-%d')}").classes('text-[10px] text-indigo-600 bg-indigo-50/80 border border-indigo-100 px-2 py-0.5 rounded-md font-bold')

        with ui.row().classes('w-full mt-2 md:mt-3 gap-2 flex-col md:flex-row items-stretch'):
            with ui.row().classes('flex-1 gap-2'):
                with ui.column().classes('min-w-[86px] bg-slate-900 text-white rounded-lg px-2 py-1.5 gap-0'):
                    ui.label('月度净流').classes('text-[9px] uppercase tracking-wider text-slate-300')
                    month_flow_label = ui.label('--').classes('text-sm font-black leading-tight')
                with ui.column().classes('min-w-[86px] bg-white/90 border border-rose-100 rounded-lg px-2 py-1.5 gap-0'):
                    ui.label('流入天数').classes('text-[9px] tracking-wider text-slate-400')
                    month_inflow_days_label = ui.label('--').classes('text-sm font-black text-rose-600 leading-tight')
                with ui.column().classes('min-w-[86px] bg-white/90 border border-emerald-100 rounded-lg px-2 py-1.5 gap-0'):
                    ui.label('流出天数').classes('text-[9px] tracking-wider text-slate-400')
                    month_outflow_days_label = ui.label('--').classes('text-sm font-black text-emerald-600 leading-tight')

            with ui.row().classes('items-center justify-between md:justify-end gap-2'):
                metric_toggle_container = ui.row().classes('bg-white border border-indigo-100 rounded-lg p-1 gap-1 shadow-sm')
                with ui.row().classes('items-center gap-1'):
                    prev_btn = ui.button(icon='chevron_left').props('flat round dense').classes('w-7 h-7 bg-white border border-indigo-100 text-indigo-500')
                    month_title = ui.label('').classes('text-base md:text-lg font-black text-slate-800 min-w-[110px] text-center')
                    next_btn = ui.button(icon='chevron_right').props('flat round dense').classes('w-7 h-7 bg-white border border-indigo-100 text-indigo-500')

        with ui.grid(columns=7).classes('w-full mt-2 gap-1 text-center'):
            for weekday in ['日', '一', '二', '三', '四', '五', '六']:
                ui.label(weekday).classes('text-[11px] font-bold text-slate-500 py-0.5')

        calendar_grid = ui.grid(columns=7).classes('w-full gap-1 mt-0.5')

        def get_flow_status(ratio):
            if ratio > 8:
                return '超入', 'bg-rose-500 text-white border border-rose-300 shadow-[0_0_10px_rgba(244,63,94,0.35)]'
            if ratio > 3:
                return '强入', 'bg-rose-400/95 text-white border border-rose-300'
            if ratio > 0:
                return '弱入', 'bg-rose-50 text-rose-700 border border-rose-200'
            if ratio < -8:
                return '超出', 'bg-emerald-600 text-white border border-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.35)]'
            if ratio < -3:
                return '强出', 'bg-emerald-500/95 text-white border border-emerald-300'
            if ratio < 0:
                return '弱出', 'bg-emerald-50 text-emerald-700 border border-emerald-200'
            return '平', 'bg-white text-slate-500 border border-slate-200'

        def format_metric(day_data):
            if view_state['metric'] == 'inflow':
                return f"{day_data['inflow']:+.1f}亿"
            return f"{day_data['ratio']:+.2f}%"

        def month_meta(year, month):
            first_day = datetime.date(year, month, 1)
            start_idx = (first_day.weekday() + 1) % 7
            if month == 12:
                next_month_day = datetime.date(year + 1, 1, 1)
            else:
                next_month_day = datetime.date(year, month + 1, 1)
            day_count = (next_month_day - first_day).days
            return first_day, start_idx, day_count

        def shift_month(step):
            year = view_state['year']
            month = view_state['month'] + step
            if month < 1:
                month = 12
                year -= 1
            elif month > 12:
                month = 1
                year += 1
            target = (year, month)
            if target in month_keys:
                view_state['year'] = year
                view_state['month'] = month
                render_month()

        def set_metric(metric):
            view_state['metric'] = metric
            render_metric_toggle()
            render_month()

        def render_metric_toggle():
            metric_toggle_container.clear()
            with metric_toggle_container:
                metric_is_amount = view_state['metric'] == 'inflow'
                ui.button('¥', on_click=lambda: set_metric('inflow')).props('flat dense no-caps').classes(
                    f'px-3 h-6 rounded-md text-[11px] font-black {"bg-indigo-600 text-white shadow-sm" if metric_is_amount else "text-indigo-500"}'
                )
                ui.button('%', on_click=lambda: set_metric('ratio')).props('flat dense no-caps').classes(
                    f'px-3 h-6 rounded-md text-[11px] font-black {"bg-indigo-600 text-white shadow-sm" if not metric_is_amount else "text-indigo-500"}'
                )

        def render_month():
            year = view_state['year']
            month = view_state['month']
            month_title.set_text(f'{year}年{month}月')

            min_key = month_keys[0]
            max_key = month_keys[-1]
            prev_btn.set_enabled((year, month) > min_key)
            next_btn.set_enabled((year, month) < max_key)

            month_data = [v for v in parsed_hist if v['date'].year == year and v['date'].month == month]
            month_inflow = sum(v['inflow'] for v in month_data)
            month_inflow_days = sum(1 for v in month_data if v['ratio'] > 0)
            month_outflow_days = sum(1 for v in month_data if v['ratio'] < 0)
            month_flow_label.set_text(f'{month_inflow:+.1f}亿')
            month_flow_label.classes(remove='text-rose-400 text-emerald-400', add='text-rose-300' if month_inflow > 0 else 'text-emerald-300')
            month_inflow_days_label.set_text(str(month_inflow_days))
            month_outflow_days_label.set_text(str(month_outflow_days))

            calendar_grid.clear()
            first_day, start_idx, day_count = month_meta(year, month)
            total_cells = ((start_idx + day_count + 6) // 7) * 7
            prev_month_last_day = first_day - datetime.timedelta(days=1)

            with calendar_grid:
                for idx in range(total_cells):
                    day_num = idx - start_idx + 1

                    if day_num < 1:
                        outside_day = prev_month_last_day.day - (start_idx - idx - 1)
                        with ui.column().classes('h-[46px] md:h-[52px] rounded-md bg-slate-50/70 border border-slate-100 items-center justify-center'):
                            ui.label(str(outside_day)).classes('text-[10px] text-slate-300 leading-none')
                        continue

                    if day_num > day_count:
                        outside_day = day_num - day_count
                        with ui.column().classes('h-[46px] md:h-[52px] rounded-md bg-slate-50/70 border border-slate-100 items-center justify-center'):
                            ui.label(str(outside_day)).classes('text-[10px] text-slate-300 leading-none')
                        continue

                    current_date = datetime.date(year, month, day_num)
                    day_data = flow_by_date.get(current_date)
                    is_today = current_date == today_date
                    is_latest = current_date == latest_date

                    if day_data:
                        status_text, cell_class = get_flow_status(day_data['ratio'])
                        border_class = 'ring-1 ring-cyan-300/80' if is_latest else ''
                        with ui.column().classes(f'h-[46px] md:h-[52px] rounded-md {cell_class} {border_class} items-center justify-center gap-0.5 cursor-help transition-all hover:scale-[1.02]'):
                            ui.label(str(day_num)).classes('text-[9px] md:text-[10px] font-semibold opacity-70 leading-none')
                            ui.label(status_text).classes('text-[11px] md:text-xs font-black leading-none')
                            ui.label(format_metric(day_data)).classes('text-[9px] md:text-[10px] font-bold leading-none opacity-90')
                            ui.tooltip(
                                f"{current_date.strftime('%Y-%m-%d')}  {status_text}\n净流入: {day_data['inflow']:+.2f} 亿\n强度: {day_data['ratio']:+.2f}%"
                            ).classes('text-xs bg-slate-900 text-white shadow-xl whitespace-pre-line')
                    elif is_today:
                        with ui.column().classes('h-[46px] md:h-[52px] rounded-md bg-white/80 border border-slate-200 items-center justify-center gap-0.5'):
                            ui.label('今').classes('text-[10px] font-bold text-slate-500 leading-none')
                            ui.label('未更新').classes('text-[9px] font-bold text-slate-300 leading-none')
                    else:
                        with ui.column().classes('h-[46px] md:h-[52px] rounded-md bg-white/70 border border-transparent items-center justify-center'):
                            ui.label(str(day_num)).classes('text-[10px] md:text-[11px] font-semibold text-slate-500 leading-none')

        prev_btn.on('click', lambda: shift_month(-1))
        next_btn.on('click', lambda: shift_month(1))
        render_metric_toggle()
        render_month()
