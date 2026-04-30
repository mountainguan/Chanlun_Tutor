#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
同步最新的社保基金、养老金、汇金持股数据到系统缓存

使用方法:
    python scripts/sync_latest_data.py [--date YYYYMMDD] [--type all|social|pension|huijin]

示例:
    python scripts/sync_latest_data.py                     # 同步所有数据到最新可用日期
    python scripts/sync_latest_data.py --date 20260331     # 同步到指定日期
    python scripts/sync_latest_data.py --type social       # 只同步社保基金数据
"""

import pandas as pd
import json
import os
import sys
import time
import argparse
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_data_dir():
    """获取数据目录路径"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

def find_latest_excel(prefix, data_dir, sub_dir=None):
    """查找最新的Excel文件"""
    search_dir = os.path.join(data_dir, sub_dir) if sub_dir else data_dir

    if not os.path.exists(search_dir):
        print(f"目录不存在: {search_dir}")
        return None, None

    files = [f for f in os.listdir(search_dir) if f.startswith(prefix) and f.endswith('.xlsx')]

    if not files:
        print(f"未找到 {prefix} 开头的Excel文件")
        return None, None

    # 按日期排序，取最新的
    files.sort(reverse=True)
    latest_file = files[0]

    # 从文件名提取日期
    date_str = latest_file.replace(prefix, '').replace('.xlsx', '').replace('_', '')

    return os.path.join(search_dir, latest_file), date_str

def convert_social_security_data(excel_path, report_date):
    """将社保基金Excel数据转换为缓存格式"""
    print(f"正在处理社保基金数据: {excel_path}")

    try:
        df = pd.read_excel(excel_path)
        print(f"读取到 {len(df)} 条记录")

        # 确保股票代码为6位字符串
        df['股票代码'] = df['股票代码'].astype(str).str.zfill(6)

        # 确保必要的列存在
        required_columns = ['股票代码', '股票简称', '持股总数', '持股市值', '持股变动数值', '持股变动比例']
        for col in required_columns:
            if col not in df.columns:
                print(f"缺少必要列: {col}")
                return None

        # 添加序号
        df['序号'] = range(1, len(df) + 1)

        # 添加持有基金家数（默认为1）
        if '持有基金家数' not in df.columns:
            df['持有基金家数'] = 1

        # 确定持股变化类型
        if '持股变化' not in df.columns:
            def determine_change(row):
                change_val = row.get('持股变动数值', 0)
                if pd.isna(change_val) or change_val == 0:
                    return '不变'
                elif change_val > 0:
                    return '增仓'
                else:
                    return '减仓'
            df['持股变化'] = df.apply(determine_change, axis=1)

        # 处理NaN值
        df = df.fillna(0)

        return df

    except Exception as e:
        print(f"处理社保基金数据失败: {e}")
        return None

def convert_pension_data(excel_path, report_date):
    """将养老金Excel数据转换为缓存格式"""
    print(f"正在处理养老金数据: {excel_path}")

    try:
        df = pd.read_excel(excel_path)
        print(f"读取到 {len(df)} 条记录")

        # 重命名列以匹配系统格式
        column_mapping = {
            '期末持股-数量': '持股总数',
            '期末持股-数量变化': '持股变动数值',
            '期末持股-数量变化比例': '持股变动比例'
        }
        df = df.rename(columns=column_mapping)

        # 确保股票代码为6位字符串
        df['股票代码'] = df['股票代码'].astype(str).str.zfill(6)

        # 添加序号
        df['序号'] = range(1, len(df) + 1)

        # 添加持有基金家数
        if '持有基金家数' not in df.columns:
            df['持有基金家数'] = 1

        # 如果没有市值列，使用估算值
        if '持股市值' not in df.columns:
            df['持股市值'] = df['持股总数'] * 15.0  # 估算

        # 确定持股变化类型
        if '持股变化' not in df.columns:
            def determine_change(row):
                change_val = row.get('持股变动数值', 0)
                if pd.isna(change_val) or change_val == 0:
                    return '新进'
                elif change_val > 0:
                    return '增加'
                else:
                    return '减少'
            df['持股变化'] = df.apply(determine_change, axis=1)

        # 处理NaN值
        df = df.fillna(0)

        return df

    except Exception as e:
        print(f"处理养老金数据失败: {e}")
        return None

def convert_huijin_data(excel_path, report_date):
    """将汇金Excel数据转换为缓存格式"""
    print(f"正在处理汇金数据: {excel_path}")

    try:
        df = pd.read_excel(excel_path)
        print(f"读取到 {len(df)} 条记录")

        # 确保股票代码为6位字符串
        df['股票代码'] = df['股票代码'].astype(str).str.zfill(6)

        # 确保必要的列存在
        required_columns = ['股票代码', '股票简称', '持股总数', '持股市值']
        for col in required_columns:
            if col not in df.columns:
                print(f"缺少必要列: {col}")
                return None

        # 添加序号
        df['序号'] = range(1, len(df) + 1)

        # 添加持有基金家数
        if '持有基金家数' not in df.columns:
            df['持有基金家数'] = 1

        # 添加持股变动相关列
        if '持股变动数值' not in df.columns:
            df['持股变动数值'] = 0
        if '持股变动比例' not in df.columns:
            df['持股变动比例'] = 0

        # 确定持股变化类型
        if '持股变化' not in df.columns:
            df['持股变化'] = '不变'

        # 处理NaN值
        df = df.fillna(0)

        return df

    except Exception as e:
        print(f"处理汇金数据失败: {e}")
        return None

def convert_to_serializable(obj):
    """将不可序列化的对象转换为可序列化的格式"""
    import pandas as pd
    if isinstance(obj, pd.Timestamp):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(obj, (pd.NaT.__class__, type(pd.NaT))):
        return None
    elif isinstance(obj, float) and pd.isna(obj):
        return None
    return obj

def save_cache(df, cache_file, report_date):
    """保存数据到JSON缓存文件"""
    # 转换DataFrame为字典列表，处理不可序列化的类型
    data_records = []
    for _, row in df.iterrows():
        record = {}
        for col, value in row.items():
            record[col] = convert_to_serializable(value)
        data_records.append(record)

    cache_data = {
        'timestamp': time.time(),
        'date': report_date,
        'data': data_records
    }

    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)

    print(f"已保存缓存: {cache_file} (日期: {report_date}, 记录数: {len(df)})")

def sync_data(target_date=None, data_type='all'):
    """同步数据到缓存"""
    data_dir = get_data_dir()

    results = {}

    # 同步社保基金数据
    if data_type in ['all', 'social']:
        print("\n=== 同步社保基金数据 ===")
        if target_date:
            excel_path = os.path.join(data_dir, f'社保基金持股_{target_date}.xlsx')
            if os.path.exists(excel_path):
                report_date = target_date
            else:
                print(f"文件不存在: {excel_path}")
                excel_path, report_date = find_latest_excel('社保基金持股_', data_dir)
        else:
            excel_path, report_date = find_latest_excel('社保基金持股_', data_dir)

        if excel_path and report_date:
            df = convert_social_security_data(excel_path, report_date)
            if df is not None:
                cache_file = os.path.join(data_dir, 'social_security_fund_cache.json')
                save_cache(df, cache_file, report_date)
                results['social_security'] = {'date': report_date, 'count': len(df)}

    # 同步养老金数据
    if data_type in ['all', 'pension']:
        print("\n=== 同步养老金数据 ===")
        if target_date:
            excel_path = os.path.join(data_dir, 'yanglaojin', f'基本养老保险持股_{target_date}.xlsx')
            if os.path.exists(excel_path):
                report_date = target_date
            else:
                print(f"文件不存在: {excel_path}")
                excel_path, report_date = find_latest_excel('基本养老保险持股_', data_dir, 'yanglaojin')
        else:
            excel_path, report_date = find_latest_excel('基本养老保险持股_', data_dir, 'yanglaojin')

        if excel_path and report_date:
            df = convert_pension_data(excel_path, report_date)
            if df is not None:
                cache_file = os.path.join(data_dir, 'pension_fund_cache.json')
                save_cache(df, cache_file, report_date)
                results['pension'] = {'date': report_date, 'count': len(df)}

    # 同步汇金数据
    if data_type in ['all', 'huijin']:
        print("\n=== 同步汇金数据 ===")
        if target_date:
            excel_path = os.path.join(data_dir, f'中央汇金持股_{target_date}.xlsx')
            if os.path.exists(excel_path):
                report_date = target_date
            else:
                print(f"文件不存在: {excel_path}")
                excel_path, report_date = find_latest_excel('中央汇金持股_', data_dir)
        else:
            excel_path, report_date = find_latest_excel('中央汇金持股_', data_dir)

        if excel_path and report_date:
            df = convert_huijin_data(excel_path, report_date)
            if df is not None:
                cache_file = os.path.join(data_dir, 'huijin_fund_cache.json')
                save_cache(df, cache_file, report_date)
                results['huijin'] = {'date': report_date, 'count': len(df)}

    # 更新元数据
    meta_file = os.path.join(data_dir, 'national_team_meta.json')
    meta_data = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'sync_results': results
    }
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(meta_data, f, ensure_ascii=False, indent=2)

    print("\n=== 同步完成 ===")
    for key, value in results.items():
        print(f"  {key}: 日期={value['date']}, 记录数={value['count']}")

    return results

def main():
    parser = argparse.ArgumentParser(description='同步国家队持股数据到系统缓存')
    parser.add_argument('--date', type=str, help='目标日期 (格式: YYYYMMDD)')
    parser.add_argument('--type', type=str, choices=['all', 'social', 'pension', 'huijin'],
                       default='all', help='同步类型')

    args = parser.parse_args()

    sync_data(target_date=args.date, data_type=args.type)

if __name__ == '__main__':
    main()
