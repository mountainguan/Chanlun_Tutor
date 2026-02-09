
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
            .mood-content-area { width: 100%; margin: 0 auto; padding: 2px; }
            @media (min-width: 768px) {
                .mood-content-area { padding: 16px; }
            }
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
        (function(){
            // Create Loading UI
            var spinCss = document.createElement('style');
            spinCss.innerHTML = '@keyframes spin{to{transform:rotate(360deg)}}';
            document.head.appendChild(spinCss);
            
            var box = document.createElement('div');
            box.id = 'res-loader';
            box.style.cssText = 'position:fixed;bottom:20px;right:20px;background:rgba(30,30,30,0.95);color:#fff;padding:12px 20px;border-radius:30px;box-shadow:0 4px 12px rgba(0,0,0,0.2);z-index:99999;font-family:system-ui,sans-serif;font-size:13px;display:flex;align-items:center;gap:10px;backdrop-filter:blur(4px);transition:all 0.5s cubic-bezier(0.68, -0.55, 0.27, 1.55);transform:translateY(100px);opacity:0;';
            box.innerHTML = '<div style="width:18px;height:18px;border:3px solid #fff;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;"></div><div><div style="font-weight:600;margin-bottom:2px;">资源加载中...</div><div style="font-size:11px;opacity:0.75;" id="res-timer">等待连接 0.0s</div></div>';
            
            function showBox() {
                if(document.body) { 
                    document.body.appendChild(box);
                    // Force reflow
                    void box.offsetWidth;
                    box.style.transform = 'translateY(0)';
                    box.style.opacity = '1';
                } else {
                    document.addEventListener('DOMContentLoaded', showBox);
                }
            }
            showBox();

            var start = Date.now();
            window._resStatus = { 'MathJax': false, 'Plotly': false };
            
            var timer = setInterval(function(){
                var t = ((Date.now()-start)/1000).toFixed(1);
                var el = document.getElementById('res-timer');
                if(el) el.innerText = '已耗时 ' + t + 's';
                
                // 简单的超时提示
                if(parseFloat(t) > 5.0 && document.querySelector('#res-loader div div:first-child').innerText === '资源加载中...') {
                     document.querySelector('#res-loader div div:first-child').innerText = '资源加载较慢，请耐心等待...';
                }
            }, 100);
            
            window._resLoad = function(name) {
                window._resStatus[name] = true;
                if(window._resStatus['MathJax'] && window._resStatus['Plotly']) {
                    clearInterval(timer);
                    if(box) {
                        box.style.background = 'rgba(46, 125, 50, 0.95)';
                        box.innerHTML = '<div style="display:flex;align-items:center;gap:8px"><span style="font-size:18px">✓</span><span style="font-weight:600">加载完成</span></div>';
                        setTimeout(function(){ 
                            box.style.opacity = '0'; 
                            box.style.transform = 'translateY(20px)';
                        }, 1500);
                        setTimeout(function(){ if(box.parentNode) box.remove(); }, 2000);
                    }
                }
            };
            
            window._resErr = function(name, fallbackSrc) {
                console.warn(name + ' CDN failed, fallback to local...');
                var el = document.getElementById('res-timer');
                if(el) el.innerText = '网络超时，切换本地源...';
                
                var s = document.createElement('script');
                s.src = fallbackSrc;
                s.onload = function() { window._resLoad(name); };
                document.head.appendChild(s);
            };
        })();
        </script>
        
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
                sre: {
                    speech: 'none'
                },
                renderActions: {
                    assistiveMml: [], 
                    explorer: []
                }
            }
        };
        </script>
        <script src="https://cdn.jsdmirror.com/npm/mathjax@4.0.0/tex-chtml.js" id="MathJax-script" async 
             onload="window._resLoad('MathJax')" 
             onerror="window._resErr('MathJax', '/static/tex-chtml.min.js')">
        </script>
        
        <script src="https://cdn.jsdmirror.com/npm/plotly.js-dist-min@3.1.1/plotly.min.js" async 
             onload="window._resLoad('Plotly')" 
             onerror="window._resErr('Plotly', '/static/plotly.min.js')">
        </script>
        <script>
            // Plotly loader removed, handled by async events above            
            
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
                var isMobile = window.innerWidth < 768 || /Mobi|Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
                if (isMobile) {
                    config.staticPlot = true;
                }
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
        ui.timer(0, lambda: ui.run_javascript(js), once=True)
    except Exception:
        ui.run_javascript(js)
    
    return c
