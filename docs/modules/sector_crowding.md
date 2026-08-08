# 板块拥挤度模块（Sector Crowding）

板块拥挤度模块提供三个维度：

1. **两融数据**：衡量两融杠杆资金在各行业中的聚集程度（行业两融余额 / 总市值）。
2. **成交量**：前 5% 个股成交量集中度。
3. **成交额**：前 5% 个股成交额集中度。

后两个维度从**行业板块**与**指数**两个角度分别统计，集中度高于 45% 标记为拥挤。

## 1. 模块概述

- **页面组件**：`pages/sector_crowding_component.py`（入口：市场情绪与资金 → 板块拥挤度标签，顶部可切换两融 / 成交量 / 成交额维度）
- **数据层（两融）**：`utils/sector_crowding.py`
- **数据层（成交量 / 成交额）**：`utils/trading_crowding.py`
- **历史构建脚本（两融）**：`scripts/build_sector_crowding_history.py`
- **历史构建脚本（成交量 / 成交额）**：`scripts/build_trading_crowding_history.py`
- **缓存（两融）**：`data/sector_crowding/sector_crowding_history.csv` + `meta.json`
- **缓存（成交量 / 成交额）**：`data/trading_crowding/`（行业 + 指数两个 CSV）+ `meta.json`

## 2. 指标定义

$$
\text{板块拥挤度} = \frac{\text{行业两融余额（融资余额 + 融券余额）}}{\text{行业总市值}} \times 100\%
$$

- 行业总市值：该行业全部 A 股当日收盘 `total_mv` 之和（含非两融标的）
- 行业两融余额：该行业两融标的 `rzrqye` 之和
- 辅助指标：融资占比（rzye/总市值）、融券占比（rqye/总市值）
- 行业分类：`stock_basic.industry`（证监会行业，与 PE 估值模块口径一致）

## 3. 数据源

优先使用 Tushare Pro，token 加载顺序：
环境变量 `TUSHARE_TOKEN` > 项目根目录 `tushare_token.txt` > `data/tushare_token.txt`。

| 接口 | 用途 | 说明 |
| --- | --- | --- |
| `pro.margin_detail` | 个股两融明细 | 按交易日拉取，T+1 发布 |
| `pro.daily_basic` | 个股每日指标 | `total_mv` 单位万元，内部换算为元 |
| `pro.stock_basic` | 行业分类 | `industry` 字段 |
| `pro.trade_cal` | 交易日历 | 确定逐日遍历范围 |

## 3.5 成交量 / 成交额维度数据源

| 接口 | 用途 | 说明 |
| --- | --- | --- |
| `pro.daily` | 全市场日行情 | `vol` 成交量（手）、`amount` 成交额（千元） |
| `pro.stock_basic` | 行业分类 | 兜底；优先本地 `data/stock_industry_cache.json` |
| `pro.trade_cal` | 交易日历 | 确定逐日遍历范围 |

指数成分股复用两融维度的 `data/index_constituents_cache/index_cons_*.json`，
缺失时按 scope（沪市 / 深市 / 科创板 / 创业板）取全市场范围，口径与两融维度一致。

## 4. 构建三年历史

```bash
# 默认：近 3 年逐交易日，断点续跑（已有缓存只补最新）
python scripts/build_sector_crowding_history.py

# 调试：只拉 5 天
python scripts/build_sector_crowding_history.py --max-days 5

# 自定义区间
python scripts/build_sector_crowding_history.py --start 20260101 --end 20260731
```

约 730 个交易日 × 每天 2 次接口调用，全程约 10-20 分钟。
构建中断后可重复执行同一命令续跑。

## 5. 使用示例

```python
from utils.sector_crowding import SectorCrowding

sc = SectorCrowding()
latest = sc.get_latest()                # 最新交易日各行业拥挤度（降序）
series = sc.get_industry_series('软件服务')  # 单行业三年序列
rank = sc.percentile_rank(series['crowding_pct'], series.iloc[-1]['crowding_pct'])
```

## 6. 两融涨跌速度（板块升温/降温）

板块拥挤度面板内置「两融涨跌速度」卡片，用于观察杠杆资金升温/降温的快慢。

**口径**：对每个行业取最新交易日 T 与 T-N 个交易日（N ∈ 3/5/10/15/20，默认 10 ≈ 近两周）：

$$
\text{两融变化额} = rzrqye_T - rzrqye_{T-N}
$$

$$
\text{市值变化额} = total\_mv_T - total\_mv_{T-N}
$$

$$
\text{增量比} = \frac{\text{两融变化额}}{\text{市值变化额}}
$$

**核心指标：增量比**（两融变化金额 ÷ 市值变化金额）。它衡量每增加 1 元市值伴随的两融增量：

- 增量比高于当前拥挤度% → 边际杠杆高于平均水平，杠杆资金加速流入（升温）
- 增量比低于当前拥挤度% → 边际杠杆低于平均水平，杠杆资金退潮（降温）
- 增量比与当前拥挤度% 接近 → 两融变化与市值变化匹配

两融增速%、市值增速% 作为辅助列保留。面板提供：

- 窗口切换（3/5/10/15/20 个交易日）
- 升温/匹配/降温行业数量统计卡
- 增量比 Top15 条形图（叠加当前拥挤度参考点）
- 行业明细表：增量比、拥挤度、两融变化额、市值变化额、两融增速、市值增速、状态，支持按增量比/两融增速/市值增速/两融变化额排序

升温/降温状态按拥挤度变化判定：拥挤度变化 ≥ +0.05pp 为升温，≤ −0.05pp 为降温，其余为匹配（市值下行时增量比符号会翻转，直接用拥挤度方向判定更稳健）。

数据层实现为 `SectorCrowding.compute_margin_speed()`（向量化 groupby.shift），结果随 `precompute()` 一起落入派生缓存，不额外请求接口。

## 7. 注意事项

- 两融明细 T+1 发布，最新交易日（当天）无数据属正常现象
- 行业归属使用当前 `stock_basic` 分类，历史行业变动不追溯调整
- 拥挤度分位：当前值在自身三年序列中的百分位（`P80` 以上视为拥挤度高位）

## 8. 成交量 / 成交额维度（前 5% 成交集中度）

面板顶部切换至「成交量」或「成交额」后，展示前 5% 个股成交集中度。

### 8.1 指标定义

$$
\text{前5\%个股成交量集中度} = \frac{\text{板块内成交量最大的前5\%个股成交量合计}}{\text{板块成交量合计}} \times 100\%
$$

$$
\text{前5\%个股成交额集中度} = \frac{\text{板块内成交额最大的前5\%个股成交额合计}}{\text{板块成交额合计}} \times 100\%
$$

- 前 5% 数量 = `max(1, ceil(板块个股数 × 5%))`
- **成交量维度按 vol 排序取前 5%，成交额维度按 amount 排序取前 5%，两个维度独立统计**
- 集中度 **高于 45%** 标记为「⚠ 拥挤」
- 统计角度：**全A市场**（全部已上市 A 股，`index_code='ALL'`）、**行业板块**（证监会行业，
  同两融维度）与**指数**（主要指数成分股）分别计算
- 行业分类优先使用 Tushare `stock_basic` 全市场分类（与两融维度口径一致），
  接口失败时兜底本地 `data/stock_industry_cache.json`
- 个股数少于 10 只的行业样本过少（前 5% 集中度易失真，如 1 只个股必为 100%），
  不参与「拥挤」标记，界面显示「样本少」

### 8.2 构建三年历史

```bash
python scripts/build_trading_crowding_history.py
python scripts/build_trading_crowding_history.py --max-days 5
python scripts/build_trading_crowding_history.py --start 20260101 --end 20260731
```

每天 1 次 `pro.daily` 调用，约 730 个交易日全程 10-20 分钟，断点续跑。
输出：

- `data/trading_crowding/trading_crowding_history.csv`（行业维度）
- `data/trading_crowding/trading_crowding_index_history.csv`（指数维度 + 全A行）

若历史在「全A」维度加入前构建，可运行回填脚本补拉全A行（幂等，可重复执行）：

```bash
python scripts/backfill_trading_crowding_market.py
```

### 8.3 使用示例

```python
from utils.trading_crowding import TradingCrowding

tc = TradingCrowding()
pre = tc.precompute()             # 行业维度：latest_df / by_industry
pre_idx = tc.precompute_indices() # 指数维度：{指数代码: (指数名, 时间序列)}
```

字段：`stock_count`、`total_vol` / `top5_vol` / `vol_concentration_pct`、
`total_amount` / `top5_amount` / `amount_concentration_pct`（指数维度另含 `coverage`）。
