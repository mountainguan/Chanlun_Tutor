import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from nicegui import ui
from pages.shared import setup_common_ui, custom_plotly
from pages.social_security_component import render_social_security_panel

def create_social_security_page():
    """
    创建美观的国家队持股情况页面（Fintech Fresh 风格）
    """
    @ui.page('/social-security')
    def social_security_page():
        ui.page_title('国家队持股情况')
        setup_common_ui()

        # --- Header ---
        with ui.header().classes('bg-white text-gray-800 border-b border-gray-200 shadow-sm'):
            with ui.row().classes('items-center w-full max-w-7xl mx-auto px-4 h-16'):
                ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to('/')).props('flat dense rounded color=gray')
                
                with ui.row().classes('items-center gap-2 ml-2'):
                    ui.icon('security', color='indigo').classes('text-2xl')
                    ui.label('国家队持股情况').classes('text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-600 to-teal-500')
                
                ui.space()
                ui.button(icon='home', on_click=lambda: ui.navigate.to('/')).props('flat round color=grey').tooltip('返回首页')

        # --- Main Content ---
        with ui.column().classes('w-full min-h-screen bg-gray-50/50 py-8'):
            with ui.column().classes('w-full max-w-7xl mx-auto px-4 gap-6'):
                # Render the component
                render_social_security_panel(plotly_renderer=custom_plotly)
                
                # Instruction Footer
                with ui.expansion('查看功能说明', icon='info').classes('w-full bg-white border border-gray-100 rounded-lg shadow-sm'):
                    with ui.column().classes('p-4 text-gray-600 text-sm'):
                        ui.markdown('''
                        **国家队持股情况说明**

                        - **数据来源**: 东方财富/Akshare 接口获取的最新季度国家队（社保、养老金）持仓数据。
                        - **更新频率**: 每一季度更新一次（通常在季报披露期结束后）。
                        - **主要指标**:
                        
                            - **总持股市值**: 当前所有被国家队持有的股票市值总和。
                            - **重仓股 TOP 10**: 按市值排名的前10大重仓股。
                        ''')

    return social_security_page

# Create page instance
social_security_page_instance = create_social_security_page()