
import requests
import pandas as pd
import time

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'http://q.10jqka.com.cn/',
    'Host': 'q.10jqka.com.cn'
}

def test_scrape_ths():
    # 1. Get Industry List (just to verify access)
    url_list = 'http://q.10jqka.com.cn/thshy/'
    print(f"Fetching {url_list}...")
    try:
        r = requests.get(url_list, headers=headers, timeout=10)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print("Successfully accessed THS Industry List page.")
            # We don't need to parse it if ak.stock_board_industry_summary_ths works.
            # We need to verify if we can access detail page.
        else:
            print("Failed to access main page.")
            return
    except Exception as e:
        print(f"Error: {e}")
        return

    # 2. Get Constituents for a specific industry (e.g., 881121 半导体)
    # The URL pattern usually involves the code.
    # Pattern: http://q.10jqka.com.cn/thshy/detail/code/881121/
    code = '881121'
    url_detail = f'http://q.10jqka.com.cn/thshy/detail/code/{code}/'
    print(f"\nFetching {url_detail}...")
    try:
        r = requests.get(url_detail, headers=headers, timeout=10)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print("Successfully accessed Detail page.")
            # Try to parse table
            # The data might be in a table with class="m-table m-pager-table"
            # It usually contains '代码', '名称', etc.
            try:
                dfs = pd.read_html(r.text)
                if dfs:
                    print(f"Found {len(dfs)} tables.")
                    print(dfs[0].head())
                else:
                    print("No tables found via read_html.")
            except Exception as e:
                print(f"Parse Error: {e}")
                # Print snippet
                print(r.text[:500])
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_scrape_ths()
