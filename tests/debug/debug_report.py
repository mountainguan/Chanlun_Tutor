import requests

def debug_report(report_name):
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": report_name,
        "columns": "ALL",
        "source": "WEB",
        "pageNumber": 1,
        "pageSize": 50
    }
    print(f"Testing {report_name}...")
    try:
        response = requests.get(url, params=params, timeout=5)
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text[:500]}")
    except Exception as e:
        print(f"Error: {e}")

debug_report("RPTA_WEB_RZRQ_HY")
debug_report("RPT_RZRQ_HY")
debug_report("RPTA_WEB_RZRQ_BK")
debug_report("RPTA_WEB_RZRQ_LSHJ")
debug_report("RPTA_WEB_RZRQ_GGMX") # Baseline success
