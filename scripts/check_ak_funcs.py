import akshare as ak
funcs = [f for f in dir(ak) if 'holder' in f]
print(funcs)

print("\n--- Testing stock_gdfx_free_top_10_em ---")
try:
    # Try different parameter combinations if needed
    df = ak.stock_gdfx_free_top_10_em(symbol="sh600036", date="20240930")
    print(df.head())
except Exception as e:
    print(f"sh600036 failed: {e}")
    try:
        df = ak.stock_gdfx_free_top_10_em(symbol="600036", date="20240930")
        print(df.head())
    except Exception as e:
        print(f"600036 failed: {e}")

print("\n--- Testing stock_main_stock_holder ---")
try:
    df = ak.stock_main_stock_holder(stock="600036") # Might return historical data
    print(df.head())
except Exception as e:
    print(f"stock_main_stock_holder failed: {e}")
