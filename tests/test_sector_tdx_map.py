from pytdx.hq import TdxHq_API
import time

# 用户提供的映射表
tdx_industry_map = {
    "881070": "有色", "881006": "石油", "881001": "煤炭",
    "881090": "建材", "881061": "钢铁", "881150": "纺织服饰",
    "881015": "化工", "881337": "通信", "881417": "房地产",
    "881105": "农林牧渔", "881318": "电子", "881405": "建筑",
    "881469": "环保", "881458": "公共事业", "881393": "非银金融",
    "881199": "商贸", "881441": "交通运输", "881166": "轻工制造",
    "881129": "食品饮料", "881385": "银行", "881260": "电力设备",
    "881351": "计算机", "881292": "机械设备", "881211": "汽车",
    "881426": "社会服务", "881368": "传媒", "881183": "家电",
    "881230": "医药医疗", "881286": "国防军工", "881477": "综合",
}

# 通达信服务器候选IP
ips = [
    ('60.191.117.167', 7709),
    ('119.147.212.81', 7709),
    ('119.147.212.80', 7709),
    ('124.71.187.100', 7709),
]

api = TdxHq_API()
connected_ip = None
for ip, port in ips:
    try:
        if api.connect(ip, port, time_out=5):
            connected_ip = ip
            print('Connected to', ip)
            break
    except Exception as e:
        print('connect failed', ip, e)

if not connected_ip:
    print('无法连接通达信服务器，测试终止')
    raise SystemExit(1)

results = {}

for code, name in tdx_industry_map.items():
    try:
        # 获取最近 250 个交易日的日线
        data = api.get_security_bars(9, 1, code, 0, 250)
        ok = bool(data)
        count = len(data) if data else 0
        first = data[-1]['datetime'] if data else ''
        results[code] = {'name': name, 'ok': ok, 'count': count, 'sample_date': first}
        print(f"{code} {name}: ok={ok}, records={count}, last={first}")
        time.sleep(0.05)
    except Exception as e:
        print(f"{code} {name}: error {e}")
        results[code] = {'name': name, 'ok': False, 'error': str(e)}

api.disconnect()

# 保存结果到本地文件
import json, os
out = os.path.join(os.path.dirname(__file__), 'data', 'tdx_industry_test_results.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print('测试完成，结果已写入', out)
