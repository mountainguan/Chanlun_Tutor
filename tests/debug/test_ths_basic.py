
import requests
from bs4 import BeautifulSoup
import time

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'http://basic.10jqka.com.cn/',
    'Host': 'basic.10jqka.com.cn'
}

def get_ths_industry_from_basic(code):
    url = f'http://basic.10jqka.com.cn/{code}/'
    print(f"Fetching {url}...")
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"Failed: {r.status_code}")
            return None
        
        soup = BeautifulSoup(r.text, 'lxml') # or html.parser
        
        # Strategy 1: Look for "所属行业" or similar text
        # Usually in a table or dl/dt/dd structure
        # In THS basic page, it's often in "公司简介" or header
        
        # Let's print some text to debug location
        # print(soup.text[:1000])
        
        # Common pattern: <td class="...">所属行业：</td><td>...</td>
        # Or in the top header
        
        # Try to find specific element
        # Based on experience: .m_logo strong (Name), .m_logo .code (Code)
        # Industry might be in .content_jota (Detailed info)
        
        # Let's search for "所属行业"
        target = soup.find(string=lambda t: t and '所属行业' in t)
        if target:
            print(f"Found '所属行业': {target.parent.text.strip()}")
            # Try to get the next sibling or parent's content
            # e.g. <th>所属行业：</th><td><span>行业Name</span></td>
            
            # Let's try to find the value
            # Often: target is "所属行业："
            # Next element is the value
            
            # Print parent and next sibling
            print(f"Parent: {target.parent}")
            # print(f"Next: {target.parent.next_sibling}")
            
        else:
            print("Could not find '所属行业' text.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_ths_industry_from_basic('600000') # PF Bank
    get_ths_industry_from_basic('300671') # Semis
