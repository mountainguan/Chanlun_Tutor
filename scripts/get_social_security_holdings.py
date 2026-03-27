import akshare as ak
import pandas as pd
from datetime import datetime
import os

def get_social_security_holdings(report_date):
    """
    获取指定报告期的社保基金持股信息
    :param report_date: 财报统计截止日期，格式 'YYYYMMDD' (例如 '20251231')
    """
    print(f"正在获取 {report_date} 社保基金持股数据，请耐心等待...")
    
    try:
        # 直接使用 akshare 获取社保基金持股数据
        df = ak.stock_report_fund_hold(symbol="社保持仓", date=report_date)
        
        if df is None or df.empty:
            print(f"未获取到 {report_date} 的数据，请检查日期是否为财报截止日或数据尚未披露。")
            return None

        print(f"筛选完成！共找到 {len(df)} 条社保基金持股记录。")
        return df

    except Exception as e:
        print(f"发生错误: {e}")
        return None

if __name__ == "__main__":
    # 查询指定季度的财报 (例如：2025年四季度 20251231, 或 2025三季度 20250930)
    target_date = "20251231" 
    
    holdings = get_social_security_holdings(target_date)
    
    if holdings is not None and not holdings.empty:
        # 显示前 10 条
        print("\n前10条持仓记录：")
        print(holdings.head(10).to_string(index=False))
        
        # 保存为 Excel 和 CSV
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        file_name = os.path.join(output_dir, f"社保基金持股_{target_date}.xlsx")
        holdings.to_excel(file_name, index=False)
        print(f"\n完整数据已保存至：{file_name}")
