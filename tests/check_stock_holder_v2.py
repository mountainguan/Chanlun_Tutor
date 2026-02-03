import akshare as ak
import inspect
import pandas as pd

def check_stock_holder_number():
    interface_name = "stock_holder_number"
    print(f"Checking for interface: ak.{interface_name}")
    
    if hasattr(ak, interface_name):
        func = getattr(ak, interface_name)
        print(f"[SUCCESS] ak.{interface_name} exists.")
    else:
        print(f"[FAILURE] ak.{interface_name} does NOT exist.")

def check_stock_gdhs_detail_em():
    interface_name = "stock_zh_a_gdhs_detail_em"
    print(f"\nChecking for interface: ak.{interface_name}")
    
    if hasattr(ak, interface_name):
        func = getattr(ak, interface_name)
        print(f"[SUCCESS] ak.{interface_name} exists.")
        
        # Check signature (parameters)
        try:
            sig = inspect.signature(func)
            print(f"Signature: {sig}")
        except Exception as e:
            print(f"Could not get signature: {e}")

        # Try to call it
        symbol = "600000"
        print(f"Calling ak.{interface_name}(symbol='{symbol}')...")
        try:
            df = func(symbol=symbol)
            if df is not None and not df.empty:
                print("Call successful.")
                print("Columns:", df.columns.tolist())
                print("First 2 rows:")
                # print a string representation
                print(df.head(2).to_string(index=False)) 
            else:
                print("Call returned empty dataframe or None.")
        
        except Exception as e:
            print(f"Error during call: {e}")

    else:
        print(f"[FAILURE] ak.{interface_name} does NOT exist.")

if __name__ == "__main__":
    check_stock_holder_number()
    check_stock_gdhs_detail_em()
