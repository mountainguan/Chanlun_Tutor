import requests
import json
import time

def test_report_name(report_name, extra_params=None):
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": report_name,
        "columns": "ALL",
        "pageSize": 5,
        "pageNumber": 1,
        "sortColumns": "",
        "sortTypes": "",
        "source": "WEB",
        "client": "WEB",
    }
    if extra_params:
        params.update(extra_params)
    
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get("success") and data.get("result") and data["result"].get("data"):
                    first_item = data["result"]["data"][0]
                    keys = str(first_item.keys())
                    
                    # Log everything valid
                    # print(f"[VALID] Report: {report_name} - Keys: {keys}")

                    if ("HY" in report_name or "BK" in report_name) and \
                       ("RZYE" in keys or "RQYE" in keys or "RZRQYE" in keys):
                        print(f"[SUCCESS] Report: {report_name}")
                        print(f"Keys: {keys}")
                        print(f"Sample: {json.dumps(first_item, ensure_ascii=False)}")
                        return True
                    elif "RZYE" in keys: # Matches even if report name doesn't say HY/BK, to discover it
                        print(f"[POTENTIAL] Report: {report_name} - Keys: {keys}")
                        print(f"Sample: {json.dumps(first_item, ensure_ascii=False)}")
                        return True
                        
                else:
                     pass
            except json.JSONDecodeError:
                pass
        else:
            pass
    except Exception as e:
        print(f"Error testing {report_name}: {e}")
    
    return False

def main():
    # Expanded Candidates
    candidates = [
        "RPTA_WEB_RZRQ_HYMX", 
        "RPTA_WEB_RZRQ_HYTJ",
        
        # Commonly used for market-wide, maybe similar naming
        "RPTA_RZRQ_LSHJ",
        
        # Try standard known ones to verify
        "RPTA_WEB_RZRQ_GG", # Individual stock
    ]
    
    # Common prefixes/suffixes generator
    prefixes = ["RPTA_WEB_", "RPT_", "RPTA_", "WEB_", ""]
    base = ["RZRQ"]
    targets = ["HY", "BK", "INDUSTRY", "SW", "GN"]
    actions = ["", "MX", "TJ", "LSHJ", "LIST", "NEW"]
    
    for p in prefixes:
        for t in targets:
            for a in actions:
                # variations
                # RPTA_WEB_RZRQ_HY_MX
                c1 = f"{p}RZRQ_{t}_{a}" if a else f"{p}RZRQ_{t}"
                c2 = f"{p}RZRQ_{t}{a}"
                candidates.append(c1)
                candidates.append(c2)

    # Unique
    candidates = list(set(candidates))
    print(f"Testing {len(candidates)} potential report names...")
    
    found = []
    for report in candidates:
        if test_report_name(report):
            found.append(report)
        time.sleep(0.05) 

    print("\n--- Summary ---")
    if found:
        print(f"Found {len(found)} potential matching reports:")
        for f in found:
            print(f"- {f}")
    else:
        print("No matching industry margin data report found.")

if __name__ == "__main__":
    main()
