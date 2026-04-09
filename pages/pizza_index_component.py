import asyncio
import json
import os
from nicegui import ui
import logging
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright

PIZZA_URL = "https://pizza.mountainguan.tech/"

def fetch_pizza_data(force=False):
    import time
    import json
    import os
    import zoneinfo
    from datetime import datetime, timedelta
    
    cache_dir = "data"
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, "pizza_index_history_cache.json")
    
    us_tz = zoneinfo.ZoneInfo("US/Eastern")
    now_et = datetime.now(us_tz)
    today_str = now_et.strftime('%Y-%m-%d')
    
    history_data = {"shops": {}, "doughcon": {}}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if "shops" in loaded: history_data = loaded
                else: history_data["shops"] = loaded
        except Exception as e:
            logging.warning(f"Failed to load history cache: {e}")

    # 如果不强制刷新，且今天的数据已经在缓存里，则直接返回整个历史缓存
    if not force and today_str in history_data.get("shops", {}):
        logging.info("读取当前的 PizzINT 披萨指数历史缓存，跳过 Playwright 抓取...")
        return history_data

    try:
        results = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            logging.info(f"Navigating to {PIZZA_URL} with headless browser...")
            try:
                page.goto(PIZZA_URL, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                err_msg = str(e)
                logging.warning(f"Page.goto threw an exception: {err_msg}")
                if "ERR_NAME_NOT_RESOLVED" in err_msg or "ERR_CONNECTION_REFUSED" in err_msg:
                    return None
            
            page.wait_for_timeout(8000)
            page.wait_for_timeout(8000) 
            
            js_script = """
            () => {
                const shopsToFind = [
                    "DOMINO'S PIZZA",
                    "EXTREME PIZZA",
                    "DISTRICT PIZZA PALACE",
                    "WE, THE PIZZA",
                    "PIZZATO PIZZA",
                    "PAPA JOHNS PIZZA",
                    "PAPA JOHN"
                ];
                
                let res = [];
                const h3_elements = Array.from(document.querySelectorAll('h3'));
                
                for (let h3 of h3_elements) {
                    let name = h3.innerText.toUpperCase();
                    let isTarget = shopsToFind.some(s => name.includes(s));
                    if (!isTarget) continue;
                    
                    let el = h3;
                    let card = null;
                    for(let i=0; i<8; i++) {
                        if (!el) break;
                        el = el.parentElement;
                        if (el && el.querySelectorAll('div[style*="height"]').length > 10) {
                            card = el;
                            break;
                        }
                    }
                    if (!card) continue;
                    
                    let textContent = card.innerText || "";
                    let topText = textContent.split('\\n').slice(0, 4).join(' ');
                    let status = "NO DATA";
                    let distance = "";
                    let desc = "";
                    
                    const distMatch = topText.match(/([0-9\.]+)\s*mi/i);
                    if (distMatch) distance = distMatch[0] + " mi";
                    
                    const statusMatch = topText.match(/(CLOSED|QUIET|[0-9]+%\s*SPIKE|SPIKE|BUSY|OPEN|NORMAL)/i);
                    if (statusMatch) status = statusMatch[0].toUpperCase();
                    
                    let hourly = [];
                    const bars = card.querySelectorAll('div[style*="height"]');
                    bars.forEach(bar => {
                        if (bar.className && bar.className.includes('animate-pulse')) return;
                        if (bar.className && bar.className.includes('skeleton')) return;
                        
                        const style = bar.getAttribute('style') || '';
                        const hMatch = style.match(/height:\s*([\d\.]+)\%/);
                        if (hMatch) {
                            let val = parseFloat(hMatch[1]);
                            let timeTitle = bar.getAttribute('title') || '';
                            if (!timeTitle && bar.parentElement) {
                                timeTitle = bar.parentElement.getAttribute('title') || '';
                            }
                            hourly.push({
                                "time": timeTitle,
                                "height": val
                            });
                        }
                    });
                    
                    if (hourly.length > 0) {
                        res.push({
                            name: name,
                            status: status,
                            distance: distance,
                            desc: desc,
                            hourly: hourly
                        });
                    }
                }
                
                // scrape doughcon banner
                let doughcon = { level: "", desc: "" };
                let spans = Array.from(document.querySelectorAll('*')).filter(el => {
                    let txt = el.innerText || "";
                    return txt.match(/DOUGHCON\s+[1-5]/) && txt.length < 150;
                });
                if (spans.length > 0) {
                    let targetEl = spans.find(el => el.innerText.split('\\n').length > 1) || spans[0];
                    let textLines = targetEl.innerText.split('\\n').map(l => l.trim()).filter(l => l);
                    let dIdx = textLines.findIndex(l => l.match(/DOUGHCON\s+[1-5]/));
                    if (dIdx >= 0) {
                        doughcon.level = textLines[dIdx];
                        if (dIdx + 1 < textLines.length) {
                            doughcon.desc = textLines[dIdx + 1];
                        }
                    }
                }

                return { shops: res, doughcon: doughcon };
            }
            """
            
            # 当前时间倒推7天，按照星期几对应到具体的日期 (只向过去推)
            date_map = {}
            for i in range(7):
                d = now_et - timedelta(days=i)
                d_str = d.strftime('%Y-%m-%d')
                d_name = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"][d.weekday()]
                date_map[d_name] = d_str
            
            # 抓取完整的当前日历包含的周数据（周日到周六）
            for d_name in ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]:
                day_str = date_map.get(d_name)
                if not day_str:
                    continue
                
                try:
                    page.evaluate(f"Array.from(document.querySelectorAll('button')).filter(b => b.innerText === '{d_name}')[0].click()")
                    page.wait_for_timeout(1500)
                except Exception as e:
                    logging.warning(f"Could not click day {d_name}: {e}")
                
                day_res = page.evaluate(js_script)
                
                # 为每小时的数据附加上当天的标记
                shops_list = day_res.get("shops", []) if isinstance(day_res, dict) else day_res
                for shop in shops_list:
                    for h in shop.get("hourly", []):
                        h["time"] = f"{h['time']} [{d_name}]"
                        h["day"] = day_str
                        
                # 如果当天抓到数据了，分别存入商店和等级的字典中
                if shops_list:
                    if day_str not in history_data["shops"]:
                        history_data["shops"][day_str] = []
                    # 避免完全覆盖旧数组丢失店面，以店名为键进行数据合并，新数据覆盖旧数据
                    existing_shops = {s["name"]: s for s in history_data["shops"][day_str]}
                    for new_shop in shops_list:
                        existing_shops[new_shop["name"]] = new_shop
                    history_data["shops"][day_str] = list(existing_shops.values())
                    
                if isinstance(day_res, dict) and day_res.get("doughcon", {}).get("level"):
                    history_data["doughcon"][day_str] = day_res.get("doughcon", {})
            
            browser.close()
            
        if not history_data.get("shops"):
            logging.warning("No data returned from Playwright script.")
            return None

        # 最大保留 90 天的历史数据
        for cat in ["shops", "doughcon"]:
            sorted_keys = sorted(history_data[cat].keys())
            if len(sorted_keys) > 90:
                for k in sorted_keys[:-90]:
                    del history_data[cat][k]

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=4)
            
        return history_data

    except Exception as e:
        logging.error(f"Failed to fetch pizza index via Playwright: {e}")
        return None

def render_pizza_index_panel(is_mobile=False):
    import zoneinfo
    from datetime import datetime
    import json
    
    us_tz = zoneinfo.ZoneInfo("US/Eastern")
    selected_date = [datetime.now(us_tz).strftime('%Y-%m-%d')]

    # Pizza Index Container
    pizza_container = ui.column().classes('w-full mt-6')
    executor = ThreadPoolExecutor(max_workers=2)

    async def _fetch_and_render_pizza(force=False):
        if pizza_container.is_deleted:
            return
            
        if force:
            ui.notify('正在刷新五角大楼披萨指数...', type='info')
            
        pizza_container.clear()
        with pizza_container:
            with ui.card().classes('w-full p-4 rounded-xl border border-gray-200 shadow-sm bg-white animate-pulse'):
                with ui.row().classes('w-full items-center justify-between mb-4'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('local_pizza', color='orange').classes('text-2xl')
                        ui.label('五角大楼披萨指数 (PizzINT)').classes('text-xl font-bold text-gray-800')
                        ui.label('数据正在加载中...').classes('text-xs bg-orange-100 text-orange-800 px-2 py-1 rounded ml-2')
                
                num_cols = 2 if is_mobile else 3
                with ui.grid(columns=num_cols).classes('w-full gap-4'):
                    for _ in range(6): # skeleton cards
                        with ui.card().classes('p-3 border border-gray-200 bg-gray-50 shadow-sm items-center justify-center text-center w-full h-32'):
                            ui.spinner(size='lg', color='orange')
                            ui.label('正在获取实时情报警报...').classes('text-xs text-gray-400 mt-3')

        try:
            history_data = await asyncio.get_running_loop().run_in_executor(executor, fetch_pizza_data, force)

            if history_data and not pizza_container.is_deleted:
                available_dates = sorted(list(history_data.get('shops', {}).keys()))
                if not available_dates:
                    return
                if selected_date[0] not in history_data.get('shops', {}):
                    selected_date[0] = available_dates[-1]

                quasar_options = json.dumps([d.replace('-', '/') for d in available_dates]).replace('"', "'")

                pizza_container.clear()
                with pizza_container:
                    with ui.card().classes('w-full p-4 rounded-xl border border-gray-200 shadow-sm bg-white'):
                        with ui.row().classes('w-full items-center justify-between mb-4'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('local_pizza', color='orange').classes('text-2xl')
                                ui.label('五角大楼披萨指数 (PizzINT)').classes('text-xl font-bold text-gray-800')
                                ui.label('地缘情绪前瞻指引').classes('text-xs bg-orange-100 text-orange-800 px-2 py-1 rounded ml-2')
                                
                            with ui.row().classes('items-center gap-2'):
                                with ui.input('选择日期', value=selected_date[0]).props('dense outlined readonly').classes('w-36 cursor-pointer bg-white') as date_input:
                                    with ui.menu() as date_menu:
                                        ui.date(value=selected_date[0].replace('-', '/'), on_change=lambda e: _on_date_change(e.value)).props(f':options="{quasar_options}"')
                                    with date_input.add_slot('append'):
                                        ui.icon('event').classes('cursor-pointer text-gray-600').on('click', lambda: date_menu.open())

                                ui.button(icon='refresh', on_click=lambda: _fetch_and_render_pizza(force=True)) \
                                    .props('flat color=blue round') \
                                    .tooltip('刷新披萨指数')                       
                        grid_container = ui.column().classes('w-full gap-4')
                        
                        def _on_date_change(new_quasar_date):
                            if new_quasar_date:
                                new_date = new_quasar_date.replace('/', '-')
                                if new_date != selected_date[0] and new_date in history_data.get('shops', {}):
                                    selected_date[0] = new_date
                                    try:
                                        date_input.value = new_date
                                    except Exception:
                                        pass
                                    render_grid(new_date)
                                    try:
                                        date_menu.close()
                                    except Exception:
                                        pass
                                        
                        def render_grid(date_key):
                            grid_container.clear()
                            with grid_container:
                                doughcon_data = history_data.get('doughcon', {}).get(date_key, {})
                                shops_data = history_data.get('shops', {}).get(date_key, [])
                                
                                # Tech finance DOUGHCON card with trend sparkline
                                import re
                                
                                d_dates = sorted(list(history_data.get('doughcon', {}).keys()))[-14:] 
                                d_levels = []
                                for d in d_dates:
                                    lvl_str = history_data['doughcon'][d].get('level', '')
                                    match = re.search(r'DOUGHCON\s+([1-5])', lvl_str)
                                    d_levels.append(int(match.group(1)) if match else 5)
                                
                                doughcon_mapping = {
                                    1: {"name": "最高戒备", "desc": "Maximum Readiness", "color": "text-red-500", "bg": "bg-red-50/50", "border": "border-red-200", "icon": "warning"},
                                    2: {"name": "临近最高戒备", "desc": "Next Step to Maximum Readiness", "color": "text-orange-500", "bg": "bg-orange-50/50", "border": "border-orange-200", "icon": "gavel"},
                                    3: {"name": "部队戒备提升", "desc": "Increase in Force Readiness", "color": "text-amber-500", "bg": "bg-amber-50/50", "border": "border-amber-200", "icon": "security"},
                                    4: {"name": "情报监控升级", "desc": "Increased Intelligence Watch", "color": "text-blue-500", "bg": "bg-blue-50/50", "border": "border-blue-200", "icon": "policy"},
                                    5: {"name": "最低戒备状态 (常态)", "desc": "Lowest State of Readiness", "color": "text-emerald-500", "bg": "bg-emerald-50/50", "border": "border-emerald-200", "icon": "verified_user"}
                                }
                                
                                current_lvl_num = 5
                                if doughcon_data and doughcon_data.get('level'):
                                    match = re.search(r'DOUGHCON\s+([1-5])', doughcon_data.get('level'))
                                    if match: current_lvl_num = int(match.group(1))
                                
                                mapping = doughcon_mapping.get(current_lvl_num, doughcon_mapping[5])
                                
                                # echart trend options (inverted Y axis, tech style)
                                echart_options = {
                                    "tooltip": {"trigger": "axis", "formatter": "{b}<br/>披萨指数等级 {c}"},
                                    "grid": {"left": "10px", "right": "10px", "top": "10px", "bottom": "10px"},
                                    "xAxis": {"type": "category", "data": d_dates, "show": False},
                                    "yAxis": {"type": "value", "min": 1, "max": 5, "inverse": True, "show": False},
                                    "series": [{
                                        "data": d_levels,
                                        "type": "line",
                                        "step": "end",
                                        "areaStyle": {"color": "rgba(99, 102, 241, 0.1)"},
                                        "lineStyle": {"color": "#6366f1", "width": 2},
                                        "itemStyle": {"color": "#6366f1"},
                                        "smooth": False
                                    }]
                                }

                                if doughcon_data:
                                    with ui.card().classes(f'w-full {mapping["bg"]} {mapping["border"]} border shadow-sm p-4 mb-2 backdrop-blur-sm relative overflow-hidden'):
                                        with ui.row().classes('w-full flex-nowrap items-center justify-between gap-4'):
                                            # Left Side: Status
                                            with ui.row().classes('items-center gap-3 flex-nowrap flex-grow'):
                                                with ui.element('div').classes(f'p-2 rounded-full bg-white shadow-sm border {mapping["border"]}'):
                                                    ui.icon(mapping["icon"], color=mapping["color"].split("-")[1] + "-500").classes('text-2xl animate-pulse')
                                                with ui.column().classes('gap-0'):
                                                    ui.label(f'披萨指数等级 {current_lvl_num}').classes(f'{mapping["color"]} text-xl font-bold tracking-tight')
                                                    with ui.row().classes('items-center gap-2'):
                                                        ui.label(mapping["name"]).classes('text-[13px] text-gray-700 font-bold')
                                                        ui.label(mapping["desc"]).classes('text-[11px] text-gray-400')

                                            # Right Side: Trend Sparkline
                                            with ui.column().classes('w-36 flex-none items-end justify-center py-1 opacity-90'):
                                                ui.label('近14天趋势').classes('text-[10px] text-gray-400 w-full text-right mb-0 tracking-widest')
                                                ui.echart(echart_options).classes('w-full').style('height: 55px;')

                                num_cols = 2 if is_mobile else 3
                                with ui.grid(columns=num_cols).classes('w-full gap-4'):
                                    for item in shops_data:
                                        status = item['status']
                                        desc = item.get('desc', '')
                                        status_upper = status.upper() if status else 'NO DATA'
                                        
                                        border_color = 'border-gray-200'
                                        bg_color = 'bg-gray-50'
                                        text_color = 'text-gray-600'
                                        icon_name = 'storefront'

                                        if 'SPIKE' in status_upper or 'BUSY' in status_upper or 'busier' in desc.lower():
                                            border_color = 'border-red-200'
                                            bg_color = 'bg-red-50'
                                            text_color = 'text-red-600'
                                            icon_name = 'local_fire_department'
                                        elif 'QUIET' in status_upper or 'NORMAL' in status_upper or 'OPEN' in status_upper or 'quieter' in desc.lower():
                                            border_color = 'border-green-200'
                                            bg_color = 'bg-green-50'
                                            text_color = 'text-green-600'
                                            icon_name = 'nightlight_round'
                                        elif 'NO DATA' in status_upper or 'CLOSED' in status_upper:
                                            border_color = 'border-gray-200'
                                            bg_color = 'bg-gray-50'
                                            text_color = 'text-gray-400'
                                            icon_name = 'data_usage' if 'NO DATA' in status_upper else 'storefront'
                                            
                                        with ui.card().classes(f'p-3 border {border_color} {bg_color} shadow-sm items-center justify-center text-center w-full'):
                                            ui.label(item['name']).classes('text-xs text-gray-400 truncate w-full mb-1 opacity-70')
                                            ui.icon(icon_name).classes(f'text-xl mb-1 {text_color}')
                                            
                                            display_status = status_upper
                                            if display_status == "CLOSED": display_status = "已关门"
                                            elif "SPIKE" in display_status: display_status = display_status.replace("SPIKE", "飙升")
                                            elif "QUIET" in display_status: display_status = display_status.replace("QUIET", "冷清")
                                            elif "OPEN" in display_status: display_status = "营业中"
                                            elif "BUSY" in display_status: display_status = "近期繁忙"
                                            elif "NORMAL" in display_status: display_status = "正常"
                                            
                                            ui.label(display_status).classes(f'font-black text-sm {text_color}')
                                            if desc:
                                                ui.label(desc).classes('text-[10px] text-gray-500 mt-1 line-clamp-1')
                                            if item['distance']:
                                                dist_val = item['distance'].replace('mi', '').strip()
                                                ui.label(f'距离五角大楼 {dist_val} 公里').classes('text-[11px] font-bold text-blue-600 mt-1 bg-blue-50 px-2 py-0.5 rounded-full')

                                            if item.get('hourly'):
                                                def parse_and_format_time(t_str):
                                                    match = re.search(r'(\d+)(a|p)', t_str)
                                                    if not match: return t_str
                                                    hour = int(match.group(1))
                                                    ampm = match.group(2)
                                                    
                                                    day_match = re.search(r'\[(SUN|MON|TUE|WED|THU|FRI|SAT)\]', t_str)
                                                    day_en = day_match.group(1) if day_match else ""
                                                    day_dict = {
                                                        "SUN": "周日", "MON": "周一", "TUE": "周二", 
                                                        "WED": "周三", "THU": "周四", "FRI": "周五", "SAT": "周六"
                                                    }
                                                    day_zh = f" ({day_dict.get(day_en, '')})" if day_en else ""
                                                    
                                                    if ampm == 'a' and hour == 12: h24 = 0
                                                    elif ampm == 'a': h24 = hour
                                                    elif ampm == 'p' and hour == 12: h24 = 12
                                                    else: h24 = hour + 12
                                                    
                                                    b_h24 = (h24 + 12) % 24
                                                    next_day = " (次日)" if (h24 + 12) >= 24 else ""
                                                    b_ampm = "上午" if b_h24 < 12 else "下午"
                                                    b_h12 = b_h24 if b_h24 <= 12 else b_h24 - 12
                                                    if b_h12 == 0: b_h12 = 12
                                                    
                                                    new_t = f"北京时 {b_ampm}{b_h12}点{next_day}"
                                                    us_t = f"{hour}{ampm}m"
                                                    
                                                    hist_match = re.search(r'Historical:\s*(\d+)%', t_str)
                                                    desc = ""
                                                    if hist_match:
                                                        desc = f"历史最大流量的 {hist_match.group(1)}%"
                                                    elif 'Restaurant Closed' in t_str:
                                                        desc = "处于关门状态"
                                                        
                                                    return f"{day_zh} {new_t} (美 {us_t})\n{desc}".strip()

                                                hourly_records = item['hourly']
                                                display_vals = [r.get("height", 0) for r in hourly_records]
                                                display_times = [parse_and_format_time(r.get("time", "Unknown time")) for r in hourly_records]
                                                
                                                with ui.row().classes('w-full mt-4 justify-start items-end h-28 gap-[6px] overflow-x-auto overflow-y-hidden pb-1 px-1 flex-nowrap custom-scrollbar'):
                                                    max_val = max(display_vals) if display_vals and max(display_vals) > 0 else 1
                                                    avg_val = sum(display_vals) / len(display_vals) if display_vals else 1
                                                    for i, val in enumerate(display_vals):
                                                        h_pct = max(3, int((val / max_val) * 100))
                                                        is_abnormal = (val > (avg_val * 2.5) and val > 20) or (val > 80)
                                                        
                                                        formatted_tooltip = f"{display_times[i]}"
                                                        
                                                        if is_abnormal:
                                                            bar_color = "bg-red-500 shadow-sm z-10"
                                                            opacity_style = "opacity: 1;"
                                                            formatted_tooltip += " | ❗️飙升"
                                                        else:
                                                            bar_color = "bg-red-400" if "red" in bg_color else ("bg-green-400" if "green" in bg_color else "bg-gray-300")
                                                            opacity_style = "opacity: 0.85;"
                                                            
                                                        ui.element('div').classes(f'flex-none w-[10px] sm:w-[14px] rounded-t-sm {bar_color} transition-all hover:scale-y-110 origin-bottom cursor-pointer').style(f'height: {h_pct}%; min-height: 4px; {opacity_style}').tooltip(formatted_tooltip)

                                with ui.row().classes('w-full mt-4 justify-end'):
                                    ui.link('数据来源: pizzint.watch', PIZZA_URL, new_tab=True).classes('text-xs text-gray-400 hover:text-orange-500')
                        # 初始渲染
                        render_grid(selected_date[0])

            elif not history_data and not pizza_container.is_deleted:
                pizza_container.clear()
                with pizza_container:
                    with ui.card().classes('w-full p-6 rounded-xl border border-red-200 shadow-sm bg-white items-center justify-center text-center'):
                        ui.icon('error_outline', color='red').classes('text-4xl mb-2')
                        ui.label('获取数据失败，可能网站拦截或网络不通').classes('text-base text-red-600 font-bold')
                        ui.button('点击重试', icon='refresh', on_click=lambda: _fetch_and_render_pizza(force=True)).classes('mt-4 text-white').props('color=red')
                                
        except Exception as e:
            if not pizza_container.is_deleted:
                with pizza_container:
                    ui.label(f"加载披萨指数数据时出错: {e}").classes('text-red-500 text-sm')

    # Initial load using timer
    ui.timer(0, lambda: asyncio.create_task(_fetch_and_render_pizza()), once=True)
