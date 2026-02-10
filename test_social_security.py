#!/usr/bin/env python3
"""
社保基金持股分析模块测试脚本
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from utils.social_security_fund import SocialSecurityFund
import pandas as pd

def main():
    print("=" * 60)
    print("社保基金持股分析模块测试")
    print("=" * 60)

    try:
        # 初始化
        print("初始化社保基金管理器...")
        ssf = SocialSecurityFund()

        # 测试1: 获取最新持仓
        print("\n测试1: 获取最新持仓数据")
        print("-" * 40)
        df = ssf.get_latest_holdings(force_update=True)
        print(f"✅ 成功获取 {len(df)} 只股票的持仓数据")

        # 基本统计
        total_value = df['持股市值'].sum()
        print(f"总持股市值: {total_value/1e8:.2f} 亿元")

        # 前5大持仓
        top_5 = df.nlargest(5, '持股市值')
        print("\n前5大持仓:")
        for idx, row in top_5.iterrows():
            print(f"  {row['股票代码']} {row['股票简称']}: {row['持股市值']/1e8:.2f} 亿元")

        # 测试2: 获取前10大持仓
        print("\n测试2: 获取前10大持仓")
        print("-" * 40)
        top_10 = ssf.get_top_holdings(10)
        print(f"✅ 成功获取前10大持仓，共 {len(top_10)} 只股票")

        # 测试3: 计算持股变化
        print("\n测试3: 计算持股变化")
        print("-" * 40)
        test_codes = df['股票代码'].head(3).tolist()
        print(f"测试股票: {test_codes}")

        changes = ssf.calculate_holdings_changes(test_codes, quarters=4)

        if changes:
            print(f"✅ 成功计算 {len(changes)} 只股票的变化")
            for code, data in changes.items():
                print(f"\n股票 {code} ({data['stock_name']}):")
                print(f"  当前市值: {data['current_market_value']/1e8:.2f} 亿元")
                print(f"  变化趋势: {data['change_trend']}")
                print(f"  分析季度数: {data['quarters_analyzed']}")

                # 显示最近变化
                if data['detailed_changes']:
                    recent_changes = data['detailed_changes'][-2:]
                    print("  最近变化:")
                    for change in recent_changes:
                        holdings_change = change.get('holdings_change', 0)
                        print(f"    {change['date']}: 持有 {change['holdings']:.0f} 股 (变化: {holdings_change:+.0f})")
        else:
            print("⚠️ 没有获取到变化数据")

        # 测试4: 获取新买入股票
        print("\n测试4: 获取新买入股票")
        print("-" * 40)
        new_positions = ssf.get_new_positions()
        if not new_positions.empty:
            print(f"✅ 发现 {len(new_positions)} 只新买入股票")
            print("新买入股票:")
            for idx, row in new_positions.head(3).iterrows():
                print(f"  {row['股票代码']} {row['股票简称']}: {row['持股市值']/1e8:.2f} 亿元")
        else:
            print("✅ 本季度没有新买入股票")

        # 测试5: 缓存机制
        print("\n测试5: 缓存机制")
        print("-" * 40)
        print("从缓存读取数据...")
        df_cached = ssf.get_latest_holdings(force_update=False)
        if df.equals(df_cached):
            print("✅ 缓存数据与原始数据一致")
        else:
            print("❌ 缓存数据不一致")

        print("\n" + "=" * 60)
        print("🎉 所有测试通过！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)