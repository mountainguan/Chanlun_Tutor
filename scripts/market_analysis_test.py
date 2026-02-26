
import akshare as ak
import pandas as pd
import time
from datetime import datetime

def analyze_market():
    print("="*50)
    print(f"Market Analysis Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)

    # 1. Market Pricing Power (Pricing Power Funds)
    print("\n[1. Pricing Power Funds / 核心资金动向]")
    
    # Northbound (Foreign Capital)
    try:
        print("\n>>> Northbound Funds (北向资金 - Smart Money):")
        df_north = ak.stock_hsgt_hist_em(symbol="北向资金")
        latest = df_north.tail(5)
        # Columns: 日期, 当日成交净买额, ...
        # Clean up for display
        cols = ['日期', '当日成交净买额', '沪深300', '沪深300-涨跌幅']
        print(latest[cols].to_string(index=False))
        
        last_net = latest.iloc[-1]['当日成交净买额']
        print(f"Latest Net Flow: {last_net:.2f} (100M RMB)")
    except Exception as e:
        print(f"Error fetching Northbound flow: {e}")

    # ETF / National Team
    print("\n>>> National Team (ETF Proxy):")
    etf_map = {
        "510300": "CSI 300 (Blue Chip)",
        "510500": "CSI 500 (Mid Cap)",
        "588000": "STAR 50 (Tech)",
        "510050": "SSE 50 (Large Cap)"
    }
    print("(Note: Fetching ETF history might fail due to network/API limits)")
    for code, name in etf_map.items():
        try:
            # Try stock_zh_a_hist which is sometimes more reliable for ETFs than fund_etf_hist
            # Use very short range
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - pd.Timedelta(days=5)).strftime("%Y%m%d")
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
            if not df.empty:
                last = df.iloc[-1]
                print(f"{code} {name}: Vol {last['成交量']:.0f}, Close {last['收盘']}")
            else:
                print(f"{code} {name}: No data returned.")
        except Exception as e:
            print(f"{code} {name}: Data unavailable ({e})")
        time.sleep(0.5)

    # 2. Institutional Crowdedness (Sector Flow)
    print("\n[2. Sector Crowdedness & Reversal / 机构拥挤度]")
    
    try:
        # Use "Instant" flow as "10-day" is unstable
        print("Fetching Real-time Sector Fund Flow...")
        df_flow = ak.stock_fund_flow_industry(symbol="即时")
        
        # Columns: 序号, 行业, 行业指数, 行业-涨跌幅, 流入资金, 流出资金, 净额, 公司家数...
        # Ensure Net Flow is numeric
        # akshare usually returns floats but sometimes strings with units?
        # Based on probe, it seems to be float (69.62, 23.12 etc.)
        
        # Sort by Net Flow (Crowdedness Proxy)
        df_flow = df_flow.sort_values(by='净额', ascending=False)
        
        top_5 = df_flow.head(5)
        bottom_5 = df_flow.tail(5)
        
        print("\n>>> Top 5 Crowded Sectors (Net Inflow - Today):")
        print(top_5[['行业', '行业-涨跌幅', '净额', '领涨股']].to_string(index=False))
        
        print("\n>>> Bottom 5 Sectors (Net Outflow - Today):")
        print(bottom_5[['行业', '行业-涨跌幅', '净额', '领涨股']].to_string(index=False))
        
        # Reversal Candidates:
        # Outflow (or Low Inflow) but Price UP (Divergence)
        # Filter: Net Flow < 0 AND Change > 0
        reversal = df_flow[(df_flow['净额'] < 0) & (df_flow['行业-涨跌幅'] > 0)]
        if not reversal.empty:
            print("\n>>> Potential Reversal Candidates (Outflow but Price Rising):")
            print(reversal[['行业', '行业-涨跌幅', '净额', '领涨股']].head(10).to_string(index=False))
        else:
            print("\nNo obvious reversal divergence (Outflow + Price Up) found today.")
            
    # ... (previous code) ...
    except Exception as e:
        print(f"Error fetching Sector Flow: {e}")

    # 3. Northbound Sector Preference
    print("\n[3. Northbound Sector Preference / 北向偏好]")
    nb_top_sectors = []
    try:
        df_nb_board = ak.stock_hsgt_board_rank_em(symbol="北向资金增持行业板块排行", indicator="今日")
        cols = [c for c in df_nb_board.columns if '名称' in c or '市值' in c or '涨跌幅' in c]
        
        print("\n>>> Top Northbound Holdings (Market Value):")
        if '北向资金今日持股-市值' in df_nb_board.columns:
             df_nb_board['市值'] = df_nb_board['北向资金今日持股-市值']
             df_nb_sorted = df_nb_board.sort_values('市值', ascending=False).head(5)
             print(df_nb_sorted[['名称', '最新涨跌幅', '市值']].to_string(index=False))
             nb_top_sectors = df_nb_sorted['名称'].tolist()
        else:
            print(df_nb_board.head(5).to_string(index=False))

    except Exception as e:
        print(f"Error fetching Northbound Sectors: {e}")

    # ... (previous code) ...
    print("\n[4. Pricing Power Analysis / 定价权资金迁徙]")
    print("Comparing Domestic Fund Flow (Real-time) vs Northbound Holdings (Stock):")
    
    # Get Top Domestic Inflow names
    try:
        domestic_top_sectors = top_5['行业'].tolist() if 'top_5' in locals() else []
        
        print(f"\nDomestic Funds Chasing (Today): {', '.join(domestic_top_sectors)}")
        print(f"Northbound Holding (Stock):   {', '.join(nb_top_sectors)}")
        
        common = set(domestic_top_sectors).intersection(set(nb_top_sectors))
        if common:
            print(f"\n>>> Consensus Sectors (Both High): {', '.join(common)}")
        else:
            print("\n>>> Divergence (Funds vs Northbound):")
            print("Domestic Funds are moving into new areas (likely Tech/Growth/Cyclical),")
            print("while Northbound stays in Core Assets (Banks/Liquor/Consumer).")
            print("Pricing Power might be shifting to Domestic Funds in the active sectors.")

        # Optional: Check THS Index for the top sector
        if domestic_top_sectors:
            top_sector = domestic_top_sectors[0]
            print(f"\n[5. Verification with Tonghuashun Data: {top_sector}]")
            try:
                # Attempt to fetch THS Index History for the top sector
                # Note: Names might need mapping (e.g. 小金属 -> 小金属 concept or industry)
                # Trying direct name first
                df_ths = ak.stock_board_industry_index_ths(symbol=top_sector, start_date="20260101", end_date=datetime.now().strftime("%Y%m%d"))
                if not df_ths.empty:
                    print(f"THS Index History for {top_sector} (Last 5 days):")
                    print(df_ths.tail(5).to_string(index=False))
                else:
                    print(f"No THS Index data found for {top_sector} (Name mismatch possible).")
            except Exception as e:
                print(f"Could not fetch THS data for verification: {e}")
            
    except:
        pass

if __name__ == "__main__":
    analyze_market()
