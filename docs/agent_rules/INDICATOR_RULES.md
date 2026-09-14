# 缠论小应用 — 特殊指标业务规则手册

> **生成日期**: 2026-09-10
> **项目根目录**: `d:\缠论小应用`
> **文档定位**: 给后续 agent 使用的"事实基础"快照。所有阈值、公式、判定规则、缓存策略、容错逻辑均固化在本文档中。
> **核心约定**:
> - 所有时间统一为 **Asia/Shanghai（UTC+8）**。
> - 颜色遵循大 A 习惯：**红=涨 / 绿=跌**（红 = 流入，绿 = 流出）。
> - 所有阈值均为**业务硬编码常量**，未在配置文件中暴露；改动必须同步修改本文档。
> - 所有公式中的"亿元"在 UI 显示统一，存储可能用"元"或"千元"，**必须对齐单位**。

---

## 目录

### 第一部分：全局架构与共性规则
1. [项目定位与技术栈](#1-项目定位与技术栈)
2. [路由与页面入口](#2-路由与页面入口)
3. [A 股交易日判定（全局复用）](#3-a-股交易日判定全局复用)
4. [Tushare Pro Token 加载顺序](#4-tushare-pro-token-加载顺序)
5. [抗反爬限流框架](#5-抗反爬限流框架)
6. [缓存范式](#6-缓存范式)
7. [通用技术指标公式（缠论基础）](#7-通用技术指标公式缠论基础)

### 第二部分：量化指标模块
8. [市场温度（Market Sentiment）](#8-市场温度market-sentiment)
9. [板块拥挤度（Sector Crowding）](#9-板块拥挤度sector-crowding)
10. [成交集中度拥挤度（Trading Crowding）](#10-成交集中度拥挤度trading-crowding)
11. [板块情绪温度（Sector Sentiment）](#11-板块情绪温度sector-sentiment)
12. [板块网格（Sector Grid）](#12-板块网格sector-grid)
13. [资金流向日历（Fund Flow Calendar）](#13-资金流向日历fund-flow-calendar)
14. [量能龙头 Top 100（Volume Leaders）](#14-量能龙头-top-100volume-leaders)
15. [主力资金雷达（Fund Radar）](#15-主力资金雷达fund-radar)
16. [多日资金雷达（Multi-Day Radar）](#16-多日资金雷达multi-day-radar)

### 第三部分：主力资金与国家队
17. [社保 / 养老金 / 中央汇金](#17-社保--养老金--中央汇金)
18. [国家队股票筛选（National Team Selector）](#18-国家队股票筛选national-team-selector)

### 第四部分：基金与 ETF
19. [基金 / ETF 订阅跟踪（Fund Tracker）](#19-基金--etf-订阅跟踪fund-tracker)

### 第五部分：估值与公告
20. [指数成分股 PE 估值跟踪（PE Tracker）](#20-指数成分股-pe-估值跟踪pe-tracker)
21. [每日股市特殊公告栏（Special Announcement）](#21-每日股市特殊公告栏special-announcement)

### 第六部分：宏观与利率
22. [SHIBOR 利率（Shibor Data）](#22-shibor-利率shibor-data)
23. [宏观存款 / 市值比例（Macro Data）](#23-宏观存款--市值比例macro-data)

### 第七部分：个股资金与技术分析
24. [个股资金流向（Money Flow）](#24-个股资金流向money-flow)
25. [缠论买卖助手（Chanlun Assistant）](#25-缠论买卖助手chanlun-assistant)
26. [吞没形态（Engulfing Pattern）](#26-吞没形态engulfing-pattern)

### 第八部分：缠论教学与模拟
27. [缠论模拟器（Simulator Logic）](#27-缠论模拟器simulator-logic)
28. [K 线技术指标](#28-k-线技术指标)

### 第九部分：附录
29. [附录 A：8 象限归因阈值表](#29-附录-a8-象限归因阈值表)
30. [附录 B：分档颜色对照表](#30-附录-b分档颜色对照表)
31. [附录 C：缓存文件清单](#31-附录-c缓存文件清单)
32. [附录 D：常用 API 接口清单](#32-附录-d常用-api-接口清单)

---

# 第一部分：全局架构与共性规则

<a id="1-项目定位与技术栈"></a>
## 1. 项目定位与技术栈

### 1.1 业务定位
A 股量化分析仪表盘，分四大模块群：

| 模块群 | 路径 | 内容 |
|---|---|---|
| 缠论学习系统 | `/learn` | 10 章缠论教学 + 模拟交易训练器 |
| 市场情绪与资金 | `/mood` | 10+ 子面板：温度、拥挤度、资金流向、量能龙头、特殊公告、吞没形态、SHIBOR 等 |
| 主力持仓分析 | `/social-security` | 社保 / 养老金 / 中央汇金持仓 + 国家队筛选 |
| PE 估值跟踪 | `/pe-tracker` | 上证 50/180/380、科创 50 等 8 指数样本调整 PE 跟踪 |

### 1.2 技术栈
- **后端**: Python 3 + NiceGUI + FastAPI + Starlette(GZipMiddleware)
- **数据源**: Tushare Pro、Akshare（含反爬策略）、通达信（pytdx）、东方财富（HTTP）、新浪（HTTP）、金十数据（Jin10）、同花顺、华尔街见闻、中国货币网
- **可视化**: Plotly（散点/柱状/折线/热力）、ECharts（缠论 K 线：中枢、笔、MACD 金叉死叉）
- **缓存**: JSON / CSV / Pickle（派生缓存）
- **部署**: `zbpack.json` + `bash start.sh`

### 1.3 后台任务（`main.py:67-94`）
`run_background_tasks()`：每 60 秒检测一次，**仅在 A 股交易日盘中**（9:25-11:35 / 12:55-15:05）触发 `radar.get_data(today, mode='BACKGROUND_AUTO')`，自动节流并失败重试 5 分钟。

---

<a id="2-路由与页面入口"></a>
## 2. 路由与页面入口

| 路由 | 入口函数 | 渲染入口 | 数据源 |
|---|---|---|---|
| `/` | 4 张卡片导航 | — | — |
| `/learn` | `learn_page()` | `LearnState` + 各章节 | `utils/charts.py`, `utils/simulator_logic.py` |
| `/mood` | `market_sentiment_page.py` | `render_sentiment_view`（Tab 切换 8 个子面板） | 多模块 |
| `/social-security` | `social_security_demo.py` | `render_social_security_panel` | `utils/social_security_fund.py` |
| `/pe-tracker` | `pe_tracker_component.py` | `render_pe_tracker_panel` | `utils/pe_tracker.py` |

---

<a id="3-a-股交易日判定全局复用"></a>
## 3. A 股交易日判定（全局复用）

**文件**: `utils/fund_radar.py:32-43, 165-186`

### 3.1 HOLIDAYS_2026（硬编码 2026 年非周末休市日）
```python
HOLIDAYS_2026 = {
    (1, 1), (1, 2),                                       # 元旦
    (2, 16), (2, 17), (2, 18), (2, 19), (2, 20), (2, 23), # 春节
    (4, 6),                                                # 清明
    (5, 1), (5, 4), (5, 5),                                # 劳动节
    (6, 19),                                               # 端午
    (9, 25),                                               # 中秋
    (10, 1), (10, 2), (10, 5), (10, 6), (10, 7),           # 国庆
}
```

### 3.2 判定函数
- `is_trading_day(cn_dt)`：先排除周末（`weekday >= 5`），再排除 `HOLIDAYS_2026`。
- `is_trading_time(cn_dt)`：交易日 + 9:25-11:35（早盘含集合竞价缓冲）OR 12:55-15:05（午盘含收盘缓冲）。

**所有面板的"自动刷新"逻辑都使用以上判定。**

### 3.3 时区
所有时间统一为 **Asia/Shanghai（UTC+8）**。`cn_now = utc_now + timedelta(hours=8)`。

---

<a id="4-tushare-pro-token-加载顺序"></a>
## 4. Tushare Pro Token 加载顺序

**多个类通用，缺失时 RuntimeError**：
1. 环境变量 `TUSHARE_TOKEN`
2. 项目根目录 `tushare_token.txt`
3. `data/tushare_token.txt`

---

<a id="5-抗反爬限流框架"></a>
## 5. 抗反爬限流框架

### 5.1 THS / AKShare 节流（`utils/fund_radar.py:60-126` `FundRadar._rate_limited_call`）
- **类级别全局锁** + `_api_last_call_ts` 保证任意两次 API 调用间隔 ≥ `_api_min_interval = 1.5s`
- **随机抖动** `_API_JITTER_RANGE = (0.3, 1.0)` 防止指纹
- **自适应退避**：连续错误 ≥5 或命中 `'NoneType' object has no attribute 'text'`（东方财富反爬标志）/ `403/429/timeout` 等关键字时，按 5→10→20→40→80 秒（封顶 120 秒）指数退避 + 额外 1-3 秒抖动
- **失败重试**：最多 3 次，每次非反爬错误延迟 attempt×2 秒
- **类级别缓存**：
  - `_ths_flow_cache`：短时缓存（成功 10 分钟，失败 2 分钟）
  - `_ths_flow_blocked_until`：被反爬封禁时全局 skip 10 分钟
- **并发上限**：`_API_MAX_WORKERS = 2`（保守，THS 不友好）

### 5.2 Tushare 节流（`utils/fund_tracker.py:64-79`）
- `_API_RPM_LIMIT = 190` → `_api_min_interval ≈ 0.316s`
- 全局 `threading.Lock` 保证相邻调用间隔

### 5.3 反爬识别关键字
- `'NoneType' object has no attribute 'text'` → THS 返回 CAPTCHA
- `403 / 429 / too many / banned / timeout` → 触发退避

---

<a id="6-缓存范式"></a>
## 6. 缓存范式

### 6.1 JSON 缓存
- 含 `_meta.{last_updated, version, ttl_seconds}`，原子写 `tmp → os.replace`
- 例：`data/fund_radar_cache/sector_sina_YYYY-MM-DD.json`

### 6.2 CSV 缓存
- 3 年时间序列，历史数据首选；命名 `snake_case.csv`
- 例：`data/shibor_cache.csv`、`data/index_history_cache.csv`

### 6.3 Pickle 派生缓存
- `sector_crowding_derived.pkl`，键含 `(mtime_ns, size, schema_version, INDEX_LIST)`
- 自动随 CSV 更新重建（缓存键 hash 含文件 mtime）

### 6.4 进程级缓存
- 单例用 `cls._PROCESS_*_CACHE` 跨实例共享，避免 tab 切换时重复 IO/解析

### 6.5 批量磁盘缓存
- FundRadar 把 90 行业 × N 日历史聚合为**单文件** `hist_batch_<start>_<end>_<days>.json`（不是 90 个独立文件）

### 6.6 目录约定
- `data/<module>/`，子目录 `index_constituents_cache/`, `fund_tracker_cache/`, `sector_crowding/`, `trading_crowding/`
- `output/<theme>/{YYYY-MM-DD}.json + .md`

### 6.7 场外 OF 基金特殊约定
- **服务端永不抓、不落盘**（`utils/fund_tracker.py` 注释）
- 仅依赖浏览器端 `localStorage` + 同源代理 `/api/fund_eastmoney/{code}`
- `_fund_cache_path` 对 `.OF` 永远返回 `_never_written_of/*.csv`（不存在路径），保证不落盘

---

<a id="7-通用技术指标公式缠论基础"></a>
## 7. 通用技术指标公式（缠论基础）

**文件**: `utils/simulator_logic.py`

### 7.1 MACD
```python
EMA_fast = EMA(close, span=12)
EMA_slow = EMA(close, span=26)
DIF = EMA_fast - EMA_slow
DEA = EMA(DIF, span=9)
HIST = (DIF - DEA) * 2
```

### 7.2 RSI(14) — Wilder 平滑
```python
delta = close.diff()
up = delta.clip(lower=0)
down = -delta.clip(upper=0)
ma_up = up.ewm(com=period-1, adjust=False).mean()
ma_down = down.ewm(com=period-1, adjust=False).mean()
rs = ma_up / ma_down
rsi = 100 - 100 / (1 + rs)
```

### 7.3 布林线(20, 2σ)
```python
middle = close.rolling(20).mean()
std = close.rolling(20).std()
upper = middle + 2 * std
lower = middle - 2 * std
```

### 7.4 KDJ（通达信 SMA）
```python
rsv1 = ((close - llv9) / (hhv9 - llv9) * 100).fillna(0)
k1 = _tdx_sma(rsv1, 3, 1)
d1 = _tdx_sma(k1, 3, 1)
j1 = 3 * k1 - 2 * d1
```

### 7.5 缠论包含处理（`process_baohan`）
- **方向 up**（前一根方向向上）：取高高、低高（合并向上延伸）
- **方向 down**：取低低、高低（合并向下延伸）

### 7.6 缠论笔识别（`find_bi`）
- **顶分型**：中间 K 高点最高 → `top`
- **底分型**：中间 K 低点最低 → `bottom`
- 同类取高低更优者（更高顶 / 更低底）
- 异类间隔 ≥3 根 K 线（旧笔定义 `index diff >= 3`）

### 7.7 底背驰判定（`check_divergence`，lookback=30）
- **底背驰**：当前 K 线 < 前 lookback=30 内最低点 **AND** MACD 绿柱未创新低（`current_hist > min_hist_prev`）
- **顶背驰**：当前 K 线 > 前 lookback=30 内最高点 **AND** MACD 红柱未创新高（`current_hist < max_hist_prev`）

---

# 第二部分：量化指标模块

<a id="8-市场温度market-sentiment"></a>
## 8. 市场温度（Market Sentiment）

**文件**: [`utils/market_sentiment.py`](utils/market_sentiment.py) `class MarketSentiment`

### 8.1 数据源
- 沪深成交额：`push2his.eastmoney.com/api/qt/stock/kline/get`（主），备选 Sohu `q.stock.sohu.com/hisHq`、新浪 `quotes.sina.cn/.../getKLineData`、Sina Live `hq.sinajs.cn`
- 融资买入额：金十数据 `cdn.jin10.com/data_center/reports/fs_1.json`（沪）+ `fs_2.json`（深）

### 8.2 核心公式
```python
融资占比% = (融资买入额 / 成交额) * 100
温度 = [(融资占比% − 4.5) × 7.5] + [(成交额万亿 − 0.65) × 17]
```

### 8.3 估值分档
| 温度区间 | 状态 | 颜色 |
|---|---|---|
| > 80 | 高位/过热 | red |
| 20 ~ 80 | 震荡 | gray |
| < 20 | 低位/机会 | emerald |

### 8.4 单位约定
- 沪深成交额原始 API 返回**元** → ÷ 1e12 转**万亿**
- 融资买入额**元**
- 联立计算前务必对齐单位（代码有强制注释）

### 8.5 容错策略（核心兜底）
- **多源 fallback**：东财失败 → Sohu → Sina → Sina Live（仅当日）
- **融资缺失估算**：当日有成交额但缺融资时，**仅当 `cst_now >= 15:00` 或日期已过期**才允许用前一日比例估算，结果标记 `is_simulated=True`（前端显示警告）
- `fetch_log` 写入 `data/market_fetch_log.json`：3 个 checkpoint（9:10 / 11:30 / 15:30），不在 checkpoint 之后不重复抓
- **沪深两市融资数据使用 inner join**，缺一即整日丢弃（避免半额导致温度骤降）

---

<a id="9-板块拥挤度sector-crowding"></a>
## 9. 板块拥挤度（Sector Crowding）

**文件**: [`utils/sector_crowding.py`](utils/sector_crowding.py) `class SectorCrowding`

### 9.1 数据源（全部 Tushare Pro）
- `pro.margin_detail(trade_date)`：两融余额（rzye/rqye/rzrqye）
- `pro.daily_basic(trade_date)`：total_mv（单位**万元** → 内部换算**元**）
- `pro.stock_basic(list_status='L')`：industry（证监会行业）
- `pro.trade_cal(exchange='SSE')`：交易日历

### 9.2 核心公式
```python
行业拥挤度% = (rzrqye / total_mv) × 100
融资占比% = (rzye / total_mv) × 100
融券占比% = (rqye / total_mv) × 100
```

### 9.3 关键口径
- **行业总市值**：该行业全部 A 股（含非两融标的）
- **行业两融余额**：仅两融标的（`margin_stock_count`）
- 历史行业变动不追溯调整（当前 stock_basic 分类为准）

### 9.4 拥挤度档位（页面颜色）
| 拥挤度% | 等级 | 颜色 |
|---|---|---|
| ≥ 4 | 严重拥挤 | red-700 / red-50 |
| 3 ~ 4 | 高拥挤 | orange-700 / orange-50 |
| 2 ~ 3 | 偏高 | amber-700 / amber-50 |
| 1 ~ 2 | 正常 | gray-700 / gray-50 |
| < 1 | 低位 | emerald-700 / emerald-50 |

### 9.5 历史分位（`percentile_rank`）
```python
分位 = |{v ∈ series : v ≤ current}| / n × 100
```
样本不足 5 个返回 None。

### 9.6 两融涨跌速度（`compute_margin_speed`）
- **观察窗口**：3 / 5 / 10 / 15 / 20 个交易日
- **核心指标**：增量比 = `(rzrqye_T − rzrqye_{T-N}) / (total_mv_T − total_mv_{T-N})`
- 辅助：两融增速%、市值增速%、拥挤度变化 pp
- **升温/降温判定**：`crowding_chg ≥ +0.05pp` = 升温，`<= -0.05pp` = 降温；其余匹配（市值下行时符号可能翻转，直接用拥挤度方向更稳健）

### 9.7 指数板块拥挤度（`precompute_all_indices`）
- 覆盖 10 个指数/板块（`INDEX_LIST`）：上证、深证成指、沪深300、上证50、创业板指、科创50、科创板、中证500、中证1000、深证100
- 算法：先用 stock_basic 把成分股 ts_code 映射到证监会行业，按行业出现次数加权
- **指数拥挤度 = Σ(行业拥挤度 × 行业成分股数) / Σ(权重) × 100%**
- 派生缓存键 = `(history_csv.mtime_ns, size, DERIVED_SCHEMA_VERSION=4, INDEX_LIST)`，自动随 CSV 更新失效

### 9.8 证监会行业层级（`get_industry_hierarchy`）
- 优先 `data/sector_sentiment_cache_erji.json` 的同花顺一级分组 + `data/csrc_to_ths_l1.json` 映射
- 兜底 `csrc_static.py`（CSRC_L1_L2_MAP + STATIC_CSRC_TO_L1）
- 未映射的证监会行业归到"其他"一级
- 缓存 `data/csrc_industry_hierarchy.json`（`l1_to_l2`, `l2_to_l1`, `csrc_to_l1`）

### 9.9 容错
- 两融明细 T+1 发布：当天数据空属正常
- `refetch_recent_days = 2` 覆盖最近 2 日的潜在修订
- 末尾 `(trade_date, industry)` 去重（`keep='last'`），最后写入胜出
- `call_delay = 0.35s` 防限频

---

<a id="10-成交集中度拥挤度trading-crowding"></a>
## 10. 成交集中度拥挤度（Trading Crowding）

**文件**: [`utils/trading_crowding.py`](utils/trading_crowding.py) `class TradingCrowding`

### 10.1 数据源
- `pro.daily`：`vol`（手）/ `amount`（**千元**）
- `pro.stock_basic`：行业兜底（优先 `data/stock_industry_cache.json`）

### 10.2 核心公式
```python
前5%数量 = max(1, ceil(行业个股数 × 5%))
成交量集中度% = Σ(前5%个股 vol) / 行业总 vol × 100
成交额集中度% = Σ(前5%个股 amount) / 行业总 amount × 100
```
> 成交量维度按 vol 排序，成交额维度按 amount 排序，**两个维度独立统计**。

### 10.3 板块成交占比（行业板块区域主指标）
```python
板块成交占比% = 板块成交额(量) / 全A成交额(量) × 100
```
> 各板块占比之和恒为 100%（同股票宇宙）。

### 10.4 拥挤阈值
- **集中度 ≥ 45% 标记为"⚠ 拥挤"**（`THRESHOLD = 45.0`）
- 行业样本（个股数）< 10 时不参与拥挤标记（避免单只股 100% 假阳性），界面显示"样本少"

### 10.5 极端行情占比（`aggregate_extreme`）
- 涨幅榜 / 跌幅榜前 5% 个股成交额合计 ÷ 全 A 成交额
- 缓存 `trading_crowding_extreme_history.csv`

### 10.6 指数维度
复用 `SectorCrowding.INDEX_LIST` 与 `data/index_constituents_cache/` 缓存。无 `.json` 缓存时按 scope（SH/SZ/STAR/GEM）取全市场范围。

---


<a id="11-板块情绪温度sector-sentiment"></a>
## 11. 板块情绪温度（Sector Sentiment）

**文件**: [`utils/sector_sentiment.py`](utils/sector_sentiment.py) `class SectorSentiment`

### 11.1 数据源
- 通达信（pytdx）：5 个固定 IP 候选，按序重试，板块 880xxx/881xxx 通过 `get_index_bars(9, market=1/0, code, 0, count=500)`
- 东方财富（EM）：`RPTA_WEB_BKJYMXN`（板块列表）+ `RPTA_WEB_BKJYMX`（融资买入历史）
- 大盘基准：复用 `MarketSentiment._fetch_market_history`

### 11.2 TDX 板块代码映射（28 个一级板块）
```python
tdx_industry_map = {
    "881070":"有色", "881006":"石油", "881001":"煤炭", ... "881477":"综合"
}
```

### 11.3 行业层级
- 一级：`tdx_industry_map`（28 个）
- 二级：`data/tdx_industry_erji.csv`（含 `一级板块名称 / 二级板块名称 / 二级板块编码`）

### 11.4 核心公式
```python
sector_vol_ma20 = amount.rolling(20).mean()
sector_vol_ratio = amount / sector_vol_ma20

market_vol_ma20 = market_vol.rolling(20).mean()
market_vol_ratio = market_vol / market_vol_ma20

score_vol = (sector_vol_ratio / market_vol_ratio - 1) * 100
# 即：板块相对大盘的资金聚集程度

sector_margin_pct = sector_margin_buy / amount
market_margin_pct = market_margin_buy / market_vol
margin_spread = sector_margin_pct - market_margin_pct
score_margin = (margin_spread - margin_spread.rolling(60).mean()) * 1000
score_margin = clip(score_margin, -50, 50)

温度 = score_vol + score_margin
```

### 11.5 温度分档
| 温度区间 | 状态 | 提示 |
|---|---|---|
| > 100 | 过热 | 风险聚集 |
| -50 ~ -20 | 较冷 | 留意转机 |
| < -50 | 过冷 | 底部反弹 |

### 11.6 容错
- TDX 连接：3 次重试，每次 sleep 2s
- 板块融资缺失：**用前一日 ratio 估算当日**，标记 `is_simulated=True`
- 没有融资数据的板块 `score_margin = 0`（避免失真）
- 缓存每 5 个板块 flush 一次到 `data/sector_sentiment_cache.json`（含 latest + history，最后 180 日）
- 缓存 30 天刷新一次（`sector_list.json`）

### 11.7 TDX → EM 板块名映射（`manual_mapping`）
148 条手工映射，覆盖 TDX 一级行业到东方财富板块。

---

<a id="12-板块网格sector-grid"></a>
## 12. 板块网格（Sector Grid）

**文件**: [`utils/sector_grid_logic.py`](utils/sector_grid_logic.py)

### 12.1 数据源
读取 `data/fund_radar_cache/sector_sina_YYYY-MM-DD.json` 中每日缓存的 90 板块。

### 12.2 行业聚合分组（`SECTOR_MAPPING`，30 组）
- 例：`"机械设备"` → `["轨交设备", "专用设备", "工程机械", "通用设备", "自动化设备"]`
- `"石油"` → `["油气开采及服务", "石油加工贸易"]`
- 完整 30 个一级分类（石油/煤炭/化工/钢铁/有色/建材/建筑/房地产/机械设备/电力设备/国防军工/汽车/商贸/家电/纺织服饰/轻工制造/食品饮料/农林牧渔/医药医疗/美容护理/公共事业/交通运输/环保/银行/非银金融/电子/通信/计算机/传媒/社会服务/综合）

### 12.3 核心字段
- `change` = 涨跌幅
- `net_inflow` = 净流入（亿元）
- `turnover` = 总成交额（亿元）
- `ratio = (net_inflow / turnover) × 100`（流入强度）

### 12.4 格子 6 档状态
| ratio | 标签 | 颜色类（Tailwind） |
|---|---|---|
| > 8 | 超入 | `bg-red-600 text-white` |
| 3 ~ 8 | 强入 | `bg-red-400 text-white` |
| 0 ~ 3 | 弱入 | `bg-red-100 text-red-800` |
| -3 ~ 0 | 弱出 | `bg-green-100 text-green-800` |
| -8 ~ -3 | 强出 | `bg-green-400 text-white` |
| < -8 | 超出 | `bg-green-600 text-white` |

### 12.5 命名归一化（`normalize_sector_name`）
- 优先查 `NAME_ALIASES` 别名表
- 否则检查是否已在某 `SECTOR_MAPPING` 的 value 列表中
- 否则原样返回

---

<a id="13-资金流向日历fund-flow-calendar"></a>
## 13. 资金流向日历（Fund Flow Calendar）

**入口**: [`pages/fund_flow_calendar_component.py`](pages/fund_flow_calendar_component.py)

### 13.1 数据
从 `data/fund_radar_cache/sector_sina_*.json` 中每个板块 365 日历史，按 `ratio = 净流入 / 总成交额 × 100` 计算。

### 13.2 日历格子 6 档状态（`get_flow_status`）
| ratio | 标记 | 颜色 |
|---|---|---|
| > 8% | 超入 | `bg-rose-500` + glow |
| 3% ~ 8% | 强入 | `bg-rose-400` |
| 0% ~ 3% | 弱入 | `bg-rose-50` |
| -3% ~ 0% | 弱出 | `bg-emerald-50` |
| -8% ~ -3% | 强出 | `bg-emerald-500` |
| < -8% | 超出 | `bg-emerald-600` + glow |

> 玫瑰色 = 流入（红=涨 大 A），emerald = 流出（绿=跌 大 A）

### 13.3 度量切换
- ¥（绝对额 亿）/%（相对强度 ratio）

---

<a id="14-量能龙头-top-100volume-leaders"></a>
## 14. 量能龙头 Top 100（Volume Leaders）

**文件**: [`pages/volume_leaders_component.py`](pages/volume_leaders_component.py)

### 14.1 数据源
- THS `stock_fund_flow_individual(symbol="即时")`，按成交额排序前 100

### 14.2 指数成分股标注
每只股票标注属于哪些大指数（沪深 300、中证 500、中证 1000、创业板、科创 50、上证 50、深证 100）：
```python
INDEX_CODES = {
    '沪深300':'000300', '中证500':'000905', '中证1000':'000852',
    '创业板':'399006', '科创50':'000688', '上证50':'000016', '深证100':'399330',
}
```

### 14.3 缓存
- 指数成分股缓存：`data/index_constituents_cache/index_cons_<code>.json`
- 自动过滤：股票代码前缀 6/9/5/8/4 → `.SH`，其他 → `.SZ`；首位补 0（如 `2384 → 002384`）
- `update_index_constituents_cache()`：手动触发，一次性更新 7 个指数

### 14.4 计算字段
- `成交额亿`、`净流入亿`、`流入亿`、`流出亿`、`占总成交比`、`净流入占比`

---

<a id="15-主力资金雷达fund-radar"></a>
## 15. 主力资金雷达（Fund Radar）

**数据层**: [`utils/fund_radar.py`](utils/fund_radar.py) `class FundRadar`

### 15.1 数据源（按优先级）
- `stock_board_industry_summary_ths`（THS 板块概览，名字/涨跌幅/总成交额）
- `stock_fund_flow_industry(symbol="即时")`（THS 主力净流入，**唯一准确口径**）
- `stock_board_industry_index_ths(symbol=..., start_date, end_date)`（多日累计成交额）
- `stock_zh_index_spot_sina`（上证指数快照）

### 15.2 关键派生数据
- `df_sina`：旧接口残留（已统一为 THS，`sina_sectors` 字段在 `fetch_and_save` 写入时别名 `df_sina = df_ths`）
- `df_ths`：行业列表 `名称/涨跌幅/总成交额/净流入`，单位统一为 **亿元**（heuristic：>1e5 自动 ÷1e8）
- `market`：上证指数 `{change_pct, amount, price, name}`

### 15.3 8 象限归因（`analyze_flow_attribution`）
**强度定义**：`S = (净流入 / 总成交额) × 100%`

**基础阈值（1 日）**：
```python
BASE_S_HIGH = 2.0   # 强度 ±2% 分界
BASE_C_HIGH = 3.0   # 大涨 ±3%
BASE_C_MOD  = 1.0   # 中涨 ±1%
BASE_C_FLAT = 1.0   # 横盘 ±1%
```

**动态因子表**（按 days 缩放）：
| days | factor_c | factor_s |
|---|---|---|
| 1 | 1.0 | 1.0 |
| 3 | 1.8 | 0.9 |
| 5 | 2.5 | 0.8 |
| 10 | 3.5 | 0.7 |
| ≥20 | 5.0 | 0.6 |

**8 象限分类规则**（fund_radar.py L560-L600）见附录 A。

### 15.4 入场模式（`get_data` mode 参数）
- `READ_CACHE`：默认 UI 模式，只读缓存
- `FORCE_UPDATE`：忽略缓存强制刷新（仅当日有效）
- `BACKGROUND_AUTO`：若缓存 ≥30 分钟过期 + 在交易日盘中则触发；失败则 5 分钟重试（`_next_retry_time`）

### 15.5 攻击性 vs 防御性板块清单
- `offensive` = 53 个板块（半导体 / 软件 / 计算机 / 通信 / 高端制造 / 创新药 / 新能源车 / 商业航天 等）
- `defensive` = 64 个板块（银行 / 保险 / 公用事业 / 煤炭 / 食品饮料 / 中药 / 地产 / 环保 / 化纤 等）
- 完整列表见 `utils/fund_radar.py: get_offensive_defensive_list()`

### 15.6 单位换算陷阱
- `净流入 / 总成交额 / 涨跌幅`：Akshare 部分接口返回**元**，部分返回**亿**。`normalize_df` 用启发式：`abs.max > 100000` → 元 → 除以 1e8 转亿
- `净额` 字段在 EM 已是"亿"，但 THS `stock_fund_flow_industry` 部分返回元，统一 `>100000 → /1e8`

---

<a id="16-多日资金雷达multi-day-radar"></a>
## 16. 多日资金雷达（Multi-Day Radar）

### 16.1 多日聚合策略（`get_multi_day_data`）
- **3/5/10/20 日**：直接调 THS `stock_fund_flow_industry(N日排行)`（`_fetch_multi_day_ths_direct`）
- **任意日**：摘要+历史回填（`_fetch_multi_day_via_summary` / `_fetch_multi_day_history_direct`）
- **兜底**：本地日缓存聚合（`_get_multi_day_from_cache`），仅累积 `净流入/总成交额/涨跌幅`

### 16.2 统一起点（cache key 一致）
```python
buffer = 15  # 周末/节假日 buffer
start_dt = end_dt - timedelta(days=days + buffer)
```

### 16.3 板块历史批缓存
- 文件：`hist_batch_{start}_{end}_{days}.json`
- TTL：16h（内存）/ 24h（磁盘清理）
- 字段：`{sector_name: {turnover_yi, pct}}`

### 16.4 强入/强出标记位（资金流向日历）
| ratio 区间 | 标记 | 颜色 |
|---|---|---|
| ratio > 8% | 超入 | rose-500（深红） |
| 3% < ratio ≤ 8% | 强入 | rose-400 |
| 0% < ratio ≤ 3% | 弱入 | rose-50 |
| -3% ≤ ratio < 0% | 弱出 | emerald-50 |
| -8% ≤ ratio < -3% | 强出 | emerald-500 |
| ratio < -8% | 超出 | emerald-600（深绿） |

---

# 第三部分：主力资金与国家队

<a id="17-社保--养老金--中央汇金"></a>
## 17. 社保 / 养老金 / 中央汇金

**文件**: [`utils/social_security_fund.py`](utils/social_security_fund.py) `class SocialSecurityFund`

### 17.1 fund_type → AKShare symbol
| fund_type | symbol | 数据形态 |
|---|---|---|
| `social_security` | `社保持仓` | AKShare `stock_report_fund_hold` |
| `pension` | `基本养老保险` | **本地 Excel**（`data/yanglaojin/基本养老保险持股_<date>.xlsx`） |
| `huijin` | `中央汇金` | **本地 JSON**（`data/huijin/*.json`，脚本 `scripts/fetch_huijin_data.py`） |

### 17.2 核心字段
- 股票代码 / 股票简称 / 持股总数 / 持股市值（由代码 + 估算股价 15 元兜底）
- 持股变化（新进 / 增仓 / 减仓 / 不变 / 退出）
- 持股变动数值 / 持股变动比例

### 17.3 变动判定
- `get_new_positions()`：当季 `持股变化 == '新进'` 的股票
- `get_exited_positions()`：`prev_quarter_codes − current_codes`（pension/huijin 无历史 → 直接返回空）
- 比较季度：`_get_start_date_by_quarter_diff(base, quarters_back=1)`

### 17.4 缓存策略
- `*_fund_cache.json`：24h TTL，`{timestamp, date, data}`
- `*_changes_cache.json`：增量缓存 `exited` 数据（避免每次拉取前一季）
- **代码校正**：股票代码若不在 AKShare `stock_info_a_code_name()`，通过名称反查修正（新三板转板、合并重组）

### 17.5 UI 表格规则（pages/social_security_component.py）
- 变动类型颜色：增仓=红 / 减仓=绿 / 新进=橙 / 退出=灰斜体
- 导出 Excel：`持股市值(亿)/持股数量/变动类型/变动数值` 四列
- AG Grid 分页 50 条

---

<a id="18-国家队股票筛选national-team-selector"></a>
## 18. 国家队股票筛选（National Team Selector）

**文件**: [`utils/national_team.py`](utils/national_team.py) `class NationalTeamSelector`

### 18.1 联动策略
把社保 / 养老金 / 汇金持仓作为底库，叠加：
1. 行业映射（EM → 同花顺行业，EM_TO_THS_MAP + 模糊匹配 + 后缀剥离）
2. 行情（MA5/10/20 + RSI + 布林线）
3. **板块净流入**（来自 `FundRadar.get_multi_day_data`，默认 5 日）
4. **缠论近似建议**

### 18.2 同花顺行业映射（3 层 fallback）
1. `EM_TO_THS_MAP` 直查（如"医药制造" → "化学制药"）
2. 去除后缀（"XX行业" → "XX"）
3. 模糊包含（"半导体" ∈ "半导体材料"）
4. 都失败则保留 `*原名`

### 18.3 涨停支持（`THS_INDUSTRIES`，utils/national_team.py:11-21）
99 个同花顺行业白名单，用于代码缺失时按行业均值补全。

### 18.4 缠论近似建议算法（`get_selection`）
| 均线 + 布林 + RSI 组合 | 缠论提示 |
|---|---|
| 多头 + 超买 / 破上轨 | 顶背驰风险 |
| 多头 + 价格贴近 MA5（abs<2%） | 三买观察 |
| 多头 + 其他 | 强势延续 |
| 空头 + 超卖 / 破下轨 | 一买潜伏 |
| 空头 + 价格贴近 MA5 | 三卖风险 |
| 空头 + 其他 | 弱势寻底 |
| 震荡 + 中轨上 + 站上 MA5 | 二买观察 |
| 震荡 + 其他 | 中枢震荡 |

### 18.5 性能关键点
- 行业缓存 TTL 默认 **10 年**（`cache_ttl=3600×24×365×10`），永久缓存避免重复抓取
- 行情缓存 `data/stock_ma_cache.json` 同上
- 抓取并发 10 线程，超时 10s/只
- **隐式过滤**：如果行业未映射，保留该股票（不删除），避免接口故障导致列表为空

---

# 第四部分：基金与 ETF

<a id="19-基金--etf-订阅跟踪fund-tracker"></a>
## 19. 基金 / ETF 订阅跟踪（Fund Tracker）

**文件**: [`utils/fund_tracker.py`](utils/fund_tracker.py) `class FundTracker`

### 19.1 数据源
| 数据 | API | 备注 |
|---|---|---|
| 基金基础信息 | `pro.fund_basic(market='E'/'O', status='L')` | Tushare Pro |
| 场内 ETF 日线 | `pro.fund_daily(ts_code=, start_date=)` | Tushare Pro |
| 指数日线 | `pro.index_daily(ts_code=, start_date=)` | Tushare Pro |
| 场外 OF 净值 | 浏览器端 fetch `/api/fund_eastmoney/{code}` | 仅 localStorage，**服务端不抓** |
| 基金搜索回退 | `fundsuggest.eastmoney.com/FundSearch/api` | 字段 CODE/NAME/CATEGORYDESC/STOCKMARKET |
| 季末规模变动 | `fundf10.eastmoney.com/FundArchivesDatas.aspx` | `type=gmbd&code={code6}` |
| 真实净值历史 | `fund.eastmoney.com/pingzhongdata/{code6}.js` | `Data_netWorthTrend` + `Data_ACWorthTrend` |

### 19.2 4 大指数固定映射（`INDEX_DEFS`）
```python
INDEX_DEFS = [
    {'ts_code':'000001.SH','name':'上证指数',   'short':'上证',   'bar':'#ef4444','text':'text-rose-600'},
    {'ts_code':'399001.SZ','name':'深证成指',   'short':'深证',   'bar':'#f59e0b','text':'text-amber-600'},
    {'ts_code':'399006.SZ','name':'创业板指数', 'short':'创业板', 'bar':'#10b981','text':'text-emerald-600'},
    {'ts_code':'000688.SH','name':'科创50',     'short':'科创板', 'bar':'#3b82f6','text':'text-blue-600'},
]
```

### 19.3 涨跌幅周期（`PERIOD_DEFS`）
| key | label | days |
|---|---|---|
| 1d | 当日 | 1 |
| 5d | 近5 日 | 5 |
| 20d | 近 20 日 | 20 |
| 60d | 近 60 日 | 60 |
| ytd | 年内 | None（以今年首个交易日为基准） |

### 19.4 多周期涨跌幅（`_pct_n_from_df`）
```python
pct_n = (close[-1] - close[-(n+1)]) / close[-(n+1)] × 100%
```
要求 df 至少 `n+1` 行。

### 19.5 年内涨跌幅（`_pct_ytd_from_df`）
基准 = 今年首个交易日收盘价；当前 = 今年最新一日收盘价。

### 19.6 因子分解（季报口径）
```
期末净资产 ≈ 期末总份额 × 期末单位净值
净资产变动率 ≈ (1 + 份额变动率) × (1 + 净值变动率) − 1
净值变动率 = (1 + 净资产变动率) / (1 + 份额变动率) − 1
```

| 因子 | 字段 | 含义 |
|---|---|---|
| 散户因子 | `shares_chg`（ZFEBDL 字段） | 期末总份额相对上期末变化 % |
| 净值因子 | `nav_chg`（公式反推） | 剔除份额后，基金自身涨跌 % |
| 净资产 | `cap_chg`（CHANGE 字段） | 净资产变动率 %（EM 原始） |
| 真实净值涨跌率 | `real_nav_chg` | 用累计净值（含分红再投资）算出的季涨跌率 % |
| 单位净值涨跌率 | `real_unit_nav_chg` | 用单位净值算出的季涨跌率 % |
| 净申赎比例 | `net_flow_ratio = 最新一期净申赎 / 上期末份额 × 100%` | 散户行为指标 |

EM F10 接口字段：
- `FSRQ`：季度末日期
- `QJSG` / `QJSH`：期间申购/赎回（份）
- `QMZFE`：期末总份额（份）
- `QMJZC`：期末净资产（元）
- `ZFEBDL`：总份额变动率 %
- `CHANGE`：净资产变动率 %

### 19.7 偏离值告警规则（`DEVIATION_RULES`）
```python
DEVIATION_RULES = [
    {'key':'5d',  'trading_days':5,  'threshold':5.0,  'label':'近5日偏离 > 5%'},
    {'key':'10d', 'trading_days':10, 'threshold':15.0, 'label':'近10日偏离 > 15%'},
    {'key':'20d', 'trading_days':20, 'threshold':20.0, 'label':'近1月偏离 > 20%'},
]
```
判定：`abs(excess) >= threshold` → 命中。
严重度：命中 ≥2 条 → `high`，否则 `medium`。
方向：`excess < 0 → down`（跑输），`>0 → up`（跑赢）。

### 19.8 关键阈值
| 维度 | 阈值 | 说明 |
|---|---|---|
| 缓存最小天数 | `_CACHE_MIN_DAYS = 400` | 日历日窗口，约 280 交易日 |
| Tushare 节流 | `_API_RPM_LIMIT = 190` → `_api_min_interval ≈ 0.316s` | |
| 缓存 schema | `CACHE_SCHEMA_VERSION = 1` | 升级时 bump |
| 场内 ETF `.SH`/`.SZ` | 服务端抓 + 落盘 | `data/fund_tracker_cache/funds/{ts_code}.csv` |
| 场外 OF `.OF` | **服务端永不抓、不落盘** | 仅浏览器 `fund_overrides` 回传 |
| 搜索回退触发 | 6 位数字且 Tushare 模糊搜索无结果 | `_OTC_CODE_RE = r'^\d{6}$'` |
| EM 搜索内存缓存 | 类级 `_em_cache: dict[str, list[dict]]` | 同 keyword 仅打一次 |
| EM 净值日缓存 | `_nav_mem_cache`、`_gmbd_mem_cache` | 当日有效 |

### 19.9 6 位 → ts_code 映射（EM 搜索回退）
```python
def _em_code_to_ts_code(code, stock_market):
    prefix2 = code[:2]; prefix3 = code[:3]
    is_etf = prefix2 in ('51','56','58') or prefix3 in ('159','160','162','163','164','165','168','169','501','502')
    if is_etf:
        if prefix2 in ('51','56','58'): return f'{code}.SH'
        return f'{code}.SZ'
    return f'{code}.OF'
```

### 19.10 单位换算陷阱
- EM `pingzhongdata` 单位：`(date, nav)` → 单位净值；`(date, ac_nav)` → 累计净值（含分红再投资）
- EM `FundArchivesDatas`：份额/净资产**原始为元/份**，UI 端 `持股市值 / 1e8` 显示为"亿"
- 基金 `_fund_cache_path` 对 `.OF` 永远返回 `_never_written_of/*.csv`（不存在路径），保证不落盘
- 持有天数为日历时：`_fund_basic_cache.json` 仅当日有效（按 `date` 字段比对 `today`）

### 19.11 关键函数
- `get_fund_basic()` → 基础信息
- `search_funds(keyword, limit=30)` → 含两层回退
- `_fetch_fund_by_exact_code(code6)` → 精确代码回退
- `_search_eastmoney(keyword, limit)` → EM 搜索
- `_em_record_to_tushare(d)` → 字段映射
- `get_fund_scale_change(ts_code, force_refresh)` → 季报规模变动 + 因子分解
- `get_subs_scale_change(subs, force_refresh)` → 批量汇总
- `get_fund_history(ts_code, lookback_days)` → 服务端不抓 OF
- `get_subs_performance(subs, period_key, fund_overrides)` → 多周期表现
- `compute_multi_period_excess(subs, tracker, ...)` → 5d/10d/20d 超额
- `detect_deviation_alerts_v2(multi)` → 偏离告警
- `aggregate_by_tag(multi, tags_index)` → 标签聚合
- `build_llm_prompt_payload(...)` → LLM 输入 JSON

### 19.12 LLM Prompt 设计（基民视角红线）
- **相对收益**：excess = fund_pct − index_pct
- **禁止编造数据**：持仓 / 北向 / 换手率 / 风格指数具体走势 / 净值绝对数
- **建议语言**：持有 / 赎回 / 转换 / 观察（不是买 / 卖 / 加仓 / 止损）
- **样本厚度**：fund_count=1 时标注「样本极薄，仅供参考」
- **三层思考链**：事实层 → 因果层 → 建议层
- **判定歧义**：基准错配 vs 风格漂移

---

# 第五部分：估值与公告

<a id="20-指数成分股-pe-估值跟踪pe-tracker"></a>
## 20. 指数成分股 PE 估值跟踪（PE Tracker）

**文件**: [`utils/pe_tracker.py`](utils/pe_tracker.py) `class PETracker`

### 20.1 统一口径（声明在文件头）
- **动态 PE** = `pro.daily_basic.pe`（唯一判断口径）
- 静态 PE = `pe_ttm`（仅辅助参考）
- PB = `pb`
- 总市值单位**万元** → 渲染**元**
- 行业分类 = `stock_basic.industry`（**申万一级**）

### 20.2 核心字段
股票编码 / 股票名称 / 所属指数 / 调入调出 / 最新价 / 动态PE / 静态PE / PB / 总市值 / 所属板块 / 行业PE（市值加权）/ PE分位

### 20.3 PE 分位档位（替代旧 PE 溢价率口径）
| 分位% | 档位 | 颜色 |
|---|---|---|
| < 20% | 低估 | emerald（bg #dcfce7 / text #15803d） |
| 20% ~ 50% | 偏低 | blue（bg #dbeafe / text #1d4ed8） |
| 50% ~ 80% | 偏高 | amber（bg #fef3c7 / text #b45309） |
| ≥ 80% | 高估 | red（bg #fee2e2 / text #b91c1c） |

### 20.4 历史 PE 序列
- 由独立脚本 `scripts/build_sector_pe_history.py` 生成
- 缓存 `data/sector_pe_history_cache.json`（schema v2 强制 `pe_type='dynamic'`）
- 样本 < `MIN_HISTORY_SAMPLES=30` 时分位返回 None（前端显示 '—'）
- 缓存缺失时整体退回用 **绝对 PE 中位数**：

| PE 中位数 | 估值 |
|---|---|
| < 15 | 低估 |
| 15-30 | 合理 |
| 30-50 | 偏高 |
| ≥ 50 | 高估 |

### 20.5 指数样本名单
8 个指数（上证 50/180/380、科创 50、创业板、创业板 50、深证 100、深证成份），从 `data/指数样本调整名单.xlsx` 读取。

### 20.6 核心洞察文案规则
- 缓存缺失：`中位PE X.X倍` + `⚠️ 历史PE分位缓存未生成，请运行 python scripts/build_sector_pe_history.py`
- 有缓存：`中位分位 X%` + 低估/高估占比
- 调出 PE 高于调入 PE 5+ 倍："符合高估替换逻辑"
- 调出 PE 低于调入 PE 5+ 倍："指数调入更高估值标的"

### 20.7 Schema 版本管理
`SCHEMA_VERSION=2`（Tushare 时代）；切换数据源时 bump 让旧缓存自动失效。

---

<a id="21-每日股市特殊公告栏special-announcement"></a>
## 21. 每日股市特殊公告栏（Special Announcement）

**文件**: [`utils/special_announcement.py`](utils/special_announcement.py) `SpecialAnnouncementBoard`

### 21.1 数据源（Tushare Pro）
- `stk_shock`：交易所异常波动
- `stk_high_shock`：严重异常波动（10/30 日累计 ≥100%）
- `stk_holdertrade`：大股东增减持
- `top_list` / `limit_list_d` / `suspend_d` / `index_daily`（扩展接口）

### 21.2 精简抓取（`fetch_day_simple`）
- 异动窗口默认 5 天（`shock_window=5`）
- 增减持窗口默认 1 天（可变）
- `trade_window` 通过 `_resolve_trade_window` 按周一动动充上下边界

### 21.3 输出结构
```json
{
  "trade_date": "20260813",
  "summary": {
    "shock": 22, "high_shock": 2,
    "holder_total": 33, "holder_in": 2, "holder_de": 31,
    "significant": 1
  },
  "shock": [{"ts_code","name","market","reason","period"}],
  "high_shock": [...],
  "holder_in": [...], "holder_de": [...]
}
```

### 21.4 "显著"大额规则（在 `build_struct_data` 内）
增减持 **绝对比例 ≥5% 或 金额 ≥1 亿** 标记为 `significant`。

### 21.5 reason 短标签压缩（`_short_reason`）
- "有价格涨跌幅限制的日收盘价格涨幅偏离值达到" → "日涨幅偏离"
- "连续三个交易日内涨幅偏离值累计达到" → "3日涨幅偏离累计"
- "涨跌幅偏离值累计达" → "涨跌幅偏离累计"
- 共 30+ 条 replace 规则

### 21.6 输出目录
`output/每日股市特殊公告栏/{YYYY-MM-DD}.json + .md`

---

# 第六部分：宏观与利率

<a id="22-shibor-利率shibor-data"></a>
## 22. SHIBOR 利率（Shibor Data）

**文件**: [`utils/shibor_data.py`](utils/shibor_data.py)

### 22.1 数据源
| 数据 | API |
|---|---|
| SHIBOR 历史 | `POST https://www.chinamoney.com.cn/ags/ms/cm-u-bk-shibor/ShiborChrt?lang=CN` |

### 22.2 8 个品种期限
```python
SHIBOR_TERMS = {
    "O/N": "隔夜", "1W": "1周", "2W": "2周",
    "1M": "1个月", "3M": "3个月", "6M": "6个月",
    "9M": "9个月", "1Y": "1年",
}
```

### 22.3 CSV 列
`date, open, high, low, close, volume, O/N, 1W, 2W, 1M, 3M, 6M, 9M, 1Y`

> CSV 头 6 字段是 date/open/high/low/close/volume，从 index 6 开始才是利率

### 22.4 缓存策略
- 文件：`data/shibor_cache.csv`、`data/market_fetch_log.json`
- `last_shibor_fetch` 字段记录上次拉取时间
- **TTL：6 小时**（`< 6 * 3600s` 直接用缓存，否则重新拉取）

### 22.5 业务解读（UI 注释）
- O/N（隔夜）利率波动最大，反映短期资金面情绪
- 3M、1Y 反映中长期利率预期
- 利率**快速上行** = 资金面趋紧
- 利率**持续下行** = 流动性宽松

### 22.6 关键函数
- `fetch_from_api()` → 解析 csv 文本
- `get_shibor_data(force_refresh=False)` → 带 TTL 缓存
- `get_shibor_term(term='O/N', force_refresh=False)` → 取单个品种时间序列

---

<a id="23-宏观存款--市值比例macro-data"></a>
## 23. 宏观存款 / 市值比例（Macro Data）

**文件**: [`utils/macro_data.py`](utils/macro_data.py)

### 23.1 数据源
| 数据 | API | 备注 |
|---|---|---|
| 人民币存款 | `https://data.10jqka.com.cn/macro/rmb/` | 同花顺宏观；HTML 表格 |
| 上证指数 | 本地 `data/index_history_cache.csv` | 由 `IndexDataManager` 缓存 |

### 23.2 关键公式
```
SCALE_FACTOR = ANCHOR_MV / ANCHOR_INDEX
             = 922898.29 亿 / 4067.738 = 226.88
```
锚点：**2026-02-03** 上证指数 4067.7，A 股总市值 92.29 万亿元。

#### 23.2.1 月末 A 股市值估算
```python
est_mv = 月末上证指数收盘价 × SCALE_FACTOR
```

#### 23.2.2 存款 / 市值比例
```
总存款比例 = est_mv / 月新增总存款
企业存款比例 = est_mv / 月新增企业存款
储蓄存款比例 = est_mv / 月新增储蓄存款
```
> UI 显示为 `1:X` 形式（即 est_mv : 存款）

### 23.3 缓存策略
| 文件 | TTL | 备注 |
|---|---|---|
| `data/macro_rmb_deposit_cache.csv` | 24h | 同花顺月度数据，月度更新为主 |
| `data/macro_deposit_ratio_cache.csv` | 永久（手动） | 由 ratio 文件生成 |

### 23.4 字段
EM 原始列：`月份`, `新增存款(亿元)`, `新增企业存款(亿元)`, `新增储蓄存款(亿元)`
→ 缓存列：MultiIndex 拍平后变为 `月份`, `新增存款(亿元)_数量` 等（注意带后缀）

### 23.5 异常处理
- 网络失败 → fallback 读历史缓存
- HTML 多表格 → 遍历找含 `新增存款` 列的表
- MultiIndex 拍平：判断 col[0] 是否含 `月份` → `new` else `f"{c0}_{c1}"`

### 23.6 关键函数
- `fetch_rmb_deposit_data(force_update=False)` → 抓取原始数据
- `get_savings_mv_ratio_data(force_update=False)` → 计算比值

---

# 第七部分：个股资金与技术分析

<a id="24-个股资金流向money-flow"></a>
## 24. 个股资金流向（Money Flow）

**文件**: [`utils/money_flow.py`](utils/money_flow.py)

### 24.1 数据源
| 数据 | API |
|---|---|
| 个股资金流向（主力/小单/中单/大单/超大单） | EM `push2his.eastmoney.com/.../fflow/kline/get`（klt=101 日线） |
| 个股 K 线 | Sina `quotes.sina.cn/.../getKLineData`（首选）+ EM `push2his.eastmoney.com/.../kline/get` |
| 实时行情 | Sina `hq.sinajs.cn/list={prefix}{code}` |
| 个股基本信息 | 腾讯 `qt.gtimg.cn/q={prefix}{code}` |
| 股票代码-名称映射 | AKShare `stock_info_a_code_name()` |
| 股东户数 | EM `stock_zh_a_gdhs_detail_em` / AKShare `stock_zh_a_gdhs` |
| 5/15/30/60/120m 分钟 K 线 | EM `push2his.../kline/get` (klt=5/15/30/60) |

### 24.2 secid 推断规则
```python
def _em_code_to_ts_code(code, klt=101):
    c_str = str(code)
    if c_str.startswith(('6','9')): secid = f"1.{c_str}"   # 沪市
    elif c_str.startswith(('0','3')): secid = f"0.{c_str}" # 深市
    elif c_str.startswith(('8','4')): secid = f"0.{c_str}" # 北交所
    else: secid = f"0.{c_str}"
```

### 24.3 资金流向字段（EM fflow）
| field | 含义 |
|---|---|
| f51 | date |
| f52 | 主力净流入-净额 |
| f53 | 小单净流入-净额 |
| f54 | 中单净流入-净额 |
| f55 | 大单净流入-净额 |
| f56 | 超大单净流入-净额 |

### 24.4 缓存策略
- **无服务端持久化**（无 JSON / CSV）— 全内存 `lru_cache`
- `_fetch_em_fund_flow_direct` 100 条；`_fetch_akshare_data` 100 条；`_fetch_kline_hist` 300 条
- `_fetch_sina_quote` 每次都打（无缓存），超时 1.2s

### 24.5 120 分钟 K 线
```python
df.resample('120min', label='right', closed='right').agg({
    'open':'first', 'high':'max', 'low':'min',
    'close':'last', 'volume':'sum', 'amount':'sum',
})
```

### 24.6 实时补全
```python
fetch_sina_quote(symbol) → 解析 hq.sinajs.cn，返回 {date, open, close, high, low, volume, amount}
# 当日 close 差异 > 1e-8 → 覆盖 df
```

### 24.7 关键函数
- `get_kline_data(code, period='day', force_update=False)` → 统一 K 线入口
- `get_stock_info(code)` / `get_stock_name(code)` / `guess_market(code)`
- `_normalize_kline_df(df)` → 字段标准化

---

<a id="25-缠论买卖助手chanlun-assistant"></a>
## 25. 缠论买卖助手（Chanlun Assistant）

**文件**: [`utils/money_flow.py`](utils/money_flow.py)（与个股资金同模块）

### 25.1 趋势判定
| 指标 | 阈值 | 标签 |
|---|---|---|
| `trend_up = close[-1] > MA20 > MA60` | 多头趋势 |
| `trend_down = close[-1] < MA20 < MA60` | 空头趋势 |
| 否则 | 震荡整理 |

### 25.2 均线排列
| 条件 | 标签 |
|---|---|
| MA5 > MA10 > MA20 > MA60 | 多头排列 |
| MA5 < MA10 < MA20 < MA60 | 空头排列 |
| 其他 | 均线缠绕 |

### 25.3 短线倾向（基于 MACD 末端）
| DIF > DEA | DIF < DEA |
|---|---|
| 短线偏多 | 短线偏空 |

### 25.4 通达信买卖指标（`build_buy_sell_assistant`）
```python
ma60 = close.rolling(60, min_periods=1).mean()
qsup = ma60 > ma60.shift(1)              # 趋势线
qsx  = close.ewm(span=13, adjust=False).mean()  # 趋势线 EMA13
vup  = volume > (volume.rolling(20, min_periods=1).mean() * 1.5)  # 量能放大 1.5x
tpm  = (close > qsx) & (close.shift(1) <= qsx.shift(1)) & vup     # 买点
cdm  = (j1.shift(1) < 0) & (j1 > j1.shift(1)) & qsup              # KDJ J 拐点
glm  = (gll < -glv) & (close > low)                                # 乖离超卖
zhm  = tpm | cdm | glm                                              # 综合买点

pdm  = (qsx > close) & (qsx.shift(1) <= close.shift(1))            # 卖点
cbm  = (j1.shift(1) > 100) & (j1 < j1.shift(1)) & (~qsup)          # KDJ J 拐头
gls  = (gll > glv) & (close < high)                                # 乖离超买
zhs  = pdm | cbm | gls                                              # 综合卖点

ph = max(high-low, close*0.005)
buy_y  = low - ph*0.6
sell_y = high + ph*0.6
```

### 25.5 乖离阈值
```python
gll = (close - MA10) / MA10 * 100
avggl = abs(close - MA10) / MA10 * 100
glv   = avggl.rolling(60, min_periods=1).mean() * 2.5  # 乖离阈值 = 60 日均绝对乖离 × 2.5
```

### 25.6 成交量盘中日内还原
- 早盘 09:30-11:30（120 分钟）
- 午盘 13:00-15:00（120 分钟）
- 当前时刻已用分钟数 → 投影到 240 分钟
- `factor = min(240 / elapsed, 5.0)`（cap 5x）
- 仅修改 `volume.iloc[-1]`，不修改显示

---

<a id="26-吞没形态engulfing-pattern"></a>
## 26. 吞没形态（Engulfing Pattern）

**文件**: [`utils/engulfing_pattern.py`](utils/engulfing_pattern.py) `EngulfingPatternBoard`

### 26.1 7 大指数定义（`INDEX_DEFS`）
000001.SH 上证 / 399001.SZ 深证 / 399006.SZ 创业板 / 000300.SH 沪深 300 / 000688.SH 科创 50 / 000905.SH 中证 500 / 930050.CSI 中证 A50

### 26.2 数据缓存
复用 `data/fund_tracker_cache/custom_indexes/`（避免与 FundTracker 的 400 天裁剪冲突，本模块窗口 3 年）。

### 26.3 识别算法（`_detect_engulfing`）
**看涨吞没**（出现在下跌趋势末端）：
1. 前一日阴线（close < open）
2. 当日阳线（close > open）
3. 当日 open ≤ 前日 close（向下跳空/切入）
4. 当日 close ≥ 前日 open（完全吞没前日实体）
5. 当日实体 ≥ 前日实体（吞没力度）

**看跌吞没**：完全对称反向。

### 26.4 附加信号字段
- `body_ratio` = 当日实体 / 前日实体（>1 表示真吞没）
- `cover_ratio` = min(body_ratio, 2.0)（用于展示封顶）
- `streak_len`：当前所处的同向连续天数
- `note` 标记："强吞没（≥2x）" / "中度吞没（≥1.5x）" / "标准吞没" / "前续 N 日同向"

### 26.5 输出
`output/吞没形态/{YYYY-MM-DD}.json` 结构化存储 + 同时存 `{YYYY-MM-DD}.md` 可读版。

---

# 第八部分：缠论教学与模拟

<a id="27-缠论模拟器simulator-logic"></a>
## 27. 缠论模拟器（Simulator Logic）

**文件**: [`utils/simulator_logic.py`](utils/simulator_logic.py)

### 27.1 模拟 K 线生成（`generate_simulation_data`）
- 默认 length=300 根 K 线，initial_price=100
- **价格范围钳制**：1 ~ 1000；涨跌幅限制 ±10%
- **趋势因子**：每天抽取 `trend = np.random.normal(0, 0.005)`
- **周期类型分布**：
  - `short_strong` (3-5 日)：权重 0.30 — 强势整理周期
  - `short_std` (5-9 日)：权重 0.35 — 常见短线波段
  - `medium_fib` (13/21/34/55 ±2 日)：权重 0.25 — 斐波那契时间窗
  - `medium_month` (20-60 日)：权重 0.08 — 周线级别调整
  - `long` (60-100 日)：权重 0.02 — 长期

### 27.2 分型识别（`identify_fenxing`）
- **顶分型**：`k2.high > k1.high and k2.high > k3.high`
- **底分型**：`k2.low < k1.low and k2.low < k3.low`
- 输入至少 3 根 K 线

### 27.3 包含处理（`process_baohan`）
- 判断包含关系：`(prev.high >= curr.high and prev.low <= curr.low)` 或反之
- **方向 up**（前一根方向向上）：取高高、低高（合并向上延伸）
- **方向 down**：取低低、高低（合并向下延伸）
- date 取后一根的 date（logical time）

### 27.4 笔识别（`find_bi`）
1. 先识别所有分型
2. 同类取高低更优者（更高顶 / 更低底）
3. 异类间隔 ≥3 根 K 线（`index diff >= 3`，旧笔定义）

### 27.5 背驰判定（`check_divergence`，lookback=30）
**底背驰**：
- 条件 1：当前 K.low < 前 lookback=30 内 min(low)
- 条件 2：MACD 绿柱未创新低（`current_hist > min_hist_prev`）
- 视觉标记：K 线图连线（粗实线灰）+ 区间背景（淡红）+ MACD 连线（虚线灰）

**顶背驰**：
- 条件 1：当前 K.high > 前 lookback=30 内 max(high)
- 条件 2：MACD 红柱未创新高（`current_hist < max_hist_prev`）
- 视觉标记：K 线图连线（粗实线灰）+ 区间背景（淡绿）+ MACD 连线（虚线灰）

### 27.6 K 线重采样（`resample_klines`）
按固定周期分块（5=周K, 20=月K, 60=季K）：open=首, close=末, high=max, low=min

### 27.7 中枢识别（笔重叠部分，utils/simulator_logic.py L518-L760）
- 连续三笔重叠部分 → 形成中枢
- 升级逻辑：合并重叠/连续的中枢为大级别中枢
- 严格缠论中枢级别升级需要 9 段；本模块使用 2 个独立中枢波动区间重叠即可合并

### 27.8 用户操作评价（`evaluate_user_action`，L815-）
| 条件 | 评价 |
|---|---|
| 底背驰 + 底分型 | 🔥 **极佳操作（一买）**：背驰引发转折，精准捕捉第一类买点 |
| 上涨中枢上方 + 底分型 | ✅ **顺势操作（二买/三买）** |
| 空头中枢压制 + 底分型 | ⚠️ **中继风险（下跌中继）**：警惕形成第三类卖点 |
| 红柱加速伸长 + 买入 | ⚠️ **追涨风险**：小级别买在山顶 |
| 顶背驰 + 顶分型 | 顶背驰风险，卖出信号 |
| 中枢突破 + 量能放大 | 三买确认 |

### 27.9 关键函数
- `calculate_ema(values, span)`
- `calculate_macd(close, fast=12, slow=26, signal=9)`
- `calculate_rsi(prices, period=14)`
- `calculate_bollinger_bands(prices, period=20, num_std=2)`
- `generate_simulation_data(initial_price, length)`
- `identify_fenxing(klines)`
- `process_baohan(klines_data)`
- `find_bi(processed_klines)`
- `check_divergence(klines, macd_data, index, lookback=30)`
- `resample_klines(daily_data, period)`
- `calculate_chanlun_structures(klines)` → 中枢 + 笔
- `evaluate_user_action(klines, macd, index, action_type, action_price)`

---

<a id="28-k-线技术指标"></a>
## 28. K 线技术指标

### 28.1 KDJ（J 值）
```python
rsv1 = ((close - llv9) / (hhv9 - llv9) * 100).fillna(0)
k1 = _tdx_sma(rsv1, 3, 1)
d1 = _tdx_sma(k1, 3, 1)
j1 = 3 * k1 - 2 * d1
```
- J > 100 = 超买
- J < 0 = 超卖
- J 拐点（j1.shift(1) < 0 → j1 > j1.shift(1) + qsup）= 买点

### 28.2 MACD 信号
- **金叉**：DIF 上穿 DEA → 短线偏多
- **死叉**：DIF 下穿 DEA → 短线偏空
- **底背驰**：价格新低 + 绿柱未加深
- **顶背驰**：价格新高 + 红柱未增长

### 28.3 均线状态
| 条件 | 含义 |
|---|---|
| MA5 > MA10 > MA20 > MA60 | 多头排列 |
| MA5 < MA10 < MA20 < MA60 | 空头排列 |
| 价格贴近 MA5（abs<2%）| 短线博弈位 |
| 价格 > 布林上轨 | 超买 |
| 价格 < 布林下轨 | 超卖 |
| 价格在中轨附近 + RSI 中性 | 中枢震荡 |

---

# 第九部分：附录

<a id="29-附录-a8-象限归因阈值表"></a>
## 29. 附录 A：8 象限归因阈值表

### 29.1 基础阈值（1 日）
```python
BASE_S_HIGH = 2.0   # 强度 ±2% 分界
BASE_C_HIGH = 3.0   # 大涨 ±3%
BASE_C_MOD  = 1.0   # 中涨 ±1%
BASE_C_FLAT = 1.0   # 横盘 ±1%
```

### 29.2 动态因子（按 days 缩放）
| days | factor_c | factor_s | C_HIGH | C_MOD | S_HIGH |
|---|---|---|---|---|---|
| 1 | 1.0 | 1.0 | 3.0% | 1.0% | 2.0% |
| 3 | 1.8 | 0.9 | 5.4% | 1.8% | 1.8% |
| 5 | 2.5 | 0.8 | 7.5% | 2.5% | 1.6% |
| 10 | 3.5 | 0.7 | 10.5% | 3.5% | 1.4% |
| ≥20 | 5.0 | 0.6 | 15.0% | 5.0% | 1.2% |

### 29.3 8 象限分类（fund_radar.py L560-L600）
| 象限 | 主力强度 S | 涨跌幅 C | 中文标签 | code | color theme |
|---|---|---|---|---|---|
| 合力拉升 | S ≥ S_HIGH | C ≥ C_HIGH | 主力强流入 + 大涨 | `joint_push` | rose |
| 纯主力拉升 | S ≥ S_HIGH | C_MOD ≤ C < C_HIGH | 主力流入温和 | `pure_main_force` | indigo |
| 主力吸筹 | S ≥ S_HIGH | -C_FLAT ≤ C < C_FLAT | 横盘震荡吸筹 | `accumulation` | amber |
| 主力洗盘 | S ≥ S_HIGH | C < -C_FLAT | 主力吸筹下跌 | `shakeout` | violet |
| 合力砸盘 | S ≤ -S_HIGH | C ≤ -C_HIGH | 强流出 + 大跌 | `panic_selling` | emerald |
| 主力出货 | S ≤ -S_HIGH | -C_HIGH < C ≤ -C_MOD | 强流出 + 阴跌 | `inst_exit` | teal |
| 诱多（拉高出货） | S ≤ -S_HIGH | C ≥ C_MOD | 强流出 + 上涨 | `bull_trap` | orange |
| 散户扎堆 | -S_HIGH < S < S_HIGH | C ≥ C_HIGH | 无主力参与的大涨 | `retail_crowd` | lime |

---

<a id="30-附录-b分档颜色对照表"></a>
## 30. 附录 B：分档颜色对照表

### 30.1 大 A 颜色约定
- **红色**（rose/red）= **上涨 / 流入 / 主力买入 / 增仓**
- **绿色**（emerald/green）= **下跌 / 流出 / 主力卖出 / 减仓**

### 30.2 流入强度格子（板块网格 + 资金流向日历）
| ratio | label | color |
|---|---|---|
| > 8% | 超入 | bg-rose-500 / bg-red-600 |
| 3% ~ 8% | 强入 | bg-rose-400 / bg-red-400 |
| 0% ~ 3% | 弱入 | bg-rose-50 / bg-red-100 |
| -3% ~ 0% | 弱出 | bg-emerald-50 / bg-green-100 |
| -8% ~ -3% | 强出 | bg-emerald-500 / bg-green-400 |
| < -8% | 超出 | bg-emerald-600 / bg-green-600 |

### 30.3 市场温度分档
| 温度 | 状态 | color |
|---|---|---|
| > 80 | 高位/过热 | red |
| 20 ~ 80 | 震荡 | gray |
| < 20 | 低位/机会 | emerald |

### 30.4 拥挤度分档（板块拥挤度）
| 拥挤度% | 等级 | color |
|---|---|---|
| ≥ 4 | 严重拥挤 | red-700 / red-50 |
| 3 ~ 4 | 高拥挤 | orange-700 / orange-50 |
| 2 ~ 3 | 偏高 | amber-700 / amber-50 |
| 1 ~ 2 | 正常 | gray-700 / gray-50 |
| < 1 | 低位 | emerald-700 / emerald-50 |

### 30.5 PE 分位分档
| 分位% | 档位 | bg / text |
|---|---|---|
| < 20% | 低估 | #dcfce7 / #15803d |
| 20% ~ 50% | 偏低 | #dbeafe / #1d4ed8 |
| 50% ~ 80% | 偏高 | #fef3c7 / #b45309 |
| ≥ 80% | 高估 | #fee2e2 / #b91c1c |

### 30.6 板块情绪温度分档
| 温度 | 状态 | 提示 |
|---|---|---|
| > 100 | 过热 | 风险聚集 |
| -50 ~ -20 | 较冷 | 留意转机 |
| < -50 | 过冷 | 底部反弹 |

### 30.7 国家队变动类型颜色
| 变动类型 | 颜色 |
|---|---|
| 增仓 | 红 |
| 减仓 | 绿 |
| 新进 | 橙 |
| 退出 | 灰斜体 |

---

<a id="31-附录-c缓存文件清单"></a>
## 31. 附录 C：缓存文件清单

### 31.1 根 data/ 目录
| 文件 | TTL | 模块 |
|---|---|---|
| `index_history_cache.csv` | 永久 | index_data |
| `shibor_cache.csv` | 6h | shibor_data |
| `macro_rmb_deposit_cache.csv` | 24h | macro_data |
| `macro_deposit_ratio_cache.csv` | 永久 | macro_data |
| `market_sentiment_cache.csv` | 永久 | market_sentiment |
| `market_fetch_log.json` | 永久 | market_sentiment |
| `sector_sentiment_cache.json` | 永久 | sector_sentiment |
| `sector_sentiment_cache_erji.json` | 30 天 | sector_sentiment |
| `sector_list.json` | 30 天 | sector_sentiment |
| `pe_sector_cache.json` | 永久 | pe_tracker |
| `pe_tracker_cache.json` | 永久 | pe_tracker |
| `sector_pe_history_cache.json` | 永久 | pe_tracker |
| `national_team_meta.json` | 永久 | national_team |
| `stock_industry_cache.json` | 永久 | national_team |
| `stock_industry_map.json` | 永久 | national_team |
| `stock_ma_cache.json` | 10 年 | national_team |
| `tdx_industry_erji.csv` | 永久 | sector_sentiment |
| `tdx_industry_test_results.json` | 永久 | sector_sentiment |
| `huijin_fund_cache.json` | 24h | social_security |
| `pension_fund_cache.json` | 24h | social_security |
| `social_security_fund_cache.json` | 24h | social_security |
| `social_security_changes_cache.json` | 增量 | social_security |
| `csrc_industry_hierarchy.json` | 永久 | sector_crowding |
| `csrc_to_ths_l1.json` | 永久 | sector_crowding |
| `tushare_token.txt` | 配置 | — |

### 31.2 data/ 子目录
| 子目录 | 内容 |
|---|---|
| `fund_radar_cache/` | sector_sina_*.json、hist_batch_*.json、volume_leaders_*.csv |
| `fund_tracker_cache/indexes/` | 4 大指数日线 CSV |
| `fund_tracker_cache/custom_indexes/` | 自定义指数日线 CSV |
| `fund_filter_cache/` | 基金筛选结果 |
| `huijin/` | 中央汇金 JSON |
| `index_constituents_cache/` | index_cons_<code>.json |
| `sector_crowding/` | 派生 pickle (sector_crowding_derived.pkl) |
| `sector_history_cache/` | 板块历史 |
| `shebaojijin/` | 社保 |
| `special_announcements/` | 特殊公告 |
| `trading_crowding/` | 极端行情占比 |
| `volume_leaders_cache/` | 量能龙头 |
| `yanglaojin/` | 基本养老保险持股_<date>.xlsx |

### 31.3 output/ 目录
| 子目录 | 内容 |
|---|---|
| `每日股市特殊公告栏/` | YYYY-MM-DD.json + .md |
| `吞没形态/` | YYYY-MM-DD.json + .md |

---

<a id="32-附录-d常用-api-接口清单"></a>
## 32. 附录 D：常用 API 接口清单

### 32.1 Tushare Pro
| 接口 | 用途 | 模块 |
|---|---|---|
| `pro.fund_basic` | 基金基础信息 | fund_tracker |
| `pro.fund_daily` | 场内 ETF 日线 | fund_tracker |
| `pro.index_daily` | 指数日线 | fund_tracker, sector_crowding |
| `pro.daily` | 个股日线（含 amount 单位千元） | trading_crowding |
| `pro.daily_basic` | 个股每日指标（PE/PB/total_mv） | sector_crowding, pe_tracker |
| `pro.stock_basic` | 股票基础（industry） | sector_crowding, pe_tracker |
| `pro.margin_detail` | 两融明细（T+1 发布） | sector_crowding |
| `pro.trade_cal` | 交易日历 | sector_crowding |
| `pro.stk_shock` | 交易所异常波动 | special_announcement |
| `pro.stk_high_shock` | 严重异常波动 | special_announcement |
| `pro.stk_holdertrade` | 大股东增减持 | special_announcement |
| `pro.top_list` | 龙虎榜 | special_announcement |
| `pro.limit_list_d` | 涨跌停 | special_announcement |
| `pro.suspend_d` | 停复牌 | special_announcement |

### 32.2 AKShare（THS / EM / Sina）
| 接口 | 用途 | 模块 |
|---|---|---|
| `stock_board_industry_summary_ths` | THS 板块概览 | fund_radar |
| `stock_fund_flow_industry` | THS 板块资金流（"即时"/"N日排行"） | fund_radar |
| `stock_board_industry_index_ths` | THS 板块指数多日 | fund_radar |
| `stock_zh_index_spot_sina` | 上证指数快照 | fund_radar |
| `stock_fund_flow_individual` | THS 个股资金流 | fund_radar (volume leaders) |
| `index_stock_cons` | 指数成分股 | fund_radar |
| `stock_report_fund_hold` | 社保持仓 | social_security |
| `stock_info_a_code_name` | 股票代码-名称 | social_security |
| `stock_zh_a_gdhs` | 股东户数 | money_flow |

### 32.3 HTTP（东方财富 / 新浪 / 腾讯 / 金十 / 同花顺 / 中国货币网）
| URL | 用途 |
|---|---|
| `push2his.eastmoney.com/api/qt/stock/kline/get` | EM 个股 K 线 |
| `push2his.eastmoney.com/.../fflow/kline/get` | EM 个股资金流 |
| `stock_zh_a_gdhs_detail_em` | EM 股东户数详情 |
| `q.stock.sohu.com/hisHq` | Sohu 个股 K 线（备用） |
| `quotes.sina.cn/.../getKLineData` | 新浪 K 线（首选） |
| `hq.sinajs.cn/list={prefix}{code}` | 新浪实时 |
| `qt.gtimg.cn/q={prefix}{code}` | 腾讯个股信息 |
| `cdn.jin10.com/data_center/reports/fs_1.json` | 金十沪融资 |
| `cdn.jin10.com/data_center/reports/fs_2.json` | 金十深融资 |
| `data.10jqka.com.cn/macro/rmb/` | 同花顺宏观人民币存款 |
| `RPTA_WEB_BKJYMXN` | EM 板块列表 |
| `RPTA_WEB_BKJYMX` | EM 板块融资历史 |
| `https://www.chinamoney.com.cn/ags/ms/cm-u-bk-shibor/ShiborChrt?lang=CN` | 中国货币网 SHIBOR |
| `fundsuggest.eastmoney.com/FundSearch/api` | 天天基金搜索 |
| `fund.eastmoney.com/pingzhongdata/{code6}.js` | 天天基金净值历史 |
| `fundf10.eastmoney.com/FundArchivesDatas.aspx?type=gmbd&code={code6}` | 天天基金规模变动 |

### 32.4 通达信（pytdx）
| 函数 | 用途 |
|---|---|
| `get_index_bars(9, market, code, 0, count=500)` | 板块 880xxx/881xxx K 线 |
| 5 个固定 IP 候选 | 按序重试 |

---

# 文档结束

> **最后更新**: 2026-09-10
> **下次更新触发条件**:
> 1. 任何 utils/ 模块的阈值常量变更
> 2. 新增/移除页面或数据源
> 3. HOLIDAYS_2026 跨年时（需重命名并扩展新一年）
> 4. 缓存 schema version 升级
> 5. 任何"分档颜色对照表"的颜色或阈值变更
