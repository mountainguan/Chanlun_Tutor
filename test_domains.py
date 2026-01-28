import requests

def test_domain(domain, path_prefix=""):
    report_name = "RPTA_RZRQ_LSHJ"
    url = f"https://{domain}{path_prefix}/api/data/v1/get"
    params = {
        "reportName": report_name,
        "columns": "ALL",
        "source": "WEB",
        "pageNumber": 1
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        print(f"Domain {domain}{path_prefix}: {response.status_code}")
        if response.status_code == 200:
            print(f"  Success: {response.json().get('success')}")
            # Try a failing report to see if behavior is same
            params["reportName"] = "RPTA_WEB_RZRQ_HY"
            r2 = requests.get(url, params=params, timeout=5)
            print(f"  Fail Check: {r2.json().get('message')}")
    except Exception as e:
        print(f"Domain {domain}{path_prefix} error: {e}")

test_domain("datacenter-web.eastmoney.com", "")
test_domain("datacenter.eastmoney.com", "")
test_domain("datacenter.eastmoney.com", "/securities")
