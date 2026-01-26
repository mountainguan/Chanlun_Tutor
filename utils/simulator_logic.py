import numpy as np
import random

def calculate_ema(values, span):
    values = np.array(values, dtype=float)
    if len(values) == 0:
        return np.array([])
    alpha = 2 / (span + 1)
    ema = np.zeros_like(values)
    ema[0] = values[0]
    for i in range(1, len(values)):
        ema[i] = alpha * values[i] + (1 - alpha) * ema[i-1]
    return ema

def calculate_macd(close_prices, fast_period=12, slow_period=26, signal_period=9):
    values = np.array(close_prices, dtype=float)
    if len(values) == 0:
        return {'dif': [], 'dea': [], 'hist': []}
        
    ema_fast = calculate_ema(values, fast_period)
    ema_slow = calculate_ema(values, slow_period)
    
    dif = ema_fast - ema_slow
    dea = calculate_ema(dif, signal_period)
    hist = (dif - dea) * 2
    
    return {
        'dif': dif.tolist(),
        'dea': dea.tolist(),
        'hist': hist.tolist()
    }

def generate_simulation_data(initial_price=100, length=300):
    """
    生成模拟的K线数据
    """
    data = []
    # 确保初始价格在合理范围内 (1~100)
    initial_price = max(5.0, min(95.0, float(initial_price)))
    price = initial_price
    trend = 0  # 趋势因子 (百分比)
    
    for i in range(length):
        # 1. 确定今日涨跌停限制 (昨收 * 1.1 / 0.9)
        # 涨跌幅最大 10%
        limit_up = round(price * 1.10, 2)
        limit_down = round(price * 0.90, 2)
        
        # 2. 只有在价格范围内 (1~100) 才有效
        limit_up = min(limit_up, 100.0)
        limit_down = max(limit_down, 1.0)
        
        # 偶尔改变趋势 (每30天)
        if i % 30 == 0: 
            # 趋势偏置: 每天倾向涨/跌多少百分比 (-1% 到 1%)
            trend = np.random.normal(0, 0.005) 
            
        # 3. 生成开盘价 (Pre-market fluctuation)
        # 多数时候平开，偶尔小幅高开低开
        open_shock = np.random.normal(0, 0.005) 
        open_p = price * (1 + open_shock)
        
        # 4. 生成收盘价 (Day fluctuation based on trend)
        # 日内波动 ~2% + 趋势
        day_change = np.random.normal(0, 0.02) + trend
        close_p = price * (1 + day_change)
        
        # 5. 生成最高最低 (High/Low)
        # 基于open/close 扩展
        raw_high = max(open_p, close_p) * (1 + abs(np.random.normal(0, 0.01)))
        raw_low = min(open_p, close_p) * (1 - abs(np.random.normal(0, 0.01)))
        
        # 6. 修正所有价格到限制范围内
        def clamp(val):
            return max(limit_down, min(limit_up, val))
            
        open_p = clamp(open_p)
        close_p = clamp(close_p)
        high_p = clamp(raw_high)
        low_p = clamp(raw_low)
        
        # 7. 再次确保逻辑一致性 (H >= max(O,C), L <= min(O,C))
        high_p = max(high_p, open_p, close_p)
        low_p = min(low_p, open_p, close_p)

        data.append({
            'time': i,
            'open': round(open_p, 2),
            'high': round(high_p, 2),
            'low': round(low_p, 2),
            'close': round(close_p, 2)
        })
        
        price = close_p

    # 计算MACD
    closes = [d['close'] for d in data]
    macd = calculate_macd(closes)
    
    return data, macd

def identify_fenxing(klines):
    """
    简单判断最后3根K线是否构成顶分型或底分型
    klines: 至少包含最后3根K线的数据 list of dict
    """
    if len(klines) < 3:
        return None
        
    k1, k2, k3 = klines[-3], klines[-2], klines[-1]
    
    # 简单的顶分型定义：中间K线高点最高，底不最低（这里简化，严谨缠论需要包含处理）
    # 缠论标准：顶分型是中指最高点最高，最低点也最高（不包含关系后）
    # 这里我们假设已经经过包含处理，或者简单判断高低点
    
    is_top = k2['high'] > k1['high'] and k2['high'] > k3['high']
    is_bottom = k2['low'] < k1['low'] and k2['low'] < k3['low']
    
    if is_top: return 'top'
    if is_bottom: return 'bottom'
    return None

def check_divergence(klines, macd_data, index, lookback=30):
    """
    检查背驰，返回描述和需要高亮的形状数据
    """
    if index < lookback: return None, []
    
    current_k = klines[index]
    current_hist = macd_data['hist'][index]
    
    # 以前 lookback 根K线作为参考系
    start_lookback = index - lookback
    prev_klines = klines[start_lookback:index]
    prev_hists = macd_data['hist'][start_lookback:index]
    
    if not prev_klines: return None, []

    # ---底背驰判断---
    # 条件1：创新低
    min_prev_low = float('inf')
    min_prev_idx = -1
    
    for i, k in enumerate(prev_klines):
        if k['low'] < min_prev_low:
            min_prev_low = k['low']
            # i 是相对 prev_klines 的索引，min_prev_idx 需要是全局索引
            min_prev_idx = start_lookback + i
            
    if current_k['low'] < min_prev_low:
        # 条件2：MACD绿柱没有创新低 (动能衰竭)
        min_hist_prev = min(prev_hists)
        if current_hist < 0 and current_hist > min_hist_prev:
            shapes = [{
                'type': 'line',
                'xref': 'x', 'yref': 'y',
                'x0': min_prev_idx, 'y0': min_prev_low,
                'x1': index, 'y1': current_k['low'],
                'line': {'color': 'rgba(255, 0, 0, 0.8)', 'width': 2, 'dash': 'dot'}
            }]
            return "底背驰（价格新低但绿柱未加深）", shapes
            
    # ---顶背驰判断---
    # 条件1：创新高
    max_prev_high = float('-inf')
    max_prev_idx = -1
    
    for i, k in enumerate(prev_klines):
        if k['high'] > max_prev_high:
            max_prev_high = k['high']
            max_prev_idx = start_lookback + i
            
    if current_k['high'] > max_prev_high:
        # 条件2：MACD红柱没有创新高
        max_hist_prev = max(prev_hists)
        if current_hist > 0 and current_hist < max_hist_prev:
            shapes = [{
                'type': 'line',
                'xref': 'x', 'yref': 'y',
                'x0': max_prev_idx, 'y0': max_prev_high,
                'x1': index, 'y1': current_k['high'],
                'line': {'color': 'rgba(0, 128, 0, 0.8)', 'width': 2, 'dash': 'dot'}
            }]
            return "顶背驰（价格新高但红柱未增长）", shapes
            
    return None, []


def analyze_action(action, klines, macd_data, current_index):
    """
    评价用户的操作，结合分型、MACD和背驰
    action: 'buy', 'sell', 'hold'
    current_index: 当前K线在总数据中的索引
    """
    # 基础数据准备
    recent_k = klines[max(0, current_index-2):current_index+1]
    dif = macd_data['dif'][current_index]
    dea = macd_data['dea'][current_index]
    hist = macd_data['hist'][current_index]
    hist_prev = macd_data['hist'][current_index-1] if current_index > 0 else 0
    
    # 形态判断
    fenxing = identify_fenxing(recent_k)
    divergence_desc, divergence_shapes = check_divergence(klines, macd_data, current_index)

    # 收集需要高亮的区域形状
    highlight_shapes = []
    if divergence_shapes:
        highlight_shapes.extend(divergence_shapes)

    if fenxing:
        # 高亮最近3根K线 (current_index-2 到 current_index)
        k_subset = klines[current_index-2 : current_index+1]
        if k_subset:
            max_h = max(k['high'] for k in k_subset)
            min_l = min(k['low'] for k in k_subset)
            
            # 底分型用淡红色背景(提示买入?)或者淡绿色，顶分型用淡绿色?
            # 通常：底分型是买点信号(红)，顶分型是卖点(绿)。
            # 注意: fillcolor 的 alpha 设置很低以免遮挡 K 线
            if fenxing == 'bottom':
                box_color = 'rgba(255, 0, 0, 0.1)' # 偏红
                border_color = 'rgba(255, 0, 0, 0.5)'
            else:
                box_color = 'rgba(0, 128, 0, 0.1)' # 偏绿
                border_color = 'rgba(0, 128, 0, 0.5)'
            
            highlight_shapes.append({
                'type': 'rect',
                'xref': 'x', 'yref': 'y',
                'x0': current_index - 2 - 0.4, 
                'x1': current_index + 0.4,
                'y0': min_l,
                'y1': max_h,
                'fillcolor': box_color,
                'line': {'color': border_color, 'width': 1, 'dash': 'solid'}
            })
    
    # 均线辅助 (MA5, MA20)
    closes = [k['close'] for k in klines[:current_index+1]]
    ma5 = np.mean(closes[-5:]) if len(closes) >= 5 else closes[-1]
    ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else closes[-1]
    trend = "多头" if ma5 > ma20 else "空头"
    
    msg = []
    
    # 1. 市场状态描述
    status_desc = []
    if hist > 0:
        if hist > hist_prev: status_desc.append("多头动能增强")
        else: status_desc.append("多头动能衰减")
    else:
        if hist < hist_prev: status_desc.append("空头动能增强")
        else: status_desc.append("空头动能衰减")
        
    if divergence_desc:
        status_desc.append(f"出现{divergence_desc}")
    
    if fenxing == 'top': status_desc.append("形成顶分型")
    elif fenxing == 'bottom': status_desc.append("形成底分型")
        
    msg.append(f"**市场状态**: {', '.join(status_desc)} ({trend}排列)")

    # 2. 操作评价
    eval_msg = ""
    score = 0 # 1: 合理/极佳, 0: 普通/中性, -1: 不合理/失误
    
    if action == 'buy':
        if divergence_desc and "底背驰" in divergence_desc:
            eval_msg = "🔥 **极佳操作 (一买)**：捕捉到底背驰，是缠论定义的第一类买点！"
            score = 1
        elif fenxing == 'bottom' and trend == '多头':
            eval_msg = "✅ **合理操作 (二买/三买)**：多头趋势回调出现的底分型，确认为次级别调整结束。"
            score = 1
        elif fenxing == 'bottom':
            eval_msg = "⚠️ **激进操作**：空头趋势下的底分型，若无大级别背驰支持，极可能是下跌中继。"
            score = 0
        elif hist > 0 and hist > hist_prev:
            eval_msg = "⚠️ **追涨风险**：红柱加速伸长时买入，易买在笔的顶部，非缠论精确买点（应在绿柱缩短或红柱回抽时关注）。"
            score = 0
        else:
            eval_msg = "❌ **无效操作**：当前无结构支持（无底分型、无背驰），属于盲目交易。"
            score = -1
            
    elif action == 'sell':
        if divergence_desc and "顶背驰" in divergence_desc:
            eval_msg = "🔥 **极佳操作 (一卖)**：捕捉到顶背驰，是缠论定义的第一类卖点！"
            score = 1
        elif fenxing == 'top' and trend == '空头':
            eval_msg = "✅ **合理操作 (二卖/三卖)**：空头趋势反弹出现的顶分型，确认为下跌中继。"
            score = 1
        elif fenxing == 'top':
            eval_msg = "⚠️ **谨慎操作**：多头趋势中的顶分型，可能是上涨中继，仅适合短差减仓。"
            score = 0
        elif hist < 0 and hist < hist_prev:
            eval_msg = "⚠️ **杀跌风险**：绿柱加速伸长时卖出往往滞后，易卖在低位，应在红柱缩短或背驰时离场。"
            score = 0
        else:
            eval_msg = "❌ **无效操作**：当前无结构支持（无顶分型、无背驰），属于恐慌性或随意抛售。"
            score = -1
            
    elif action == 'hold':
        if divergence_desc and "底背驰" in divergence_desc:
            eval_msg = "❌ **错失良机**：当前出现底背驰一买信号，理应尝试建仓。"
            score = -1
        elif divergence_desc and "顶背驰" in divergence_desc:
            eval_msg = "⚠️ **风险提示**：当前出现顶背驰一卖信号，建议减仓或离场。"
            score = -1
        elif fenxing == 'bottom' and trend == '多头':
            eval_msg = "ℹ️ **关注机会**：多头回调出现底分型，是潜在买点，观望可能踏空。"
            score = 0
        elif fenxing == 'top' and trend == '空头':
            eval_msg = "ℹ️ **关注风险**：空头反弹出现顶分型，是潜在卖点，观望可能坐过山车。"
            score = 0
        else:
            eval_msg = "☕ **合理观望**：走势延续中或无明确信号，持仓/持币不动是明智的（缠论讲究“不患”）。"
            score = 1

    msg.append(eval_msg)
    
    return "\n\n".join(msg), score, highlight_shapes
