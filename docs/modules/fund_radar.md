# Fund Radar Module

This module tracks and visualizes major fund flows and sector movements.

## 1. Overview
- **Path**: `pages/fund_radar_component.py`
- **Business Logic**: `utils/fund_radar.py`
- **Key Feature**: Real-time fund flow tracking and sector analysis.

## 2. Components
### `render_fund_radar_panel`
- **Description**: Main dashboard for fund flows.
- **Layout**:
  - Top Row: Sector Heatmap (Money In/Out).
  - Bottom Row: Fund Flow Timeline (Line Chart).
  - Side Panel: Top Stocks by Net Flow.

### `FundRadar` (Utils)
- **Class**: `utils.fund_radar.FundRadar`
- **Responsibilities**:
  - Fetch sector money flow data.
  - Calculate net inflow/outflow.
  - Generate radar charts for sector strength.

## 3. Data Sources
- **AkShare**: `stock_sector_fund_flow_rank` (Real-time flow).
- **EastMoney**: Sector index data.

## 4. Usage Example
```python
from pages.fund_radar_component import render_fund_radar_panel

# In a page function
render_fund_radar_panel(plotly_renderer=plotly, is_mobile=False)
```

## 5. Dependencies
- `ui.card`, `ui.grid` (NiceGUI)
- `plotly.express` (Visualization)
- `pandas` (Data aggregation)
