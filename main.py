import os

# 配置环境变量以解决云端部署可能的权限问题
os.environ['MPLCONFIGDIR'] = '/tmp'
os.environ['XDG_CONFIG_HOME'] = '/tmp'

from nicegui import ui, app
import json
import re
import uuid
import urllib.request
from plotly.utils import PlotlyJSONEncoder
from utils.charts import create_candlestick_chart, get_demo_fenxing_data, get_chart_data
from utils.simulator_logic import generate_simulation_data, analyze_action, resample_klines, analyze_advanced_action, get_chanlun_shapes
from pages.market_sentiment_page import render_sentiment_view
from pages.shared import setup_common_ui, custom_plotly


# 获取当前文件所在的目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- 自动下载静态资源 ---
def ensure_static_assets():
    """检查并下载静态资源文件，避免手动下载"""
    static_dir = os.path.join(BASE_DIR, 'static')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    
    # 资源配置: 文件名 -> 下载地址
    assets = [
        ('plotly.min.js', "https://cdn.bootcdn.net/ajax/libs/plotly.js/3.1.1/plotly.min.js"),
        ('tex-chtml.min.js', "https://cdn.bootcdn.net/ajax/libs/mathjax/4.0.0/tex-chtml.min.js")
    ]
    
    for filename, url in assets:
        file_path = os.path.join(static_dir, filename)
        if not os.path.exists(file_path):
            print(f"检测到本地缺少 {file_path}，正在自动下载...")
            try:
                urllib.request.urlretrieve(url, file_path)
                print(f"{filename} 下载完成！")
            except Exception as e:
                print(f"自动下载 {filename} 失败，将使用在线CDN回退: {e}")

# 确保资源存在
ensure_static_assets()

# 挂载静态文件目录
app.add_static_files('/static', os.path.join(BASE_DIR, 'static'))


# --- 通用数据加载 ---
def load_chapter_content(chapter_id):
    try:
        file_path = os.path.join(BASE_DIR, 'content', f'{chapter_id}.md')
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            return f.read()
    except FileNotFoundError:
        return "章节内容未找到。"

def protect_math_content(text):
    if not text:
        return text
    def repl(match):
        delimiter = match.group(1)
        content = match.group(2)
        content = content.replace('_', '\\_').replace('*', '\\*')
        return delimiter + content + delimiter
    return re.sub(r'(\$\$?)(.*?)\1', repl, text, flags=re.DOTALL)

def load_questions(chapter_id):
    try:
        file_path = os.path.join(BASE_DIR, 'questions', f'{chapter_id}.json')
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

# --- 1. 入口导航页面 ---
@ui.page('/')
def landing_page():
    ui.page_title('缠论量化分析系统')
    
    # 容器：使用 min-h-screen 配合 flex 布局，确保垂直居中和 Footer 沉底
    with ui.column().classes('w-full min-h-screen bg-gray-50 p-4'):
        
        # 上部占位，把内容推到中间 (flex-grow)
        ui.space()
        
        # 中间内容区域
        with ui.column().classes('w-full items-center justify-center'):
            # 标题区域
            with ui.column().classes('items-center mb-10'):
                ui.icon('ssid_chart', size='64px').classes('text-primary mb-4')
                ui.label('缠论量化分析系统').classes('text-4xl font-bold text-gray-800 tracking-wider mb-2 text-center')
                ui.label('Chanlun Quantitative Analysis System').classes('text-lg text-gray-500 font-light text-center')

            # 卡片链接区域
            with ui.row().classes('gap-8 justify-center flex-wrap'):
                
                # 卡片 1: 学习系统
                with ui.card().classes('w-72 h-80 items-center justify-center p-6 hover:shadow-xl transition-shadow cursor-pointer border-t-4 border-indigo-500 gap-4 bg-white') \
                    .on('click', lambda: ui.navigate.to('/learn')):
                    
                    with ui.element('div').classes('w-20 h-20 rounded-full bg-indigo-50 flex items-center justify-center mb-2'):
                        ui.icon('school', size='40px').classes('text-indigo-600')
                    
                    ui.label('学习与训练').classes('text-2xl font-bold text-gray-800')
                    ui.label('系统化学习缠论知识，通过模拟交易进行实战训练').classes('text-center text-gray-500 leading-relaxed text-sm')
                    ui.button('进入系统', on_click=lambda: ui.navigate.to('/learn')).props('flat color=indigo')

                # 卡片 2: 市场工具
                with ui.card().classes('w-72 h-80 items-center justify-center p-6 hover:shadow-xl transition-shadow cursor-pointer border-t-4 border-red-500 gap-4 bg-white') \
                    .on('click', lambda: ui.navigate.to('/mood')):
                    
                    with ui.element('div').classes('w-20 h-20 rounded-full bg-red-50 flex items-center justify-center mb-2'):
                        ui.icon('insights', size='40px').classes('text-red-600')
                    
                    ui.label('市场情绪与资金').classes('text-2xl font-bold text-gray-800')
                    ui.label('实时监控大盘情绪，板块热度追踪及资金流向分析').classes('text-center text-gray-500 leading-relaxed text-sm')
                    ui.button('进入工具', on_click=lambda: ui.navigate.to('/mood')).props('flat color=red')
        
        # 下部占位 (flex-grow) + Footer 位于最底
        ui.space()
        
        with ui.row().classes('w-full justify-center py-8'):
            ui.label('© 2026 关山AI实验室').classes('text-gray-400 text-xs')

# --- 2. 缠论学习应用 ---
class LearnState:
    def __init__(self):
        self.current_chapter = 'chapter1' 
        self.current_view = 'learn'
        self.sim_mode = 'basic' 
        self.sim_view_period = 'day'
        self.sim_data = []  
        self.sim_data_week = []
        self.sim_data_month = []
        self.sim_data_60d = []
        self.sim_macd = {}
        self.sim_macd_week = {}
        self.sim_macd_month = {}
        self.sim_macd_60d = {}
        self.sim_index = 0
        self.sim_balance = 100000  
        self.sim_shares = 0
        self.sim_feedback = "点击“开始新游戏”开始模拟交易。"
        self.sim_game_active = False
        self.sim_trade_percent = 100 
        self.sim_stats = {'correct': 0, 'wrong': 0, 'total': 0}
        self.sim_shapes = []

@ui.page('/learn')
def learn_page():
    ui.page_title('缠论学习系统')
    setup_common_ui()
    state = LearnState()
    
    with ui.header(elevated=True).classes('bg-white text-gray-800 border-b border-gray-200 md:hidden'):
        ui.button(on_click=lambda: drawer.toggle(), icon='menu').props('flat color=primary')
        ui.label('缠论学习系统').classes('text-lg font-bold text-primary q-ml-sm')
        with ui.element('div').classes('ml-auto'):
             ui.button(icon='home', on_click=lambda: ui.navigate.to('/')).props('flat round color=grey')

    with ui.left_drawer(value=True).classes('bg-gray-50 border-r border-gray-200') as drawer:
        with ui.row().classes('items-center justify-between w-full q-pa-md'):
            ui.label('缠论学习系统').classes('text-h6 text-primary font-bold hidden md:block')
            ui.button(icon='home', on_click=lambda: ui.navigate.to('/')).props('flat round dense color=grey').classes('hidden md:block').tooltip('返回首页')
        ui.separator().classes('hidden md:block')
        menu_container = ui.column().classes('w-full')

    content_container = ui.column().classes('w-full content-area')

    def render_menu():
        menu_container.clear()
        chapters_struct = [
            {'title': '第一卷：分型与笔', 'items': [
                {'id': 'chapter1', 'label': '第1章：K线包含处理'},
                {'id': 'chapter2', 'label': '第2章：分型'},
                {'id': 'chapter3', 'label': '第3章：笔的定义'},
            ]},
            {'title': '第二卷：线段与中枢', 'items': [
                {'id': 'chapter4', 'label': '第4章：线段'},
                {'id': 'chapter5', 'label': '第5章：中枢'},
                {'id': 'chapter6', 'label': '第6章：走势类型'},
            ]},
            {'title': '第三卷：动力学与背驰', 'items': [
                {'id': 'chapter7', 'label': '第7章：背驰'},
                {'id': 'chapter8', 'label': '第8章：区间套与MACD'},
                {'id': 'chapter9', 'label': '第9章：三类买卖点'},
            ]},
            {'title': '第四卷：实战心法', 'items': [
                {'id': 'chapter10', 'label': '第10章：同级别分解'},
            ]},
            {'title': '第五卷：实战演练', 'items': [
                {'id': 'simulator', 'label': '股票走势模拟器', 'special': True},
            ]}
        ]
        with menu_container:
            for group in chapters_struct:
                ui.label(group['title']).classes('q-ml-md text-grey-7 q-mt-sm text-sm font-bold')
                for item in group['items']:
                    is_active = state.current_chapter == item['id']
                    base_classes = 'cursor-pointer q-px-md q-py-sm transition-colors duration-200'
                    if is_active: style_classes = f'{base_classes} bg-blue-100 text-blue-800 border-r-4 border-blue-600 font-medium'
                    else: style_classes = f'{base_classes} hover:bg-gray-200 text-gray-700'
                    if item.get('special') and not is_active: style_classes += ' font-bold text-blue-800'
                    lbl = ui.label(item['label']).classes(style_classes)
                    lbl.on('click', lambda _, i=item['id']: load_chapter(i))

    async def load_chapter(chapter_id):
        state.current_chapter = chapter_id
        state.current_view = 'simulator' if chapter_id == 'simulator' else 'learn'
        render_menu(); render_content()
        try:
            if await ui.run_javascript('window.innerWidth < 768'): drawer.value = False
        except: pass
            
    def switch_view(view_mode):
        state.current_view = view_mode
        render_content()

    def render_content():
        content_container.clear()
        with content_container:
            if state.current_chapter == 'simulator': render_simulator_view(); return
            with ui.row().classes('w-full justify-between items-center q-mb-md wrap gap-2'):
                ui.label(f'当前章节: {state.current_chapter}').classes('text-h5 font-bold text-gray-800')
                with ui.button_group().classes('shadow-sm'):
                    ui.button('学习模式', on_click=lambda: switch_view('learn')).props(f'{"outline" if state.current_view != "learn" else ""} color=primary')
                    ui.button('实战练习', on_click=lambda: switch_view('quiz')).props(f'{"outline" if state.current_view != "quiz" else ""} color=primary')
            if state.current_view == 'learn': render_learning_view()
            else: render_quiz_view()

    def render_learning_view():
        text = load_chapter_content(state.current_chapter)
        text = protect_math_content(text)
        parts = re.split(r'(:::\s*chart:[\w_]+\s*:::)', text)
        for part in parts:
            part = part.strip()
            if not part: continue
            chart_match = re.match(r':::\s*chart:([\w_]+)\s*:::', part)
            if chart_match:
                scene_name = chart_match.group(1)
                chart_res = get_chart_data(scene_name)
                if len(chart_res) >= 4:
                    data, title, annotations, shapes = chart_res[0:4]
                    macd_data = chart_res[4] if len(chart_res) > 4 else None
                    if data:
                        with ui.card().classes('w-full q-my-md p-1 bg-white shadow-sm border border-gray-200 overflow-hidden'):
                            ui.label(f'图解：{title}').classes('text-sm font-bold text-gray-700 px-3 py-2 bg-gray-50 border-b w-full')
                            fig = create_candlestick_chart(data, "", annotations=annotations, shapes=shapes, macd_data=macd_data)
                            fig.update_layout(
                                autosize=True,
                                height=None,
                                margin=dict(l=10, r=10, t=10, b=10),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10))
                            )
                            with ui.element('div').classes('w-full h-[350px] md:h-[450px] relative'):
                                custom_plotly(fig).classes('w-full h-full absolute inset-0')
                    else: ui.label(f"⚠️ 暂无图表数据: {scene_name}").classes('text-red')
            else: ui.markdown(part).classes('w-full nicegui-markdown')
        ui.run_javascript('if (window.MathJax && window.MathJax.typesetPromise) MathJax.typesetPromise()')

    def render_quiz_view():
        questions = load_questions(state.current_chapter)
        if not questions: ui.label('本章暂无练习题。').classes('text-gray-500'); return
        for idx, q in enumerate(questions):
            with ui.card().classes('w-full q-mb-md p-4 bg-white border border-gray-200 shadow-sm'):
                ui.label(f"题目 {idx+1}: {q['question']}").classes('text-lg text-bold q-mb-sm')
                if q.get('type') == 'chart_recognition' and 'chart_config' in q:
                    conf = q['chart_config']
                    fig = create_candlestick_chart(conf['data'], "识别形态", annotations=conf.get('annotations'), shapes=conf.get('shapes'), macd_data=conf.get('macd_data'))
                    custom_plotly(fig).classes('w-full h-80')
                def check_ans(uv, opts, ci, rl, ec, et):
                    ec.clear()
                    if not uv: ui.notify('请选择答案', type='warning'); return
                    try: ai = opts.index(uv)
                    except: return
                    if ai == ci: rl.set_text('✅ 回答正确！').classes('text-green-600', remove='text-red-600')
                    else: rl.set_text('❌ 回答错误。').classes('text-red-600', remove='text-green-600')
                    with ec: ui.markdown(f"**解析：** {et}").classes('q-mt-sm bg-gray-100 p-2 rounded')
                opts = q['options']
                with ui.column().classes('q-mt-sm'):
                    radio = ui.radio(opts).props('column')
                    result_lbl = ui.label().classes('text-lg font-bold q-mt-sm')
                    exp_ui = ui.column()
                    ui.button('提交答案', on_click=lambda r=radio, q=q, l=result_lbl, ec=exp_ui, o=opts: check_ans(r.value, o, q['answer'], l, ec, q['explanation'])).classes('q-mt-sm')

    # --- Simulator Logic (Full Restoration) ---
    def set_mode(mode): state.sim_mode = mode; start_new_game()
    def switch_sim_period(p): state.sim_view_period = p; render_content()
    def start_new_game():
        data_len = 2000 if state.sim_mode == 'advanced' else 400
        data, macd = generate_simulation_data(initial_price=20, length=data_len)
        state.sim_data = data; state.sim_macd = macd
        if state.sim_mode == 'advanced':
            state.sim_data_week, state.sim_macd_week = resample_klines(data, 5)
            state.sim_data_month, state.sim_macd_month = resample_klines(data, 20)
            state.sim_data_60d, state.sim_macd_60d = resample_klines(data, 60)
            state.sim_index = 1250
        else: state.sim_index = 80
        state.sim_balance = 100000; state.sim_shares = 0; state.sim_game_active = True
        state.sim_feedback = "游戏开始！请观察当前走势。"; state.sim_stats = {'correct': 0, 'wrong': 0, 'total': 0}; state.sim_shapes = []
        render_content()

    def process_action(action):
        if not state.sim_game_active: return
        cp = state.sim_data[state.sim_index]['close']; pct = state.sim_trade_percent / 100.0
        msg = ""
        if action == 'buy':
            shares = int((state.sim_balance * pct) // cp)
            if shares > 0: state.sim_balance -= shares * cp; state.sim_shares += shares; msg = f"买入 {shares} 股"
            else: ui.notify('资金不足', type='warning'); return
        elif action == 'sell':
            shares = int(state.sim_shares * pct)
            if shares == 0 and state.sim_shares > 0: shares = 1
            if shares > 0: state.sim_balance += shares * cp; state.sim_shares -= shares; msg = f"卖出 {shares} 股"
            else: ui.notify('没有持仓', type='warning'); return
        else: msg = "观望"
        
        if state.sim_mode == 'advanced':
             fb, sc, sh = analyze_advanced_action(action, state.sim_index, state.sim_data[:state.sim_index+1], {k: v[:state.sim_index+1] for k, v in state.sim_macd.items()}, state.sim_data_week, state.sim_macd_week, state.sim_data_month, state.sim_macd_month)
        else:
             fb, sc, sh = analyze_action(action, state.sim_data[:state.sim_index+1], {k: v[:state.sim_index+1] for k, v in state.sim_macd.items()}, state.sim_index)
        
        state.sim_shapes = sh
        if sc > 0: state.sim_stats['correct'] += 1
        elif sc == -1: state.sim_stats['wrong'] += 1
        state.sim_stats['total'] += 1
        state.sim_feedback = f"**操作**: {action.upper()} - {msg}\n\n**分析**: {fb}"
        if state.sim_index < len(state.sim_data) - 1: state.sim_index += 1
        else: state.sim_game_active = False
        render_content()

    def render_simulator_view():
        with ui.row().classes('w-full items-center justify-between py-1 px-2 bg-white rounded-lg shadow-sm mb-1'):
            if not state.sim_game_active:
                ui.label('实战模拟').classes('text-lg font-bold')
                ui.button(on_click=start_new_game).props('flat dense icon=restart_alt color=primary round')
            else:
                with ui.row().classes('w-full items-center no-wrap gap-2'):
                    ui.label(f'资金: ¥{state.sim_balance:,.0f}').classes('text-xs font-bold text-blue-700')
                    val = (state.sim_shares * state.sim_data[state.sim_index]["close"]) if state.sim_index < len(state.sim_data) else 0
                    ui.label(f'持仓: ¥{val:,.0f}').classes('text-xs font-bold')
                    total = state.sim_stats['total']
                    rate = (state.sim_stats['correct'] / total * 100) if total > 0 else 0
                    ui.label(f'胜率: {rate:.0f}%').classes('text-xs font-bold text-green-600')
                    ui.button(on_click=start_new_game).props('flat dense icon=restart_alt color=primary round')

        if not state.sim_game_active:
            with ui.column().classes('w-full min-h-[500px] items-center justify-center bg-blue-50 rounded-2xl p-8'):
                ui.label('缠论实战训练').classes('text-4xl font-extrabold mb-8')
                with ui.row().classes('gap-4'):
                    ui.button('初级模式', on_click=lambda: set_mode('basic')).props('large color=indigo')
                    ui.button('高级模式', on_click=lambda: set_mode('advanced')).props('large color=purple')
            return

        # SIMULATOR CORE CONTENT
        with ui.column().classes('w-full gap-4'):
            with ui.card().classes('w-full h-[350px] md:h-[450px] p-0 flex flex-col no-inner-shadow border border-gray-100 overflow-hidden'):
                if state.sim_mode == 'advanced':
                    with ui.row().classes('w-full px-2 py-1 bg-gray-50 border-b'):
                        with ui.button_group().props('flat dense'):
                             for p, label in [('day','日线'), ('week','周线'), ('month','月线')]:
                                ui.button(label, on_click=lambda p=p: switch_sim_period(p)).props(f'size=sm {"color=primary" if state.sim_view_period==p else ""}')
                
                # Dynamic data based on period
                chart_data = []; chart_macd = {}; disp_sh = []
                idx = state.sim_index
                if state.sim_view_period == 'day':
                    vs = max(0, idx - 79); ve = idx + 1
                    chart_data = state.sim_data[vs:ve]
                    chart_macd = {k: v[vs:ve] for k, v in state.sim_macd.items()}
                    for s in state.sim_shapes:
                        if 'x0' in s:
                            ns = s.copy()
                            if 'x0' in ns: ns['x0'] -= vs
                            if 'x1' in ns: ns['x1'] -= vs
                            disp_sh.append(ns)
                else:
                    source = state.sim_data_week if state.sim_view_period == 'week' else state.sim_data_month
                    m_source = state.sim_macd_week if state.sim_view_period == 'week' else state.sim_macd_month
                    curr_time = state.sim_data[idx]['time']
                    cut = 0
                    for i, k in enumerate(source):
                        if k['start_day_idx'] <= curr_time: cut = i + 1
                        else: break
                    vs = max(0, cut - 80); ve = cut
                    chart_data = source[vs:ve]
                    chart_macd = {k: v[vs:ve] for k, v in m_source.items()}
                    if len(source[:cut]) > 3:
                        raw = get_chanlun_shapes(source[:cut], {k: v[:cut] for k, v in m_source.items()}, cut-1)
                        for s in raw:
                            if max(s.get('x0', 0), s.get('x1', 0)) >= vs:
                                ns = s.copy(); ns['x0'] -= vs; ns['x1'] -= vs; disp_sh.append(ns)

                fig = create_candlestick_chart(chart_data, "", macd_data=chart_macd, shapes=disp_sh)
                fig.update_layout(
                    margin=dict(l=5, r=5, t=5, b=5),
                    autosize=True,
                    height=None, # Allow container to define height
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10))
                )
                with ui.element('div').classes('w-full flex-grow relative bg-white'):
                     custom_plotly(fig).classes('w-full h-full absolute inset-0')

            # Controls
            with ui.row().classes('w-full gap-4 flex-col md:flex-row items-stretch'):
                with ui.card().classes('flex-1 p-4 bg-indigo-50 shadow-none border border-indigo-100'):
                    feedback_html = re.sub(r'\*\*(.*?)\*\*', r'<b class="text-blue-900">\1</b>', state.sim_feedback.replace('\n', '<br/>'))
                    ui.html(f'<div class="text-[13px] leading-relaxed text-blue-800 font-sans">{feedback_html}</div>', sanitize=False)
                
                with ui.card().classes('w-full md:w-80 p-4 flex flex-col gap-4 shadow-none border border-gray-100'):
                    with ui.row().classes('w-full items-center justify-between'):
                        ui.label('每次交易比例').classes('text-xs font-bold text-gray-500')
                        ui.label(f'{state.sim_trade_percent}%').classes('text-xs font-bold text-primary').bind_text_from(state, 'sim_trade_percent', backward=lambda v: f'{v}%')
                    
                    ui.slider(min=10, max=100, step=10).bind_value(state, 'sim_trade_percent').props('label-always')
                    
                    with ui.row().classes('w-full gap-2 no-wrap'):
                         ui.button('买入', on_click=lambda: process_action('buy')).props('color=red unelevated').classes('flex-1')
                         ui.button('卖出', on_click=lambda: process_action('sell')).props('color=green unelevated').classes('flex-1')
                    ui.button('下根K线', on_click=lambda: process_action('hold')).props('outline color=primary').classes('w-full')

    render_menu(); render_content()

# --- 3. 市场工具应用 ---
class MoodState:
    def __init__(self): self.current_mood_tab = 'market'

@ui.page('/mood')
def mood_page():
    ui.page_title('市场情绪与资金')
    setup_common_ui(); state = MoodState()

    # Header 必须是顶层元素，不能嵌套在 Column 中
    with ui.header().classes('bg-white text-gray-800 border-b'):
        with ui.row().classes('items-center w-full max-w-7xl mx-auto px-4'):
             ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to('/')).props('flat dense')
             ui.label('市场情绪与资金').classes('text-lg font-bold')
             ui.space(); ui.button(icon='home', on_click=lambda: ui.navigate.to('/')).props('flat round color=grey')

    # 使用浅灰色背景包裹内容区域
    with ui.column().classes('w-full min-h-screen bg-mood'):
        content_container = ui.column().classes('w-full mood-content-area mt-4')
        def render_content():
            content_container.clear()
            # 彻底清理可能残留的类和样式
            # 使用 classes(replace='...') 对类进行全量替换
            # 必须清除残留的 inline style (如 max-width), 否则它会覆盖 CSS 类
            content_container.style(replace='')

            if state.current_mood_tab == 'money':
                # 资金流向：全屏宽屏模式，不使用 .mood-content-area
                # 移动端 px-[2px], PC端 px-8
                content_container.classes(replace='w-full px-[2px] md:px-8 mt-4')
            else:
                # 其他模块：受限宽度居中模式，使用 .mood-content-area
                content_container.classes(replace='w-full mood-content-area mt-4') 
                
            with content_container:
                is_mob = False
                try: is_mob = re.search(r'(mobile|android|iphone|ipad)', ui.context.client.request.headers.get('User-Agent', ''), re.I) is not None
                except: pass
                render_sentiment_view(state.current_mood_tab, on_nav, custom_plotly, is_mob)
        def on_nav(nt): state.current_mood_tab = nt; render_content()
        render_content()

if __name__ in {"__main__", "__mp_main__"}:
    try: port = int(os.environ.get('PORT', 8080))
    except: port = 8080
    ui.run(title='缠论 quant', port=port, host='0.0.0.0', reload=False, storage_secret='chanlun-secret')
