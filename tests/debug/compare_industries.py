
import akshare as ak
import pandas as pd

def compare_industries():
    print("Fetching THS Industries...")
    try:
        df_ths = ak.stock_board_industry_summary_ths()
        ths_names = set(df_ths['板块'].tolist()) if not df_ths.empty else set()
        print(f"THS Count: {len(ths_names)}")
    except Exception as e:
        print(f"THS Error: {e}")
        ths_names = set()

    print("Fetching EM Industries...")
    try:
        df_em = ak.stock_board_industry_name_em()
        em_names = set(df_em['板块名称'].tolist()) if not df_em.empty else set()
        print(f"EM Count: {len(em_names)}")
    except Exception as e:
        print(f"EM Error: {e}")
        em_names = set()

    # Compare
    common = ths_names.intersection(em_names)
    only_ths = ths_names - em_names
    only_em = em_names - ths_names
    
    print(f"\nCommon: {len(common)}")
    print(f"Only THS: {len(only_ths)}")
    print(f"Only EM: {len(only_em)}")
    
    print("\n--- Only in THS (Sample) ---")
    print(list(only_ths)[:10])
    
    print("\n--- Only in EM (Sample) ---")
    print(list(only_em)[:10])

if __name__ == "__main__":
    compare_industries()
