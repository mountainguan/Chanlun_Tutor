import json
import uuid
import re
from nicegui import ui
from plotly.utils import PlotlyJSONEncoder

from pages.money_flow_component import render_money_flow_panel
from pages.market_sentiment_component import render_market_sentiment_panel
from pages.sector_sentiment_component import render_sector_sentiment_panel
from pages.fund_radar_component import render_fund_radar_panel

def setup_common_header():
    # Inject Plotly optimization script
    ui.add_head_html('''
        <script src="/static/plotly.min.js"></script>
        <script>
            // Load Plotly robustly: try local static first, then CDN fallback
            if (typeof window._plotly_ready === 'undefined') {
                window._plotly_ready = false;
                (function(){
                    function markReady(){ window._plotly_ready = true; }
                    var s = document.createElement('script');
                    s.src = '/static/plotly.min.js';
                    s.async = true;
                    s.onload = function(){ markReady(); };
                    s.onerror = function(){
                        var c = document.createElement('script');
                        c.src = 'https://cdn.bootcdn.net/ajax/libs/plotly.js/3.1.1/plotly.min.js';
                        c.async = true;
                        c.onload = function(){ markReady(); };
                        document.head.appendChild(c);
                    };
                    document.head.appendChild(s);
                })();
            }

            // Global render queue to handle charts in hidden tabs or conditional v-if
            window._chartQueue = window._chartQueue || [];
            window._chartQueueRunning = false;
            
            window._processChartQueue = function() {
                if (window._chartQueue.length > 0) {
                     for (var i = window._chartQueue.length - 1; i >= 0; i--) {
                         var item = window._chartQueue[i];
                         var el = document.getElementById(item.id);
                         
                         if (!el) {
                              if (Date.now() - item.ts > 120000) { 
                                  window._chartQueue.splice(i, 1);
                              }
                              continue;
                         }
                         
                         var rect = el.getBoundingClientRect();
                         if (rect.width > 0 && rect.height > 0) {
                             var hasPlotly = (typeof window.Plotly !== 'undefined') || window._plotly_ready;
                             if (hasPlotly) {
                                 try {
                                     if (window.Plotly) {
                                         Plotly.newPlot(item.id, item.data, item.layout, item.config).then(function(gd){
                                             try { Plotly.Plots.resize(gd); } catch(ex){}
                                         });
                                         window._chartQueue.splice(i, 1);
                                     }
                                 } catch(e) {
                                     console.error("Queue Render failed for " + item.id, e);
                                 }
                             }
                         }
                     }
                }
                setTimeout(window._processChartQueue, 300);
            };
            
            if (!window._chartQueueRunning) {
               window._chartQueueRunning = true;
               window._processChartQueue();
            }

            window.addToChartQueue = function(id, data, layout, config) {
                var found = false;
                for(var i=0; i<window._chartQueue.length; i++){
                    if(window._chartQueue[i].id === id) {
                        window._chartQueue[i] = {id: id, data: data, layout: layout, config: config, ts: Date.now()};
                        found = true;
                        break;
                    }
                }
                if (!found) {
                    window._chartQueue.push({id: id, data: data, layout: layout, config: config, ts: Date.now()});
                }
            };
        </script>
    ''')

    # Inject additional CSS
    ui.add_head_html('''
        <style>
            .no-inner-shadow .shadow-sm, .no-inner-shadow .shadow-md, .no-inner-shadow .shadow-lg,
            .no-inner-shadow .rounded-lg, .no-inner-shadow .rounded-xl { box-shadow: none !important; }
            .no-inner-shadow .px-3 { padding-left: 0.6rem; padding-right: 0.6rem; }
            .hide-on-mobile { display: block !important; }
            @media (max-width: 767px) {
                .hide-on-mobile { display: none !important; }
            }
            .ag-row-estimated { background-color: #FFF9C4 !important; }
            .ag-row-estimated .ag-cell { color: #827717 !important; }
            
            /* Add active tab style - match exact look from user screenshot */
            .nav-tab-active {
                background-color: #5897d4 !important;
                color: white !important;
                border-radius: 9999px !important;
                box-shadow: none !important;
            }
            .nav-tab-active .q-btn__content {
                color: white !important;
            }
            .nav-tab-inactive {
                color: #5897d4 !important;
                opacity: 0.9;
            }
            /* Mobile scrollbar hide */
            .hide-scrollbar::-webkit-scrollbar { display: none; }
            .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
        </style>
    ''')

def custom_plotly(fig):
    chart_id = f"chart_{uuid.uuid4().hex}"
    
    if hasattr(fig, 'to_dict'):
        fig_dict = fig.to_dict()
    else:
        fig_dict = fig if isinstance(fig, dict) else {}
        
    layout = fig_dict.get('layout', {})
    height_px = layout.get('height') if isinstance(layout, dict) else None
    
    style_attr = 'style="width: 100%; min-height: 200px;"'
    if height_px:
        try:
            style_attr = f'style="height:{int(height_px)}px; min-height:{int(height_px)}px; width:100%;"'
        except Exception:
            pass
    
    c = ui.element('div').props(f'id="{chart_id}" {style_attr}')
    
    data = fig_dict.get('data', [])
    layout = fig_dict.get('layout', {})
    config = fig_dict.get('config', {'responsive': True, 'displayModeBar': False})
    config['responsive'] = True
    
    j_data = json.dumps(data, cls=PlotlyJSONEncoder)
    j_layout = json.dumps(layout, cls=PlotlyJSONEncoder)
    j_config = json.dumps(config, cls=PlotlyJSONEncoder)
    
    js = f'window.addToChartQueue("{chart_id}", {j_data}, {j_layout}, {j_config});'
    
    try:
        ui.timer(0.05, lambda: ui.run_javascript(js), once=True)
        ui.timer(0.5, lambda: ui.run_javascript(js), once=True)
    except Exception:
        ui.run_javascript(js)
    return c

def render_mood_layout(active_tab_name):
    # Header
    with ui.header().classes(replace='row items-center bg-white text-gray-800 shadow-sm border-b border-gray-200 h-16 px-4') as header:
        ui.button(icon='arrow_back', on_click=lambda: ui.run_javascript('window.location.href="/"')).props('flat round color=grey-8')
        ui.label('市场情绪温度监控').classes('text-xl font-bold ml-2')
        ui.space()

    with ui.column().classes('w-full items-center bg-gray-100 min-h-screen p-2 md:p-4'):
        # --- TABS: 悬浮胶囊风格 (URL 驱动 + 移动端滑动优化) ---
        with ui.row().classes('w-full justify-center mb-4 px-2'):
            with ui.row().classes('bg-white text-gray-500 rounded-full shadow-sm p-1 items-center flex-nowrap overflow-x-auto hide-scrollbar max-w-full border border-gray-100'):
                tabs_config = [
                    ('大盘温度', '/mood/market'),
                    ('板块温度', '/mood/sector'),
                    ('资金流向', '/mood/money'),
                    ('主力雷达', '/mood/radar'),
                ]
                for label, url in tabs_config:
                    is_active = label == active_tab_name
                    # 使用 no-ripple 移除 Q弹效果，使用 flat 保持扁平
                    btn = ui.button(label, on_click=lambda u=url: ui.run_javascript(f'window.location.href="{u}"')) \
                        .props('flat no-caps no-ripple') \
                        .classes('px-6 md:px-10 py-2 font-bold rounded-full flex-shrink-0 text-sm md:text-base')
                    
                    if is_active:
                        btn.classes('nav-tab-active')
                    else:
                        btn.classes('nav-tab-inactive')
        
        # 返回内容容器
        return ui.column().classes('w-full max-w-6xl mx-auto p-0 flex flex-col items-center gap-4')

def init_sentiment_page():
    @ui.page('/mood')
    def mood_redirect():
        ui.run_javascript('window.location.href="/mood/market"')

    @ui.page('/mood/market')
    def market_page():
        setup_common_header()
        ui.page_title('大盘温度 - 缠论小应用')
        is_mobile = re.search(r'(mobile|android|iphone|ipad)', ui.context.client.request.headers.get('User-Agent', ''), re.I) is not None
        with render_mood_layout('大盘温度'):
            render_market_sentiment_panel(plotly_renderer=custom_plotly, is_mobile=is_mobile)

    @ui.page('/mood/sector')
    def sector_page():
        setup_common_header()
        ui.page_title('板块温度 - 缠论小应用')
        is_mobile = re.search(r'(mobile|android|iphone|ipad)', ui.context.client.request.headers.get('User-Agent', ''), re.I) is not None
        with render_mood_layout('板块温度'):
            render_sector_sentiment_panel(plotly_renderer=custom_plotly, is_mobile=is_mobile)

    @ui.page('/mood/money')
    def money_page():
        setup_common_header()
        ui.page_title('资金流向 - 缠论小应用')
        # Money flow panel logic might handle wide layouts
        with render_mood_layout('资金流向').classes('max-w-[1920px]'):
            render_money_flow_panel(plotly_renderer=custom_plotly)

    @ui.page('/mood/radar')
    def radar_page():
        setup_common_header()
        ui.page_title('主力雷达 - 缠论小应用')
        is_mobile = re.search(r'(mobile|android|iphone|ipad)', ui.context.client.request.headers.get('User-Agent', ''), re.I) is not None
        with render_mood_layout('主力雷达'):
            render_fund_radar_panel(plotly_renderer=custom_plotly, is_mobile=is_mobile)

