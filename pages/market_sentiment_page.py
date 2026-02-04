from nicegui import ui
from pages.money_flow_component import render_money_flow_panel
from pages.market_sentiment_component import render_market_sentiment_panel
from pages.sector_sentiment_component import render_sector_sentiment_panel
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

                // Robust render: wait until element exists AND has non-zero size before plotting
                window._plotly_cache = window._plotly_cache || {};
                window.renderPlotly = function(id, data, layout, config) {
                    var attempt = 0;
                    function tryRender() {
                        var el = document.getElementById(id);
                        var hasPlotly = (typeof window.Plotly !== 'undefined') || window._plotly_ready;
                        if (el && hasPlotly) {
                            var width = el.offsetWidth || el.clientWidth || (el.getBoundingClientRect && el.getBoundingClientRect().width) || 0;
                            var height = el.offsetHeight || el.clientHeight || (el.getBoundingClientRect && el.getBoundingClientRect().height) || 0;
                            if (width > 0 && height > 0) {
                                try {
                                    // If Plotly is not yet attached to window but _plotly_ready is true,
                                    // give browser a brief moment to expose the global.
                                    if (typeof window.Plotly === 'undefined' && window._plotly_ready) {
                                        setTimeout(function(){ try{ window.Plotly && Plotly.newPlot(id, data, layout, config).then(function(){ window._plotly_cache[id] = {data:data, layout:layout, config:config}; }); }catch(e){} }, 50);
                                    } else {
                                        Plotly.newPlot(id, data, layout, config).then(function(){ window._plotly_cache[id] = {data:data, layout:layout, config:config}; });
                                    }
                                    // attempt a safe resize after render
                                    setTimeout(function(){ try{ window.Plotly && Plotly.Plots.resize(document.getElementById(id)); }catch(e){} }, 120);
                                } catch (err) {
                                    // swallow error to avoid noisy console spam
                                }
                            } else {
                                if (attempt < 20) {
                                    attempt++;
                                    setTimeout(tryRender, 100);
                                }
                                return;
                            }
                        } else {
                            if (attempt < 20) {
                                attempt++;
                                setTimeout(tryRender, 100);
                            }
                        }
                    }
                    tryRender();
                }
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
            style_attr = ''
            if height_px:
                try:
                    style_attr = f'style="height:{int(height_px)}px;min-height:{int(height_px)}px; width:100%;"'
                except Exception:
                    style_attr = ''
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
            js = f'''
(function(){{
    var id = "{chart_id}";
    var data = {j_data};
    var layout = {j_layout};
    var config = {j_config};
    var attempts = 0;
    function tryRender(){{
        try{{
            var el = document.getElementById(id);
            var hasPlotly = (typeof window.Plotly !== 'undefined') || window._plotly_ready;
            if (el && hasPlotly){{
                var width = el.offsetWidth || el.clientWidth || (el.getBoundingClientRect && el.getBoundingClientRect().width) || 0;
                var height = el.offsetHeight || el.clientHeight || (el.getBoundingClientRect && el.getBoundingClientRect().height) || 0;
                // if height is zero, try to find a parent width/height or set a sensible minHeight
                if (height === 0){{
                    try{{ el.style.minHeight = el.style.minHeight || '260px'; }}catch(e){{}}
                    height = el.offsetHeight || el.clientHeight || (el.getBoundingClientRect && el.getBoundingClientRect().height) || 0;
                }}
                if (width > 0 && height > 0){{
                    try{{
                        // prefer the shared helper if available
                        if (window.renderPlotly){{
                            window.renderPlotly(id, data, layout, config);
                        }} else if (window.Plotly){{
                            Plotly.newPlot(id, data, layout, config).then(function(){{ try{{ Plotly.Plots.resize(document.getElementById(id)); }}catch(e){{}} }});
                        }}
                        // attempt a resize after render
                        setTimeout(function(){{ try{{ window.Plotly && Plotly.Plots.resize(document.getElementById(id)); }}catch(e){{}} }}, 120);
                    }}catch(err){{}}
                    return;
                }}
            }}
        }}catch(e){{}}
        attempts += 1;
        if (attempts < 40){{
            setTimeout(tryRender, 100);
        }}
    }}
    tryRender();
}})();
'''
            # schedule JS render shortly after the element is attached to DOM
            try:
                ui.timer(0.05, lambda: ui.run_javascript(js), once=True)
                # extra fallback run to handle longer race windows
                ui.timer(0.25, lambda: ui.run_javascript(js), once=True)
            except Exception:
                # final fallback: run immediately
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

        # Finished rendering panels
