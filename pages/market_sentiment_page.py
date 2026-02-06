
from nicegui import ui
from pages.money_flow_component import render_money_flow_panel
from pages.market_sentiment_component import render_market_sentiment_panel
from pages.sector_sentiment_component import render_sector_sentiment_panel
from pages.fund_radar_component import render_fund_radar_panel

def render_mood_tabs(active_tab, on_nav):
    with ui.row().classes('w-full justify-center mb-4 px-2'):
        with ui.row().classes('bg-white text-gray-500 rounded-full shadow-sm p-1 items-center flex-nowrap overflow-x-auto hide-scrollbar max-w-full border border-gray-200'):
            tabs_config = [
                ('market', '大盘温度'),
                ('sector', '板块温度'),
                ('money', '资金流向'),
                ('radar', '主力雷达'),
            ]
            for tab_id, label in tabs_config:
                is_active = (tab_id == active_tab)
                
                # Style logic
                base_classes = 'px-6 md:px-10 py-2 font-bold rounded-full flex-shrink-0 text-sm md:text-base'
                
                btn = ui.button(label, on_click=lambda t=tab_id: on_nav(t)) \
                    .props('flat no-caps no-ripple') \
                    .classes(base_classes)
                
                if is_active:
                    btn.classes('nav-tab-active')
                else:
                    btn.classes('nav-tab-inactive')

def render_sentiment_view(active_tab, on_nav, plotly_renderer, is_mobile):
    # 1. Navigation Tabs
    render_mood_tabs(active_tab, on_nav)
    
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
            with ui.column().classes('w-full px-2'):
                render_money_flow_panel(plotly_renderer=plotly_renderer)
        elif active_tab == 'radar':
            render_fund_radar_panel(plotly_renderer=plotly_renderer, is_mobile=is_mobile)

