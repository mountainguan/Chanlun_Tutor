from utils.sector_sentiment import SectorSentiment

ss = SectorSentiment()
code = '880301'
print('Calling _fetch_sector_from_tdx for', code)
df = ss._fetch_sector_from_tdx(code, count=250)
if df is None:
    print('Returned None')
else:
    print('Rows:', len(df))
    print(df.head().to_string())
    print(df.tail().to_string())
