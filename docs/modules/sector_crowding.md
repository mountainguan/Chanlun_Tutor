# 板块拥挤度模块（Sector Crowding）

衡量两融杠杆资金在各行业中的聚集程度。

## 1. 模块概述

- **页面组件**：`pages/sector_crowding_component.py`（入口：市场情绪与资金 → 板块拥挤度标签）
- **数据层**：`utils/sector_crowding.py`
- **历史构建脚本**：`scripts/build_sector_crowding_history.py`
- **缓存**：`data/sector_crowding/sector_crowding_history.csv` + `meta.json`

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

## 6. 注意事项

- 两融明细 T+1 发布，最新交易日（当天）无数据属正常现象
- 行业归属使用当前 `stock_basic` 分类，历史行业变动不追溯调整
- 拥挤度分位：当前值在自身三年序列中的百分位（`P80` 以上视为拥挤度高位）
