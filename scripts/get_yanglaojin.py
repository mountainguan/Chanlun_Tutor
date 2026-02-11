import akshare as ak
import pandas as pd
from datetime import datetime

def get_pension_fund_holdings(report_date):
    """
    获取指定报告期的基本养老保险持股信息
    :param report_date: 财报统计截止日期，格式 'YYYYMMDD' (例如 '20240930')
    """
    print(f"正在获取 {report_date} 全市场十大流通股东数据，数据量较大请耐心等待...")
    
    try:
        # 1. 获取全市场十大流通股东数据 (数据来源: 东方财富)
        # 该接口一次性返回全市场数据，比单只股票遍历效率高很多
        df = ak.stock_gdfx_free_holding_analyse_em(date=report_date)
        
        if df is None or df.empty:
            print(f"未获取到 {report_date} 的数据，请检查日期是否为财报截止日（3月31日/6月30日/9月30日/12月31日）或数据尚未披露。")
            return None

        # 2. 筛选“基本养老保险”持股
        # 股东名称中通常包含 "基本养老保险基金八零二组合" 这样的字样
        # 也可以同时筛选 "社保基金" (包含养老金和社保)
        keywords = ["基本养老保险", "养老保险基金"] 
        mask = df['股东名称'].str.contains('|'.join(keywords), na=False)
        pension_df = df[mask]

        # 3. 数据清洗与整理
        # 选取关键列，重置索引
        columns_to_keep = [
            '股票代码', '股票简称', '股东名称', '期末持股-数量', 
            '期末持股-数量变化', '期末持股-数量变化比例', '公告日'
        ]
        # 检查列名是否存在，防止接口字段变更
        valid_columns = [c for c in columns_to_keep if c in pension_df.columns]
        result_df = pension_df[valid_columns].reset_index(drop=True)

        print(f"筛选完成！共找到 {len(result_df)} 条基本养老保险持股记录。")
        return result_df

    except Exception as e:
        print(f"发生错误: {e}")
        return None

if __name__ == "__main__":
    # 示例：查询 2025年三季度报 (截止日通常为 03-31, 06-30, 09-30, 12-31)
    # 注意：最新财报披露有一定的滞后性，例如 10月底才披露完三季报
    target_date = "20250930" 
    
    holdings = get_pension_fund_holdings(target_date)
    
    if holdings is not None and not holdings.empty:
        # 显示前 10 条
        print(holdings.head(10))
        
        # 保存为 Excel (可选)
        file_name = f"基本养老保险持股_{target_date}.xlsx"
        holdings.to_excel(file_name, index=False)
        print(f"数据已保存至 {file_name}")