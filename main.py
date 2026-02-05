import os

# 配置环境变量以解决云端部署可能的权限问题
os.environ['MPLCONFIGDIR'] = '/tmp'
os.environ['XDG_CONFIG_HOME'] = '/tmp'

from nicegui import ui, app
import json
import re
import uuid
from plotly.utils import PlotlyJSONEncoder
from utils.charts import create_candlestick_chart, get_demo_fenxing_data, get_chart_data
from utils.simulator_logic import generate_simulation_data, analyze_action, resample_klines, analyze_advanced_action, get_chanlun_shapes
from pages.market_sentiment_page import init_sentiment_page
import urllib.request


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

# 挂载静态文件目录，用于本地服务 Plotly.js 等资源
# 请确保下载 plotly.min.js 到 static 目录中
app.add_static_files('/static', os.path.join(BASE_DIR, 'static'))

# 初始化新页面
init_sentiment_page()

# --- 数据加载 ---
def load_chapter_content(chapter_id):
    try:
        file_path = os.path.join(BASE_DIR, 'content', f'{chapter_id}.md')
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            return f.read()
    except FileNotFoundError:
        return "章节内容未找到。"

def protect_math_content(text):
    # 保护LaTeX公式中的特殊字符(_和*)不被Markdown解析
    if not text:
        return text
    
    def repl(match):
        delimiter = match.group(1)
        content = match.group(2)
        # 保护下划线和星号，防止被Markdown解析为斜体或加粗
        content = content.replace('_', '\\_').replace('*', '\\*')
        return delimiter + content + delimiter
    
    # 匹配 $$...$$ 或 $...$
    # group 1: 捕获 $ 或 $$
    # group 2: 内容
    return re.sub(r'(\$\$?)(.*?)\1', repl, text, flags=re.DOTALL)

def load_questions(chapter_id):
    try:
        file_path = os.path.join(BASE_DIR, 'questions', f'{chapter_id}.json')
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

# --- 状态管理 ---
class AppState:
    def __init__(self):
        self.current_chapter = 'chapter1' 
        self.current_view = 'learn'
        
        # 模拟器状态
        self.sim_mode = 'basic' # basic / advanced
        self.sim_view_period = 'day' # day / week / month / 60d

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
        self.sim_history = []
        self.sim_feedback = "点击“开始新游戏”开始模拟交易。"
        self.sim_game_active = False
        self.sim_trade_percent = 100 # 交易仓位百分比
        self.sim_stats = {'correct': 0, 'wrong': 0, 'total': 0}
        self.sim_shapes = []

# --- 界面构建 ---
@ui.page('/')
def main_page():
    # 每个客户端连接创建一个新的状态实例
    state = AppState()

    # 自定义样式
    ui.add_head_html('''
        <style>
            .q-drawer { background-color: #f8f9fa; }
            .content-area { max-width: 800px; margin: 0 auto; padding: 20px; }
            .nicegui-markdown h1 { font-size: 2.5rem; color: #d32f2f; margin-top: 2rem; }
            .nicegui-markdown h2 { font-size: 1.8rem; color: #1976d2; margin-top: 1.5rem; border-bottom: 2px solid #eee; padding-bottom: 0.5rem; }
            .nicegui-markdown h3 { font-size: 1.4rem; color: #424242; margin-top: 1.2rem; }
            .nicegui-markdown p { font-size: 1.1rem; line-height: 1.8; color: #333; margin-bottom: 1rem; }
            .nicegui-markdown ul, .nicegui-markdown ol { font-size: 1.1rem; line-height: 1.8; color: #333; margin-bottom: 1rem; }
            .nicegui-markdown blockquote { border-left: 4px solid #1976d2; padding-left: 1rem; color: #555; background: #f5f5f5; padding: 10px; border-radius: 4px; }
        </style>
        <script>
        window.MathJax = {
            tex: {
                inlineMath: [['$', '$'], ['\\\\(', '\\\\)']]
            },
            svg: {
                fontCache: 'global'
            },
            // 通过置空 renderActions 彻底移除辅助功能模块的执行，防止浏览器尝试加载 speech-worker.js
            options: {
                enableMenu: false,
                renderActions: {
                    assistiveMml: [], 
                    explorer: []
                }
            }
        };
        </script>
        <!-- MathJax: 优先本地加载，失败回退 BootCDN -->
        <script src="/static/tex-chtml.min.js" id="MathJax-script" async onerror="this.onerror=null;this.src='https://cdn.bootcdn.net/ajax/libs/mathjax/4.0.0/tex-chtml.min.js';"></script>
        
        <!-- Plotly Optimization -->
        <script src="/static/plotly.min.js"></script>
        <script>
            if (typeof Plotly === 'undefined') {
                // 如果本地没有，尝试使用 BootCDN (国内速度快)
                document.write('<script src="https://cdn.bootcdn.net/ajax/libs/plotly.js/3.1.1/plotly.min.js"><\/script>');
            }            
            // 全局渲染函数：彻底解耦 NiceGUI 的 ui.plotly 依赖
            window.renderPlotly = function(id, data, layout, config) {
                // 简单的重试机制，确保 DOM 已创建
                var attempt = 0;
                function tryRender() {
                    var el = document.getElementById(id);
                    if (el && typeof Plotly !== 'undefined') {
                        Plotly.newPlot(id, data, layout, config);
                    } else {
                        if (attempt < 10) {
                            attempt++;
                            setTimeout(tryRender, 50);
                        } else {
                            console.error('Plotly render failed: element or library not found', id);
                        }
                    }
                }
                tryRender();
            }        </script>
    ''')

    # 左侧导航栏 - 重新梳理的目录
    with ui.header(elevated=True).classes('bg-white text-gray-800 border-b border-gray-200 md:hidden'):
        ui.button(on_click=lambda: drawer.toggle(), icon='menu').props('flat color=primary')
        ui.label('缠论学习系统').classes('text-lg font-bold text-primary q-ml-sm')

    with ui.left_drawer(value=True).classes('bg-gray-50 border-r border-gray-200') as drawer:
        ui.label('缠论学习系统').classes('text-h6 q-pa-md text-primary font-bold hidden md:block')
        ui.separator().classes('hidden md:block')
        
        menu_container = ui.column().classes('w-full')

    # 主要内容容器
    content_container = ui.column().classes('w-full content-area')

    # --- 自定义 Plotly 渲染组件 ---
    # 目的：替代 ui.plotly 以避免 NiceGUI 从服务器加载庞大的 plotly.js (1.4MB)，改用本地/CDN静态资源
    def custom_plotly(fig):
        # 生成唯一ID
        chart_id = f"chart_{uuid.uuid4().hex}"
        
        # 创建容器 div
        c = ui.element('div').props(f'id="{chart_id}"')
        
        # 处理数据
        if hasattr(fig, 'to_dict'):
            fig = fig.to_dict()
            
        data = fig.get('data', [])
        layout = fig.get('layout', {})
        config = fig.get('config', {'responsive': True, 'displayModeBar': False})
        
        # 强制响应式
        config['responsive'] = True
        
        # 序列化数据 (使用 Plotly 专用 Encoder 处理 Numpy 类型)
        j_data = json.dumps(data, cls=PlotlyJSONEncoder)
        j_layout = json.dumps(layout, cls=PlotlyJSONEncoder)
        j_config = json.dumps(config, cls=PlotlyJSONEncoder)
        
        # 调用前端渲染
        ui.run_javascript(f'window.renderPlotly("{chart_id}", {j_data}, {j_layout}, {j_config})')
        
        return c

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
            ]},
            {'title': '市场工具', 'items': [
                {'id': 'mood', 'label': '大盘情绪温度 🌡️', 'special': True, 'link': '/mood/market'},
            ]}
        ]

        with menu_container:
            for group in chapters_struct:
                ui.label(group['title']).classes('q-ml-md text-grey-7 q-mt-sm text-sm font-bold')
                for item in group['items']:
                    is_active = state.current_chapter == item['id']
                    
                    # 动态计算样式
                    base_classes = 'cursor-pointer q-px-md q-py-sm transition-colors duration-200'
                    if is_active:
                        # 选中状态
                        style_classes = f'{base_classes} bg-blue-100 text-blue-800 border-r-4 border-blue-600 font-medium'
                    else:
                        # 未选中状态
                        style_classes = f'{base_classes} hover:bg-gray-200 text-gray-700'
                    
                    # 特殊项目（模拟器）额外样式
                    if item.get('special'):
                         if not is_active:
                             style_classes += ' font-bold text-blue-800'
                    
                    lbl = ui.label(item['label']).classes(style_classes)
                    if item.get('link'):
                        lbl.on('click', lambda _, l=item['link']: ui.run_javascript(f'window.location.href="{l}"'))
                    else:
                        lbl.on('click', lambda _, i=item['id']: load_chapter(i))

    def render_content():
        content_container.clear()
        
        with content_container:
            if state.current_chapter == 'simulator':
                render_simulator_view()
                return

            # 标题与切换
            with ui.row().classes('w-full justify-between items-center q-mb-md wrap gap-2'):
                ui.label(f'当前章节: {state.current_chapter}').classes('text-h5 font-bold text-gray-800')
                with ui.button_group().classes('shadow-sm'):
                    ui.button('学习模式', on_click=lambda: switch_view('learn')).props(f'{"outline" if state.current_view != "learn" else ""} color=primary')
                    ui.button('实战练习', on_click=lambda: switch_view('quiz')).props(f'{"outline" if state.current_view != "quiz" else ""} color=primary')

            if state.current_view == 'learn':
                render_learning_view()
            else:
                render_quiz_view()

    def render_simulator_view():
        # --- 1. 顶部紧凑工具栏 ---
        # 优化：减少上下内边距 (py-1) 和底部外边距 (mb-1)，节省移动端空间
        with ui.row().classes('w-full items-center justify-between py-1 px-2 bg-white rounded-lg shadow-sm border border-gray-100 mb-1'):
            
            if not state.sim_game_active:
                # 游戏未开始：简单标题
                with ui.row().classes('items-center gap-2'):
                    ui.icon('candlestick_chart', size='sm', color='primary')
                    ui.label('实战模拟').classes('text-lg font-bold text-gray-800')
                # 右侧按钮
                ui.button(on_click=start_new_game).props('flat dense icon=restart_alt color=primary round').tooltip('开始挑战')
            else:
                # 游戏进行中：移动端grid平铺，PC端flex
                with ui.row().classes('w-full items-center no-wrap gap-2'):
                    # PC 端标题 (移动端隐藏)
                    with ui.row().classes('items-center gap-2 hidden md:flex mr-4'):
                        ui.icon('candlestick_chart', size='sm', color='primary')
                        ui.label('实战模拟').classes('text-lg font-bold text-gray-800')
                        ui.separator().props('vertical')
                    
                    # 数据区域：移动端 grid-cols-3 平铺，PC 端 flex gap-6
                    with ui.element('div').classes('col-grow grid grid-cols-3 gap-1 md:flex md:gap-6 items-center'):
                        
                        # 样式：移动端居中，PC端左对齐
                        col_style = 'flex flex-col items-center md:items-start gap-1'
                        lbl_style = 'text-[10px] md:text-xs text-gray-500 leading-none'
                        val_style = 'text-xs md:text-sm font-bold leading-none'

                        # 1. 资金
                        with ui.element('div').classes(col_style):
                            ui.label('当前资金').classes(lbl_style)
                            ui.label(f'¥{state.sim_balance:,.0f}').classes(f'{val_style} text-blue-700')
                        
                        # 2. 持仓
                        with ui.element('div').classes(col_style):
                            ui.label('持仓市值').classes(lbl_style)
                            val = (state.sim_shares * state.sim_data[state.sim_index]["close"]) if state.sim_index < len(state.sim_data) else 0
                            ui.label(f'¥{val:,.0f}').classes(f'{val_style} text-gray-700')
                        
                        # 3. 胜率
                        with ui.element('div').classes(col_style):
                            ui.label('合理率').classes(lbl_style)
                            rate_text = '--'
                            total = state.sim_stats['correct'] + state.sim_stats['wrong']
                            if total > 0:
                                rate = (state.sim_stats['correct'] / total) * 100
                                rate_text = f'{rate:.0f}%'
                            color = 'text-green-600' if total > 0 and rate >= 60 else 'text-orange-600'
                            ui.label(rate_text).classes(f'{val_style} {color}')

                    # 右侧按钮组
                    with ui.row().classes('items-center gap-2'):
                        ui.button(on_click=start_new_game).props('flat dense icon=restart_alt color=primary round').tooltip('重置/新游戏')

        # --- 2. 游戏未开始状态 ---
        if not state.sim_game_active:
             # 使用 min-h 代替 h，防止内容溢出；padding 在移动端适当减小
             with ui.column().classes('w-full min-h-[500px] items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-100 rounded-2xl p-4 md:p-8 shadow-sm'):
                
                # 视觉中心图像
                with ui.element('div').classes('relative w-24 h-24 md:w-32 md:h-32 mb-4 md:mb-6 flex items-center justify-center bg-white rounded-full shadow-md'):
                    ui.icon('ssid_chart', size='3rem').classes('md:text-6xl text-blue-500')
                    # 装饰性小图标
                    ui.icon('currency_yen', size='1rem').classes('absolute -top-2 -right-2 text-yellow-500 bg-yellow-100 rounded-full p-1 md:text-2xl')
                    ui.icon('show_chart', size='1rem').classes('absolute -bottom-2 -left-2 text-green-500 bg-green-100 rounded-full p-1 md:text-2xl')

                ui.label('缠论操盘手训练营').classes('text-2xl md:text-4xl font-extrabold text-gray-800 mb-2 md:mb-3 tracking-tight text-center')
                
                with ui.column().classes('items-center mb-6 md:mb-8 gap-1 w-full px-2'):
                    ui.label('随机生成历史K线走势，完全模拟真实交易环境').classes('text-sm md:text-lg text-gray-600 text-center')
                    ui.label('运用分型、笔、线段、中枢理论，通过实战检验你的缠论水平').classes('text-xs md:text-base text-gray-500 text-center max-w-lg leading-relaxed')
                
                # 模式选择
                # 移动端 flex-col (垂直堆叠), 桌面端 flex-row (水平排列)
                with ui.element('div').classes('w-full flex flex-col md:flex-row justify-center items-center gap-4 mb-4 md:mb-8'):
                    with ui.card().classes('w-full md:w-48 p-4 cursor-pointer hover:shadow-lg transition-all text-center flex flex-col items-center gap-2 group hover:bg-blue-50 border border-blue-100').on('click', lambda: set_mode('basic')):
                        ui.icon('school', size='lg').classes('text-blue-500 mb-1 group-hover:scale-110 transition-transform')
                        ui.label('初级模式').classes('font-bold text-lg md:text-xl text-blue-900')
                        ui.label('单一K线级别(日线)').classes('text-xs text-gray-500')
                        ui.label('点击直接开始').classes('text-xs text-blue-400 mt-2 font-bold')

                    with ui.card().classes('w-full md:w-48 p-4 cursor-pointer hover:shadow-lg transition-all text-center flex flex-col items-center gap-2 group hover:bg-purple-50 border border-purple-100').on('click', lambda: set_mode('advanced')):
                        ui.icon('auto_graph', size='lg').classes('text-purple-500 mb-1 group-hover:scale-110 transition-transform')
                        ui.label('高级模式').classes('font-bold text-lg md:text-xl text-purple-900')
                        ui.label('多级别联立(日/周/月)').classes('text-xs text-gray-500')
                        ui.label('点击直接开始').classes('text-xs text-purple-400 mt-2 font-bold')

             return

        # --- 3. 游戏主界面 (响应式布局) ---
        with ui.column().classes('w-full gap-4'):
            
            # Layer 1: Chart Area
            # 移动端高度较小，桌面端较大
            # 改为 flex column 布局，确保 toolbar 和 chart 垂直排列且不重叠
            # 优化：PC端高度从 500px 减小到 380px，以便一屏显示
            with ui.card().classes('w-full h-[250px] md:h-[380px] p-0 overflow-hidden relative-position border-none shadow-sm flex flex-col'):
                
                # 统一的周期切换工具栏 (所有端可见)
                if state.sim_mode == 'advanced':
                    with ui.row().classes('w-full items-center justify-between px-2 py-1 bg-gray-50 border-b'):
                        ui.label('K线周期').classes('text-xs text-gray-500 font-bold ml-1')
                        # 使用 flat 无边框风格，更加融入 Toolbar
                        with ui.button_group().props('flat'):
                             for p, label in [('day','日线'), ('week','周线'), ('month','月线'), ('60d','60分')]:
                                ui.button(label, on_click=lambda p=p: switch_sim_period(p)).props(f'size=sm {"color=primary" if state.sim_view_period==p else "color=grey"}')
                
                # Determine data source based on current view period
                # Default is daily
                chart_data = []
                chart_macd = {}
                highlight_shapes = getattr(state, 'sim_shapes', [])
                
                if state.sim_view_period == 'day':
                    # 日线模式下，只显示到 sim_index
                    visible_end = state.sim_index + 1
                    visible_start = max(0, visible_end - 80)
                    chart_data = state.sim_data[visible_start:visible_end]
                    
                    chart_macd = {
                        'dif': state.sim_macd['dif'][visible_start:visible_end],
                        'dea': state.sim_macd['dea'][visible_start:visible_end],
                        'hist': state.sim_macd['hist'][visible_start:visible_end]
                    }
                    
                    # 转换高亮形状坐标 (全局索引 -> 视图相对索引)
                    display_shapes = []
                    for s in highlight_shapes:
                        # 优化：只显示视野范围内的形状，防止旧数据导致的 Y 轴压缩变形
                        # 如果形状是区间(有x1)，且结束点在视野开始之前，则跳过
                        if 'x1' in s and s['x1'] < visible_start:
                            continue
                        # 如果形状是点(无x1有x0)，且点在视野开始之前，则跳过
                        if 'x1' not in s and 'x0' in s and s['x0'] < visible_start:
                            continue

                        new_s = s.copy()
                        if 'x0' in new_s: new_s['x0'] -= visible_start
                        if 'x1' in new_s: new_s['x1'] -= visible_start
                        display_shapes.append(new_s)
                        
                elif state.sim_view_period in ['week', 'month', '60d']:
                    # 高级周期：根据当前日线时间，找到对应的大级别截止时间
                    # 1. 找到当前日线时间
                    current_time_idx = state.sim_data[state.sim_index]['time']
                    
                    # 2. 确定对应大级别数据的截止索引
                    target_source = []
                    target_macd = {}
                    
                    if state.sim_view_period == 'week':
                        target_source = state.sim_data_week
                        target_macd = state.sim_macd_week
                    elif state.sim_view_period == 'month':
                        target_source = state.sim_data_month
                        target_macd = state.sim_macd_month
                    elif state.sim_view_period == '60d':
                        target_source = state.sim_data_60d
                        target_macd = state.sim_macd_60d
                        
                    # 截取到包含当前日期的那一根（或者之前）
                    cut_idx = 0
                    for i, k in enumerate(target_source):
                        if k['start_day_idx'] <= current_time_idx:
                            cut_idx = i + 1
                        else:
                            break
                    
                    visible_end = cut_idx
                    visible_start = max(0, visible_end - 80)
                    chart_data = target_source[visible_start:visible_end]
                    
                    if target_macd and 'dif' in target_macd:
                        chart_macd = {
                            'dif': target_macd['dif'][visible_start:visible_end],
                            'dea': target_macd['dea'][visible_start:visible_end],
                            'hist': target_macd['hist'][visible_start:visible_end]
                        }
                    
                    # 高级级别：实时计算该级别的缠论形态
                    # 需要传入所有已知数据来进行计算，然后截取显示区域
                    known_data = target_source[:cut_idx]
                    
                    # 构造对应的 known_macd 数据
                    known_macd = {}
                    if target_macd and 'dif' in target_macd:
                        known_macd = {
                            'dif': target_macd['dif'][:cut_idx],
                            'dea': target_macd['dea'][:cut_idx],
                            'hist': target_macd['hist'][:cut_idx]
                        }
                        
                    # 只有数据足够时才计算
                    display_shapes = []
                    if len(known_data) > 3:
                        # 计算所有形态
                        raw_shapes = get_chanlun_shapes(known_data, known_macd, len(known_data)-1)
                        
                        # 转换坐标 (从全局索引 -> 视图相对索引)
                        for s in raw_shapes:
                            # 过滤：只显示 visible_start 之后的形状
                            # 对于 type='line'，x0 和 x1 至少有一个在视野内
                            # 对于 type='rect'，x0 或 x1 在视野内
                            s_in_view = False
                            
                            # 获取形状的时间坐标
                            x0 = s.get('x0', -999)
                            x1 = s.get('x1', -999)
                            
                            # 简单判断：如果形状右边界在视野左侧之前，则不显示
                            # 如果形状左边界在视野右侧之后（不可能，因为只计算到 cut_idx），则不显示
                            if max(x0, x1) >= visible_start:
                                s_in_view = True
                                
                            if s_in_view:
                                new_s = s.copy()
                                if 'x0' in new_s: new_s['x0'] -= visible_start
                                if 'x1' in new_s: new_s['x1'] -= visible_start
                                display_shapes.append(new_s)

                fig = create_candlestick_chart(chart_data, "", macd_data=chart_macd, shapes=display_shapes)
                fig.update_layout(
                    margin=dict(l=10, r=0, t=0, b=0), # 减小边距
                    height=None, 
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    showlegend=False,
                    dragmode=False, # 禁止交互，防止移动端误触
                    # 移除 ModeBar 工具栏的所有按钮，变相隐藏工具条
                    modebar=dict(
                        remove=['zoom', 'pan', 'select', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d', 'toImage', 'hoverClosestCartesian', 'hoverCompareCartesian', 'toggleSpikelines']
                    )
                )
                # 全局禁用缩放和平移
                fig.update_xaxes(fixedrange=True)
                fig.update_yaxes(fixedrange=True)
                
                # 将图表渲染在一个容器中，并且不使用 absolute
                # 如果有 toolbar，图表需要减去 toolbar 高度。但最简单的是使用 flex 布局。
                # 由于外层 card 是 relative-position 且 overflow-hidden
                # 我们将 card 改为 column flex，这样 Toolbar 和 Chart 自然垂直排列
                # custom_plotly(fig).classes('w-full h-full absolute') -> Remove absolute, use flex-grow
                
                # 注意：外层 card 已经被设置为 p-0。
                # 我们需要一个占位符来容纳 Plotly，并让它填满剩余空间。
                with ui.element('div').classes('w-full flex-grow relative'):
                     custom_plotly(fig).classes('w-full h-full absolute inset-0')

            # Legend (Outside the card)
            with ui.row().classes('w-full justify-start gap-2 px-2 py-1 text-[10px] text-gray-600 bg-gray-100 rounded-md border border-gray-200'):
                ui.label('图例:').classes('font-bold mr-1')
                with ui.row().classes('items-center gap-1.5'):
                    ui.element('div').classes('w-4 h-0.5 bg-gray-600')
                    ui.label('笔(Bi)')
                with ui.row().classes('items-center gap-1.5'):
                    ui.element('div').classes('w-3 h-3 bg-orange-200 border border-orange-400 opacity-80')
                    ui.label('中枢(Box)')
                with ui.row().classes('items-center gap-1.5'):
                     ui.element('div').classes('w-3 h-3 bg-green-100 border border-green-600')
                     ui.label('顶分型')
                with ui.row().classes('items-center gap-1.5'):
                     ui.element('div').classes('w-3 h-3 bg-red-100 border border-red-600')
                     ui.label('底分型')

            # Layer 2: Analysis & Control
            # 移动端: 垂直堆叠 (Wrap), 桌面端: 水平排列 (No-wrap)
            with ui.row().classes('w-full items-stretch gap-4 md:flex-nowrap flex-wrap'):
                
                # Part A: Analysis (移动端占满, 桌面端占2/3)
                # 移动端: h-auto min-h-[120px] 让内容自然撑开
                # 桌面端: 高度稍微减小以适应一屏
                with ui.card().classes('w-full md:w-2/3 h-auto min-h-[120px] md:min-h-[140px] p-2 bg-indigo-50 border-l-4 border-indigo-400 gap-1 no-wrap'):
                    with ui.row().classes('items-center gap-1 text-indigo-900 q-px-xs'):
                        ui.icon('psychology', size='xs')
                        ui.label('分析师解读').classes('font-bold text-xs')
                    
                    # 移除 scroll_area，改用普通 div 让内容自然撑开高度 (移动端体验更好)
                    with ui.column().classes('w-full bg-white/60 rounded p-2'):
                        # 分割内容以进行布局优化
                        full_text = state.sim_feedback
                        if "**分析**:" in full_text:
                            parts = full_text.split("**分析**:")
                            action_part = parts[0].replace("**操作**:", "").strip()
                            analysis_part = parts[1].strip()
                            
                            # 1. 操作行 - 现代化小卡片样式
                            # 根据操作类型给不同的颜色装饰
                            op_style = 'bg-gray-100 text-gray-700 border-gray-200'
                            if '买' in action_part: op_style = 'bg-red-50 text-red-700 border-red-200'
                            elif '卖' in action_part: op_style = 'bg-green-50 text-green-700 border-green-200'
                            
                            with ui.row().classes(f'w-full items-center px-2 py-1.5 mb-2 rounded border {op_style}'):
                                ui.icon('touch_app', size='xs').classes('opacity-70')
                                ui.label(action_part).classes('text-xs font-bold')

                            # 2. 分析行 - 优化排版与字体大小
                            # 处理加粗样式
                            html_content = re.sub(r'\*\*(.*?)\*\*', r'<span class="font-bold text-indigo-900">\1</span>', analysis_part)
                            # 智能处理换行：保留段落结构，增加段间距
                            html_content = html_content.replace('\n', '<br/>')
                            
                            # 优化：移动端行间距紧凑 (leading-normal/snug)，桌面端宽松 (leading-relaxed)
                            ui.html(html_content, sanitize=False).classes('text-[13px] leading-snug md:leading-relaxed text-gray-800 font-sans')
                        else:
                             # 初始状态或纯文本
                             ui.label(full_text).classes('text-[13px] text-gray-600 leading-snug md:leading-relaxed')

                # Part B: Control Pad (移动端占满, 桌面端占1/3)
                with ui.card().classes('w-full md:w-1/3 p-4 bg-white shadow-sm flex flex-col justify-between gap-3'):
                    # Slider
                    with ui.column().classes('w-full gap-1'):
                        with ui.row().classes('justify-between w-full'):
                            ui.label('仓位控制').classes('text-sm font-bold text-gray-600')
                            ui.label().bind_text_from(state, 'sim_trade_percent', lambda v: f'{v}%').classes('text-sm font-bold text-primary')
                        
                        slider = ui.slider(min=10, max=100, step=10, value=state.sim_trade_percent).props('dense selection-color=primary')
                        slider.bind_value(state, 'sim_trade_percent')

                    # Buttons
                    with ui.row().classes('w-full gap-2 no-wrap'):
                         can_buy = state.sim_balance > 0
                         ui.button('买入', on_click=lambda: process_action('buy')) \
                            .props(f'color=red glossy glossy icon=trending_up size=md {"disabled" if not can_buy else ""}') \
                            .classes('col-grow')
                         
                         can_sell = state.sim_shares > 0
                         ui.button('卖出', on_click=lambda: process_action('sell')) \
                            .props(f'color=green glossy icon=trending_down size=md {"disabled" if not can_sell else ""}') \
                            .classes('col-grow')
                    
                    ui.button('观望 / 下一根K线', on_click=lambda: process_action('hold')) \
                        .props('outline color=grey icon=visibility size=md') \
                        .classes('w-full')

    def render_learning_view():
        text = load_chapter_content(state.current_chapter)
        # 预处理文本，保护数学公式
        text = protect_math_content(text)
        
        # Markdown 解析 + 图表注入
        # 使用正则分割文本，查找 ::: chart:xxx ::: 模式
        parts = re.split(r'(:::\s*chart:[\w_]+\s*:::)', text)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 检查是否为图表标签
            # 匹配 ::: chart:xxx :::
            chart_match = re.match(r':::\s*chart:([\w_]+)\s*:::', part)
            if chart_match:
                scene_name = chart_match.group(1)
                
                # 获取动态图表数据
                chart_res = get_chart_data(scene_name)
                # 解包，支持 4 个或 5 个返回值 (MACD)
                if len(chart_res) >= 4:
                    data = chart_res[0]
                    title = chart_res[1]
                    annotations = chart_res[2]
                    shapes = chart_res[3]
                    macd_data = chart_res[4] if len(chart_res) > 4 else None
                    
                    if data:
                        with ui.card().classes('w-full q-my-md p-2 bg-gray-50'):
                            ui.label(f'【图解】{title}').classes('text-subtitle1 text-grey-8 q-mb-sm')
                            fig = create_candlestick_chart(data, title, annotations=annotations, shapes=shapes, macd_data=macd_data)
                            custom_plotly(fig).classes('w-full h-80')
                    else:
                        ui.label(f"⚠️ 暂无图表数据: {scene_name}").classes('text-red')
                else:
                     ui.label(f"⚠️ 图表数据格式异常").classes('text-red')
            else:
                # 普通 Markdown 文本
                if part:
                    ui.markdown(part).classes('w-full nicegui-markdown')
        
        # 页面内容更新后，触发MathJax渲染
        # 必须检查 typesetPromise 是否存在，因为 MathJax 可能还在加载中（此时 window.MathJax 是配置对象）
        ui.run_javascript('if (window.MathJax && window.MathJax.typesetPromise) MathJax.typesetPromise()')

    def render_quiz_view():
        questions = load_questions(state.current_chapter)
        if not questions:
            ui.label('本章暂无练习题。').classes('text-gray-500')
            return

        for idx, q in enumerate(questions):
            with ui.card().classes('w-full q-mb-md p-4'):
                ui.label(f"题目 {idx+1}: {q['question']}").classes('text-lg text-bold q-mb-sm')
                
                # 如果题目包含图表数据
                if q.get('type') == 'chart_recognition' and 'chart_config' in q:
                    config = q['chart_config']
                    fig = create_candlestick_chart(
                        config['data'], 
                        "识别形态", 
                        annotations=config.get('annotations'),
                        shapes=config.get('shapes'),
                        macd_data=config.get('macd_data')
                    )
                    custom_plotly(fig).classes('w-full h-80')

                # 选项逻辑
                def check_answer(user_value, options_list, correct_idx, result_label, explain_container, explain_text):
                    # 先清空之前的解析显示
                    explain_container.clear()
                    
                    if not user_value:
                        ui.notify('请先选择一个答案', type='warning')
                        return

                    try:
                        ans_idx = options_list.index(user_value)
                    except ValueError:
                        ui.notify('选项数据已更新，请刷新页面', type='negative')
                        return
                    
                    if ans_idx == correct_idx:
                        result_label.set_text('✅ 回答正确！')
                        result_label.classes('text-green-600', remove='text-red-600')
                    else:
                        result_label.set_text('❌ 回答错误。')
                        result_label.classes('text-red-600', remove='text-green-600')
                    
                    # 显示解析
                    with explain_container:
                         ui.markdown(f"**解析：** {explain_text}").classes('q-mt-sm bg-gray-100 p-2 rounded')

                options = q['options']
                
                with ui.column().classes('q-mt-sm'):
                    radio = ui.radio(options).props('column')
                    result_lbl = ui.label().classes('text-lg font-bold q-mt-sm')
                    explanation_ui = ui.column() # 占位容器
                    
                    ui.button('提交答案', on_click=lambda 
                              r=radio, 
                              c=q['answer'], 
                              l=result_lbl, 
                              ec=explanation_ui,
                              e=q['explanation'],
                              opts=options: 
                              check_answer(r.value, opts, c, l, ec, e)
                    ).classes('q-mt-sm')

    # --- 交互动作 ---
    async def load_chapter(chapter_id):
        state.current_chapter = chapter_id
        if chapter_id == 'simulator':
            state.current_view = 'simulator'
        else:
            state.current_view = 'learn'
        
        # 刷新菜单状态（高亮当前章节）
        render_menu()
        render_content()
        
        # 移动端加载章节后自动收起左侧菜单
        # 通过 JS 检查屏幕宽度，如果小于 md (768px) 则收起抽屉
        try:
            is_mobile = await ui.run_javascript('window.innerWidth < 768')
            if is_mobile:
                drawer.value = False
        except:
            # 忽略可能的 JS 执行错误（例如连接断开）
            pass

    def switch_view(view_mode):
        state.current_view = view_mode
        render_content()

    def set_mode(mode):
        state.sim_mode = mode
        start_new_game()

    def switch_sim_period(period):
        state.sim_view_period = period
        render_content()

    def start_new_game():
        # 增加数据长度以支持大级别
        # 5年数据约为 1250 天，为了保证游戏还能继续玩，生成 2000 天
        data_len = 2000 if state.sim_mode == 'advanced' else 400
        data, macd = generate_simulation_data(initial_price=20, length=data_len)
        
        state.sim_data = data
        state.sim_macd = macd
        
        if state.sim_mode == 'advanced':
            state.sim_data_week, state.sim_macd_week = resample_klines(data, 5)
            state.sim_data_month, state.sim_macd_month = resample_klines(data, 20)
            state.sim_data_60d, state.sim_macd_60d = resample_klines(data, 60)
            # 高级模式下，初始让时间多走一些，以展示长期趋势（约5年）
            state.sim_index = 1250
        else:
            state.sim_data_week = []
            state.sim_macd_week = {}
            state.sim_data_month = []
            state.sim_macd_month = {}
            state.sim_data_60d = []
            state.sim_macd_60d = {}
            # 初级模式保持较短热身期
            state.sim_index = 80

        state.sim_balance = 100000
        state.sim_balance = 100000
        state.sim_shares = 0
        state.sim_game_active = True
        state.sim_feedback = "游戏开始！请观察当前走势，寻找买卖点。"
        state.sim_stats = {'correct': 0, 'wrong': 0, 'total': 0}
        state.sim_shapes = []
        render_content()

    def process_action(action):
        if not state.sim_game_active: return
        
        # 1. 获取当前价格
        current_price = state.sim_data[state.sim_index]['close']
        percent = state.sim_trade_percent / 100.0
        
        # 2. 执行交易
        trade_msg = ""
        if action == 'buy':
            if state.sim_balance >= current_price: 
                # 计算可用资金的百分比用于买入
                funds_to_use = state.sim_balance * percent
                shares_to_buy = int(funds_to_use // current_price)
                
                if shares_to_buy > 0:
                    cost = shares_to_buy * current_price
                    state.sim_balance -= cost
                    state.sim_shares += shares_to_buy
                    trade_msg = f"买入 {shares_to_buy} 股 ({state.sim_trade_percent}%)"
                else:
                    ui.notify('资金不足以买入一手', type='warning')
                    return
            else:
                ui.notify('资金不足', type='warning')
                # 买入失败时不推进
                return 
                
        elif action == 'sell':
            if state.sim_shares > 0:
                # 计算持仓的百分比用于卖出
                shares_to_sell = int(state.sim_shares * percent)
                if shares_to_sell == 0 and state.sim_shares > 0 and percent > 0:
                     shares_to_sell = 1 # 至少卖一股

                if shares_to_sell > 0:
                    revenue = shares_to_sell * current_price
                    state.sim_balance += revenue
                    state.sim_shares -= shares_to_sell
                    trade_msg = f"卖出 {shares_to_sell} 股 ({state.sim_trade_percent}%)"
                else:
                     ui.notify('卖出数量为0', type='warning')
                     return
            else:
                 ui.notify('没有持仓', type='warning')
                 return 
        else:
             trade_msg = "观望"
        
        # 3. 产生评价
        if state.sim_mode == 'advanced':
             feedback, score, shapes = analyze_advanced_action(
                 action, 
                 state.sim_index, 
                 state.sim_data[:state.sim_index+1], 
                 {k: v[:state.sim_index+1] for k, v in state.sim_macd.items()},
                 state.sim_data_week, state.sim_macd_week,
                 state.sim_data_month, state.sim_macd_month
             )
        else:
             feedback, score, shapes = analyze_action(action, state.sim_data[:state.sim_index+1], {
                k: v[:state.sim_index+1] for k, v in state.sim_macd.items()
             }, state.sim_index)
        
        state.sim_shapes = shapes
        
        # 更新统计
        if score > 0: # 1 or more (bonus)
            state.sim_stats['correct'] += 1
            state.sim_stats['total'] += 1
        elif score == -1:
            state.sim_stats['wrong'] += 1
            state.sim_stats['total'] += 1
        
        state.sim_feedback = f"**操作**: {action.upper()} - {trade_msg}\n\n**分析**: {feedback}"

        # 4. 推进时间
        if state.sim_index < len(state.sim_data) - 1:
            state.sim_index += 1
        else:
            state.sim_feedback += "\n\n**游戏结束！数据已走完。**"
            state.sim_game_active = False
            
        render_content()


    # 初始化渲染
    render_menu()
    render_content()

if __name__ in {"__main__", "__mp_main__"}:
    # Zeabur deployment support: Use PORT env var and bind to 0.0.0.0
    try:
        port = int(os.environ.get('PORT', 8080))
    except ValueError:
        # Fallback to default port if PORT env var is not a valid integer (e.g. "${WEB_PORT}")
        port = 8080
        
    # reload=False is important for production to avoid file watching errors
    ui.run(title='缠论学习助手', port=port, host='0.0.0.0', reload=False, storage_secret='chanlun-secret')
