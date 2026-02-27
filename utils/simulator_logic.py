import numpy as np
import random
import pandas as pd

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

def calculate_rsi(prices, period=14):
    """
    计算RSI
    """
    prices = pd.Series(prices)
    if len(prices) < period + 1:
        return [50.0] * len(prices)
        
    delta = prices.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    
    ma_up = up.ewm(com=period-1, adjust=False).mean()
    ma_down = down.ewm(com=period-1, adjust=False).mean()
    
    rs = ma_up / ma_down
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0).tolist()

def calculate_bollinger_bands(prices, period=20, num_std=2):
    """
    计算布林线
    """
    prices = pd.Series(prices)
    if len(prices) < period:
        return {
            'upper': prices.tolist(),
            'middle': prices.tolist(),
            'lower': prices.tolist()
        }
        
    middle = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = middle + (std * num_std)
    lower = middle - (std * num_std)
    
    return {
        'upper': upper.fillna(0).tolist(),
        'middle': middle.fillna(0).tolist(),
        'lower': lower.fillna(0).tolist()
    }


def generate_simulation_data(initial_price=100, length=300):
    """
    生成模拟的K线数据
    """
    data = []
    # 确保初始价格在合理范围内 (1~1000)
    initial_price = max(5.0, min(950.0, float(initial_price)))
    price = initial_price
    trend = 0  # 趋势因子 (百分比)
    days_until_change = 0 # 距离下次变盘的天数

    for i in range(length):
        # 1. 确定今日涨跌停限制 (昨收 * 1.1 / 0.9)
        # 涨跌幅最大 10%
        limit_up = round(price * 1.10, 2)
        limit_down = round(price * 0.90, 2)
        
        # 2. 只有在价格范围内 (1~1000) 才有效
        limit_up = min(limit_up, 1000.0)
        limit_down = max(limit_down, 1.0)
        
        # 随机改变趋势 (基于真实市场的变盘周期)
        if days_until_change <= 0: 
            # 趋势偏置: 每天倾向涨/跌多少百分比 (-1% 到 1%)
            trend = np.random.normal(0, 0.005)
            
            # 根据真实市场规律选择周期类型
            cycle_type = random.choices(
                ['short_strong', 'short_std', 'medium_fib', 'medium_month', 'long'],
                weights=[0.30, 0.35, 0.25, 0.08, 0.02], # 权重：短期波动最常见，中期次之
                k=1
            )[0]
            
            if cycle_type == 'short_strong':
                # 3-5个交易日 (强势整理周期)
                days_until_change = random.randint(3, 5)
            elif cycle_type == 'short_std':
                # 5-9个交易日 (常见短线波段)
                days_until_change = random.randint(5, 9)
            elif cycle_type == 'medium_fib':
                # 斐波那契时间窗 (13, 21, 34, 55)，加少量随机扰动
                base = random.choice([13, 21, 34, 55])
                days_until_change = base + random.randint(-2, 2)
            elif cycle_type == 'medium_month':
                # 1-2个月 (周线级别调整)
                days_until_change = random.randint(20, 60)
            else:
                # 长期 (由于模拟长度限制，适当缩小)
                days_until_change = random.randint(60, 100)
        
        days_until_change -= 1 
            
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

def process_baohan(klines_data):
    """
    处理K线包含关系
    input: list of dict {'time', 'open', 'high', 'low', 'close'}
    output: list of dict (processed)
    """
    if not klines_data:
        return []
        
    processed = []
    # 转换格式方便处理
    for k in klines_data:
        processed.append({
            'high': float(k['high']), 
            'low': float(k['low']), 
            'date': k.get('time', k.get('date')),
            'original': k
        })
        
    if len(processed) < 2:
        return processed
        
    result = [processed[0]]
    direction = 1 # 1 for up, -1 for down (default up)
    
    for i in range(1, len(processed)):
        curr = processed[i]
        prev = result[-1]
        
        # 判断包含关系: (High1 >= High2 and Low1 <= Low2) or (High2 >= High1 and Low2 <= Low1)
        is_included = (prev['high'] >= curr['high'] and prev['low'] <= curr['low']) or \
                      (curr['high'] >= prev['high'] and curr['low'] <= prev['low'])
                      
        if is_included:
            # 处理包含
            if direction == 1: # 向上趋势，取高高，低高
                new_high = max(prev['high'], curr['high'])
                new_low = max(prev['low'], curr['low'])
            else: # 向下趋势，取低低，高低
                new_high = min(prev['high'], curr['high'])
                new_low = min(prev['low'], curr['low'])
            
            # 更新前一根K线（合并）
            result[-1]['high'] = new_high
            result[-1]['low'] = new_low
            # date通常取后一根的date
            result[-1]['date'] = curr['date']
            result[-1]['original'] = curr['original'] # Keep reference to latest
            
        else:
            # 确定新趋势方向 (如果不是包含，则确定新方向)
            if curr['high'] > prev['high']:
                direction = 1
            elif curr['low'] < prev['low']:
                direction = -1
            
            result.append(curr)
            
    return result

def find_bi(processed_klines):
    """
    识别笔 (Bi)
    input: processed klines (after inclusion handling)
    output: list of {'type': 'top'/'bottom', 'index': i, 'price': val, 'date': ...}
    """
    if len(processed_klines) < 5:
        return []
        
    fx_list = []
    # 1. Find all FenXing (Fractals)
    for i in range(1, len(processed_klines)-1):
        k1 = processed_klines[i-1]
        k2 = processed_klines[i]
        k3 = processed_klines[i+1]
        
        if k2['high'] > k1['high'] and k2['high'] > k3['high']:
            fx_list.append({'type': 'top', 'index': i, 'price': k2['high'], 'date': k2['date']})
        elif k2['low'] < k1['low'] and k2['low'] < k3['low']:
            fx_list.append({'type': 'bottom', 'index': i, 'price': k2['low'], 'date': k2['date']})
            
    if not fx_list:
        return []
        
    # 2. Connect FenXing to form Bi
    # 规则：
    # a. 顶底交替
    # b. 中间至少隔3根K线 (index diff >= 4) ? 
    #    标准缠论：顶分型与底分型之间至少有一根K线不属于这两个分型，即 index diff >= 3 (e.g. 1(top), 2, 3, 4(bottom)) -> 4-1=3 ?
    #    Strictly: Top(i), Bottom(j) -> j > i+3 (at least 3 K-lines between the peak and valley points? No, between the constituent K-lines)
    #    Simpler rule: Index difference >= 4 (Top is at i, Bottom at j, j-i >= 4)
    
    bi_points = []
    # Find first strong point to start? Or just start from first valid pair
    
    # 简单回溯算法
    # 找到最高/最低点作为起点
    
    last_bi = fx_list[0]
    bi_points.append(last_bi)
    
    for fx in fx_list[1:]:
        if fx['type'] == last_bi['type']:
            # Same type, check if better (higher top or lower bottom)
            if fx['type'] == 'top':
                if fx['price'] > last_bi['price']:
                    bi_points[-1] = fx # Replace with higher top
                    last_bi = fx
            else: # bottom
                if fx['price'] < last_bi['price']:
                    bi_points[-1] = fx # Replace with lower bottom
                    last_bi = fx
        else:
            # Different type, check distance
            if fx['index'] - last_bi['index'] >= 4:
                bi_points.append(fx)
                last_bi = fx
            else:
                # Distance too short, ignore? Or maybe the previous one was wrong?
                # This is complex. Simplified: Ignore current if too close.
                pass
                
    return bi_points

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
        
        # 找到前低MACD的索引，用于画图
        min_hist_idx_rel = prev_hists.index(min_hist_prev)
        min_hist_idx = start_lookback + min_hist_idx_rel
        
        if current_hist < 0 and current_hist > min_hist_prev:
            shapes = [
                # 1. K线图：背驰连线 (加粗实线)
                {
                    'type': 'line',
                    'xref': 'x', 'yref': 'y',
                    'x0': min_prev_idx, 'y0': min_prev_low,
                    'x1': index, 'y1': current_k['low'],
                    'line': {'color': 'rgb(128, 128, 128)', 'width': 3} # 灰色
                },
                # 2. K线图：背驰区间背景 (淡红高亮)
                {
                    'type': 'rect',
                    'xref': 'x', 'yref': 'y',
                    'x0': min_prev_idx,
                    'x1': index,
                    'y0': min(min_prev_low, current_k['low']) * 0.99, # 稍微扩一点范围
                    'y1': max(min_prev_low, current_k['low']) * 1.01,
                    'fillcolor': 'rgba(254, 202, 202, 0.4)', # Red-200
                    'line': {'width': 0}
                },
                # 3. MACD图：背驰连线 (虚线指示)
                {
                    'type': 'line',
                    'xref': 'x', 'yref': 'y2', # 指向副图Y轴
                    'x0': min_hist_idx, 'y0': min_hist_prev,
                    'x1': index, 'y1': current_hist,
                    'line': {'color': 'rgb(128, 128, 128)', 'width': 2, 'dash': 'dot'} 
                }
            ]
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
        
        # 找到前高MACD的索引
        max_hist_idx_rel = prev_hists.index(max_hist_prev)
        max_hist_idx = start_lookback + max_hist_idx_rel
        
        if current_hist > 0 and current_hist < max_hist_prev:
            shapes = [
                # 1. K线图：背驰连线 (加粗实线)
                {
                    'type': 'line',
                    'xref': 'x', 'yref': 'y',
                    'x0': max_prev_idx, 'y0': max_prev_high,
                    'x1': index, 'y1': current_k['high'],
                    'line': {'color': 'rgb(128, 128, 128)', 'width': 3} # 灰色
                },
                # 2. K线图：背驰区间背景 (淡绿高亮)
                {
                    'type': 'rect',
                    'xref': 'x', 'yref': 'y',
                    'x0': max_prev_idx,
                    'x1': index,
                    'y0': min(max_prev_high, current_k['high']) * 0.99,
                    'y1': max(max_prev_high, current_k['high']) * 1.01,
                    'fillcolor': 'rgba(187, 247, 208, 0.4)', # Green-200
                    'line': {'width': 0}
                },
                # 3. MACD图：背驰连线 (虚线指示)
                {
                    'type': 'line',
                    'xref': 'x', 'yref': 'y2', # 指向副图Y轴
                    'x0': max_hist_idx, 'y0': max_hist_prev,
                    'x1': index, 'y1': current_hist,
                    'line': {'color': 'rgb(128, 128, 128)', 'width': 2, 'dash': 'dot'}
                }
            ]
            return "顶背驰（价格新高但红柱未增长）", shapes
            
    return None, []

def resample_klines(daily_data, period):
    """
    将日线数据重采样为更大级别的数据 (周K, 月K等)
    period: 聚合的K线数量，例如 5 (周), 20 (月), 60 (季)
    """
    resampled = []
    if not daily_data:
        return [], calculate_macd([]) # 返回空MACD结构

    # 按固定周期分块
    for i in range(0, len(daily_data), period):
        chunk = daily_data[i : i + period]
        if not chunk: continue
        
        # 聚合
        open_p = chunk[0]['open']
        close_p = chunk[-1]['close']
        high_p = max(d['high'] for d in chunk)
        low_p = min(d['low'] for d in chunk)
        
        # 使用新的索引作为time
        new_time = len(resampled)
        
        resampled.append({
            'time': new_time,
            'open': open_p,
            'high': high_p,
            'low': low_p,
            'close': close_p,
            # 保留原始的对应日线索引范围，用于UI映射
            'start_day_idx': chunk[0]['time'],
            'end_day_idx': chunk[-1]['time']
        })
        
    # 计算新级别的MACD
    closes = [d['close'] for d in resampled]
    macd = calculate_macd(closes)
    
    return resampled, macd

def calculate_bi_and_zhongshu_shapes(klines):
    """
    计算并返回笔（Bi）和中枢（Zhongshu/Box）的形状数据
    简化版逻辑，仅用于模拟器展示辅助
    """
    shapes = []
    
    # 1. 识别所有分型点 (Fenxing Points)
    fenxings = [] # list of {'index': i, 'type': 'top'/'bottom', 'val': price}
    
    # 这里需要遍历整个序列来通过交替规则确认笔
    # 注意：klines 是截止到当前的全部数据，我们重新计算整个历史的笔
    for i in range(2, len(klines)):
        subset = klines[i-2 : i+1]
        fx_type = identify_fenxing(subset)
        if fx_type:
            # 简化版笔识别逻辑：
            # 1. 必须是一顶一底交替
            # 2. 顶底之间至少间隔一定K线 (这里设为3根，即中间有K线)
            k2 = subset[1]
            # k2的索引在全局序列中是 i-1
            k2_idx = i - 1
            val = k2['high'] if fx_type == 'top' else k2['low']
            
            if not fenxings:
                # 第一个分型直接接纳
                fenxings.append({'index': k2_idx, 'type': fx_type, 'val': val})
            else:
                last = fenxings[-1]
                if last['type'] != fx_type:
                    # 类型不同，检查距离
                    if k2_idx - last['index'] >= 3:
                        fenxings.append({'index': k2_idx, 'type': fx_type, 'val': val})
                    # 如果距离太近，忽略这个新分型（或者这是一个更优的分型？）
                    # 简化处理：忽略过近的转折
                else:
                    # 类型相同，保留更极端的那个
                    if fx_type == 'top':
                        if val > last['val']:
                            fenxings[-1] = {'index': k2_idx, 'type': fx_type, 'val': val}
                    else:
                        if val < last['val']:
                            fenxings[-1] = {'index': k2_idx, 'type': fx_type, 'val': val}

    # 2. 生成笔的连线 (Bi Shapes)
    bi_segments = [] 
    for i in range(len(fenxings) - 1):
        p1 = fenxings[i]
        p2 = fenxings[i+1]
        
        shapes.append({
            'type': 'line',
            'xref': 'x', 'yref': 'y',
            'x0': p1['index'], 'y0': p1['val'],
            'x1': p2['index'], 'y1': p2['val'],
            'line': {'color': 'rgba(70, 70, 70, 0.6)', 'width': 2}, # 深灰色实线
            # 'layer': 'below' # Plotly shape layer (not supported directly in dict always, simplified)
        })
        bi_segments.append({
            'x0': p1['index'], 'y0': p1['val'],
            'x1': p2['index'], 'y1': p2['val']
        })

    # 3. 生成中枢矩形 (Zhongshu Shapes)
    # 逻辑：连续三笔重叠部分 -> 升级逻辑：合并重叠/连续的中枢为大级别中枢
    raw_zhongshus = []
    if len(bi_segments) >= 3:
        for i in range(len(bi_segments) - 2):
            b1 = bi_segments[i]
            b2 = bi_segments[i+1]
            b3 = bi_segments[i+2]
            
            # 计算三笔价格区间的交集 (中枢核心区域)
            r1 = (min(b1['y0'], b1['y1']), max(b1['y0'], b1['y1']))
            r2 = (min(b2['y0'], b2['y1']), max(b2['y0'], b2['y1']))
            r3 = (min(b3['y0'], b3['y1']), max(b3['y0'], b3['y1']))
            
            overlap_min = max(r1[0], r2[0], r3[0])
            overlap_max = min(r1[1], r2[1], r3[1])
            
            if overlap_min < overlap_max:
                # 存在有效中枢区域
                raw_zhongshus.append({
                    'x0': b1['x0'], 
                    'x1': b3['x1'],
                    'y0': overlap_min,
                    'y1': overlap_max
                })

    # 合并重叠的中枢 (Expansion/Extension)
    merged_zhongshus = []
    if raw_zhongshus:
        # 按开始时间排序 (通常已经是顺序的)
        current_z = raw_zhongshus[0]
        
        for i in range(1, len(raw_zhongshus)):
            next_z = raw_zhongshus[i]
            
            # 判断是否重叠 (Overlap)
            # 1. 时间上：raw_zhongshus 是基于滑动窗口生成的，天生时间重叠/连续
            # 2. 空间上：判断价格区间是否有交集
            mn = max(current_z['y0'], next_z['y0'])
            mx = min(current_z['y1'], next_z['y1'])
            
            if mn < mx:
                # 存在价格交集，视为同一中枢的延伸/扩张 -> 合并
                # 新的范围：时间并集，价格并集 (体现大级别/扩张范围)
                # 注：缠论严格定义中枢级别升级需要9段，或者两个独立中枢波动区间重叠。
                # 这里做视觉简化：凡是连在一起且价格重叠的，都画成一个大框。
                current_z['x1'] = max(current_z['x1'], next_z['x1'])
                current_z['y0'] = min(current_z['y0'], next_z['y0'])
                current_z['y1'] = max(current_z['y1'], next_z['y1'])
            else:
                # 不重叠，结束当前中枢，开始下一个
                merged_zhongshus.append(current_z)
                current_z = next_z
        
        merged_zhongshus.append(current_z)

    # 生成最终形状
    for z in merged_zhongshus:
        shapes.append({
            'type': 'rect',
            'xref': 'x', 'yref': 'y',
            'x0': z['x0'], 
            'x1': z['x1'],
            'y0': z['y0'],
            'y1': z['y1'],
            'fillcolor': 'rgba(255, 165, 0, 0.15)', # 橙色半透明
            'line': {'width': 0},
        })
        # 画边框
        shapes.append({
             'type': 'rect',
             'xref': 'x', 'yref': 'y',
             'x0': z['x0'], 
             'x1': z['x1'],
             'y0': z['y0'],
             'y1': z['y1'],
             'line': {'color': 'rgba(255, 165, 0, 0.6)', 'width': 1.5, 'dash': 'dot'}, # 加粗一点边框
             'fillcolor': 'rgba(0,0,0,0)'
        })

    return shapes

def calculate_bi_and_centers(klines):
    """
    计算笔和中枢，返回结构化数据（非图形Shapes）
    """
    # 1. 识别分型
    fenxings = []
    for i in range(2, len(klines)):
        subset = klines[i-2 : i+1]
        fx_type = identify_fenxing(subset)
        if fx_type:
            k2 = subset[1]
            k2_idx = i - 1
            val = k2['high'] if fx_type == 'top' else k2['low']
            date = k2.get('date', '')
            
            if not fenxings:
                fenxings.append({'index': k2_idx, 'type': fx_type, 'val': val, 'date': date})
            else:
                last = fenxings[-1]
                if last['type'] != fx_type:
                    if k2_idx - last['index'] >= 3:
                        fenxings.append({'index': k2_idx, 'type': fx_type, 'val': val, 'date': date})
                else:
                    if fx_type == 'top':
                        if val > last['val']:
                            fenxings[-1] = {'index': k2_idx, 'type': fx_type, 'val': val, 'date': date}
                    else:
                        if val < last['val']:
                            fenxings[-1] = {'index': k2_idx, 'type': fx_type, 'val': val, 'date': date}
                            
    # 2. 生成笔
    bi_list = []
    for i in range(len(fenxings) - 1):
        p1 = fenxings[i]
        p2 = fenxings[i+1]
        bi_list.append({
            'start_index': p1['index'],
            'start_val': p1['val'],
            'start_date': p1['date'],
            'end_index': p2['index'],
            'end_val': p2['val'],
            'end_date': p2['date'],
            'type': 'up' if p2['val'] > p1['val'] else 'down'
        })
        
    # 3. 生成中枢
    centers = []
    if len(bi_list) >= 3:
        raw_centers = []
        for i in range(len(bi_list) - 2):
            b1 = bi_list[i]
            b2 = bi_list[i+1]
            b3 = bi_list[i+2]
            
            min1, max1 = min(b1['start_val'], b1['end_val']), max(b1['start_val'], b1['end_val'])
            min2, max2 = min(b2['start_val'], b2['end_val']), max(b2['start_val'], b2['end_val'])
            min3, max3 = min(b3['start_val'], b3['end_val']), max(b3['start_val'], b3['end_val'])
            
            zg = min(max1, max2, max3)
            zd = max(min1, min2, min3)
            
            if zg > zd:
                raw_centers.append({
                    'start_index': b1['end_index'], # 逻辑起点调整为 b1 的结束（即 b2 的开始），去除进入笔
                    'end_index': b3['end_index'], 
                    'visual_end_index': b2['end_index'], 
                    'start_date': b1['end_date'], # 对应 b2.start_date
                    'end_date': b3['end_date'],
                    'visual_end_date': b2['end_date'],
                    'zg': zg,
                    'zd': zd,
                    'is_up': b1['type'] == 'up' # 记录方向，后续可选用于颜色区分
                })
        
        # 合并重叠的中枢
        if raw_centers:
            curr = raw_centers[0]
            # 默认使用 visual_end 作为显示结束
            curr['end_index'] = curr['visual_end_index']
            curr['end_date'] = curr['visual_end_date']
            
            for next_c in raw_centers[1:]:
                mn = max(curr['zd'], next_c['zd'])
                mx = min(curr['zg'], next_c['zg'])
                
                if mn < mx:
                    # 合并
                    # 只要有重叠，就延伸到下一个中枢的视觉结束点
                    curr['end_index'] = max(curr['end_index'], next_c['visual_end_index'])
                    curr['end_date'] = next_c['visual_end_date'] 
                    
                    # 区间合并策略：取并集（保持最大包容性）
                    curr['zd'] = min(curr['zd'], next_c['zd'])
                    curr['zg'] = max(curr['zg'], next_c['zg'])
                else:
                    centers.append(curr)
                    curr = next_c
                    # 初始化新中枢的结束时间
                    curr['end_index'] = curr['visual_end_index']
                    curr['end_date'] = curr['visual_end_date']
            centers.append(curr)
            
    return bi_list, centers

def get_chanlun_shapes(klines, macd_data, current_index):
    """
    计算并返回K线对应的笔、中枢、分型和背驰形状
    功能集成，用于任意级别的K线分析
    """
    highlight_shapes = []
    
    # 1. 笔和中枢
    # 为了性能，可以只计算最近的一段，但为了准确性，这里传入全部历史（klines是切片过的）
    # 在模拟器中 current_index < 400 左右，计算开销可控
    bi_zhongshu_shapes = calculate_bi_and_zhongshu_shapes(klines)
    highlight_shapes.extend(bi_zhongshu_shapes)
    
    # 2. 背驰
    divergence_desc, divergence_shapes = check_divergence(klines, macd_data, current_index)
    if divergence_shapes:
        highlight_shapes.extend(divergence_shapes)
    
    # 3. 分型（当前K线）
    recent_k = klines[max(0, current_index-2):current_index+1]
    fenxing = identify_fenxing(recent_k)
    
    if fenxing:
        k_subset = klines[current_index-2 : current_index+1]
        if k_subset:
            max_h = max(k['high'] for k in k_subset)
            min_l = min(k['low'] for k in k_subset)
            
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
            
    return highlight_shapes

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
    
    # 收集需要高亮的区域形状 (使用重构后的函数)
    highlight_shapes = get_chanlun_shapes(klines, macd_data, current_index)
    
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
        
    msg.append(f"🧭 **市场状态**: {', '.join(status_desc)} ({trend}排列)")

    # 2. 操作评价
    eval_msg = ""
    score = 0 # 1: 合理/极佳, 0: 普通/中性, -1: 不合理/失误
    
    if action == 'buy':
        if divergence_desc and "底背驰" in divergence_desc:
            eval_msg = "🔥 **极佳操作 (一买)**：背驰引发转折，精准捕捉第一类买点。次级别走势背驰确立，当下买入符合区间套定位。"
            score = 1
        elif fenxing == 'bottom' and trend == '多头':
            eval_msg = "✅ **顺势操作 (二买/三买)**：在上涨中枢上方/附近出现底分型，确认为次级别回调结束，顺势介入坐享主升浪。"
            score = 1
        elif fenxing == 'bottom':
            eval_msg = "⚠️ **中继风险 (下跌中继)**：空头中枢压制下的底分型，往往是下跌中继而非反转，需警惕形成第三类卖点。" # 修正为更专业的表述
            score = 0
        elif hist > 0 and hist > hist_prev:
            eval_msg = "⚠️ **追涨风险**：红柱加速伸长时买入，此时往往处于向上笔的末端，容易在小级别买在山顶。"
            score = 0
        else:
            eval_msg = "❌ **无效操作**：当前无底分型、无背驰结构，属于随意开仓。缠论告诫：没有买点就没有操作。"
            score = -1
            
    elif action == 'sell':
        if divergence_desc and "顶背驰" in divergence_desc:
            eval_msg = "🔥 **极佳操作 (一卖)**：顶背驰信号确认，当下即是第一类卖点。动力学衰竭引发走势转折，果断离场。"
            score = 1
        elif fenxing == 'top' and trend == '空头':
            eval_msg = "✅ **顺势减仓 (二卖/三卖)**：下跌趋势反弹受阻，出现顶分型，确认为次级别反弹结束，顺势离场防守。"
            score = 1
        elif fenxing == 'top':
            eval_msg = "⚠️ **短差操作**：多头趋势中出现顶分型，大概率是上涨中继（构筑新的上涨中枢），仅适合短线做T。"
            score = 0
        elif hist < 0 and hist < hist_prev:
            eval_msg = "⚠️ **杀跌风险**：绿柱伸长时卖出往往滞后，容易卖在向下笔的底端。应等待反弹构成二卖/三卖再离场。"
            score = 0
        else:
            eval_msg = "❌ **无序操作**：当前无顶分型、无背驰结构，属于恐慌性抛售。缠论铁律：卖点都在上涨中产生。"
            score = -1
            
    elif action == 'hold':
        if divergence_desc and "底背驰" in divergence_desc:
            eval_msg = "❌ **错失买点**：当下出现底背驰一买信号！根据“走势终完美”，此处极大概率发生转折，观望将错失良机。"
            score = -1
        elif divergence_desc and "顶背驰" in divergence_desc:
            eval_msg = "⚠️ **风险提示**：当下出现顶背驰一卖信号！动力学已衰竭，此时不走，更待何时？"
            score = -1
        elif fenxing == 'bottom' and trend == '多头':
            eval_msg = "ℹ️ **关注机会**：多头回调确认底分型，这是潜在的二买/三买位置，建议择机介入。"
            score = 0
        elif fenxing == 'top' and trend == '空头':
            eval_msg = "ℹ️ **关注风险**：空头反弹确认顶分型，这是潜在的二卖/三卖位置，持仓风险巨大。"
            score = 0
        else:
            eval_msg = "☕ **中枢震荡/顺势持有**：走势延续中（无顶底背驰破坏），符合“不患”原则，耐心持有或空仓观望是最高智慧。"
            score = 1

    msg.append(eval_msg)
    
    return "\n\n".join(msg), score, highlight_shapes

def _analyze_level_status(klines, macd_data, idx):
    """
    辅助函数：分析单个级别的趋势和结构
    返回: stats 字典 (以前是tuple)
    """
    if idx < 0 or idx >= len(klines):
        return None
        
    # 1. 均线趋势
    closes = [k['close'] for k in klines[:idx+1]]
    ma5 = np.mean(closes[-5:]) if len(closes) >= 5 else closes[-1]
    ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else closes[-1]
    trend = 'UP' if ma5 > ma20 else 'DOWN'
    ma_desc = "均线多头" if trend == 'UP' else "均线空头"
    
    signals = []
    
    # 2. 分型
    range_k = klines[:idx+1] # 传入全部历史供切片
    fenxing = identify_fenxing(range_k) # identify_fenxing 内部会取最后3根
    if fenxing == 'top': signals.append('顶分型')
    elif fenxing == 'bottom': signals.append('底分型')
    
    # 3. 背驰 (只看最近的)
    try:
        div_desc, _ = check_divergence(klines, macd_data, idx)
        if div_desc:
            if '顶背驰' in div_desc: signals.append('顶背驰')
            if '底背驰' in div_desc: signals.append('底背驰')
    except Exception:
        pass

    # 4. MACD 状态
    macd_desc = "MACD数据缺失"
    try:
        # macd_data 结构是 {'dif': [...], 'dea': [...], 'hist': [...]}
        # 必须通过 key 访问 list
        if idx < len(macd_data['hist']):
            hist = macd_data['hist'][idx]
            
            # 获取前一根hist用于比较
            prev_hist = macd_data['hist'][idx-1] if idx > 0 else hist
            
            if hist > 0:
                macd_desc = "红柱" + ("伸长" if hist >= prev_hist else "缩短")
            else:
                macd_desc = "绿柱" + ("伸长" if hist <= prev_hist else "缩短")
    except Exception:
        pass
        
    return {
        'trend': trend,
        'signals': signals,
        'ma_desc': ma_desc,
        'macd_desc': macd_desc
    }

def analyze_advanced_action(action, current_idx, day_data, day_macd, week_data, week_macd, month_data, month_macd):
    """
    高级模式分析，结合日、周、月线进行联动分析
    """
    # 1. 基础日线分析 (保持原有的日线评价逻辑)
    # day_msg 格式通常为: "**市场状态**: ... \n\n **评价**: ..."
    day_msg_text, day_score, day_shapes = analyze_action(action, day_data, day_macd, current_idx)
    
    # 2. 寻找对应的周、月线索引
    c_time = day_data[current_idx]['time']
    
    week_idx = -1
    for i, w in enumerate(week_data):
        if w['start_day_idx'] <= c_time <= w['end_day_idx']:
            week_idx = i
            break
            
    month_idx = -1
    for i, m in enumerate(month_data):
        if m['start_day_idx'] <= c_time <= m['end_day_idx']:
            month_idx = i
            break
            
    if week_idx < 0:
        return day_msg_text + "\n\n(大级别数据不足)", day_score, day_shapes

    # 3. 分析大级别状态
    w_stats = _analyze_level_status(week_data, week_macd, week_idx)
    m_stats = _analyze_level_status(month_data, month_macd, month_idx)
    
    if not w_stats or not m_stats:
        return day_msg_text + "\n\n(大级别数据不足)", day_score, day_shapes
        
    w_trend = w_stats['trend']
    w_signals = w_stats['signals']
    
    m_trend = m_stats['trend']
    m_signals = m_stats['signals']

    # 4. 生成联动分析和共振评价
    linkage_msg = ""
    bonus_score = 0
    
    # 根据操作方向 + 大级别背景生成深度建议
    if action == 'buy':
        if w_trend == 'UP':
            linkage_msg = "✅ **大级别顺势**：周线向上笔/线段延伸中，日线买点属于顺大势操作，成功率极高。"
            if '底分型' in w_signals: linkage_msg += " (周线底分型共振，极佳)"
            bonus_score += 1
        elif w_trend == 'DOWN':
            if '底背驰' in w_signals:
                linkage_msg = "🔥 **区间套共振**：周线底背驰构筑大级别一买，日线作为次级别精确打击，这是缠论区间套的完美应用。"
                bonus_score += 2
            elif '底分型' in w_signals:
                linkage_msg = "⚠️ **周线反弹**：周线空头结构中出现底分型，预示次级别反弹（或许是构建大级别中枢），操作需谨慎，快进快出。"
            else:
                linkage_msg = "🛑 **逆势接飞刀**：周线处于空头下跌西风烈中（均线空排），且无止跌信号。此时日线的所谓买点往往是“刀口舔血”。"
                bonus_score -= 2
                
    elif action == 'sell':
        if w_trend == 'DOWN':
            linkage_msg = "✅ **顺势离场**：周线空头向下，日线卖出顺应大势，建议保持空仓，等待周线级别的底背驰或底分型。"
            bonus_score += 1
        elif w_trend == 'UP':
            if '顶背驰' in w_signals:
                linkage_msg = "🔥 **逃顶良机**：周线多头出现顶背驰！这是大级别的卖出信号（大级别一卖），日线卖点与之共振，务必清仓。"
                bonus_score += 2
            elif '顶分型' in w_signals:
                linkage_msg = "⚠️ **周线震荡**：周线多头中出现顶分型，大概率是上涨中枢的震荡洗盘。卖出后需关注回调结束后的三买机会。"
            else:
                linkage_msg = "🛑 **逆势卖出**：周线多头强劲（均线多排），日线调整可能仅是构筑次级别中枢，盲目卖出容易“卖飞”主升浪。"
                bonus_score -= 1 # 扣分，因为容易卖飞

    elif action == 'hold':
        if w_trend == 'UP':
             if '顶背驰' in w_signals:
                 linkage_msg = "⚠️ **警惕见顶**：虽然日线平稳，但周线已出现顶背驰，大厦将倾，持仓需高度警惕，随时准备离场。"
             else:
                 linkage_msg = "☕ **中枢上移**：周线多头趋势健康，次级别的震荡只是中枢上移的过程，持仓躺赢是最佳策略。"
        elif w_trend == 'DOWN':
             if '底背驰' in w_signals:
                 linkage_msg = "ℹ️ **抄底准备**：周线出现底背驰，大底将近，空仓者应密切关注日线一买/二买，准备进场。"
             else:
                 linkage_msg = "☕ **空仓为王**：周线空头趋势延续中，覆巢之下无完卵，耐心观望等待大级别买点。"

    # 5. 组合最终文案
    final_output = []
    
    # 如果有联动评价，优先显示
    if linkage_msg:
        final_output.append(linkage_msg)
    else:
        # 否则使用日线基础评价
        pass
        
    final_output.append(day_msg_text)
    
    # 状态摘要 - 增强版
    def fmt_level(name, stats):
        sig_str = ', '.join(stats['signals']) if stats['signals'] else '无结构'
        return f"• **{name}**: {stats['ma_desc']} | {stats['macd_desc']} | {sig_str}"
        
    status_summary = (
        f"📊 **大级别全景**\n"
        f"{fmt_level('周线', w_stats)}\n"
        f"{fmt_level('月线', m_stats)}"
    )
    final_output.append(status_summary)
    
    # 调整分数
    final_score = day_score
    if bonus_score > 0 and day_score >= 0: final_score = 1
    if bonus_score < 0 and day_score >= 0: final_score = 0 # 降级
    if bonus_score <= -2: final_score = -1 # 严重扣分
    
    return "\n\n".join(final_output), final_score, day_shapes
