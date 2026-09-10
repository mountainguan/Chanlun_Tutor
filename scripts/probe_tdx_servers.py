"""并行探测 TDX 行情服务器：TCP 连通性 + 实际 K 线数据返回能力。

用法:
    .venv\\Scripts\\python.exe scripts\\probe_tdx_servers.py

输出:
    - 可用服务器列表（能返回 000001 和 881070 的 K 线）
    - 结果写入 data/tdx_server_probe.json
"""
import os
import sys
import json
import socket
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pytdx.config.hosts import hq_hosts  # noqa: E402


TCP_TIMEOUT = 3.0
API_TIMEOUT = 6.0

# 探测目标：大盘指数 + 行业板块（用户实际需要的）
PROBES = [
    # (label, category, market, code, use_index_bars)
    ('szzz_000001', 9, 0, '000001', False),   # 平安银行（个股）
    ('sh_000001', 9, 1, '000001', True),      # 上证指数
    ('tdx_881070', 9, 1, '881070', True),     # TDX 有色金属行业
]


def tcp_check(ip, port, timeout=TCP_TIMEOUT):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def probe_one(name, ip, port):
    """返回 dict: {name, ip, port, tcp, bars: {label: count}}"""
    result = {'name': name, 'ip': ip, 'port': port, 'tcp': False, 'bars': {}, 'error': None}
    if not tcp_check(ip, port):
        return result
    result['tcp'] = True

    try:
        from pytdx.hq import TdxHq_API
        api = TdxHq_API()
        ok = api.connect(ip, port, time_out=API_TIMEOUT)
        if not ok:
            result['error'] = 'connect returned falsy'
            return result
        try:
            for label, cat, mkt, code, use_index in PROBES:
                try:
                    if use_index:
                        data = api.get_index_bars(cat, mkt, code, 0, 10)
                    else:
                        data = api.get_security_bars(cat, mkt, code, 0, 10)
                    result['bars'][label] = len(data) if data else 0
                except Exception as e:
                    result['bars'][label] = f'err: {str(e)[:40]}'
        finally:
            try:
                api.disconnect()
            except Exception:
                pass
    except Exception as e:
        result['error'] = str(e)[:100]
    return result


def main():
    seen = set()
    targets = []
    for name, ip, port in hq_hosts:
        key = (ip, port)
        if key in seen:
            continue
        seen.add(key)
        targets.append((name, ip, port))

    print(f'探测 {len(targets)} 个 TDX 服务器（去重后）...')
    print(f'TCP 超时 {TCP_TIMEOUT}s / API 超时 {API_TIMEOUT}s\n')

    results = []
    with ThreadPoolExecutor(max_workers=32) as pool:
        futures = {pool.submit(probe_one, n, ip, p): (n, ip, p) for n, ip, p in targets}
        done = 0
        for fut in as_completed(futures):
            done += 1
            try:
                results.append(fut.result())
            except Exception as e:
                n, ip, p = futures[fut]
                results.append({'name': n, 'ip': ip, 'port': p, 'tcp': False,
                                'bars': {}, 'error': str(e)[:100]})
            if done % 20 == 0:
                print(f'  进度 {done}/{len(targets)}')

    # 分类
    tcp_ok = [r for r in results if r['tcp']]
    data_ok = []
    for r in tcp_ok:
        counts = [v for v in r['bars'].values() if isinstance(v, int)]
        if counts and any(c > 0 for c in counts):
            data_ok.append(r)

    print(f'\n=== TCP 可达: {len(tcp_ok)}/{len(results)} ===')
    print(f'=== 能返回 K 线数据: {len(data_ok)} ===\n')

    if data_ok:
        print('--- 可用服务器（按 881070 行业板块优先排序）---')
        data_ok.sort(key=lambda r: (
            -(r['bars'].get('tdx_881070', 0) if isinstance(r['bars'].get('tdx_881070', 0), int) else -1),
            -(r['bars'].get('sh_000001', 0) if isinstance(r['bars'].get('sh_000001', 0), int) else -1),
        ))
        for r in data_ok:
            bars = r['bars']
            print(f"  {r['ip']:>16}:{r['port']:<5} {r['name']:<18} "
                  f"881070={bars.get('tdx_881070')} sh000001={bars.get('sh_000001')} "
                  f"sz000001={bars.get('szzz_000001')}")
    else:
        print('!!! 没有服务器能返回 K 线数据 !!!')

    # TCP 通但无数据
    tcp_only = [r for r in tcp_ok if r not in data_ok]
    if tcp_only:
        print(f'\n--- TCP 通但无 K 线数据 ({len(tcp_only)}) ---')
        for r in tcp_only[:15]:
            print(f"  {r['ip']:>16}:{r['port']:<5} {r['name']:<18} bars={r['bars']}")

    tcp_fail = [r for r in results if not r['tcp']]
    print(f'\n--- TCP 不可达 ({len(tcp_fail)}) ---')
    for r in tcp_fail[:15]:
        print(f"  {r['ip']:>16}:{r['port']:<5} {r['name']}")

    # 写文件
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'tdx_server_probe.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'probed_at': datetime.datetime.now().isoformat(),
            'total': len(results),
            'tcp_ok': len(tcp_ok),
            'data_ok': [{'name': r['name'], 'ip': r['ip'], 'port': r['port'],
                         'bars': r['bars']} for r in data_ok],
            'all': results,
        }, f, ensure_ascii=False, indent=2)
    print(f'\n结果已写入: {out_path}')


if __name__ == '__main__':
    main()