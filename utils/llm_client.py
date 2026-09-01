"""MiniMax 国内版 Token Plan API 客户端

接入规范参考：https://platform.minimaxi.com/docs/token-plan/quickstart
              https://platform.minimaxi.com/docs/api-reference/text-chat-anthropic.md

要点：
    - Token Plan 走 Anthropic 兼容的 Messages API
    - 端点：POST {BASE_URL}/anthropic/v1/messages
    - 模型：MiniMax-M3（最新 Token Plan 推荐，多模态 + 长上下文 + thinking）
    - 鉴权：Authorization: Bearer <API_KEY>（也支持 x-api-key header）
    - 请求必填字段：model / messages / max_tokens
    - 响应 content 是数组，每个 block 是 {type, text/thinking/...}
    - 订阅 Key ≠ 按量计费 Key（两把 Key 不互通）

Token 加载顺序：
    1. 环境变量 MINIMAX_TOKEN
    2. 项目根目录 minimax_token.txt
    3. data/minimax_token.txt

如果三个位置都没有 token：
    - call_minimax_analyze() 抛 RuntimeError('MINIMAX_TOKEN_MISSING')
    - 上层 UI 应该捕获这个错误并提示用户配置 token。
"""

from __future__ import annotations

import os
import json
import asyncio
import datetime
from typing import Any

import httpx

# 默认 BASE_URL：参考 https://platform.minimaxi.com/docs/token-plan/quickstart
# 国内 Token Plan：https://api.minimaxi.com/anthropic
DEFAULT_BASE_URL = os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic")
MESSAGES_PATH = "/v1/messages"

# 默认模型：MiniMax-M3（最新 Token Plan 推荐，多模态 / Agentic SOTA / 1M 上下文）
# 也可以改成 MiniMax-M2.7 / MiniMax-M2.7-highspeed 等
DEFAULT_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M3")

# 默认超时 60 秒；Token Plan 偶有排队可能更久
HTTP_TIMEOUT = float(os.environ.get("MINIMAX_TIMEOUT", "60"))


def _load_token() -> str | None:
    """三段式加载 token。"""
    tok = os.environ.get("MINIMAX_TOKEN", "").strip()
    if tok:
        return tok
    # 项目根目录 + data/ 目录
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for p in (os.path.join(here, "minimax_token.txt"),
              os.path.join(here, "data", "minimax_token.txt")):
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    tok = f.read().strip()
                if tok:
                    return tok
            except Exception:
                pass
    return None


def _build_messages(payload: dict, system_prompt: str) -> list[dict]:
    """构造 Anthropic Messages API 的 messages 数组。

    Anthropic 格式：system 是顶层字段（不在 messages 里），messages 是 [user/assistant, ...]
    """
    user_text = (
        "请基于以下 JSON 数据，给出板块偏离分析与新问题建议：\n\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
    )
    return [
        {"role": "user", "content": user_text},
    ]


def _extract_text_from_response(data: Any) -> str:
    """从 Anthropic Messages 响应中提取纯文本。

    响应结构：
        {
          "content": [
            {"type": "thinking", "thinking": "...", "signature": "..."},
            {"type": "text",     "text":     "..."},
          ],
          ...
        }
    """
    if not isinstance(data, dict):
        raise ValueError(f"MiniMax 响应不是 JSON 对象: {str(data)[:200]}")
    content = data.get("content")
    if not isinstance(content, list) or not content:
        raise ValueError(f"MiniMax 响应 content 缺失或为空: {json.dumps(data)[:200]}")
    text_parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            t = block.get("text")
            if isinstance(t, str) and t:
                text_parts.append(t)
        # 跳过 thinking / tool_use 块；只取文本
    full_text = "".join(text_parts).strip()
    if not full_text:
        # 兼容：如果只有 thinking 块（M3 默认关闭 thinking，但用户可能开启）
        # 在这种情况下，把 thinking 当 fallback 文本返回
        think_parts = [
            block.get("thinking", "") for block in content
            if isinstance(block, dict) and block.get("type") == "thinking"
            and isinstance(block.get("thinking"), str)
        ]
        full_text = "\n".join(think_parts).strip()
    if not full_text:
        raise ValueError(f"MiniMax 响应未包含可读文本: {json.dumps(data)[:300]}")
    return full_text


async def call_minimax_analyze(payload: dict,
                                system_prompt: str,
                                *,
                                model: str | None = None,
                                max_tokens: int = 4096,
                                temperature: float = 1.0,
                                thinking: bool = False) -> str:
    """异步调用 MiniMax 国内版 Token Plan Messages API，返回报告文本。

    Args:
        payload: 喂给模型的用户数据（JSON）
        system_prompt: 系统提示词
        model: 模型名（默认 MiniMax-M3，可被 MINIMAX_MODEL 覆盖）
        max_tokens: 生成上限（必填；M3 推荐 131072 = 128K；这里默认 4K 已够分析）
        temperature: 温度系数（默认 1.0；[0, 2]）
        thinking: 是否启用 M3 thinking（默认 False）

    Returns:
        Markdown 报告字符串（来自响应 content[type=text] 块）

    Raises:
        RuntimeError('MINIMAX_TOKEN_MISSING')   — 没找到 token
        httpx.HTTPStatusError                   — 非 2xx 响应
        ValueError                              — 响应结构异常
    """
    token = _load_token()
    if not token:
        raise RuntimeError(
            "MINIMAX_TOKEN_MISSING：未配置 MiniMax Token。"
            "请在项目根目录 minimax_token.txt 写入 token，"
            "或设置环境变量 MINIMAX_TOKEN。"
            "Token Plan 的订阅 Key 与按量计费 API Key 不互通，请确认使用的是 Token Plan Key。"
        )

    model = model or DEFAULT_MODEL
    url = DEFAULT_BASE_URL.rstrip("/") + MESSAGES_PATH
    body: dict[str, Any] = {
        "model": model,
        "system": system_prompt,
        "messages": _build_messages(payload, system_prompt),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    # M3 支持 thinking 控制；显式传 disabled 比较稳
    if thinking:
        body["thinking"] = {"type": "adaptive"}
    else:
        body["thinking"] = {"type": "disabled"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        # Anthropic 兼容要求 x-api-key 也带上（如果只用 Bearer 也 OK）
        "x-api-key": token,
        "anthropic-version": "2023-06-01",
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(url, headers=headers, json=body)

    if resp.status_code >= 400:
        # 把错误体截断到 500 字以内，避免 UI 弹出巨长错误
        snippet = (resp.text or "")[:500]
        raise httpx.HTTPStatusError(
            f"MiniMax {resp.status_code}: {snippet}",
            request=resp.request,
            response=resp,
        )

    data: Any = resp.json()
    return _extract_text_from_response(data)


# ── 同步封装（方便非 asyncio 上下文使用，比如调试脚本） ───────────

def call_minimax_analyze_sync(payload: dict, system_prompt: str, **kwargs) -> str:
    return asyncio.run(call_minimax_analyze(payload, system_prompt, **kwargs))


if __name__ == "__main__":
    # 自检：探测 token 是否可用，返回 token 状态 + 端点信息
    tok = _load_token()
    print(f"token loaded: {bool(tok)}")
    if tok:
        print(f"token prefix: {tok[:8]}...  length: {len(tok)}")
    print(f"endpoint: {DEFAULT_BASE_URL.rstrip('/')}{MESSAGES_PATH}")
    print(f"model: {DEFAULT_MODEL}")
    print(f"timeout: {HTTP_TIMEOUT}s")
    print(f"server time: {datetime.datetime.now().isoformat(timespec='seconds')}")