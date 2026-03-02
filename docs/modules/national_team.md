# National Team Module

This module tracks stocks held by major state-backed funds ("National Team").

## 1. Overview
- **Path**: `pages/national_team_component.py`
- **Business Logic**: `utils/national_team.py`
- **Key Feature**: Identify and analyze stocks with heavy state investment.

## 2. Components
### `render_national_team_panel`
- **Description**: Displays a grid of stocks held by National Team.
- **Layout**:
  - Filter controls (Sector, Holding %, etc.).
  - Interactive data grid (AgGrid or Table).

### `NationalTeam` (Utils)
- **Class**: `utils.national_team.NationalTeam`
- **Responsibilities**:
  - Parse shareholder data to identify specific funds (e.g., Huijin, CSFC).
  - Calculate holding ratios.

## 3. Data Sources
- **AkShare**: `stock_share_hold_top_10` (Quarterly reports).
- **EastMoney**: Top 10 shareholders.

## 4. Usage Example
```python
from pages.national_team_component import render_national_team_panel

# In a page function
render_national_team_panel(plotly_renderer=plotly, is_mobile=False)
```

## 5. Dependencies
- `ui.table`, `ui.aggrid` (NiceGUI)
- `pandas` (Filtering/Sorting)
