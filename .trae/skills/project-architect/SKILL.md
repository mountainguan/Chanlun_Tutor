---
name: "project-architect"
description: "Enforces project design specs and code standards. Invoke when reviewing code, planning new features, or refactoring."
---

# Project Architect & Standards Guardian

This skill acts as the project's technical lead, ensuring all changes adhere to the established design patterns and coding standards.

## Project Overview
- **Type**: Python Web Application (NiceGUI).
- **Structure**:
  - `pages/`: UI Components. Pure presentation logic.
  - `utils/`: Business logic, data fetching (AkShare), data processing.
  - `data/`: Local data storage (JSON/CSV).
  - `scripts/`: Standalone maintenance scripts.
  - `tests/`: Unit and integration tests.

## Design Specifications

### 1. Architecture Patterns
- **Separation of Concerns**: UI code (`pages/`) must NOT contain heavy business logic or direct API calls. Delegate to `utils/`.
- **State Management**: Use NiceGUI's reactive state management. Avoid global state where possible; use class-based components.
- **Data Persistence**:
  - **Reference**: See `docs/modules/data_caching.md` for full details.
  - **Location**: All cache files must reside in `data/` or `data/cache/`.
  - **Format**: JSON for structured data (MUST include `_meta`), CSV for time-series.
  - **Logic**: Implement Read-Through Caching with TTL. Use atomic writes (write-tmp-rename).
  - **Fallback**: Implement "stale-while-revalidate" - return expired cache on API failure.

### 2. UI/UX Standards (NiceGUI)
- **Reference**: See `docs/modules/style_guide.md` for full details.
- **Mobile-First Strategy**:
  - **MANDATORY**: All UI components must be designed for mobile screens first (vertical stack `flex-col`, full width `w-full`).
  - **PC Adaptation**: Use `md:` or `lg:` prefixes to adjust for larger screens (e.g., `md:flex-row`, `md:w-1/2`).
  - **Touch Targets**: Ensure clickable elements are at least 44px high on mobile.
- **Styling**: Use Tailwind CSS classes.
  - Backgrounds: `#fcfcfc` (body), `#f5f7f9` (layout).
  - Primary: `indigo-600` (interactive elements).
  - Text: `gray-800` (headings), `gray-600` (body).
- **Layout**: Responsive design using `ui.row`, `ui.column`, `ui.grid`. Mobile-first (`flex-col` -> `md:flex-row`).
- **Components**: Reusable components should be classes inheriting from `ui.element` or similar wrappers.
- **Charts**: Use ECharts (via `ui.echart`) or Plotly for data visualization. Charts must be responsive.

### 3. Module Documentation
- **Reference**: See `docs/modules/index.md` for a list of all business modules.
- **Before Coding**: ALWAYS check the existing module documentation to reuse logic and UI patterns.
- **New Modules**: Create a corresponding markdown file in `docs/modules/` for any new major feature.

## Code Functional Specifications

### 1. Naming Conventions
- **Variables/Functions**: `snake_case` (e.g., `fetch_stock_data`).
- **Classes**: `PascalCase` (e.g., `StockAnalyzer`).
- **Constants**: `UPPER_CASE` (e.g., `DEFAULT_TIMEOUT`).
- **Files**: `snake_case` (e.g., `market_sentiment.py`).

### 2. Error Handling & Logging
- **API Calls**: Wrap AkShare/external calls in try-except blocks. Handle network timeouts and data format changes gracefully.
- **UI Feedback**: Show `ui.notify` for user-facing errors. Log detailed errors to console/file.
- **Data Validation**: Validate data schema before processing. Handle `NaN` or missing values in financial data.

### 3. Documentation
- **Docstrings**: All public functions and classes must have docstrings (Google style or NumPy style).
- **Comments**: Explain *why*, not just *what*, especially for complex financial logic.

## Workflow for New Features
1. **Plan**: Define the data source (API) and UI requirements.
2. **Data Layer**: Implement fetching and processing in `utils/`. Add caching.
3. **UI Layer**: Create a component in `pages/` that consumes the `utils` function.
4. **Integration**: Add the page/component to `main.py` or the navigation menu.
5. **Verify**: Test edge cases (no data, API failure).

## Checklist for Code Reviews
- [ ] Is business logic separated from UI?
- [ ] Is data cached appropriately?
- [ ] Are variable names descriptive?
- [ ] Is error handling robust?
- [ ] Does it follow Tailwind CSS conventions?
