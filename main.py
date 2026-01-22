from nicegui import ui
import json
import os
import re
from utils.charts import create_candlestick_chart, get_demo_fenxing_data, get_chart_data

# --- 数据加载 ---
def load_chapter_content(chapter_id):
    try:
        with open(f'content/{chapter_id}.md', 'r', encoding='utf-8-sig') as f:
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
        with open(f'questions/{chapter_id}.json', 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

# --- 状态管理 ---
class AppState:
    def __init__(self):
        self.current_chapter = 'chapter1' # 改为第0章开始
        self.current_view = 'learn' 

state = AppState()

# --- 界面构建 ---
@ui.page('/')
def main_page():
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
            }
        };
        </script>
        <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js" id="MathJax-script" async></script>
    ''')

    # 左侧导航栏 - 重新梳理的目录
    with ui.left_drawer(value=True).classes('w-64') as drawer:
        ui.label('缠论学习系统').classes('text-h6 q-pa-md')
        ui.separator()
        
        with ui.list().classes('w-full'):
            ui.label('第一卷：分型与笔').classes('q-ml-md text-grey-7 q-mt-sm text-sm')
            ui.item('第1章：K线包含处理', on_click=lambda: load_chapter('chapter1')).classes('cursor-pointer hover:bg-gray-200')
            ui.item('第2章：分型', on_click=lambda: load_chapter('chapter2')).classes('cursor-pointer hover:bg-gray-200')
            ui.item('第3章：笔的定义', on_click=lambda: load_chapter('chapter3')).classes('cursor-pointer hover:bg-gray-200')
            
            ui.separator()
            ui.label('第二卷：线段与中枢').classes('q-ml-md text-grey-7 q-mt-sm text-sm')
            ui.item('第4章：线段', on_click=lambda: load_chapter('chapter4')).classes('cursor-pointer hover:bg-gray-200')
            ui.item('第5章：中枢', on_click=lambda: load_chapter('chapter5')).classes('cursor-pointer hover:bg-gray-200')
            ui.item('第6章：走势类型', on_click=lambda: load_chapter('chapter6')).classes('cursor-pointer hover:bg-gray-200')
            
            ui.separator()
            ui.label('第三卷：动力学与背驰').classes('q-ml-md text-grey-7 q-mt-sm text-sm')
            ui.item('第7章：背驰', on_click=lambda: load_chapter('chapter7')).classes('cursor-pointer hover:bg-gray-200')
            ui.item('第8章：区间套与MACD', on_click=lambda: load_chapter('chapter8')).classes('cursor-pointer hover:bg-gray-200')
            ui.item('第9章：三类买卖点', on_click=lambda: load_chapter('chapter9')).classes('cursor-pointer hover:bg-gray-200')

            ui.separator()
            ui.label('第四卷：实战心法').classes('q-ml-md text-grey-7 q-mt-sm text-sm')
            ui.item('第10章：同级别分解', on_click=lambda: load_chapter('chapter10')).classes('cursor-pointer hover:bg-gray-200')
    
    # 主要内容容器
    content_container = ui.column().classes('w-full content-area')

    def render_content():
        content_container.clear()
        
        with content_container:
            # 标题与切换
            with ui.row().classes('w-full justify-between items-center q-mb-md'):
                ui.label(f'当前章节: {state.current_chapter}').classes('text-h5')
                with ui.button_group():
                    ui.button('学习模式', on_click=lambda: switch_view('learn')).props('outline' if state.current_view != 'learn' else '')
                    ui.button('实战练习', on_click=lambda: switch_view('quiz')).props('outline' if state.current_view != 'quiz' else '')

            if state.current_view == 'learn':
                render_learning_view()
            else:
                render_quiz_view()

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
                            ui.plotly(fig).classes('w-full h-80')
                    else:
                        ui.label(f"⚠️ 暂无图表数据: {scene_name}").classes('text-red')
                else:
                     ui.label(f"⚠️ 图表数据格式异常").classes('text-red')
            else:
                # 普通 Markdown 文本
                if part:
                    ui.markdown(part).classes('w-full nicegui-markdown')
        
        # 页面内容更新后，触发MathJax渲染
        ui.run_javascript('if (window.MathJax) MathJax.typesetPromise()')

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
                    ui.plotly(fig).classes('w-full h-80')

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
    def load_chapter(chapter_id):
        state.current_chapter = chapter_id
        state.current_view = 'learn' # 切换章节默认回学习模式
        render_content()

    def switch_view(view_mode):
        state.current_view = view_mode
        render_content()

    # 初始化渲染
    render_content()

ui.run(title='缠论学习助手', port=8080)
