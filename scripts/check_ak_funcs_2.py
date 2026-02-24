import akshare as ak
try:
    # Try stock_circulate_stock_holder (no arguments?)
    print("\n--- Testing stock_circulate_stock_holder ---")
    # Usually it takes no args or a date
    # Try getting docstring
    print(ak.stock_circulate_stock_holder.__doc__)
except Exception as e:
    print(f"Failed: {e}")
