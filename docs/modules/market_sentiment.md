# Market Sentiment Module

This module analyzes and visualizes the overall market temperature based on leverage ratios and trading activity.

## 1. Overview
- **Path**: `pages/market_sentiment_component.py`
- **Business Logic**: `utils/market_sentiment.py`, `utils/index_data.py`, `utils/macro_data.py`
- **Key Metric**: Market Temperature (0-100 scale).
  - **High (>80)**: Risk accumulation (Red).
  - **Normal (20-80)**: Oscillation (Gray).
  - **Low (<20)**: Opportunity (Green).

## 2. Components
### `render_market_sentiment_panel`
- **Description**: Main entry point for the sentiment dashboard.
- **Layout**:
  - Top Row: Info Card (Left) + Gauge Chart (Right).
  - Middle Row: Historical Trend Chart (Line chart with multiple indices).
  - Bottom Row: Shibor Rates (Interbank offered rates).

### `MarketSentiment` (Utils)
- **Class**: `utils.market_sentiment.MarketSentiment`
- **Responsibilities**:
  - Fetch margin trading data (RongZiRongQuan).
  - Fetch turnover data (ChengJiaoE).
  - Calculate "Market Temperature" using the formula:
    `[(Margin% - 4.5) * 7.5] + [(Turnover(Trillion) - 0.65) * 17]`

## 3. Data Sources
- **AkShare**: `stock_zh_a_spot_em` (Real-time data).
- **EastMoney**: Margin data.
- **Sina**: Sector data.

## 4. Usage Example
```python
from pages.market_sentiment_component import render_market_sentiment_panel

# In a page function
render_market_sentiment_panel(plotly_renderer=plotly, is_mobile=False)
```

## 5. Dependencies
- `ui.card`, `ui.row`, `ui.column` (NiceGUI)
- `plotly.graph_objects` (Visualization)
- `pandas` (Data processing)
