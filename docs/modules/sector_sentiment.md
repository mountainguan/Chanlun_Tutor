# Sector Sentiment Module

This module analyzes sector performance and sentiment.

## 1. Overview
- **Path**: `pages/sector_sentiment_component.py`
- **Business Logic**: `utils/sector_sentiment.py`, `utils/sector_analysis.py`
- **Key Feature**: Sector heatmaps and performance tables.

## 2. Components
### `render_sector_sentiment_panel`
- **Description**: Displays sector-level market data.
- **Layout**:
  - Heatmap (Treemap) of sectors by market cap or change.
  - Performance Table (Sortable).

### `SectorSentiment` (Utils)
- **Class**: `utils.sector_sentiment.SectorSentiment`
- **Responsibilities**:
  - Fetch sector indices.
  - Calculate daily/weekly changes.
  - Group stocks by industry.

## 3. Data Sources
- **AkShare**: `stock_board_industry_name_em`.
- **Sina**: Sector quotes.

## 4. Usage Example
```python
from pages.sector_sentiment_component import render_sector_sentiment_panel

# In a page function
render_sector_sentiment_panel(plotly_renderer=plotly, is_mobile=False)
```

## 5. Dependencies
- `ui.table`, `ui.echart` (NiceGUI)
- `pandas` (Data manipulation)
