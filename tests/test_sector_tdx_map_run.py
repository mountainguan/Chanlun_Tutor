from utils.sector_sentiment import tdx_industry_map
from pytdx.hq import TdxHq_API
import json, os, time

ips = [
    ('60.191.117.167', 7709),
    ('119.147.212.81', 7709),
    ('119.147.212.80', 7709),
    ('124.71.187.100', 7709)
]
api = TdxHq_API()
connected = False
for ip, port in ips:
    try:
        if api.connect(ip, port, time_out=5):
            print('Connected to', ip)
            connected = True
            break
    except Exception as e:
        print('connect failed', ip, e)

if not connected:
    print('无法连接 TDX，退出')
    raise SystemExit(1)

results = {}
for code, name in tdx_industry_map.items():
    try:
        data = api.get_security_bars(9, 1, code, 0, 250)
        ok = bool(data)
        count = len(data) if data else 0
        last = data[-1]['datetime'] if data else ''
        results[code] = {'name': name, 'ok': ok, 'count': count, 'sample_date': last}
        print(code, name, 'ok=', ok, 'count=', count, 'last=', last)
        time.sleep(0.05)
    except Exception as e:
        print('error', code, name, e)
        results[code] = {'name': name, 'ok': False, 'error': str(e)}

api.disconnect()

out = os.path.join(os.path.dirname(__file__), 'data', 'tdx_industry_test_results.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print('写入', out)
