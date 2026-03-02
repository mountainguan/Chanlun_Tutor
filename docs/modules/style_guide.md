# UI Design System & Style Guide

This document defines the interface design standards for the project. All new UI components must adhere to these guidelines to ensure consistency.

## 1. Color Palette

### Backgrounds
- **Global Body**: `#fcfcfc` (Clean white-ish)
- **Layout/Container**: `#f5f7f9` (Light gray for structure)
- **Cards/Panels**: `bg-white` (Pure white)

### Primary Colors
- **Brand/Primary**: `indigo-600` (Buttons, Active Tabs, Highlights)
- **Secondary**: `blue-600` (Info, Secondary actions)

### Text Colors
- **Headings**: `gray-800` or `gray-900`
- **Body**: `gray-600`
- **Muted/Labels**: `gray-400`
- **Positive (Up/Buy)**: `red-700` (China market convention: Red = Up)
- **Negative (Down/Sell)**: `green-700` (China market convention: Green = Down)

### Semantic Colors (Status)
- **High Temperature/Risk**: `red-700` bg `red-50`
- **Normal**: `gray-700` bg `gray-100`
- **Low Temperature/Opportunity**: `green-700` bg `green-50`

## 2. Typography

- **Font Family**: System UI defaults (San Francisco, Segoe UI, Roboto).
- **Headings**:
  - H1: `text-2xl font-bold text-gray-800`
  - H2: `text-xl font-bold text-indigo-700`
  - Section Titles: `text-lg font-bold text-gray-800`
- **Body**: `text-base` or `text-sm` for dense data.
- **Data/Numbers**: `font-mono` where alignment matters.

## 3. Layout & Spacing

### Responsive Strategy (Mobile-First)
**Rule**: Always design for mobile screens first, then use `md:` and `lg:` modifiers to adapt for larger screens.

- **Layout Direction**: Default to `flex-col` (vertical stack), switch to `md:flex-row` (horizontal) on PC.
  ```python
  with ui.row().classes('w-full flex-col md:flex-row gap-4'):
      # Elements stack on mobile, side-by-side on PC
  ```
- **Widths**: Use `w-full` by default. Restrict width on PC if needed (e.g., `md:w-1/2` or `md:max-w-[300px]`).
- **Padding**: Use `p-2` or `p-3` for mobile to save space, `md:p-4` for PC.
- **Hiding Elements**: 
  - Hide on mobile: `classes('hidden md:block')`
  - Hide on PC: `classes('block md:hidden')`

### Container
- **Content Area**: `max-w-[900px]` (PC) / `w-full` (Mobile).
- **Padding**: `p-4` (Standard), `p-2` (Compact/Mobile).
- **Gap**: `gap-6` (Between major modules), `gap-4` (Inside cards).

### Touch Targets
- **Buttons**: Ensure minimum height of 44px (`h-11`) or add padding on mobile for touchability.
- **Navigation**: Use bottom bars or large tap areas for mobile menus.

### Responsive Design
- **Mobile First**: Design for mobile, then upgrade for PC (`md:` prefix).
- **Breakpoints**: Standard Tailwind breakpoints (`md: 768px`, `lg: 1024px`).
- **Flex Direction**: `flex-col` (Mobile) -> `md:flex-row` (PC).

## 4. Components

### Cards (Panels)
Standard container for modules.
```python
with ui.card().classes('w-full bg-white p-4 rounded-xl shadow-sm border border-gray-200'):
    # Content here
```

### Tabs
Custom pill-shaped tabs.
- **Active**: `bg-indigo-600 text-white shadow-md rounded-full`
- **Inactive**: `text-gray-500 hover:text-indigo-600 hover:bg-gray-50 rounded-full`

### Charts
- **Container**: Fixed height (`h-[400px]` or similar).
- **Library**: Plotly (via `ui.plotly`) or ECharts (via `ui.echart`).
- **Responsiveness**: Must handle resize events.

## 5. Icons
- **Library**: Material Icons (NiceGUI default).
- **Size**: `text-2xl` for section headers, `text-lg` for inline.
- **Color**: `color='indigo'` for primary icons.
