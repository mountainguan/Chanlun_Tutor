#!/usr/bin/env python3
"""
获取中央汇金持股数据的脚本
数据来源：东方财富网-十大流通股东（全市场分析接口）
逻辑：使用 ak.stock_gdfx_free_holding_analyse_em 获取指定季度的全市场十大流通股东数据，
      筛选包含“中央汇金”的数据（包括资产管理公司和投资公司）。
"""

import sys
import os
import json
import time
import pandas as pd
import akshare as ak

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

def get_huijin_data(date_str='20250930'):
    print(f"开始获取 {date_str} 的中央汇金持股数据...")
    print("注意：该接口获取全市场数据，可能需要几分钟，请耐心等待...")
    
    try:
        # 获取全市场十大流通股东数据
        # 该接口返回所有股票的十大流通股东信息
        df = ak.stock_gdfx_free_holding_analyse_em(date=date_str)
        
        if df is None or df.empty:
            print(f"未获取到 {date_str} 的数据")
            return []
            
        print(f"成功获取全市场数据，共 {len(df)} 条记录")
        
        # 筛选中央汇金
        # 股东名称包含“中央汇金”
        mask = df['股东名称'].str.contains('中央汇金', na=False)
        huijin_rows = df[mask]
        
        if huijin_rows.empty:
            print("未找到中央汇金持仓记录")
            return []
            
        print(f"筛选出 {len(huijin_rows)} 条中央汇金持仓记录")
        
        results = []
        for _, row in huijin_rows.iterrows():
            # 映射字段
            # API返回列名: ['序号', '股东名称', '股东类型', '股票代码', '股票简称', '报告期', '期末持股-数量', '期末持股-数量变化', '期末持股-数量变化比例', '期末持股-持股变动', '期末持股-流通市值', ...]
            
            try:
                holdings = float(row['期末持股-数量'])
            except:
                holdings = 0.0
                
            try:
                market_value = float(row['期末持股-流通市值'])
            except:
                market_value = 0.0
                
            try:
                change_amount = float(row['期末持股-数量变化'])
            except:
                change_amount = 0.0
                
            # 处理变动比例 (有些可能是字符串带%)
            try:
                change_ratio = float(row['期末持股-数量变化比例'])
            except:
                change_ratio = 0.0
                
            change_type = row['期末持股-持股变动']
            # 如果变动类型为空，根据变动数值判断
            if not change_type or pd.isna(change_type):
                if change_amount > 0:
                    change_type = '增加'
                elif change_amount < 0:
                    change_type = '减少'
                elif change_amount == 0:
                    change_type = '不变'
                if holdings > 0 and change_amount == holdings:
                    change_type = '新进'

            results.append({
                '股票代码': str(row['股票代码']),
                '股票简称': row['股票简称'],
                '股东名称': row['股东名称'],
                '持股总数': holdings,
                '持股市值': market_value,
                '持股变动数值': change_amount,
                '持股变动比例': change_ratio,
                '持股变化': change_type,
                '股份类型': '流通A股', # 默认为流通A股
                '名次': row.get('序号', 0) # 这个序号可能是全表的序号，不是排名的名次，但API没给名次
            })
            
        return results
            
    except Exception as e:
        print(f"获取数据失败: {e}")
        import traceback
        traceback.print_exc()
        return []

def save_data(holdings, date_str):
    if not holdings:
        print("未获取到任何数据，不进行保存")
        return

    # 转换为DataFrame进行汇总
    df = pd.DataFrame(holdings)
    
    # 汇总
    # 同一个股票可能有多个汇金账户（如资产管理公司和投资公司）
    # 我们需要合并它们的持股
    df_grouped = df.groupby(['股票代码', '股票简称']).agg({
        '持股总数': 'sum',
        '持股市值': 'sum',
        '持股变动数值': 'sum',
        '持股变动比例': 'mean', # 比例取平均还是重算？重算比较复杂，这里取平均或忽略
        '股东名称': 'count' # 这里的count就是持有家数
    }).reset_index()
    
    df_grouped = df_grouped.rename(columns={'股东名称': '持有基金家数'})
    
    # 重新判断持股变化
    df_grouped['持股变化'] = df_grouped.apply(
        lambda row: '新进' if (row['持股变动数值'] == row['持股总数'] and row['持股总数'] > 0) else 
                   ('增加' if row['持股变动数值'] > 0 else 
                   ('减少' if row['持股变动数值'] < 0 else '不变')), 
        axis=1
    )
    
    # 添加序号
    df_grouped['序号'] = range(1, len(df_grouped) + 1)
    
    # 保存为JSON
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        
    cache_file = os.path.join(data_dir, 'huijin_fund_cache.json')
    
    result_data = {
        'timestamp': time.time(),
        'date': date_str,
        'data': df_grouped.to_dict('records')
    }
    
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
        
    print(f"数据已保存至 {cache_file}")
    print(f"共获取 {len(df_grouped)} 只股票的中央汇金持仓数据")

if __name__ == "__main__":
    # 默认获取 20250930 数据
    target_date = '20250930'
    
    if len(sys.argv) > 1:
         target_date = sys.argv[1]
    
    data = get_huijin_data(date_str=target_date)
    save_data(data, target_date)
