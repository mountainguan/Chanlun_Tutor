from utils.sector_sentiment import SectorSentiment

print("Initializing SectorSentiment...")
ss = SectorSentiment()

print("Connecting to TDX...")
if not ss._connect_tdx():
    print("Failed to connect!")
    exit(1)

try:
    sectors = ss.get_sector_list()
    print('Got sector list count:', len(sectors) if sectors else 0)
    # Print first 5
    for s in (sectors or [])[:5]:
        print(s)

    # Try fetching a sample known code
    sample = None
    # Prefer 881xxxx codes as they are in the map
    for s in sectors:
        if s['code'].startswith('881'):
            sample = s
            break
    
    if not sample and sectors:
         sample = sectors[0]

    if sample:
        print('Testing fetch for', sample)
        
        df = ss.fetch_sector_history_raw(sample['code'], sample['name'])
        if df is None:
            print('Fetch returned None')
        else:
            print('Fetch rows:', len(df))
            print(df.head().to_string())
            print(df.tail().to_string())
            
            # Verify we have recent data
            last_date = df.index[-1]
            print(f"Last date in data: {last_date}")

    else:
        print('No sample found in sector list')

finally:
    ss._disconnect_tdx()
    print("Disconnected.")

