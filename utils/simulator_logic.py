import numpy as np
import pandas as pd
import random

def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calculate_macd(close_prices, fast_period=12, slow_period=26, signal_period=9):
    close_series = pd.Series(close_prices)
    ema_fast = calculate_ema(close_series, fast_period)
    ema_slow = calculate_ema(close_series, slow_period)
    
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
    price = initial_price
    trend = 0  # 趋势因子
    
    for i in range(length):
        # 随机波动 + 趋势
        change = np.random.normal(0, 1.0) + trend
        
        # 偶尔改变趋势
        if i % 30 == 0: 
            trend = np.random.normal(0, 0.2)
            
        open_p = price
        close_p = price + change
        high_p = max(open_p, close_p) + abs(np.random.normal(0, 0.5))
        low_p = min(open_p, close_p) - abs(np.random.normal(0, 0.5))
        
        # 确保价格不为负
        if low_p <= 0:
            low_p = 0.01
            high_p = max(high_p, 0.02)
            close_p = max(close_p, 0.01)
            open_p = max(open_p, 0.01)

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
    简单的背驰判断
    """
    if index < lookback: return None
    
    current_k = klines[index]
    current_hist = macd_data['hist'][index]
    
    # 以前 lookback 根K线作为参考系
    prev_klines = klines[index-lookback:index]
    prev_hists = macd_data['hist'][index-lookback:index]
    
    if not prev_klines: return None

    # ---底背驰判断---
    # 条件1：创新低
    prev_low = min(k['low'] for k in prev_klines)
    if current_k['low'] < prev_low:
        # 条件2：MACD绿柱没有创新低 (动能衰竭)
        # 找到前一段的绿柱极值
        min_hist_prev = min(prev_hists)
        if current_hist < 0 and current_hist > min_hist_prev:
            return "底背驰（价格新低但绿柱未加深）"
            
    # ---顶背驰判断---
    # 条件1：创新高
    prev_high = max(k['high'] for k in prev_klines)
    if current_k['high'] > prev_high:
        # 条件2：MACD红柱没有创新高
        max_hist_prev = max(prev_hists)
        if current_hist > 0 and current_hist < max_hist_prev:
            return "顶背驰（价格新高但红柱未增长）"
            
    return None


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
    divergence = check_divergence(klines, macd_data, current_index)
    
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
        
    if divergence:
        status_desc.append(f"出现{divergence}")
    
    if fenxing == 'top': status_desc.append("形成顶分型")
    elif fenxing == 'bottom': status_desc.append("形成底分型")
        
    msg.append(f"**市场状态**: {', '.join(status_desc)} ({trend}排列)")

    # 2. 操作评价
    eval_msg = ""
    score = 0 # 1: 合理/极佳, 0: 普通/中性, -1: 不合理/失误
    
    if action == 'buy':
        if divergence and "底背驰" in divergence:
            eval_msg = "🔥 **极佳操作**：捕捉到底背驰买点，反转概率大！"
            score = 1
        elif fenxing == 'bottom' and trend == '多头':
            eval_msg = "✅ **合理操作**：顺势回调底分型买入。"
            score = 1
        elif fenxing == 'bottom':
            eval_msg = "⚠️ **激进操作**：逆势底分型买入，注意止损。"
            score = 0
        elif hist > 0 and hist > hist_prev:
            eval_msg = "👌 **追涨操作**：动能增强时买入，谨防回调。"
            score = 0
        else:
            eval_msg = "❌ **风险操作**：当前缺乏明确买入信号（无底分型或背驰）。"
            score = -1
            
    elif action == 'sell':
        if divergence and "顶背驰" in divergence:
            eval_msg = "🔥 **极佳操作**：捕捉到顶背驰卖点，逃顶及时！"
            score = 1
        elif fenxing == 'top' and trend == '空头':
            eval_msg = "✅ **合理操作**：顺势反弹顶分型卖出。"
            score = 1
        elif fenxing == 'top':
            eval_msg = "⚠️ **谨慎操作**：上升途中的顶分型，可能是中继。"
            score = 0
        elif hist < 0 and hist < hist_prev:
            eval_msg = "👌 **杀跌操作**：空头增强时离场，规避风险。"
            score = 0
        else:
            eval_msg = "❓ **疑惑操作**：未见明显卖出信号，或许卖飞。"
            score = -1
            
    elif action == 'hold':
        if divergence and "底背驰" in divergence:
            eval_msg = "miss **错失良机**：当前出现底背驰，理应尝试买入。"
            score = -1
        elif divergence and "顶背驰" in divergence:
            eval_msg = "warning **风险提示**：当前出现顶背驰，建议减仓或离场。"
            score = -1
        elif fenxing == 'bottom' and trend == '多头':
            eval_msg = "info **关注**：多头回调出现底分型，是潜在买点。"
            score = 0
        elif fenxing == 'top' and trend == '空头':
            eval_msg = "info **关注**：空头反弹出现顶分型，是卖出时机。"
            score = 0
        else:
            eval_msg = "☕ **观望**：当前走势延续，持仓不动是明智的。"
            score = 1

    msg.append(eval_msg)
    
    return "\n\n".join(msg), score
