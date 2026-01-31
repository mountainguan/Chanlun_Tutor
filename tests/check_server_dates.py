from pytdx.hq import TdxHq_API
import pandas as pd

ips = [
    ('218.75.126.9', 7709),
    ('115.238.56.198', 7709)
]

code = '881070' 

for ip, port in ips:
    api = TdxHq_API()
    try:
        print(f"Connecting to {ip}...")
        if api.connect(ip, port, time_out=4):
            print(f"Connected to {ip}")

            # Try get_INDEX_bars
            try:
                print("  Trying get_INDEX_bars...")
                data = api.get_index_bars(9, 1, code, 0, 1)
                if data:
                    print("  Keys:", data[0].keys())
            except Exception as e:
                print(f"  get_index_bars fail: {e}")
            
            api.disconnect()
        else:
            print(f"Failed to connect to {ip}")
                
    except Exception as e:
        print(f"Server {ip} Error: {e}")
