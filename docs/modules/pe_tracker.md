# PE Tracker Module

跟踪上证 50/180/380、科创 50 四个指数样本调整名单的成分股估值，识别"高剔低纳"的指数调整方向。

## 1. Overview
- **Path**: `pages/pe_tracker_component.py`
- **Business Logic**: `utils/pe_tracker.py`
- **Key Concept**: 对比"调入"与"调出"标的的 PE 分布，识别本次指数调整的估值倾向（高估替换低估 vs 反之）。

## 2. Components
### `render_pe_tracker_panel`
- **Description**: 主面板入口，路由 `/pe-tracker`。
- **Layout**:
  - 顶部：标题 + 核心洞察 + 4 维筛选（指数 / 状态 / 估值档 / 溢价率）
  - 中部：调入 vs 调出 对比 + 各指数估值水平柱状图 + 估值分布
  - 底部：AG Grid 明细表 + Excel 导出

### `PETracker` (Utils)
- **Class**: `utils.pe_tracker.PETracker`
- **Responsibilities**:
  - 从 `data/指数样本调整名单.xlsx` 加载成分股名单
  - 拉取个股 PE/PB/股价/总市值
  - 计算行业板块 PE（基于成分股市值加权）
  - 合并并计算个股相对板块的 PE 溢价率

## 3. Data Source
- **Tushare Pro** (https://tushare.pro)
  - `daily_basic` → 个股 `pe, pe_ttm, pb, total_mv, close`（一次拉全 A）
  - `stock_basic` → 个股 `name, industry`（申万一级行业）
  - 板块 PE = 成分股 PE 的市值加权平均

### Token 配置
按以下任一方式配置后**重启服务**：

1. **环境变量**（推荐）
   ```bash
   # Windows PowerShell
   $env:TUSHARE_TOKEN = "你的token"
   # Windows CMD
   set TUSHARE_TOKEN=你的token
   # bash
   export TUSHARE_TOKEN=你的token
   ```

2. **配置文件**
   在 `data/tushare_token.txt` 写入 token（一行，无 BOM）。

> 缺失 token 时 `PETracker` 启动会抛 `RuntimeError`，错误信息已包含配置指引。

## 4. Field Mapping
| 原东方财富字段 | Tushare 字段          | 说明                          |
|---------------|----------------------|------------------------------|
| `f43` (最新价) | `close`              | 一致                          |
| `f162` (动态PE) | `pe`                | 动态市盈率                     |
| `f163` (静态PE) | `pe_ttm`            | Tushare 没有静态 PE，用 pe_ttm 近似 |
| `f167` (PB)    | `pb`                | 一致                          |
| `f183` (总市值) | `total_mv` × 1e4   | Tushare 单位是万元，转换为元   |

> 总市值单位保持「元」与原实现一致，UI 端 `总市值 / 1e8` 显示为"亿"。

## 5. Cache Schema
- **文件**：`data/pe_tracker_cache.json`, `data/pe_sector_cache.json`
- **格式**：JSON，`schema_version` 字段标识数据源版本
  - `1` = 东方财富时代
  - `2` = Tushare Pro 时代
- **失效条件**：
  - `schema_version` 不匹配 → 视为旧数据源残留，自动清空
  - `date` 不是今天 → 视为过期
- **切换数据源**：在 `PETracker.SCHEMA_VERSION` 中 bump 数字即可让旧缓存一次性失效

## 6. Usage Example
```python
from pages.pe_tracker_component import render_pe_tracker_panel
from pages.shared import custom_plotly

@ui.page('/pe-tracker')
def pe_tracker_page():
    render_pe_tracker_panel(custom_plotly, is_mobile=False)
```

## 7. Dependencies
- `nicegui.ui` (Page)
- `plotly.graph_objects` (Bar chart)
- `pandas` (DataFrame merge)
- `openpyxl` (Excel 导入/导出)
- `tushare` (Tushare Pro SDK)
