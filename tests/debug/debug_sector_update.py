
from utils.sector_sentiment import SectorSentiment
import logging
import time

logging.basicConfig(level=logging.INFO)

print("Starting debug...")
ss = SectorSentiment()
print("Connecting TDX...")
if not ss._connect_tdx():
    print("Cannot connect TDX")
else:
    print("TDX Connected")

print("Test connection stability...")
# Try a simple fetch
try:
    df = ss._fetch_sector_from_tdx('999999')
    print("Fetch SH index result:", len(df) if df is not None else "None")
except Exception as e:
    print(f"Fetch failed: {e}")

print("Calling update_data...")
try:
    data = ss.update_data()
    print(f"Update returned {len(data)} items")
except Exception as e:
    print(f"Update failed: {e}")
