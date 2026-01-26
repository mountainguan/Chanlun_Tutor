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
    # 确保初始价格在合理范围内 (1~1000)
    initial_price = max(5.0, min(950.0, float(initial_price)))
    price = initial_price
    trend = 0  # 趋势因子 (百分比)
    
    for i in range(length):
        # 1. 确定今日涨跌停限制 (昨收 * 1.1 / 0.9)
        # 涨跌幅最大 10%
        limit_up = round(price * 1.10, 2)
        limit_down = round(price * 0.90, 2)
        
        # 2. 只有在价格范围内 (1~1000) 才有效
        limit_up = min(limit_up, 1000.0)
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

def analyze_advanced_action(action, current_idx, day_data, day_macd, week_data, week_macd, month_data, month_macd):
    """
    高级模式分析，结合日、周、月线
    """
    # 1. 基础日线分析
    day_msg, day_score, day_shapes = analyze_action(action, day_data, day_macd, current_idx)
    
    # 2. 寻找对应的周、月线索引
    c_time = day_data[current_idx]['time'] # current day index/time
    
    # 找到包含 c_time 的周K线
    week_idx = -1
    for i, w in enumerate(week_data):
        if w['start_day_idx'] <= c_time <= w['end_day_idx']:
            week_idx = i
            break
            
    # 找到包含 c_time 的月K线
    month_idx = -1
    for i, m in enumerate(month_data):
        if m['start_day_idx'] <= c_time <= m['end_day_idx']:
            month_idx = i
            break
            
    adv_msg = []
    
    # 分析大级别趋势
    week_trend = "无"
    week_details = []
    if week_idx >= 0:
        w_closes = [k['close'] for k in week_data[:week_idx+1]]
        w_ma5 = sum(w_closes[-5:]) / len(w_closes[-5:]) if len(w_closes)>=5 else w_closes[-1]
        w_ma20 = sum(w_closes[-20:]) / len(w_closes[-20:]) if len(w_closes)>=20 else w_closes[-1]
        week_trend = "多头" if w_ma5 > w_ma20 else "空头"
        
        # 简单判断周线分型
        w_fenxing = identify_fenxing(week_data[:week_idx+1])
        if w_fenxing == 'top': week_details.append("周线顶分型")
        elif w_fenxing == 'bottom': week_details.append("周线底分型")

    month_trend = "无"
    if month_idx >= 0:
        m_closes = [k['close'] for k in month_data[:month_idx+1]]
        m_ma5 = sum(m_closes[-5:]) / len(m_closes[-5:]) if len(m_closes)>=5 else m_closes[-1]
        m_ma20 = sum(m_closes[-20:]) / len(m_closes[-20:]) if len(m_closes)>=20 else m_closes[-1]
        month_trend = "多头" if m_ma5 > m_ma20 else "空头"

    # 生成共振评价
    resonance_msg = f"**大级别配合**: 周线{week_trend} ({', '.join(week_details)})，月线{month_trend}。" if week_details else f"**大级别配合**: 周线{week_trend}，月线{month_trend}。"
    
    bonus_score = 0
    
    if action == 'buy':
        if week_trend == '多头':
            resonance_msg += " (周线顺势，加分)"
            bonus_score += 1
        elif week_trend == '空头':
            resonance_msg += " (周线逆势，注意快进快出)"
            
        # 检查周线底背驰
        if week_idx > 10:
            w_div_desc, _ = check_divergence(week_data, week_macd, week_idx, lookback=10)
            if w_div_desc and "底背驰" in w_div_desc:
                resonance_msg += " 🔥周线底背驰共振！"
                bonus_score += 2

    elif action == 'sell':
        if week_trend == '空头':
            resonance_msg += " (周线顺势下跌，加分)"
            bonus_score += 1
        
        if week_idx > 10:
            w_div_desc, _ = check_divergence(week_data, week_macd, week_idx, lookback=10)
            if w_div_desc and "顶背驰" in w_div_desc:
                resonance_msg += " 🔥周线顶背驰共振！"
                bonus_score += 2
    
    final_msg = f"{day_msg}\n\n{resonance_msg}"
    
    return final_msg, day_score, day_shapes
