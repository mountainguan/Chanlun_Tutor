import akshare as ak
import inspect

def check_stock_holder_number():
    interface_name = "stock_holder_number"
    print(f"Checking for interface: ak.{interface_name}")
    
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
        print(f"\nAttempting to call ak.{interface_name} with symbol='{symbol}'...")
        try:
            # First try with 'symbol' parameter if it seems appropriate or as positional
            # Based on akshare conventions, often it's symbol
            df = func(symbol=symbol)
            
            if df is not None and not df.empty:
                print("Call successful.")
                print("Columns:", df.columns.tolist())
                print("First row data:")
                print(df.iloc[0].to_dict())
            else:
                print("Call returned empty dataframe or None.")
        
        except TypeError as e:
            print(f"TypeError during call (maybe wrong params?): {e}")
            # Fallback: maybe it takes 'date' if not symbol? 
            # Or maybe no args?
            try:
                print("Retrying with date='20231231' just in case...")
                df = func(date="20231231")
                print("Call with date successful.")
                print("Columns:", df.columns.tolist())
            except Exception as e2:
                 print(f"Retry failed: {e2}")

        except Exception as e:
            print(f"Error during call: {e}")

    else:
        print(f"[FAILURE] ak.{interface_name} does NOT exist.")
        
        # Check for close matches
        print("\nChecking for similar names in akshare...")
        all_attrs = dir(ak)
        matches = [a for a in all_attrs if "stock_holder" in a or "gdhs" in a]
        print("Found similar interfaces:", matches)

        # Fallback check on stock_zh_a_gdhs if requested
        if "stock_zh_a_gdhs" in matches:
             print("\nChecking stock_zh_a_gdhs as alternative...")
             try:
                 func_alt = getattr(ak, "stock_zh_a_gdhs")
                 # This usually takes a date symbol like '20210331' for quarter end
                 # But let's check sig
                 print(f"Signature: {inspect.signature(func_alt)}")
                 
                 test_date = "20230930"
                 print(f"Calling stock_zh_a_gdhs(symbol='{test_date}')...")
                 df_alt = func_alt(symbol=test_date)
                 print("Columns:", df_alt.columns.tolist())
                 print("First row:", df_alt.head(1).to_dict(orient='records'))
             except Exception as e:
                 print(f"Error checking alternative: {e}")

if __name__ == "__main__":
    check_stock_holder_number()
