"""Test script to discover 同花顺 industry fund flow API - page 2 tests."""
import requests
import re
import time

session = requests.Session()
main_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

def parse_rows(text):
    rows_data = []
    all_rows = re.findall(r'<tr[^>]*>(.*?)</tr>', text, re.DOTALL)
    for row in all_rows:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(tds) >= 7:
            clean = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
            rows_data.append(clean)
    return rows_data

# Test page 2 approaches
page2_urls = {
    'page2_direct': 'https://data.10jqka.com.cn/funds/hyzjl/page/2/',
    'page2_field': 'https://data.10jqka.com.cn/funds/hyzjl/field/tradezdf/order/desc/page/2/',
    'page2_full': 'https://data.10jqka.com.cn/funds/hyzjl/field/tradezdf/order/desc/page/2/free/1/',
    '3日_page2': 'https://data.10jqka.com.cn/funds/hyzjl/board/3/field/tradezdf/order/desc/page/2/',
    '3日_page2_v2': 'https://data.10jqka.com.cn/funds/hyzjl/board/3/page/2/',
}

for name, url in page2_urls.items():
    time.sleep(0.5)
    try:
        resp = session.get(url, headers=main_headers, timeout=15)
        rows = parse_rows(resp.text)
        print(f"[{name}] Status: {resp.status_code}, Rows: {len(rows)}")
        if rows:
            print(f"  First: {rows[0]}")
        else:
            print(f"  Content[:200]: {resp.text[:200]}")
        print()
    except Exception as e:
        print(f"[{name}] Error: {e}\n")

# Also check total page info from the main page
print("=== Check pagination info ===")
resp = session.get('https://data.10jqka.com.cn/funds/hyzjl/', headers=main_headers, timeout=15)
# Look for page count info
page_info = re.findall(r'(\d+)/(\d+)', resp.text)
print(f"Page fractions found: {page_info[-5:]}")

# Find how many total industries
total_match = re.search(r'共\s*(\d+)\s*条', resp.text)
if total_match:
    print(f"Total records: {total_match.group(1)}")

# Look for pagination more carefully
pag_match = re.findall(r'1/(\d+)', resp.text)
print(f"1/N patterns: {pag_match}")



