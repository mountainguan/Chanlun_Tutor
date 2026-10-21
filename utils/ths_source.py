# -*- coding: utf-8 -*-
"""
同花顺(THS)数据源 —— 抗反爬 / 抗限流的健壮抓取层。

为什么需要这一层（相对直接调用 akshare）：

1. akshare 的每个 THS 接口都会 `py_mini_racer.MiniRacer()` 实例化一次 V8 引擎
   来生成 `v` 反爬 token。py_mini_racer 0.14 的 V8 隔离区在**多线程并发实例化**
   时会直接 abort 整个进程：
       [FATAL:partition_address_space.cc(243)] Check failed: !IsConfigurablePoolInitialized().
   而 akshare 的 `_get_stock_board_industry_name_ths()` 只用 `@lru_cache` 装饰，
   lru_cache **不会**串行化"未命中时的函数体执行"，因此两个线程同时 cache miss
   就会并发创建 MiniRacer → 进程崩溃。
   本模块用一个**进程级单例** MiniRacer + 一把锁生成 token，线程安全且只付一次成本。

2. akshare 按**列位置**重命名 THS 返回的表格。THS 的资金流接口在不同时间会
   返回两种列宽：
       即时 (hyzjl)          → 11 列
       N日排行 (board/N)     → 8 列
   CDN 偶发把两种表交叉投递时，akshare 会抛：
       ValueError: Length mismatch: Expected axis has 11 elements, new values have 8 elements
   本模块改为按**表头文本**映射列，天然免疫列宽变化。

3. akshare 在解析失败时抛 `'NoneType' object has no attribute 'text'`
   （`soup.find(...).text` 中 find 返回 None）。这个异常信息不透明，
   调用方只能靠字符串匹配猜测。本模块改为抛出语义明确的异常类型：
       ThsBlockedError —— 被反爬拦截 (HTTP 401/403/429 或 chameleon 挑战页)
       ThsHollowError  —— 拿到 200 但响应体是空壳（缺少 page_info 分页信息）

4. THS 的 `v` token 校验很严格：token 非法/过期/被篡改 → HTTP 401 + chameleon
   挑战页。本模块在收到 401 时自动刷新 token 并重试。

5. 行业名称→代码映射、板块指数历史都走免 token 的接口，可安全并发。
"""

import io
import json
import pathlib
import re
import threading
import time
from typing import Dict, List, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

__all__ = [
    "ThsSourceError",
    "ThsBlockedError",
    "ThsHollowError",
    "ThsSource",
    "get_ths_source",
]


# ──────────────────────────────────────────────────────────────────────
# 异常类型
# ──────────────────────────────────────────────────────────────────────
class ThsSourceError(Exception):
    """THS 抓取失败的基类。"""


class ThsBlockedError(ThsSourceError):
    """被 THS 反爬拦截（HTTP 401/403/429 或 chameleon 挑战页）。"""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class ThsHollowError(ThsSourceError):
    """拿到 HTTP 200，但响应体是空壳（缺少分页信息 / 表格为空）。"""


# ──────────────────────────────────────────────────────────────────────
# 反爬 token（进程级单例 MiniRacer，避免多线程崩溃）
# ──────────────────────────────────────────────────────────────────────
class _TokenFactory:
    """按需生成 THS 的 `v` / `hexin-v` 反爬 token。

    py_mini_racer 的 V8 隔离区不支持并发实例化，这里用一把全局锁把
    "创建引擎" 与 "调用 JS" 串行化，并且只创建一个引擎实例。
    """

    _lock = threading.Lock()
    _engine = None
    _js = None

    @classmethod
    def _ensure_engine(cls):
        if cls._engine is not None:
            return cls._engine
        with cls._lock:
            if cls._engine is None:
                import py_mini_racer  # 延迟导入，避免无 THS 场景的启动开销
                from akshare.datasets import get_ths_js

                js_path = get_ths_js("ths.js")
                js_src = pathlib.Path(js_path).read_text(encoding="utf-8")
                engine = py_mini_racer.MiniRacer()
                engine.eval(js_src)
                cls._js = js_src
                cls._engine = engine
        return cls._engine

    @classmethod
    def token(cls) -> str:
        """返回一个新的反爬 token（每次调用都会生成一个新的有效值）。"""
        engine = cls._ensure_engine()
        with cls._lock:
            return engine.call("v")


# ──────────────────────────────────────────────────────────────────────
# 表头工具
# ──────────────────────────────────────────────────────────────────────
def _norm_header(value) -> str:
    """归一化表头：去空白、去单位括号。

    注意 pandas 的 `read_html` 会把重名表头改写成 `xxx.1` / `xxx.2`。
    这类后缀由 `_pick_column` 负责识别（它能看到全部原始表头），
    这里只做单位括号与空白的清理。
    """
    text = str(value).strip()
    text = re.sub(r"[（(][^)）]*[)）]", "", text)
    return text.strip()


def _pick_column(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    """按表头文本挑列，返回**原始列名**或 None。

    - 先在未去重的表头上做精确匹配，再做包含匹配。
    - THS 的「涨跌幅(%)」在表格里会出现两次（板块涨跌幅 / 领涨股涨跌幅），
      pandas 会把第二个改写成 `涨跌幅(%).1`。这里必须取**第一次出现**的列，
      否则会拿到领涨股的涨跌幅，板块涨跌幅就错了。
    """
    raw_names = [str(c) for c in df.columns]
    raw_set = set(raw_names)

    def _base(name: str) -> str:
        """去掉 pandas 的重名后缀 `.1`（仅当去掉后与某个真实表头重名时）。"""
        match = re.match(r"^(.*)\.(\d+)$", name)
        if match and match.group(1) in raw_set:
            return name  # 是重名标记，保留以便区分
        return name

    # 第一轮：精确匹配（按原始顺序，取第一个命中）
    for candidate in candidates:
        for name in raw_names:
            if _norm_header(name) == candidate:
                return name
    # 第二轮：包含匹配（同样取第一个命中）
    for candidate in candidates:
        for name in raw_names:
            if candidate in _norm_header(name):
                return name
    return None


def _numeric(series: pd.Series) -> pd.Series:
    """把带 `%` / `亿` / 千分位的字符串列转成数值。"""
    if series is None:
        return pd.Series(dtype="float64")
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace("亿", "", regex=False)
        .str.replace("万", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce")


# ──────────────────────────────────────────────────────────────────────
# 主体
# ──────────────────────────────────────────────────────────────────────
class ThsSource:
    """同花顺行业板块数据源（线程安全，可并发使用）。"""

    SUMMARY_URL = (
        "http://q.10jqka.com.cn/thshy/index/field/199112/order/desc/page/{page}/ajax/1/"
    )
    FLOW_URL = (
        "http://data.10jqka.com.cn/funds/hyzjl/field/tradezdf/order/desc/page/{page}/ajax/1/free/1/"
    )
    FLOW_BOARD_URL = (
        "http://data.10jqka.com.cn/funds/hyzjl/board/{board}/field/tradezdf/"
        "order/desc/page/{page}/ajax/1/free/1/"
    )
    NAME_MAP_URL = "https://q.10jqka.com.cn/thshy/detail/code/881272/"
    LINE_URL = "https://d.10jqka.com.cn/v4/line/bk_{code}/01/{year}.js"

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # 板块(N日)排行 → THS board 参数
    BOARD_PERIODS = {"3日排行": 3, "5日排行": 5, "10日排行": 10, "20日排行": 20}

    def __init__(self, timeout: int = 20, min_interval: float = 0.6, max_retries: int = 3):
        self.timeout = timeout
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._last_request_ts = 0.0
        self._throttle_lock = threading.Lock()
        self._name_map: Optional[Dict[str, str]] = None
        self._name_map_lock = threading.Lock()
        self._token = None
        self._token_lock = threading.Lock()

    # ── 低层 HTTP ────────────────────────────────────────────────────
    def _throttle(self):
        """串行化请求并保证最小间隔，避免把 THS 打到限流。"""
        with self._throttle_lock:
            elapsed = time.time() - self._last_request_ts
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_request_ts = time.time()

    def _headers(self, *, need_token: bool, referer: str, extra: Optional[dict] = None) -> dict:
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html, */*; q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": referer,
        }
        if need_token:
            headers["Cookie"] = f"v={self._current_token()}"
        if extra:
            headers.update(extra)
        return headers

    def _current_token(self) -> str:
        with self._token_lock:
            if self._token is None:
                self._token = _TokenFactory.token()
            return self._token

    def _refresh_token(self):
        with self._token_lock:
            self._token = _TokenFactory.token()

    def _request(self, url: str, headers: dict, *, expect_json: bool = False) -> requests.Response:
        """发起一次请求，识别反爬挑战页并抛出明确异常。"""
        self._throttle()
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ThsSourceError(f"请求失败 {url}: {exc}") from exc

        if response.status_code in (401, 403, 429):
            raise ThsBlockedError(
                f"THS 反爬拦截 (HTTP {response.status_code})",
                status=response.status_code,
            )

        if expect_json:
            return response

        body = response.text
        # chameleon 挑战页的特征：HTTP 200 但正文极短，且带 chameleon 脚本。
        # 注意：正常的资金流页面也会内嵌 chameleon 脚本，所以必须同时要求
        # "正文很短" 才能判定为挑战页，避免误判正常响应。
        if "chameleon" in body.lower() and len(body) < 2000:
            raise ThsBlockedError("THS chameleon 反爬挑战页", status=response.status_code)
        return response

    def _fetch_pages(self, url_tpl: str, headers: dict) -> pd.DataFrame:
        """抓取分页表格并合并。任一页为空壳即抛 ThsHollowError。"""
        first = self._request(url_tpl.format(page=1), headers)
        page_count = self._parse_page_count(first.text)
        frames = [self._parse_table(first.text)]

        for page in range(2, page_count + 1):
            response = self._request(url_tpl.format(page=page), headers)
            frames.append(self._parse_table(response.text))

        if not frames:
            raise ThsHollowError("THS 返回空表格")
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def _parse_page_count(html_text: str) -> int:
        """从 `page_info` 里读总页数；缺失说明是空壳响应。"""
        soup = BeautifulSoup(html_text, "lxml")
        node = soup.find(name="span", attrs={"class": "page_info"})
        if node is None or not node.text:
            raise ThsHollowError("THS 响应缺少 page_info（空壳响应）")
        try:
            total = int(node.text.split("/")[1])
        except (IndexError, ValueError) as exc:
            raise ThsHollowError(f"THS page_info 解析失败: {node.text!r}") from exc
        return max(1, total)

    @staticmethod
    def _parse_table(html_text: str) -> pd.DataFrame:
        """解析 HTML 表格；没有有效表格即视为空壳。"""
        try:
            tables = pd.read_html(io.StringIO(html_text))
        except ValueError as exc:
            raise ThsHollowError(f"THS 表格解析失败: {exc}") from exc
        if not tables:
            raise ThsHollowError("THS 响应中没有表格")
        frame = tables[0]
        if frame.empty:
            raise ThsHollowError("THS 表格为空")
        return frame

    def _with_retry(self, operation, *args, **kwargs):
        """带重试的调用：被拦截时刷新 token 后重试，空壳时直接重试。"""
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return operation(*args, **kwargs)
            except ThsBlockedError as exc:
                last_error = exc
                self._refresh_token()
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 8))
            except ThsHollowError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(min(1.5 * attempt, 6))
            except ThsSourceError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 8))
        raise last_error if last_error else ThsSourceError("THS 请求失败")

    # ── 对外接口 ────────────────────────────────────────────────────
    def fetch_summary(self) -> pd.DataFrame:
        """同花顺行业一览表（板块 / 涨跌幅 / 总成交额 / 净流入 …）。"""
        headers = self._headers(need_token=True, referer="http://q.10jqka.com.cn/thshy/")
        raw = self._with_retry(self._fetch_pages, self.SUMMARY_URL, headers)

        result = pd.DataFrame()
        mapping = {
            "序号": ("序号",),
            "板块": ("板块", "行业"),
            "涨跌幅": ("涨跌幅",),
            "总成交量": ("总成交量",),
            "总成交额": ("总成交额",),
            "净流入": ("净流入",),
            "上涨家数": ("上涨家数",),
            "下跌家数": ("下跌家数",),
            "均价": ("均价",),
            "领涨股": ("领涨股",),
        }
        for target, candidates in mapping.items():
            column = _pick_column(raw, *candidates)
            result[target] = raw[column] if column is not None else None

        for column in ("涨跌幅", "总成交量", "总成交额", "净流入", "上涨家数", "下跌家数", "均价"):
            result[column] = _numeric(result[column]).fillna(0.0)
        return result

    def fetch_flow(self, symbol: str = "即时") -> pd.DataFrame:
        """行业资金流。symbol ∈ {即时, 3日排行, 5日排行, 10日排行, 20日排行}。"""
        board = self.BOARD_PERIODS.get(symbol)
        url_tpl = self.FLOW_BOARD_URL if board else self.FLOW_URL
        if board:
            url_tpl = url_tpl.replace("{board}", str(board))

        headers = self._headers(
            need_token=False,
            referer="http://data.10jqka.com.cn/funds/hyzjl/",
            extra={
                "Accept": "text/html, */*; q=0.01",
                "Accept-Encoding": "gzip, deflate",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Host": "data.10jqka.com.cn",
                "Pragma": "no-cache",
                "X-Requested-With": "XMLHttpRequest",
                "hexin-v": self._current_token(),
            },
        )
        raw = self._with_retry(self._fetch_pages, url_tpl, headers)

        result = pd.DataFrame()
        mapping = {
            "序号": ("序号",),
            "行业": ("行业", "板块"),
            "公司家数": ("公司家数",),
            "行业指数": ("行业指数",),
            "阶段涨跌幅": ("阶段涨跌幅",),
            "行业-涨跌幅": ("涨跌幅",),
            "流入资金": ("流入资金",),
            "流出资金": ("流出资金",),
            "净额": ("净额", "净流入"),
        }
        for target, candidates in mapping.items():
            column = _pick_column(raw, *candidates)
            result[target] = raw[column] if column is not None else None

        for column in ("阶段涨跌幅", "行业-涨跌幅", "流入资金", "流出资金", "净额", "行业指数"):
            result[column] = _numeric(result[column]).fillna(0.0)
        return result

    def industry_name_map(self, refresh: bool = False) -> Dict[str, str]:
        """行业名称 → THS 行业代码（免 token 接口，进程内缓存）。"""
        with self._name_map_lock:
            if self._name_map is not None and not refresh:
                return self._name_map

            def load():
                headers = self._headers(
                    need_token=False, referer="http://q.10jqka.com.cn/thshy/"
                )
                response = self._request(self.NAME_MAP_URL, headers)
                soup = BeautifulSoup(response.text, "lxml")
                container = soup.find(name="div", attrs={"class": "cate_inner"})
                if container is None:
                    raise ThsHollowError("THS 行业列表缺少 cate_inner 容器")
                mapping: Dict[str, str] = {}
                for anchor in container.find_all("a"):
                    match = re.search(r"/code/(\d+)", anchor.get("href", ""))
                    name = anchor.text.strip()
                    if match and name:
                        mapping[name] = match.group(1)
                if not mapping:
                    raise ThsHollowError("THS 行业列表为空")
                return mapping

            self._name_map = self._with_retry(load)
            return self._name_map

    def fetch_index_history(
        self, code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """板块指数日线（免 token 接口，可并发）。

        返回列：日期 / 开盘价 / 最高价 / 最低价 / 收盘价 / 成交量 / 成交额
        """
        headers = self._headers(
            need_token=False,
            referer="http://q.10jqka.com.cn",
            extra={"Host": "d.10jqka.com.cn"},
        )
        rows: List[List[str]] = []
        start_year = int(start_date[:4])
        end_year = int(end_date[:4])
        for year in range(start_year, end_year + 1):
            url = self.LINE_URL.format(code=code, year=year)
            response = self._request(url, headers)
            text = response.text
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end < 0:
                continue
            try:
                payload = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
            for line in payload.get("data", "").split(";"):
                if not line.strip():
                    continue
                fields = line.split(",")
                if len(fields) >= 7:
                    rows.append(fields[:7])

        if not rows:
            return pd.DataFrame(
                columns=["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "成交额"]
            )

        frame = pd.DataFrame(
            rows, columns=["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "成交额"]
        )
        frame = frame[(frame["日期"] >= start_date) & (frame["日期"] <= end_date)]
        frame = frame.reset_index(drop=True)
        for column in ("开盘价", "最高价", "最低价", "收盘价", "成交量", "成交额"):
            frame[column] = _numeric(frame[column])
        return frame


# ──────────────────────────────────────────────────────────────────────
# 进程级单例
# ──────────────────────────────────────────────────────────────────────
_SOURCE: Optional[ThsSource] = None
_SOURCE_LOCK = threading.Lock()


def get_ths_source() -> ThsSource:
    """返回进程级共享的 ThsSource 实例（保证 token / 名称映射只生成一次）。"""
    global _SOURCE
    if _SOURCE is not None:
        return _SOURCE
    with _SOURCE_LOCK:
        if _SOURCE is None:
            _SOURCE = ThsSource()
    return _SOURCE
