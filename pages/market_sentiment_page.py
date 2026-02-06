
from nicegui import ui
from pages.money_flow_component import render_money_flow_panel
from pages.market_sentiment_component import render_market_sentiment_panel
from pages.sector_sentiment_component import render_sector_sentiment_panel
from pages.fund_radar_component import render_fund_radar_panel

def render_mood_tabs(active_tab, on_nav, is_mobile):
    tabs_config = [
        ('market', '大盘温度'),
        ('sector', '板块温度'),
        ('money', '资金流向'),
        ('radar', '主力雷达'),
    ]

    # --- PC 端视图 (仅在非移动设备渲染) ---
    if not is_mobile:
        with ui.row().classes('w-full justify-center mb-6'):
            with ui.row().classes('bg-white text-gray-500 rounded-full shadow-sm p-1.5 items-center gap-2 border border-gray-200'):
                for tab_id, label in tabs_config:
                    is_active = (tab_id == active_tab)
                    btn = ui.button(label, on_click=lambda t=tab_id: on_nav(t)) \
                        .props('flat no-caps no-ripple') \
                        .classes('px-8 py-2 rounded-full text-base font-bold transition-all duration-300')
                    
                    if is_active:
                        btn.classes('bg-indigo-600 text-white shadow-md transform scale-105')
                    else:
                        btn.classes('text-gray-500 hover:text-indigo-600 hover:bg-gray-50')

    # --- 移动端视图 (仅在移动设备渲染) ---
    if is_mobile:
        # 采用全宽网格布局 (Grid)，4等分，Segmented Control 风格
        with ui.element('div').classes('w-full px-1 mb-4'):
            with ui.grid(columns=4).classes('w-full gap-1 p-1 bg-gray-100/80 rounded-lg border border-gray-200'):
                for tab_id, label in tabs_config:
                    is_active = (tab_id == active_tab)
                    
                    # 字体大小 text-[11px] 约为 0.6875rem，防止小屏折行
                    btn = ui.button(label, on_click=lambda t=tab_id: on_nav(t)) \
                        .props('flat no-caps dense') \
                        .classes('w-full text-[11px] h-8 rounded-md font-bold transition-all duration-200') 
                    
                    if is_active:
                        # 选中状态：白色背景，轻微阴影，凸起感
                        btn.classes('bg-white text-indigo-700 shadow-sm border border-gray-100')
                    else:
                        # 未选中：透明，灰色文字
                        btn.classes('text-gray-500 bg-transparent')

def render_sentiment_view(active_tab, on_nav, plotly_renderer, is_mobile):
    # 1. Navigation Tabs
    render_mood_tabs(active_tab, on_nav, is_mobile)
    
    # 2. Content
    # Use wider container for 'money' flow
    container_classes = 'w-full items-center min-h-[500px]'
    if active_tab == 'money':
        # Remove constrained max-width by adding a full-width class that overrides mood-content-area if possible
        # Or we can just ensure the components inside are responsive.
        pass

    with ui.column().classes(container_classes):
        if active_tab == 'market':
            render_market_sentiment_panel(plotly_renderer=plotly_renderer, is_mobile=is_mobile)
        elif active_tab == 'sector':
            render_sector_sentiment_panel(plotly_renderer=plotly_renderer, is_mobile=is_mobile)
        elif active_tab == 'money':
            # Money flow needs full width on PC
            with ui.column().classes('w-full px-0 md:px-2'):
                render_money_flow_panel(plotly_renderer=plotly_renderer)
        elif active_tab == 'radar':
            render_fund_radar_panel(plotly_renderer=plotly_renderer, is_mobile=is_mobile)

