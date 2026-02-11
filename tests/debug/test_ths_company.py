
import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'http://basic.10jqka.com.cn/',
    'Host': 'basic.10jqka.com.cn'
}

def get_ths_industry_from_company(code):
    url = f'http://basic.10jqka.com.cn/{code}/company.html'
    print(f"Fetching {url}...")
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"Failed: {r.status_code}")
            return
        
        soup = BeautifulSoup(r.text, 'lxml')
        
        # Look for "所属行业"
        # Usually in a table with label
        target = soup.find(string=lambda t: t and '所属行业' in t)
        if target:
            print(f"Found keyword '所属行业' in: {target.parent.name}")
            # Usually target.parent is a <th> or <td class="name">
            # The value is in the next <td>
            
            # Example: <td class="name">所属行业：</td><td><span>银行 — 国有大型银行</span></td>
            
            parent = target.parent
            if parent.name in ['td', 'th', 'span', 'p', 'div']:
                # Try next sibling
                sibling = parent.find_next_sibling()
                if sibling:
                    print(f"Next Sibling: {sibling.text.strip()}")
                else:
                    # Maybe it's inside the same tag?
                    print(f"Content: {parent.text.strip()}")
        else:
            print("Keyword '所属行业' NOT found.")
            # print(r.text[:500]) # Debug

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_ths_industry_from_company('600000')
    get_ths_industry_from_company('300671')
