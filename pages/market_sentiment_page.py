from nicegui import ui
from pages.money_flow_component import render_money_flow_panel
from pages.market_sentiment_component import render_market_sentiment_panel
from pages.sector_sentiment_component import render_sector_sentiment_panel
from pages.fund_radar_component import render_fund_radar_panel
import json
import uuid
from plotly.utils import PlotlyJSONEncoder

def init_sentiment_page():
    @ui.page('/mood')
    def sentiment_page():
        import re
        is_mobile = re.search(r'(mobile|android|iphone|ipad)', ui.context.client.request.headers.get('User-Agent', ''), re.I) is not None
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
                    // Always request next frame first to keep loop alive if we want persistent checking,
                    // but for performance we might want to be smart.
                    // For now, let's just run every 500ms via setTimeout instead of RAF to save battery 
                    // when idle, or mix them. 
                    // Let's use a simpler approach: run loop.
                    
                    if (window._chartQueue.length > 0) {
                         // Iterate backwards to allow safe removal
                         for (var i = window._chartQueue.length - 1; i >= 0; i--) {
                             var item = window._chartQueue[i];
                             var el = document.getElementById(item.id);
                             
                             if (!el) {
                                  // Element might be gone (re-rendered or removed)
                                  // Keep it for a bit? No, just remove it if it's truly gone from DOM.
                                  // But maybe it's just detached momentarily? 
                                  // Let's assume if it's not by ID, it's gone or hasn't arrived.
                                  // We'll give it a lifespan (timestamp)
                                  if (Date.now() - item.ts > 120000) { // 2 mins timeout
                                      window._chartQueue.splice(i, 1);
                                  }
                                  continue;
                             }
                             
                             // Check visibility
                             var rect = el.getBoundingClientRect();
                             // Width/Height > 0 usually means visible
                             if (rect.width > 0 && rect.height > 0) {
                                 // Check Plotly lib
                                 var hasPlotly = (typeof window.Plotly !== 'undefined') || window._plotly_ready;
                                 if (hasPlotly) {
                                     try {
                                         // Render!
                                         // If Plotly object exists on window but might not be fully ready? 
                                         // We assume if _plotly_ready is set, window.Plotly is available or will be momentarily.
                                         if (window.Plotly) {
                                             Plotly.newPlot(item.id, item.data, item.layout, item.config).then(function(gd){
                                                 try { Plotly.Plots.resize(gd); } catch(ex){}
                                             });
                                             // Remove from queue
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
                    // Check if already in queue, update if so
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

        # Inject additional CSS to support flat card styling for specific sections
        ui.add_head_html('''
            <style>
                /* no-inner-shadow helper: keep outer element shadows but remove shadows from inner elements */
                .no-inner-shadow .shadow-sm, .no-inner-shadow .shadow-md, .no-inner-shadow .shadow-lg,
                .no-inner-shadow .rounded-lg, .no-inner-shadow .rounded-xl { box-shadow: none !important; }
                /* Ensure inner card elements don't show elevated borders */
                .no-inner-shadow .px-3 { padding-left: 0.6rem; padding-right: 0.6rem; }
                /* hide-on-mobile: show by default, hide when viewport is narrow */
                .hide-on-mobile { display: block !important; }
                @media (max-width: 767px) {
                    .hide-on-mobile { display: none !important; }
                }
                /* AgGrid estimated row style */
                .ag-row-estimated { background-color: #FFF9C4 !important; }
                .ag-row-estimated .ag-cell { color: #827717 !important; }
            </style>
        ''')

        # Custom Plotly render function
        def custom_plotly(fig):
            chart_id = f"chart_{uuid.uuid4().hex}"
            # determine desired height from figure layout (fallback None)
            layout = fig.get('layout', {}) if isinstance(fig, dict) else {}
            height_px = layout.get('height') if isinstance(layout, dict) else None
            
            # Default styling to ensure non-zero height
            style_attr = 'style="width: 100%; min-height: 400px;"'
            if height_px:
                try:
                    style_attr = f'style="height:{int(height_px)}px; min-height:{int(height_px)}px; width:100%;"'
                except Exception:
                    pass
            
            # Create element
            c = ui.element('div').props(f'id="{chart_id}" {style_attr}')
            
            if hasattr(fig, 'to_dict'):
                fig = fig.to_dict()
            data = fig.get('data', [])
            layout = fig.get('layout', {})
            config = fig.get('config', {'responsive': True, 'displayModeBar': False})
            config['responsive'] = True
            
            j_data = json.dumps(data, cls=PlotlyJSONEncoder)
            j_layout = json.dumps(layout, cls=PlotlyJSONEncoder)
            j_config = json.dumps(config, cls=PlotlyJSONEncoder)
            
            # Simply push to queue
            js = f'window.addToChartQueue("{chart_id}", {j_data}, {j_layout}, {j_config});'
            
            try:
                ui.timer(0.05, lambda: ui.run_javascript(js), once=True)
                # Backup push
                ui.timer(0.5, lambda: ui.run_javascript(js), once=True)
            except Exception:
                ui.run_javascript(js)
            return c

        ui.page_title('情绪温度监控 - 缠论小应用')
        
        # Header
        with ui.header().classes(replace='row items-center bg-white text-gray-800 shadow-sm border-b border-gray-200 h-16 px-4') as header:
            ui.button(icon='arrow_back', on_click=lambda: ui.run_javascript('window.location.href="/"')).props('flat round color=grey-8')
            ui.label('市场情绪温度监控').classes('text-xl font-bold ml-2')
            
            ui.space() # Spacer

        with ui.column().classes('w-full items-center bg-gray-100 min-h-screen p-4'):
            
            # --- TABS: 悬浮胶囊风格 ---
            with ui.row().classes('w-full justify-center mb-4'):
                with ui.tabs().classes('bg-white text-gray-500 rounded-full shadow-md p-1') \
                        .props('indicator-color="transparent" active-color="white" active-bg-color="primary" active-class="shadow-sm rounded-full bg-gradient-to-r from-blue-500 to-indigo-600 text-white"') as tabs:
                    market_tab = ui.tab('大盘温度').classes('px-8 font-bold tracking-wide transition-all')
                    sector_tab = ui.tab('板块温度').classes('px-8 font-bold tracking-wide transition-all')
                    money_tab = ui.tab('资金流向').classes('px-8 font-bold tracking-wide transition-all')
                    radar_tab = ui.tab('主力雷达').classes('px-8 font-bold tracking-wide transition-all')

            with ui.tab_panels(tabs, value=market_tab).classes('w-full bg-transparent p-0'):
                
                # --- MARKET TAB ---
                with ui.tab_panel(market_tab).classes('w-full max-w-6xl mx-auto p-0 flex flex-col items-center gap-4'):
                    render_market_sentiment_panel(plotly_renderer=custom_plotly, is_mobile=is_mobile)

                # --- SECTOR TAB ---
                with ui.tab_panel(sector_tab).classes('w-full max-w-6xl mx-auto p-0 flex flex-col items-center gap-4'):
                    render_sector_sentiment_panel(plotly_renderer=custom_plotly, is_mobile=is_mobile)

                # --- MONEY FLOW TAB ---
                with ui.tab_panel(money_tab).classes('w-full max-w-[1920px] mx-auto p-0 flex flex-col gap-6'):
                    render_money_flow_panel(plotly_renderer=custom_plotly)

                # --- RADAR TAB ---
                with ui.tab_panel(radar_tab).classes('w-full max-w-6xl mx-auto p-0 flex flex-col items-center gap-4'):
                    render_fund_radar_panel(plotly_renderer=custom_plotly, is_mobile=is_mobile)

        # Finished rendering panels
