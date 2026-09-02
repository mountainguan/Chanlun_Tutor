import akshare as ak
import pandas as pd
from datetime import datetime
import os
import json

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
    target_date = "20260331"

    import sys
    if len(sys.argv) > 1:
        target_date = sys.argv[1]

    holdings = get_social_security_holdings(target_date)

    if holdings is not None and not holdings.empty:
        # 显示前 10 条
        print("\n前10条持仓记录：")
        print(holdings.head(10).to_string(index=False))

        # 保存为 Excel (按季度归档到 data/shebaojijin 目录)
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'shebaojijin')
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        file_name = os.path.join(output_dir, f"社保基金持股_{target_date}.xlsx")
        holdings.to_excel(file_name, index=False)
        print(f"\n完整数据已保存至：{file_name}")

        # 同步写入 social_security_fund_cache.json (JSON 格式，供前端读取)
        # 注意：ak.stock_report_fund_hold 返回的字段已经是目标格式（持股总数/持股市值/持股变化等），
        # 不需要按股票代码再聚合，直接以 6 位字符串股票代码保存即可。
        import time as _time

        # 确保股票代码为 6 位字符串（akshare 返回的可能是数字）
        df_cache = holdings.copy()
        df_cache['股票代码'] = df_cache['股票代码'].astype(str).str.zfill(6)

        # 补全必要的列，避免前端 KeyError
        for col, default in [
            ('持有基金家数', 1),
            ('持股总数', 0),
            ('持股市值', 0.0),
            ('持股变动数值', 0.0),
            ('持股变动比例', 0.0),
            ('持股变化', '不变'),
            ('序号', None),
        ]:
            if col not in df_cache.columns:
                df_cache[col] = default

        if '序号' in df_cache.columns and df_cache['序号'].isna().all():
            df_cache['序号'] = range(1, len(df_cache) + 1)

        # NaN → 0（数值列），避免 JSON 里写 NaN 导致前端解析失败
        for col in ['持股总数', '持股市值', '持股变动数值', '持股变动比例']:
            df_cache[col] = pd.to_numeric(df_cache[col], errors='coerce').fillna(0)

        df_cache['持股变化'] = df_cache['持股变化'].fillna('不变')

        cache_data = {
            'timestamp': _time.time(),
            'date': target_date,
            'data': df_cache.to_dict('records'),
        }
        cache_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'social_security_fund_cache.json')
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        print(f"JSON 缓存已同步至：{cache_file} (共 {len(df_cache)} 条)")
