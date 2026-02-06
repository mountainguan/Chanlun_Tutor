
from nicegui import ui
import uuid
import json
from plotly.utils import PlotlyJSONEncoder

def setup_common_ui():
    """Sets up common UI elements like styles and scripts for Plotly."""
    ui.add_head_html('''
        <style>
            body { background-color: #fcfcfc; }
            .q-layout { background-color: #f5f7f9; } /* 全局背景 */
            .q-drawer { background-color: #f8f9fa; }
            .content-area { max-width: 900px; margin: 0 auto; padding: 20px; }
            /* mood-content-area: PC端占据 2/3 宽度 (66.67vw)，移动端及小屏保持全宽 */
            .mood-content-area { width: 100%; margin: 0 auto; padding: 16px; }
            @media (min-width: 1024px) {
                .mood-content-area { max-width: 66.67vw; }
            }
            .bg-mood { background-color: #f5f7f9 !important; }
            .nicegui-markdown h1 { font-size: 2.5rem; color: #d32f2f; margin-top: 2rem; }
            .nicegui-markdown h2 { font-size: 1.8rem; color: #1976d2; margin-top: 1.5rem; border-bottom: 2px solid #eee; padding-bottom: 0.5rem; }
            .nicegui-markdown h3 { font-size: 1.4rem; color: #424242; margin-top: 1.2rem; }
            .nicegui-markdown p { font-size: 1.1rem; line-height: 1.8; color: #333; margin-bottom: 1rem; }
            .nicegui-markdown ul, .nicegui-markdown ol { font-size: 1.1rem; line-height: 1.8; color: #333; margin-bottom: 1rem; }
            .nicegui-markdown blockquote { border-left: 4px solid #1976d2; padding-left: 1rem; color: #555; background: #f5f5f5; padding: 10px; border-radius: 4px; }
            
            .no-inner-shadow .shadow-sm, .no-inner-shadow .shadow-md, .no-inner-shadow .shadow-lg,
            .no-inner-shadow .rounded-lg, .no-inner-shadow .rounded-xl { box-shadow: none !important; }
            .no-inner-shadow .px-3 { padding-left: 0.6rem; padding-right: 0.6rem; }
            .hide-on-mobile { display: block !important; }
            @media (max-width: 767px) {
                .hide-on-mobile { display: none !important; }
            }
            .ag-row-estimated { background-color: #FFF9C4 !important; }
            .ag-row-estimated .ag-cell { color: #827717 !important; }

            /* Tab Navigation Styles */
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
            .hide-scrollbar::-webkit-scrollbar { display: none; }
            .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
        </style>
        <script>
        window.MathJax = {
            tex: {
                inlineMath: [['$', '$'], ['\\\\(', '\\\\)']]
            },
            svg: {
                fontCache: 'global'
            },
            options: {
                enableMenu: false,
                renderActions: {
                    assistiveMml: [], 
                    explorer: []
                }
            }
        };
        </script>
        <script src="/static/tex-chtml.min.js" id="MathJax-script" async onerror="this.onerror=null;this.src='https://cdn.bootcdn.net/ajax/libs/mathjax/4.0.0/tex-chtml.min.js';"></script>
        
        <script src="/static/plotly.min.js"></script>
        <script>
            if (typeof Plotly === 'undefined') {
                document.write('<script src="https://cdn.bootcdn.net/ajax/libs/plotly.js/3.1.1/plotly.min.js"><\/script>');
            }            
            
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
                             var hasPlotly = (typeof window.Plotly !== 'undefined');
                             if (hasPlotly) {
                                 try {
                                     Plotly.newPlot(item.id, item.data, item.layout, item.config).then(function(gd){
                                         try { Plotly.Plots.resize(gd); } catch(ex){}
                                     });
                                     window._chartQueue.splice(i, 1);
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

            window.renderPlotly = window.addToChartQueue; 
        </script>
    ''')

def custom_plotly(fig):
    """Renders a Plotly figure using the custom queue mechanism."""
    chart_id = f"chart_{uuid.uuid4().hex}"
    
    c = ui.element('div').props(f'id="{chart_id}"')
    
    if hasattr(fig, 'to_dict'):
        fig = fig.to_dict()
        
    data = fig.get('data', [])
    layout = fig.get('layout', {})
    config = fig.get('config', {'responsive': True, 'displayModeBar': False})
    
    config['responsive'] = True
    
    j_data = json.dumps(data, cls=PlotlyJSONEncoder)
    j_layout = json.dumps(layout, cls=PlotlyJSONEncoder)
    j_config = json.dumps(config, cls=PlotlyJSONEncoder)
    
    js = f'window.addToChartQueue("{chart_id}", {j_data}, {j_layout}, {j_config});'

    try:
        ui.timer(0.05, lambda: ui.run_javascript(js), once=True)
    except Exception:
        ui.run_javascript(js)
    
    return c
