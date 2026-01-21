import plotly.graph_objects as go
import pandas as pd
import numpy as np

def create_candlestick_chart(data, title="K线图展示", annotations=None, shapes=None):
    """
    创建一个Plotly K线图
    :param data: list of dict, e.g. [{'open': 10, 'high': 12, ...}, ...]
    :param title: 图表标题
    :param annotations: list of dict, Plotly layout.annotations
    :param shapes: list of dict, Plotly layout.shapes (lines, rects)
    :return: plotly figure dict or object
    """
    df = pd.DataFrame(data)
    # 确保索引是数字，方便画线
    df.reset_index(drop=True, inplace=True)
    
    # 构建基础K线
    fig = go.Figure(data=[go.Candlestick(
        x=df.index,
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        increasing_line_color='red', 
        decreasing_line_color='green',
        name='K线'
    )])

    layout_update = {
        "title": title,
        "xaxis_rangeslider_visible": False,
        "template": "plotly_white",
        "margin": dict(l=20, r=20, t=40, b=20),
        "height": 400,
        "xaxis": dict(showgrid=False),
        "yaxis": dict(showgrid=True, gridcolor='lightgray')
    }

    if annotations:
        layout_update["annotations"] = annotations
        
    if shapes:
        layout_update["shapes"] = shapes

    fig.update_layout(**layout_update)
    
    return fig

def _generate_bi(start_price, end_price, steps=5):
    """
    生成一段简单的K线数据模拟“笔”
    :param start_price: 笔的起点价格
    :param end_price: 笔的终点价格
    :param steps: 包含多少根K线（至少3根）
    :return: list of dict
    """
    data = []
    # 简单的线性插值
    prices = np.linspace(start_price, end_price, steps)
    is_up = end_price > start_price
    
    for i, p in enumerate(prices):
        # 加上一点随机波动，或者固定的形态
        # 这里的gap用来制造K线的实体
        half_body = abs(end_price - start_price) / (steps * 4)
        if half_body < 0.1: half_body = 0.1
        
        # 构造K线
        if is_up:
            # 向上笔，中间主要是阳线
            o_ = p - half_body
            c_ = p + half_body
            l_ = o_ - half_body * 0.5
            h_ = c_ + half_body * 0.5
        else:
            # 向下笔，中间主要是阴线
            o_ = p + half_body
            c_ = p - half_body
            l_ = c_ - half_body * 0.5
            h_ = o_ + half_body * 0.5

        # 修正起点（底/顶分型）和终点（顶/底分型）
        # 这里只做简单的极值处理，保证顶是最高，底是最低
        if i == 0:
            if is_up: # 起点是底
                l_ = start_price
                h_ = start_price + half_body * 1.5
                o_ = start_price + half_body * 0.5
                c_ = start_price + half_body * 1.0
            else: # 起点是顶
                h_ = start_price
                l_ = start_price - half_body * 1.5
                o_ = start_price - half_body * 0.5
                c_ = start_price - half_body * 1.0
        
        if i == steps - 1:
            if is_up: # 终点是顶
                h_ = end_price
                l_ = end_price - half_body * 1.5
                o_ = end_price - half_body * 0.5
                c_ = end_price - half_body * 1.0
            else: # 终点是底
                l_ = end_price
                h_ = end_price + half_body * 1.5
                o_ = end_price + half_body * 0.5
                c_ = end_price + half_body * 1.0
                
        data.append({"open": round(o_, 2), "high": round(h_, 2), "low": round(l_, 2), "close": round(c_, 2)})
    return data

def get_chart_data(scene_name):
    """
    根据场景名返回图表数据和配置
    返回: (data_list, chart_title, annotations_list, shapes_list)
    """
    
    # 场景1：K线包含关系 - 向上处理
    # Case: K1包含K2 (K1 High > K2 High, K1 Low < K2 Low) -> 向上趋势中取高高
    if scene_name == 'inclusion_up':
        data = [
            {"open": 10, "high": 12, "low": 8, "close": 11},   # K1: 大阳线
            {"open": 10.5, "high": 11.5, "low": 8.5, "close": 10} # K2: 被K1包含
        ]
        # 标注说明
        annotations = [
            dict(x=0, y=12.2, text="K1", showarrow=False),
            dict(x=1, y=11.7, text="K2 (被包含)", showarrow=False),
            dict(x=0.5, y=7.5, text="处理结果: High=Max(H1,H2)=12, Low=Max(L1,L2)=8.5", showarrow=False, font=dict(color="blue"))
        ]
        return data, "K线包含处理（向上趋势）", annotations, []

    # 场景2：顶分型标准形态
    elif scene_name == 'fenxing_top':
        data = [
            {"open": 10, "high": 12, "low": 9, "close": 11},   # K1
            {"open": 11, "high": 13, "low": 10, "close": 10.5}, # K2 (顶)
            {"open": 10.5, "high": 11.5, "low": 9.5, "close": 10} # K3
        ]
        annotations = [
            dict(x=1, y=13.2, text="顶：13", showarrow=True, arrowhead=1),
            dict(x=1, y=10, text="区间下沿", showarrow=False, yshift=-30)
        ]
        # 画个框表示分型区间
        shapes = [
            dict(type="rect", x0=-0.2, y0=9.5, x1=2.2, y1=13, line=dict(color="RoyalBlue", width=2, dash="dash"))
        ]
        return data, "顶分型标准形态", annotations, shapes

    # 场景3：底分型标准形态
    elif scene_name == 'fenxing_bottom':
        data = [
            {"open": 12, "high": 13, "low": 11, "close": 11.5},
            {"open": 11.5, "high": 12, "low": 9, "close": 10}, # 底
            {"open": 10, "high": 11, "low": 9.5, "close": 10.5}
        ]
        return data, "底分型标准形态", [], []

    # 场景4：笔的定义（简单版）
    # 顶分型 + 独立K线 + 底分型
    elif scene_name == 'bi_standard':
        data = [
            {"open": 10, "high": 12, "low": 9, "close": 11},    # 顶分左
            {"open": 11, "high": 13, "low": 10, "close": 10.5}, # 顶分中 (Top)
            {"open": 10.5, "high": 11.5, "low": 9.5, "close": 10}, # 顶分右
            {"open": 10, "high": 11, "low": 9, "close": 9.5},    # 独立K线
            {"open": 9, "high": 10, "low": 8, "close": 8.5},     # 底分左
            {"open": 8, "high": 9, "low": 7, "close": 8.5},      # 底分中 (Bottom)
            {"open": 8.5, "high": 9.5, "low": 8, "close": 9}     # 底分右
        ]
        # 画连线表示“笔”
        shapes = [
            dict(type="line", x0=1, y0=13, x1=5, y1=7, line=dict(color="blue", width=4))
        ]
        annotations = [
            dict(x=1, y=13.2, text="顶", showarrow=False),
            dict(x=5, y=6.8, text="底", showarrow=False),
            dict(x=3, y=11, text="独立K线", ax=0, ay=-40)
        ]
        return data, "标准向下笔", annotations, shapes

    elif scene_name == 'bi_comparison':
        # 左侧展示老笔（5K），右侧展示新笔（4K/共用）
        data = [
            # 老笔 (0-6)
            {"open": 10, "high": 11, "low": 9, "close": 10.5},   # 1
            {"open": 10.5, "high": 12, "low": 11, "close": 11.5}, # 2 顶
            {"open": 11.5, "high": 11.8, "low": 10.8, "close": 11},# 3
            {"open": 11, "high": 11.5, "low": 9.5, "close": 10},   # 4 独立K线
            {"open": 10, "high": 10.5, "low": 8.5, "close": 9},    # 5
            {"open": 9, "high": 9.5, "low": 8.0, "close": 8.5},    # 6 底
            {"open": 8.5, "high": 10, "low": 8.5, "close": 9.5},   # 7
            # 间隔
            {"open": None, "high": None, "low": None, "close": None},
            # 新笔 (9-12) - 无独立K线
            {"open": 10, "high": 11, "low": 9, "close": 10.5},   # 9
            {"open": 10.5, "high": 12, "low": 11, "close": 11.5}, # 10 顶 (共用)
            {"open": 11.5, "high": 11.8, "low": 10.8, "close": 11},# 11 (共用)
            {"open": 11, "high": 11.5, "low": 9, "close": 10},    # 12
            {"open": 10, "high": 10.5, "low": 8.5, "close": 9},    # 13 底
            {"open": 9, "high": 10, "low": 9, "close": 9.5},      # 14
        ]
        shapes = [
            # 老笔连线
            dict(type="line", x0=1, y0=12, x1=5, y1=8, line=dict(color="blue", width=3, dash="dash")),
            # 新笔连线
            dict(type="line", x0=9, y0=12, x1=12, y1=8.5, line=dict(color="red", width=3))
        ]
        annotations = [
            dict(x=3, y=12.5, text="老笔 (需独立K线)", showarrow=False, font=dict(color="blue")),
            dict(x=11, y=12.5, text="新笔 (允许分型共用)", showarrow=False, font=dict(color="red")),
            dict(x=3, y=10, text="中间有空隙", ax=0, ay=30),
            dict(x=10.5, y=11.3, text="顶底紧挨着", ax=0, ay=-30)
        ]
        return data, "新老笔辨析", annotations, shapes

    # 场景5：中枢示意图 (详细构建)
    elif scene_name == 'center_standard':
        # 构造下-上-下三段重叠 (通常用于上涨中枢的构建，或者下跌中枢的第一个中枢)
        # 假设：
        # S1 (Down): 12 -> 10 (High=12, Low=10)
        # S2 (Up):   10 -> 11.5 (High=11.5, Low=10)
        # S3 (Down): 11.5 -> 10.5 (High=11.5, Low=10.5)
        
        # ZG = Min(g1=12, g2=11.5, g3=11.5) = 11.5
        # ZD = Max(d1=10, d2=10, d3=10.5) = 10.5
        # 中枢区间 = [10.5, 11.5]
        
        bi1 = _generate_bi(12, 10, 6)
        bi2 = _generate_bi(10, 11.5, 6)
        bi3 = _generate_bi(11.5, 10.5, 6)
        
        data = bi1 + bi2[1:] + bi3[1:]
        
        i1 = len(bi1) - 1
        i2 = i1 + len(bi2) - 1
        i3 = i2 + len(bi3) - 1
        
        shapes = [
            # 中枢区间 Box (ZD ~ ZG)
            dict(type="rect", x0=0, y0=10.5, x1=i3, y1=11.5, fillcolor="rgba(128, 0, 128, 0.2)", line=dict(width=0), label=dict(text="中枢")),
            
            # ZG Line
            dict(type="line", x0=0, y0=11.5, x1=i3, y1=11.5, line=dict(color="purple", width=2, dash="dash")),
            # ZD Line
            dict(type="line", x0=0, y0=10.5, x1=i3, y1=10.5, line=dict(color="purple", width=2, dash="dash")),
            
            # 标记每段及其高低点
            dict(type="line", x0=0, y0=12, x1=i1, y1=10, line=dict(color="green", width=3), label=dict(text="S1(下)")),
            dict(type="line", x0=i1, y0=10, x1=i2, y1=11.5, line=dict(color="red", width=3), label=dict(text="S2(上)")),
            dict(type="line", x0=i2, y0=11.5, x1=i3, y1=10.5, line=dict(color="green", width=3), label=dict(text="S3(下)"))
        ]
        
        annotations = [
            dict(x=i2, y=11.6, text="ZG=Min(Highs)=11.5", showarrow=False, font=dict(color="purple", size=12)),
            dict(x=i1, y=10.4, text="ZD=Max(Lows)=10.5", showarrow=False, font=dict(color="purple", size=12)),
            dict(x=0, y=12.2, text="g1=12", showarrow=False, font=dict(size=10)),
            dict(x=i1, y=9.8, text="d1=10, d2=10", showarrow=False, font=dict(size=10)),
            dict(x=i2, y=11.8, text="g2=11.5, g3=11.5", showarrow=False, font=dict(size=10))
        ]
        return data, "中枢构建原理图 (S1+S2+S3)", annotations, shapes

    # 场景6：线段基础定义 (三笔)
    elif scene_name == 'segment_basics':
        # 构造三笔数据：上、下、上
        # 1. 上: 10 -> 13
        bi1 = _generate_bi(10, 13, 6)
        # 2. 下: 13 -> 11 (保证重叠)
        bi2 = _generate_bi(13, 11, 6)
        # 3. 上: 11 -> 14
        bi3 = _generate_bi(11, 14, 6)
        
        # 合并数据，注意去重连接点
        data = bi1 + bi2[1:] + bi3[1:] 
        
        # 计算连接点的索引
        idx1 = 0
        idx2 = len(bi1) - 1 # 笔1结束
        idx3 = idx2 + len(bi2) - 1 # 笔2结束
        idx4 = idx3 + len(bi3) - 1 # 笔3结束
        
        shapes = [
            dict(type="line", x0=idx1, y0=10, x1=idx2, y1=13, line=dict(color="red", width=3), label=dict(text="笔1")),
            dict(type="line", x0=idx2, y0=13, x1=idx3, y1=11, line=dict(color="green", width=3), label=dict(text="笔2")),
            dict(type="line", x0=idx3, y0=11, x1=idx4, y1=14, line=dict(color="red", width=3), label=dict(text="笔3"))
        ]
        annotations = [
            dict(x=idx3, y=11.5, text="三笔重叠 -> 线段", ax=0, ay=40, font=dict(size=14, color="blue"))
        ]
        return data, "线段的基本构成", annotations, shapes

    # 场景7：特征序列示意
    elif scene_name == 'segment_feature_sequence':
        # 向上线段，特征序列是“向下笔”
        # 1. Up (Base)
        bi0 = _generate_bi(10, 12, 5)
        # 2. Down (S1) - Feature Element
        bi1 = _generate_bi(12, 11, 5)
        # 3. Up
        bi2 = _generate_bi(11, 13, 5)
        # 4. Down (S2) - Feature Element
        bi3 = _generate_bi(13, 12, 5)
        # 5. Up
        bi4 = _generate_bi(12, 14, 5)
        # 6. Down (S3) - Feature Element
        bi5 = _generate_bi(14, 13, 5)
        
        data = bi0 + bi1[1:] + bi2[1:] + bi3[1:] + bi4[1:] + bi5[1:]
        
        # Indices
        end0 = len(bi0) - 1
        end1 = end0 + len(bi1) - 1
        end2 = end1 + len(bi2) - 1
        end3 = end2 + len(bi3) - 1
        end4 = end3 + len(bi4) - 1
        end5 = end4 + len(bi5) - 1
        
        shapes = [
            # 标记 S1, S2, S3 (向下笔)
            # 使用矩形框住整笔范围
            dict(type="rect", x0=end0, y0=11, x1=end1, y1=12, fillcolor="rgba(0,128,0,0.1)", line=dict(color="green", width=2)),
            dict(type="rect", x0=end2, y0=12, x1=end3, y1=13, fillcolor="rgba(0,128,0,0.1)", line=dict(color="green", width=2)),
            dict(type="rect", x0=end4, y0=13, x1=end5, y1=14, fillcolor="rgba(0,128,0,0.1)", line=dict(color="green", width=2))
        ]
        annotations = [
            dict(x=(end0+end1)/2, y=10.8, text="S1\n(看作K线)", showarrow=False, font=dict(size=10)),
            dict(x=(end2+end3)/2, y=11.8, text="S2", showarrow=False, font=dict(size=10)),
            dict(x=(end4+end5)/2, y=12.8, text="S3", showarrow=False, font=dict(size=10)),
            dict(x=end2, y=14.5, text="特征序列：只看向下笔", showarrow=False, font=dict(color="purple"))
        ]
        return data, "线段的特征序列", annotations, shapes

    # 场景8：线段破坏第一种情况 (Case 1: No Gap)
    elif scene_name == 'segment_break_case1':
        # Up (S1) -> Down (S2) -> Break
        bi_up1 = _generate_bi(10, 12, 5)
        bi_s2 = _generate_bi(12, 11, 5) # S2: Low=11
        bi_up2 = _generate_bi(11, 13, 5)
        # Break Pen: Huge Down 13 -> 10 (Breaks S2 low 11)
        bi_break = _generate_bi(13, 10, 6)
        
        data = bi_up1 + bi_s2[1:] + bi_up2[1:] + bi_break[1:]
        
        idx_s2_start = len(bi_up1) - 1
        idx_s2_end = idx_s2_start + len(bi_s2) - 1
        idx_break_start = idx_s2_end + len(bi_up2) - 1
        idx_break_end = idx_break_start + len(bi_break) - 1
        
        shapes = [
            # S2 Range
            dict(type="line", x0=idx_s2_start, y0=11, x1=idx_s2_start, y1=12, line=dict(color="green", width=4, dash="dot")),
            dict(type="line", x0=idx_s2_end, y0=11, x1=idx_s2_end, y1=12, line=dict(color="green", width=4, dash="dot")),
            
            # S2 Low Mark
            dict(type="line", x0=idx_s2_start, y0=11, x1=idx_break_start, y1=11, line=dict(color="green", width=1, dash="dot")),
            
            # Break Pen
            dict(type="line", x0=idx_break_start, y0=13, x1=idx_break_end, y1=10, line=dict(color="black", width=4), label=dict(text="破坏笔"))
        ]
        annotations = [
            dict(x=idx_s2_end, y=10.8, text="S2底:11", showarrow=False, font=dict(color="green")),
            dict(x=idx_break_end, y=9.8, text="强力跌穿且包含S2\n(笔破坏)", showarrow=True, font=dict(color="red"))
        ]
        return data, "第一种破坏(笔破坏)", annotations, shapes

    # 场景9：线段破坏第二种情况 (Case 2: With Gap / Feature Fenxing)
    elif scene_name == 'segment_break_case2':
        # Up (S_prev) -> Down (S2, Feature) -> Up (High)
        bi0 = _generate_bi(10, 12, 5)
        bi1 = _generate_bi(12, 11, 5)   # S2 Low=11
        bi2 = _generate_bi(11, 13.5, 5) # High=13.5
        
        # P1: Down to 12.5 (> S2 Low 11) -> Gap exists
        bi3 = _generate_bi(13.5, 12.5, 5)
        
        # P2: Up Rebound to 13 (< 13.5)
        bi4 = _generate_bi(12.5, 13, 4)
        
        # P3: Down to 11.5 (Breaks P1 Low 12.5) -> Confirms
        bi5 = _generate_bi(13, 11.5, 5)
        
        data = bi0 + bi1[1:] + bi2[1:] + bi3[1:] + bi4[1:] + bi5[1:]
        
        # Indices
        i0 = len(bi0) - 1
        i1 = i0 + len(bi1) - 1 # S2 end
        i2 = i1 + len(bi2) - 1 # P1 start
        i3 = i2 + len(bi3) - 1 # P1 end
        i4 = i3 + len(bi4) - 1 # P2 end
        i5 = i4 + len(bi5) - 1 # P3 end

        shapes = [
            # S2
            dict(type="line", x0=i0, y0=12, x1=i1, y1=11, line=dict(color="green", width=3), label=dict(text="前特征S2")),
            # S2 Low Ref
            dict(type="line", x0=i1, y0=11, x1=i3, y1=11, line=dict(color="green", width=1, dash="dot")),

            # P1
            dict(type="line", x0=i2, y0=13.5, x1=i3, y1=12.5, line=dict(color="orange", width=4), label=dict(text="第一笔P1")),
            # P1 Low Ref
            dict(type="line", x0=i3, y0=12.5, x1=i5, y1=12.5, line=dict(color="orange", width=2, dash="dot")),

            # P2 Rebound
            dict(type="line", x0=i3, y0=12.5, x1=i4, y1=13, line=dict(color="gray", width=2, dash="dash"), label=dict(text="反抽")),
            
            # P3 Final Break
            dict(type="line", x0=i4, y0=13, x1=i5, y1=11.5, line=dict(color="red", width=4), label=dict(text="确立笔P3"))
        ]
        annotations = [
            dict(x=i3, y=12.2, text="P1底(12.5) > S2底(11)\n(未包含)", showarrow=True, ax=0, ay=30, arrowcolor="green"),
            dict(x=i5, y=11.2, text="最终跌破P1底\n(分型确立)", showarrow=True, ax=0, ay=30, font=dict(color="red"))
        ]
        return data, "第二种破坏(线段分型)-图解", annotations, shapes

    # 场景7：超强顶分型（断头铡刀）
    elif scene_name == 'fenxing_top_strong':
        data = [
            {"open": 10, "high": 11, "low": 9.5, "close": 10.8},   # K1: 阳线
            {"open": 10.8, "high": 12, "low": 10.5, "close": 11},  # K2: 顶，冲高回落
            {"open": 10.5, "high": 10.5, "low": 9.0, "close": 9.2} # K3: 大阴线，跌穿K1低点(9.5)
        ]
        annotations = [
            dict(x=0, y=9.5, text="K1低点", showarrow=True, arrowhead=1, ax=-40, ay=0),
            dict(x=2, y=9.2, text="跌穿！(最强力度)", showarrow=True, arrowhead=1, ax=40, ay=0, font=dict(color="red"))
        ]
        return data, "超强顶分型（断头铡刀）", annotations, []

    # 场景8：中继顶分型（弱势）
    elif scene_name == 'fenxing_top_weak':
        data = [
            {"open": 10, "high": 11, "low": 9.5, "close": 10.8},   # K1
            {"open": 10.8, "high": 11.2, "low": 10.6, "close": 10.9}, # K2: 小顶
            {"open": 10.9, "high": 11.0, "low": 10.5, "close": 10.6}  # K3: 小幅回调，未破K1实体中值
        ]
        annotations = [
            dict(x=2, y=10.5, text="回调极弱，大概率中继", showarrow=True, arrowhead=1, ax=0, ay=40)
        ]
        return data, "中继顶分型（弱势）", annotations, []
    
    # 场景9：超强底分型（V型反转）
    elif scene_name == 'fenxing_bottom_strong':
        data = [
            {"open": 10, "high": 10.2, "low": 8.5, "close": 8.8},   # K1: 大阴线
            {"open": 8.8, "high": 9.0, "low": 8.0, "close": 8.5},   # K2: 见底
            {"open": 8.5, "high": 10.5, "low": 8.5, "close": 10.3}  # K3: 大阳线反包，收盘(10.3) > K1高点(10.2)
        ]
        annotations = [
            dict(x=2, y=10.3, text="反包新高！(V反)", showarrow=True, arrowhead=1, ax=40, ay=0, font=dict(color="red"))
        ]
        return data, "超强底分型（V型反转）", annotations, []

    return [], "未知场景", [], []

def get_demo_fenxing_data(type='top'):
    # 兼容旧代码，虽然这会被 get_chart_data 替代
    if type == 'top':
         data, _, _, _ = get_chart_data('fenxing_top')
         return data
    elif type == 'bottom':
         data, _, _, _ = get_chart_data('fenxing_bottom')
         return data
    return []
