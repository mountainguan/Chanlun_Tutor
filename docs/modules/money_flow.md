# Money Flow Module

This module tracks the overall market money flow trends.

## 1. Overview
- **Path**: `pages/money_flow_component.py`
- **Business Logic**: `utils/money_flow.py`
- **Key Feature**: Visualization of capital inflows/outflows for the broad market.

## 2. Components
### `render_money_flow_panel`
- **Description**: Main panel for money flow data.
- **Layout**:
  - Time series chart of net inflow.
  - Distribution by investor type (Retail, Institution, etc.).

### `MoneyFlow` (Utils)
- **Class**: `utils.money_flow.MoneyFlow`
- **Responsibilities**:
  - Fetch aggregated market flow data.
  - Calculate cumulative flows.

## 3. Data Sources
- **AkShare**: `stock_individual_fund_flow_rank` (Aggregated).

## 4. Usage Example
```python
from pages.money_flow_component import render_money_flow_panel

# In a page function
render_money_flow_panel(plotly_renderer=plotly)
```

## 5. Dependencies
- `ui.echart` (NiceGUI)
- `pandas` (Analysis)
