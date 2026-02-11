
import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'http://q.10jqka.com.cn/',
    'Host': 'q.10jqka.com.cn',
    'X-Requested-With': 'XMLHttpRequest'
}

def test_json_endpoint():
    code = '881121' # Semis
    # Note: field 199112 is usually price or something. Order desc.
    # We need to find the correct parameters. 
    # The browser usually sends: field=199112, order=desc, page=1, ajax=1, code=...
    url = f'http://q.10jqka.com.cn/thshy/detail/field/199112/order/desc/page/1/ajax/1/code/{code}'
    
    print(f"Fetching {url}...")
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {r.status_code}")
        # print(r.text[:500])
        
        # It usually returns HTML snippet inside JSON or plain HTML if not truly AJAX
        # Let's inspect content type
        print(f"Content-Type: {r.headers.get('Content-Type')}")
        
        # Try to parse as JSON
        try:
            data = r.json()
            print("Response is JSON.")
            # It might look like {status: 1, data: "<table>...</table>"}
            if isinstance(data, dict):
                print(f"Keys: {data.keys()}")
                if 'data' in data:
                    print(f"Data length: {len(data['data'])}")
                    print("Snippet:", data['data'][:100])
        except:
            print("Response is NOT JSON.")
            print(r.text[:200])

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_json_endpoint()
