# -*- coding: utf-8 -*-
"""通达信（TDX）连接兼容层。

【背景】
2026-07 起，通达信行情服务端调整了握手协议。pytdx 的 ``TdxHq_API.setup()``
会依次发送三个握手包：

    SetupCmd1  0c 02 18 93 ...
    SetupCmd2  0c 02 18 94 ...
    SetupCmd3  0c 03 18 99 ...   <-- 旧版「认证包」

其中 **SetupCmd3 已被服务端拒绝**。服务端不会断开连接，而是把该连接的
后续所有 K 线请求（cmd ``0x052D``）统一降级为一个 2 字节空壳响应：

    响应头 zipsize=2 / unzipsize=2，响应体 = b'\\x20\\x03'  (0x0320 = 800)

pytdx 的 ``GetSecurityBarsCmd.parseResponse`` 会把 ``0x0320`` 误当作
「返回 800 根 K 线」，随后因没有实际数据而抛出::

    struct.error: unpack requires a buffer of 4 bytes

表现为「服务器失效」，但实际上**服务器完全正常**——其他接口
（get_security_list / get_minute_time_data / get_xdxr_info 等）不受影响，
这正是该问题难以定位的原因。

【修复】
握手只发送 SetupCmd1 + SetupCmd2，跳过 SetupCmd3。实测 10+ 个节点上
K 线数据立即恢复（0 根 → 30 根），其余接口行为完全不变。

【用法】
在本项目任何使用 pytdx 之前调用一次即可::

    from utils.tdx_compat import patch_tdx
    patch_tdx()
    from pytdx.hq import TdxHq_API
"""

import logging

logger = logging.getLogger(__name__)

_patched = False


def patch_tdx():
    """修正 pytdx 的 TDX 握手流程（跳过服务端已拒绝的 SetupCmd3）。

    幂等：重复调用只会生效一次。返回 True 表示补丁已生效。
    """
    global _patched
    if _patched:
        return True

    try:
        from pytdx.hq import TdxHq_API
        from pytdx.parser.setup_commands import SetupCmd1, SetupCmd2
    except Exception as e:  # pragma: no cover - pytdx 缺失
        logger.warning("patch_tdx: pytdx 不可用，跳过补丁 (%s)", e)
        return False

    def setup(self):
        # 只发送 SetupCmd1 / SetupCmd2。SetupCmd3（旧认证包）已被通达信
        # 服务端拒绝，发送后会导致后续 K 线请求恒返回 2 字节空壳响应。
        SetupCmd1(self.client).call_api()
        SetupCmd2(self.client).call_api()

    TdxHq_API.setup = setup
    _patched = True
    logger.info("patch_tdx: 已启用 TDX 握手兼容补丁（跳过 SetupCmd3）")
    return True


def unpatch_tdx():
    """恢复 pytdx 原始握手流程（主要用于测试）。"""
    global _patched
    if not _patched:
        return False
    try:
        from pytdx.hq import TdxHq_API
        from pytdx.parser.setup_commands import SetupCmd1, SetupCmd2, SetupCmd3

        def setup(self):
            SetupCmd1(self.client).call_api()
            SetupCmd2(self.client).call_api()
            SetupCmd3(self.client).call_api()

        TdxHq_API.setup = setup
    except Exception:
        pass
    _patched = False
    return True


def create_api():
    """创建已应用兼容补丁的 TdxHq_API 实例。"""
    patch_tdx()
    from pytdx.hq import TdxHq_API
    return TdxHq_API()


if __name__ == '__main__':
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    patch_tdx()
    api = create_api()
    if api.connect('117.34.114.15', 7709, time_out=6):
        try:
            bars = api.get_index_bars(9, 1, '881070', 0, 5)
            print('881070 K 线条数:', len(bars) if bars else 0)
            for b in (bars or [])[:3]:
                print(' ', b.get('datetime'), b.get('close'), b.get('amount'))
        finally:
            api.disconnect()
    else:
        print('连接失败')
