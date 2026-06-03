# PE Tracker UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 PE 跟踪模块的 3 个核心区域，让数据呈现可读、可信、可联动

**Architecture:** 单文件改动（`pages/pe_tracker_component.py`），不重构模块结构，不动数据层 `utils/pe_tracker.py`；图1 卡片加 tooltip + 差值徽章，图2 改内联展开代替弹窗，图3 修 bug + 改列名 + 加档位联动筛选

**Tech Stack:** Python 3.x · NiceGUI · AG-Grid (via nicegui) · Plotly · Tushare Pro

**Spec:** [`docs/superpowers/specs/2026-06-03-pe-tracker-ux-redesign.md`](../specs/2026-06-03-pe-tracker-ux-redesign.md)

---

## File Structure

| 文件 | 责任 | 状态 |
|---|---|---|
| `pages/pe_tracker_component.py` | UI 组件（本次主要改动） | Modify |
| `utils/pe_tracker.py` | 数据层（**不动**） | — |
| `tests/test_pe_tracker_component.py` | 结构/冒烟测试 | Create |
| `docs/superpowers/specs/2026-06-03-pe-tracker-ux-redesign.md` | 设计文档 | Created (已存在) |

**任务边界**：每个 Task 改一处，单独 commit。Table 列重命名拆成 2 个子任务（rename + reorder）以保持 diff 可读。

---

## Task 1: 添加结构测试基础（为后续 TDD 铺路）

**Files:**
- Create: `tests/test_pe_tracker_component.py`

- [ ] **Step 1: 创建测试文件骨架**

```python
# tests/test_pe_tracker_component.py
import re
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPONENT_PATH = PROJECT_ROOT / 'pages' / 'pe_tracker_component.py'


def read_source() -> str:
    return COMPONENT_PATH.read_text(encoding='utf-8')


class TestPETrackerComponentStructure(unittest.TestCase):
    """结构/冒烟测试，验证 UI 改动不破坏既有契约。"""

    def test_state_has_expanded_percentile_band(self):
        src = read_source()
        self.assertIn("'expanded_percentile_band'", src)

    def test_state_has_table_level_filter(self):
        src = read_source()
        self.assertIn("'table_level_filter'", src)

    def test_no_show_percentile_detail_function(self):
        """重构后应删除弹窗函数。"""
        src = read_source()
        self.assertNotIn('def show_percentile_detail', src)

    def test_columns_renamed(self):
        src = read_source()
        # 新列名必须出现
        for name in ['PE（动态）', 'PE（TTM）', '行业PE', '行业历史分位', '估值档位', '分位档位', '所属行业', '市净率']:
            self.assertIn(name, src, f'列名 "{name}" 未找到')

    def test_old_column_names_removed(self):
        src = read_source()
        for old in ["'headerName': 'P. 2'"]:
            self.assertNotIn(old, src, f'旧列名 "{old}" 仍存在')

    def test_static_pe_none_handled(self):
        """静态 PE 应处理 None（不能直接 round(None)）。"""
        src = read_source()
        # 必须有显式的 None 判断
        self.assertRegex(src, r'pe_static.*?is not None', re.DOTALL)
        # 仍输出 '—' 而不是 "Invalid Number"
        self.assertIn("pct_color", src)  # 沿用同一处理

    def test_diff_badge_appears(self):
        """差值徽章文案应出现。"""
        src = read_source()
        self.assertIn('调出−调入', src)

    def test_no_unit_in_main_number(self):
        """主数字旁不应再独立出现 '倍' 标签。"""
        src = read_source()
        # 之前有 ui.label('倍').classes(...)
        self.assertNotIn("ui.label('倍')", src)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 运行测试确认全部失败（红）**

Run: `cd "d:/缠论小应用" && python -m pytest tests/test_pe_tracker_component.py -v`
Expected: 8 个测试全部 FAIL（因为实现还没改）

- [ ] **Step 3: 提交测试骨架**

```bash
cd "d:/缠论小应用"
git add tests/test_pe_tracker_component.py
git commit -m "test: PE tracker component structure test skeleton"
```

---

## Task 2: state 字典新增 2 个键

**Files:**
- Modify: `pages/pe_tracker_component.py:30-38`（state 字典）

- [ ] **Step 1: 修改 state 字典**

把现有 state 字典：

```python
state = {
    'df': None,
    'selected_index': 'all',
    'selected_action': 'all',
    'selected_level': 'all',
    'selected_percentile': 'all',  # 历史PE分位档位筛选
    'selected_level_view': '低估',  # 估值分布区点击的档位
    'loading': False,
}
```

改为：

```python
state = {
    'df': None,
    'selected_index': 'all',
    'selected_action': 'all',
    'selected_level': 'all',
    'selected_percentile': 'all',  # 历史PE分位档位筛选
    'selected_level_view': '低估',  # 估值分布区点击的档位
    'expanded_percentile_band': None,  # 图2 档位内联展开状态
    'table_level_filter': None,  # 图3 档位徽章联动筛选
    'loading': False,
}
```

- [ ] **Step 2: 运行 state 相关测试**

Run: `cd "d:/缠论小应用" && python -m pytest tests/test_pe_tracker_component.py::TestPETrackerComponentStructure::test_state_has_expanded_percentile_band tests/test_pe_tracker_component.py::TestPETrackerComponentStructure::test_state_has_table_level_filter -v`
Expected: 2 PASS

- [ ] **Step 3: 提交**

```bash
cd "d:/缠论小应用"
git add pages/pe_tracker_component.py
git commit -m "feat(pe-tracker): add state keys for inline band expand and table level filter"
```

---

## Task 3: 修复图3 静态 PE "Invalid Number" bug

**Files:**
- Modify: `pages/pe_tracker_component.py:755-833`（`render_table` 中 rows 构造部分）

- [ ] **Step 1: 修改 rows 构造，处理 静态PE 的 None**

在 `rows.append({...})` 中找到 `pe_static` 字段位置（当前 `pb` 之前）：

原：
```python
'pb': round(row.get('PB', 0), 2) if row.get('PB', 0) else 0,
```

替换为：
```python
'pb': round(float(row.get('PB', 0) or 0), 2) if (row.get('PB') or 0) > 0 else None,
```

- [ ] **Step 2: 修改 静态PE 列的 cellRenderer**

找到 `{'headerName': '静态PE' ...}` 这列（整列重命名见 Task 4，但 cellRenderer 修复先做）：

原（可能不存在，先定位）：
```python
{'headerName': '静态PE', 'field': 'pe_static', 'sortable': True, 'width': 80,
 'cellStyle': {...}},
```

替换为（先占位，等 Task 4 改列名）：
```python
{'headerName': 'PE（TTM）', 'field': 'pe_static', 'sortable': True, 'width': 85,
 'cellStyle': {'textAlign': 'right', 'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace', 'color': '#0ea5e9', 'fontSize': '13px'},
 'cellRenderer': "function(params) { if(params.value === null || params.value === undefined) return '<span style=\"color:#94a3b8;font-family:ui-monospace,monospace\">—</span>'; return '<span style=\"color:#0ea5e9;font-weight:500\">'+params.value.toFixed(2)+'</span>'; }"},
```

- [ ] **Step 3: 在 rows.append 中加 pe_static 字段规范化**

在 rows.append 块中找 `'pe_dynamic': round(pe_dynamic, 2) if pe_dynamic else 0,` 之后，加入：

```python
# pe_static None 规范化
pe_static_raw = row.get('静态PE', None)
pe_static_val = round(float(pe_static_raw), 2) if (pe_static_raw is not None and pe_static_raw > 0) else None,
```

实际把它整体改写 `rows.append` 中的 `pe_static` 键为 `pe_static_val`：

原：
```python
rows.append({
    'code': row.get('股票编码', ''),
    ...
})
```

改为（把 `pe_dynamic` 那行后面追加 pe_static 字段，并修改 `pb` 那行）：

```python
# 静态PE 规范化（处理 None -> None，避免 round() 抛 TypeError）
pe_static_raw = row.get('静态PE', None)
pe_static_val = round(float(pe_static_raw), 2) if (pe_static_raw is not None and pe_static_raw > 0) else None

# PB 规范化（同样处理）
pb_raw = row.get('PB', None)
pb_val = round(float(pb_raw), 2) if (pb_raw is not None and pb_raw > 0) else None

rows.append({
    'code': row.get('股票编码', ''),
    'name': row.get('股票名称', ''),
    'index': row.get('所属指数', '').replace('指数', ''),
    'action': action,
    'price': f"{row.get('最新价', 0):.2f}",
    'pe_dynamic': round(pe_dynamic, 2) if pe_dynamic else 0,
    'level': level,
    'level_bg': level_bg,
    'level_color': level_color,
    'sector_name': row.get('所属板块', ''),
    'sector_pe': round(sector_pe, 2) if sector_pe else 0,
    'pe_static': pe_static_val,   # 改：使用规范化后的值
    'pe_percentile': pct_display,
    'pct_color': pct_color,
    'pct_level': pct_level,
    'pct_level_bg': pct_level_bg,
    'pct_level_color': pct_level_color,
    'pb': pb_val,                 # 改：使用规范化后的值
    'market_cap': round(row.get('总市值', 0) / 1e8, 2) if row.get('总市值', 0) else 0,
    'action_color': action_style['color'],
    'action_bg': action_style['bg'],
})
```

- [ ] **Step 4: 跑 static_pe 测试**

Run: `cd "d:/缠论小应用" && python -m pytest tests/test_pe_tracker_component.py::TestPETrackerComponentStructure::test_static_pe_none_handled -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd "d:/缠论小应用"
git add pages/pe_tracker_component.py
git commit -m "fix(pe-tracker): handle None for static PE and PB to prevent 'Invalid Number'"
```

---

## Task 4: 图3 列重命名 + 重排

**Files:**
- Modify: `pages/pe_tracker_component.py:835-875`（column_defs）
- Modify: `pages/pe_tracker_component.py:963-989`（export_to_excel 头部）

- [ ] **Step 1: 重写 column_defs 列表**

把 `column_defs = [...]` 整个替换为：

```python
column_defs = [
    # 基本信息
    {'headerName': '代码', 'field': 'code', 'sortable': True, 'filter': True, 'width': 85, 'pinned': 'left',
     'cellStyle': {'fontWeight': '500', 'fontSize': '13px'},
     'headerClass': 'pe-grid-header',
     'headerTooltip': '股票代码'},
    {'headerName': '名称', 'field': 'name', 'sortable': True, 'filter': True, 'width': 90, 'pinned': 'left',
     'cellStyle': {'fontWeight': '600', 'fontSize': '13px'},
     'headerClass': 'pe-grid-header',
     'headerTooltip': '股票名称'},
    {'headerName': '指数', 'field': 'index', 'sortable': True, 'filter': True, 'width': 70,
     'cellStyle': {'fontSize': '12px', 'color': '#64748b'},
     'headerClass': 'pe-grid-header',
     'headerTooltip': '所属指数（样本调整对应指数）'},
    {'headerName': '状态', 'field': 'action', 'sortable': True, 'filter': True, 'width': 65,
     'cellRenderer': "function(params) { return '<span style=\"background:'+params.data.action_bg+';color:'+params.data.action_color+';padding:3px 8px;border-radius:4px;font-size:12px;font-weight:600\">'+params.value+'</span>'; }",
     'headerClass': 'pe-grid-header',
     'headerTooltip': '本次样本调整：调入/调出/备选'},

    # 个股动态估值
    {'headerName': '最新价', 'field': 'price', 'sortable': True, 'width': 75,
     'cellStyle': {'textAlign': 'right', 'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace', 'fontSize': '13px'},
     'headerClass': 'pe-grid-header',
     'headerTooltip': '最近一个交易日收盘价'},
    {'headerName': 'PE（动态）', 'field': 'pe_dynamic', 'sortable': True, 'width': 95, 'sort': 'asc',
     'cellStyle': {'textAlign': 'right', 'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace', 'fontWeight': '600', 'fontSize': '13px'},
     'headerClass': 'pe-grid-header',
     'headerTooltip': '动态市盈率 = 股价 / 预测EPS（Tushare pro.daily_basic.pe）'},
    {'headerName': '估值档位', 'field': 'level', 'sortable': True, 'filter': True, 'width': 80,
     'cellRenderer': "function(params) { return '<span style=\"background:'+params.data.level_bg+';color:'+params.data.level_color+';padding:3px 8px;border-radius:4px;font-size:12px;font-weight:600\">'+params.value+'</span>'; }",
     'headerClass': 'pe-grid-header',
     'headerTooltip': '基于动态PE分4档：<15低估 / 15-30合理 / 30-50偏高 / ≥50高估'},

    # 行业对比
    {'headerName': '所属行业', 'field': 'sector_name', 'sortable': True, 'filter': True, 'width': 100,
     'cellStyle': {'fontSize': '12px', 'color': '#475569'},
     'headerClass': 'pe-grid-header',
     'headerTooltip': '所属申万一级行业'},
    {'headerName': '行业PE', 'field': 'sector_pe', 'sortable': True, 'width': 85,
     'cellStyle': {'textAlign': 'right', 'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace', 'color': '#6366f1', 'fontWeight': '500', 'fontSize': '13px'},
     'headerClass': 'pe-grid-header',
     'headerTooltip': '所属申万一级行业市值加权动态PE'},

    # 静态辅助
    {'headerName': 'PE（TTM）', 'field': 'pe_static', 'sortable': True, 'width': 95,
     'cellStyle': {'textAlign': 'right', 'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace', 'color': '#0ea5e9', 'fontWeight': '500', 'fontSize': '13px'},
     'cellRenderer': "function(params) { if(params.value === null || params.value === undefined) return '<span style=\"color:#94a3b8;font-family:ui-monospace,monospace\">—</span>'; return '<span style=\"color:#0ea5e9;font-weight:500\">'+params.value.toFixed(2)+'</span>'; }",
     'headerClass': 'pe-grid-header',
     'headerTooltip': '滚动12个月静态市盈率（Tushare pro.daily_basic.pe_ttm）'},

    # 历史分位
    {'headerName': '行业历史分位', 'field': 'pe_percentile', 'sortable': True, 'width': 110, 'sort': 'desc',
     'cellRenderer': "function(params) { if(params.value==='—') return '<span style=\"color:#94a3b8;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,monospace;font-size:13px\">—</span>'; var color = params.data.pct_color; return '<span style=\"color:'+color+';font-weight:600;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,monospace;font-size:13px\">'+params.value.toFixed(1)+'%</span>'; }",
     'headerClass': 'pe-grid-header',
     'headerTooltip': '当前动态PE在所属申万一级行业过去10年日频PE序列中的位置（需构建历史PE缓存）'},
    {'headerName': '分位档位', 'field': 'pct_level', 'sortable': True, 'filter': True, 'width': 85,
     'cellRenderer': "function(params) { return '<span style=\"background:'+params.data.pct_level_bg+';color:'+params.data.pct_level_color+';padding:3px 8px;border-radius:4px;font-size:12px;font-weight:600\">'+params.value+'</span>'; }",
     'headerClass': 'pe-grid-header',
     'headerTooltip': '基于行业历史分位的4档：<20%低估 / 20-50%偏低 / 50-80%偏高 / ≥80%高估'},

    # 估值辅助
    {'headerName': '市净率', 'field': 'pb', 'sortable': True, 'width': 75,
     'cellStyle': {'textAlign': 'right', 'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace', 'fontSize': '13px'},
     'cellRenderer': "function(params) { if(params.value === null || params.value === undefined) return '<span style=\"color:#94a3b8\">—</span>'; return params.value.toFixed(2); }",
     'headerClass': 'pe-grid-header',
     'headerTooltip': 'PB = 股价 / 每股净资产'},
    {'headerName': '总市值(亿)', 'field': 'market_cap', 'sortable': True, 'width': 105,
     'cellStyle': {'textAlign': 'right', 'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace', 'fontSize': '13px'},
     'headerClass': 'pe-grid-header',
     'headerTooltip': '总市值（亿元）'},
]
```

- [ ] **Step 2: 更新 export_to_excel 头部**

定位到 `export_to_excel` 函数（约 `pages/pe_tracker_component.py:953-1000`）。原代码：

```python
export_df = df[['股票编码', '股票名称', '所属指数', '调入调出', '最新价',
                '动态PE', '静态PE', '所属板块', '板块PE', 'PE分位',
                'PB', '总市值']].copy()
```

改为：

```python
export_df = df[['股票编码', '股票名称', '所属指数', '调入调出', '最新价',
                '动态PE', '静态PE', '所属板块', '板块PE', 'PE分位',
                'PB', '总市值']].copy()
# 同步重命名（与 UI 表格一致）
export_df = export_df.rename(columns={
    '动态PE': 'PE（动态）',
    '静态PE': 'PE（TTM）',
    '所属板块': '所属行业',
    '板块PE': '行业PE',
    'PE分位': '行业历史分位',
})
```

并修改 `export_df` 后续重排部分：

原：
```python
export_df = export_df[['数据日期', '股票编码', '股票名称', '所属指数', '调入调出',
                       '最新价', '动态PE', '估值档位', '静态PE',
                       '所属板块', '板块PE', 'PE分位', 'PB', '总市值(亿)']]
```

改为：

```python
export_df = export_df[['数据日期', '股票编码', '股票名称', '所属指数', '调入调出',
                       '最新价', 'PE（动态）', '估值档位', 'PE（TTM）',
                       '所属行业', '行业PE', '行业历史分位', 'PB', '总市值(亿)']]
```

- [ ] **Step 3: 运行列名相关测试**

Run: `cd "d:/缠论小应用" && python -m pytest tests/test_pe_tracker_component.py -v -k "columns_renamed or old_column_names"`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
cd "d:/缠论小应用"
git add pages/pe_tracker_component.py
git commit -m "refactor(pe-tracker): rename and reorder table columns, add header tooltips"
```

---

## Task 5: 图1 卡片 — tooltip + 去除主数字"倍" + 加差值徽章 + 空态

**Files:**
- Modify: `pages/pe_tracker_component.py:257-333`（`_render_action_card`）

- [ ] **Step 1: 重写 `_render_action_card` 函数**

把整个 `_render_action_card` 函数（`def _render_action_card(action, df, color, icon_name, trend_icon, hint_text):` 到下一个 `def` 之前）替换为：

```python
def _render_action_card(action, df, color, icon_name, trend_icon, hint_text):
    """渲染调入/调出对比卡片（含差值徽章 + 标签 tooltip）"""
    action_data = df[(df['调入调出'] == action) & (df['动态PE'] > 0)]
    other_action = '调出' if action == '调入' else '调入'
    other_data = df[(df['调入调出'] == other_action) & (df['动态PE'] > 0)]

    color_map = {
        'emerald': {
            'bg': 'bg-gradient-to-br from-emerald-50 to-white',
            'border': 'border-emerald-200',
            'text': 'text-emerald-700',
            'accent': 'bg-emerald-500',
        },
        'rose': {
            'bg': 'bg-gradient-to-br from-rose-50 to-white',
            'border': 'border-rose-200',
            'text': 'text-rose-700',
            'accent': 'bg-rose-500',
        },
    }
    c = color_map[color]

    with ui.card().classes(f'flex-1 p-5 {c["bg"]} rounded-xl border {c["border"]} relative overflow-hidden'):
        # 装饰圆
        ui.element('div').classes(f'absolute -right-6 -top-6 w-24 h-24 rounded-full {c["accent"]} opacity-10')

        # 空态
        if action_data.empty:
            with ui.column().classes('relative z-10 gap-3 items-center justify-center min-h-[180px]'):
                ui.icon('inbox', size='2rem', color='slate-300')
                ui.label(f'本次调整无{action}标的').classes('text-sm text-slate-400')
            return

        count = len(action_data)
        median_pe = action_data['动态PE'].median()
        avg_pe = action_data['动态PE'].mean()
        sector_pe = action_data['板块PE'].median()

        # 估值档位
        if median_pe < 15:
            level = '低估'
            level_color = 'emerald'
        elif median_pe < 30:
            level = '合理'
            level_color = 'sky'
        elif median_pe < 50:
            level = '偏高'
            level_color = 'amber'
        else:
            level = '高估'
            level_color = 'rose'

        with ui.column().classes('relative z-10 gap-3'):
            # 标题行
            with ui.row().classes('items-center gap-2'):
                ui.icon(icon_name, size='sm').classes(c['text'])
                ui.label(action).classes(f'text-sm font-bold {c["text"]}')
                ui.badge(level, color=level_color).props('dense')

            # 主数值（单位"倍"放入 tooltip）
            with ui.row().classes('items-baseline gap-1').props('title="动态市盈率（倍）"'):
                ui.label(f'{median_pe:.1f}').classes(f'text-4xl font-bold {c["text"]}')
                ui.label('倍').classes('text-sm text-slate-400')

            # 副指标
            with ui.row().classes('w-full gap-4 mt-1'):
                with ui.column().classes('gap-0').props('title="样本算术平均"'):
                    ui.label('平均PE').classes('text-[10px] text-slate-400')
                    ui.label(f'{avg_pe:.1f}').classes('text-sm font-bold text-slate-700')

                with ui.column().classes('gap-0').props('title="所属申万一级行业市值加权动态PE"'):
                    ui.label('行业PE').classes('text-[10px] text-slate-400')
                    ui.label(f'{sector_pe:.1f}' if sector_pe > 0 else '—').classes('text-sm font-bold text-slate-700')

                with ui.column().classes('gap-0'):
                    ui.label('数量').classes('text-[10px] text-slate-400')
                    ui.label(f'{count}只').classes('text-sm font-bold text-slate-700')

            # 差值徽章（仅在另一侧也有数据时显示）
            if not other_data.empty:
                other_median = other_data['动态PE'].median()
                diff = other_median - median_pe  # 调出 - 调入
                if abs(diff) < 5:
                    badge_text = f'{other_action}−{action} = {diff:+.1f} 倍 · 差异不大'
                    badge_color = 'sky'
                elif diff > 0:  # 调出 > 调入 → 高剔低纳
                    badge_text = f'{other_action}−{action} = {diff:+.1f} 倍 · 高剔低纳'
                    badge_color = 'emerald'
                else:  # 调出 < 调入 → 反向
                    badge_text = f'{other_action}−{action} = {diff:+.1f} 倍 · 反向：{action}更贵'
                    badge_color = 'rose'

                ui.separator().classes('my-1')
                with ui.row().classes('items-center gap-1').props(f'title="差值 = {other_action}中位PE - {action}中位PE"'):
                    ui.icon(trend_icon, size='xs').classes(c['text'])
                    ui.label(badge_text).classes(f'text-[11px] text-{badge_color}-600 font-medium')
            else:
                ui.separator().classes('my-1')
                with ui.row().classes('items-center gap-1'):
                    ui.icon(trend_icon, size='xs').classes(c['text'])
                    ui.label(hint_text).classes('text-[11px] text-slate-500')
```

- [ ] **Step 2: 移除原独立 `ui.label('倍')` 行（保险检查）**

跑 grep 确认主数字旁无独立 "倍" label：

Run: `cd "d:/缠论小应用" && grep -n "ui.label('倍')" pages/pe_tracker_component.py`
Expected: 0 命中（已被 Step 1 改掉，且测试 `test_no_unit_in_main_number` 也会拦截）

- [ ] **Step 3: 运行图1 相关测试**

Run: `cd "d:/缠论小应用" && python -m pytest tests/test_pe_tracker_component.py -v -k "diff_badge or no_unit_in_main_number"`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
cd "d:/缠论小应用"
git add pages/pe_tracker_component.py
git commit -m "feat(pe-tracker): add diff badge, label tooltips, and empty state to action cards"
```

---

## Task 6: 图2 — 替换 dialog 为内联展开

**Files:**
- Modify: `pages/pe_tracker_component.py:578-624`（`_render_percentile_distribution`）
- Modify: `pages/pe_tracker_component.py:626-713`（删除 `show_percentile_detail`）

- [ ] **Step 1: 重写 `_render_percentile_distribution` 为内联展开版**

整个函数替换为：

```python
def _render_percentile_distribution(df):
    """PE历史分位分布 - 按行业历史PE分位档位统计（点击内联展开股票列表）"""
    pct_valid = df[df['PE分位'].notna()]
    if pct_valid.empty:
        # 空态：升级文案 + 复制命令按钮
        with ui.column().classes('w-full items-center justify-center py-8 gap-3'):
            ui.icon('analytics', size='2rem', color='slate-300')
            ui.label('行业历史PE分位缓存未生成').classes('text-slate-500 text-sm font-medium')
            ui.label('首次构建约 5-10 分钟（拉取申万一级行业 10 年日频数据）').classes('text-slate-400 text-xs')

            cmd = 'python scripts/build_sector_pe_history.py'
            with ui.row().classes('items-center gap-2 mt-1 p-2 rounded-md bg-slate-50 border border-slate-200'):
                ui.icon('terminal', size='xs', color='slate-500')
                ui.label(cmd).classes('text-xs font-mono text-slate-600')
                async def _copy():
                    try:
                        await ui.run_javascript(f'navigator.clipboard.writeText("{cmd}")')
                        ui.notify('命令已复制', type='positive', position='top')
                    except Exception:
                        ui.notify('复制失败，请手动选择', type='warning')
                ui.button(icon='content_copy', on_click=_copy).props('flat dense round size=sm').tooltip('复制命令')
        return

    # 4档分位
    ranges = [
        ('低估', 0, 20,  '#10b981', 'bg-emerald-500', 'text-emerald-700', 'emerald'),
        ('偏低', 20, 50, '#3b82f6', 'bg-blue-500',    'text-blue-700',    'blue'),
        ('偏高', 50, 80, '#f59e0b', 'bg-amber-500',   'text-amber-700',   'amber'),
        ('高估', 80, 100,'#ef4444', 'bg-rose-500',    'text-rose-700',    'rose'),
    ]

    total = len(pct_valid)
    expanded = state.get('expanded_percentile_band')

    with ui.column().classes('w-full gap-2'):
        for name, low, high, color, bg_class, text_class, ring_class in ranges:
            level_stocks = pct_valid[(pct_valid['PE分位'] >= low) & (pct_valid['PE分位'] < high)]
            count = len(level_stocks)
            pct = count / total * 100
            is_expanded = (expanded == name)

            # 档位主行
            with ui.element('div').classes(
                f'w-full p-3 rounded-lg cursor-pointer transition-all '
                f'{"ring-2 ring-" + ring_class + "-400 bg-" + ring_class + "-50/50" if is_expanded else "hover:bg-slate-50 hover:shadow-sm border border-transparent hover:border-slate-200"}'
            ).on('click', lambda n=name: on_percentile_band_toggle(n)):
                with ui.column().classes('w-full gap-1'):
                    with ui.row().classes('w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-2'):
                            ui.element('div').classes(f'w-3 h-3 rounded-full {bg_class}')
                            ui.label(f'{name}（{low}%-{high if high<100 else "100%"}）').classes(f'text-sm font-medium {text_class}')
                            ui.icon('expand_more' if not is_expanded else 'expand_less', size='xs', color='slate-400')
                        with ui.row().classes('items-center gap-2'):
                            ui.label(f'{count}只').classes('text-xs text-slate-600')
                            ui.label(f'{pct:.0f}%').classes('text-sm font-bold').style(f'color: {color}')

                    # 进度条
                    with ui.element('div').classes('w-full h-2 bg-slate-100 rounded-full overflow-hidden'):
                        ui.element('div').classes(f'h-full {bg_class} transition-all').style(f'width: {pct}%')

            # 内联展开区
            if is_expanded:
                with ui.element('div').classes('w-full pl-4 pr-1 py-2'):
                    if level_stocks.empty:
                        with ui.row().classes('w-full justify-center py-3'):
                            ui.label('该档位暂无股票').classes('text-xs text-slate-400')
                    else:
                        # 排序 + 限制 10 行
                        top10 = level_stocks.sort_values('PE分位', ascending=False).head(10)
                        with ui.column().classes('w-full gap-0.5'):
                            # 表头
                            with ui.row().classes('w-full px-2 py-1 text-[10px] text-slate-400 font-medium'):
                                ui.label('名称').classes('flex-1')
                                ui.label('个股PE').classes('w-16 text-right')
                                ui.label('行业历史分位').classes('w-20 text-right')
                                ui.label('行业').classes('w-16 text-right')
                                ui.label('状态').classes('w-12 text-right')
                            for _, stock in top10.iterrows():
                                pe = float(stock.get('动态PE', 0) or 0)
                                pct_v = float(stock.get('PE分位', 0) or 0)
                                action = stock.get('调入调出', '')
                                action_color = {'调入': '#059669', '调出': '#dc2626', '备选': '#d97706'}.get(action, '#64748b')
                                with ui.row().classes('w-full items-center px-2 py-1 rounded hover:bg-slate-50 text-xs'):
                                    ui.label(stock.get('股票名称', '')).classes('flex-1 font-medium text-slate-700 truncate')
                                    ui.label(f'{pe:.1f}').classes('w-16 text-right font-mono font-bold text-slate-700')
                                    ui.label(f'{pct_v:.1f}%').classes('w-20 text-right font-mono font-bold').style(f'color: {color}')
                                    ui.label(stock.get('所属板块', '')).classes('w-16 text-right text-[11px] text-slate-500 truncate')
                                    ui.label(action).classes('w-12 text-right text-[10px] font-medium').style(f'color: {action_color}')

        # 提示
        ui.separator().classes('my-2')
        with ui.row().classes('items-center gap-2'):
            ui.icon('info', size='xs', color='slate')
            ui.label(f'共 {total} 只股票有分位数据 | 点击档位展开明细').classes('text-[11px] text-slate-400')


def on_percentile_band_toggle(band):
    """点击档位：相同则收起，不同则切换。"""
    state['expanded_percentile_band'] = None if state.get('expanded_percentile_band') == band else band
    # 只重渲染图2 卡片
    if chart_container:
        render_charts(state['df'])
```

- [ ] **Step 2: 删除 `show_percentile_detail` 函数**

定位到 `def show_percentile_detail(name, low, high, stocks):` 一直到下一个 `def _generate_logic_text` 之前（约 88 行），整段删除。

- [ ] **Step 3: 跑 show_percentile_detail 缺失测试**

Run: `cd "d:/缠论小应用" && python -m pytest tests/test_pe_tracker_component.py::TestPETrackerComponentStructure::test_no_show_percentile_detail_function -v`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
cd "d:/缠论小应用"
git add pages/pe_tracker_component.py
git commit -m "refactor(pe-tracker): replace percentile detail dialog with inline expansion"
```

---

## Task 7: 图3 — 档位徽章联动筛选

**Files:**
- Modify: `pages/pe_tracker_component.py:1077-1110`（chart_container 之后、table 区域之前，插入档位徽章行）

- [ ] **Step 1: 在 chart_container 后、表格卡片前插入档位徽章行**

定位到 `chart_container = ui.column().classes('w-full gap-4')` 这一行。在其后插入：

```python
    # 档位徽章筛选行（图3 表格上方）
    with ui.card().classes('w-full p-3 mb-2 bg-white rounded-xl shadow-sm border border-slate-100'):
        with ui.row().classes('w-full items-center gap-2 flex-wrap'):
            ui.icon('filter_alt', size='xs', color='slate-400')
            ui.label('档位快速筛选').classes('text-xs font-medium text-slate-500 mr-1')

            level_options = [
                ('低估',  '<20%',  'emerald', '#dcfce7', '#15803d'),
                ('偏低',  '20-50%','blue',    '#dbeafe', '#1d4ed8'),
                ('偏高',  '50-80%','amber',   '#fef3c7', '#b45309'),
                ('高估',  '≥80%',  'rose',    '#fee2e2', '#b91c1c'),
            ]
            current_filter = state.get('table_level_filter')
            for name, rng, quasar_color, bg_hex, text_hex in level_options:
                is_active = current_filter == name
                style = (
                    f'background:{bg_hex};color:{text_hex};border:1px solid {text_hex}33;'
                    if is_active else
                    f'background:#f8fafc;color:#475569;border:1px solid #e2e8f0;'
                )
                btn = ui.button(
                    f'{name} {rng}',
                    on_click=lambda n=name: on_table_level_filter(n)
                ).props(f'flat dense no-caps size=sm').style(style)
                if is_active:
                    btn.props('outline')

            if current_filter:
                ui.button('重置', icon='close', on_click=lambda: on_table_level_filter(None))\
                    .props('flat dense size=sm color=slate').classes('ml-2 text-slate-500')
```

- [ ] **Step 2: 在文件末尾（load_data 调用前）增加 handler**

定位到 `def on_percentile_change(value):` 后（约 `pe_tracker_component.py:941-946`）之后、`def on_level_view_change(level):` 之前。插入：

```python
    def on_table_level_filter(level):
        """档位徽章快速筛选（通过 aggrid filter 客户端过滤）"""
        state['table_level_filter'] = level
        # 重渲染表格 + 徽章行
        if table_container:
            render_table(state['df'])
        # 徽章行本身：重渲染整张图（成本可接受，因为卡片少）
        if chart_container:
            render_charts(state['df'])
```

- [ ] **Step 3: 跑全量测试**

Run: `cd "d:/缠论小应用" && python -m pytest tests/test_pe_tracker_component.py -v`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
cd "d:/缠论小应用"
git add pages/pe_tracker_component.py
git commit -m "feat(pe-tracker): add level badge quick filter for detail table"
```

---

## Task 8: 表格下方图例说明

**Files:**
- Modify: `pages/pe_tracker_component.py:887-918`（render_table 末尾的 ui.add_head_html 之前）

- [ ] **Step 1: 在表格容器外、ui.add_head_html 之前插入图例**

定位到 `with table_container:` 块（`render_table` 末尾）。在 `with table_container:` 块结束（`ui.aggrid({...})` 后）追加图例。

具体修改：在 `render_table` 函数末尾找到：
```python
            ui.aggrid({
                ...
            }).classes('w-full h-full border-none pe-table').style(...)
```

在该 `ui.aggrid(...)` 之后、`render_table` 函数 return/结束前，插入：

```python
        # 字段说明图例
        with ui.element('div').classes('w-full px-5 py-3 border-t border-slate-100 bg-slate-50/50'):
            with ui.row().classes('w-full items-start gap-2'):
                ui.icon('info', size='xs', color='slate-400').classes('mt-0.5')
                with ui.column().classes('gap-1 flex-1'):
                    ui.label('字段说明').classes('text-[10px] font-bold text-slate-500 tracking-wider uppercase')
                    with ui.row().classes('flex-wrap gap-x-4 gap-y-1 text-[10px] text-slate-500'):
                        ui.label('• 估值档位：基于动态PE分4档（<15/15-30/30-50/≥50）')
                        ui.label('• 行业PE：所属申万一级行业市值加权动态PE')
                        ui.label('• PE（TTM）：滚动12个月静态PE')
                        ui.label('• 行业历史分位：当前PE在所属申万一级行业过去10年日频PE序列中的位置（需构建历史缓存）')
                        ui.label('• 分位档位：基于行业历史分位的4档（<20%/20-50%/50-80%/≥80%）')
                        ui.label('• 市净率（PB）：股价 / 每股净资产')
```

- [ ] **Step 2: 跑全量测试**

Run: `cd "d:/缠论小应用" && python -m pytest tests/test_pe_tracker_component.py -v`
Expected: 全部 PASS

- [ ] **Step 3: 提交**

```bash
cd "d:/缠论小应用"
git add pages/pe_tracker_component.py
git commit -m "docs(pe-tracker): add field legend below detail table"
```

---

## Task 9: 手动验证（§6 验收清单）

**Files:** 浏览器手动操作（不修改代码）

- [ ] **Step 1: 启动服务并打开 PE 跟踪页**

Run: `cd "d:/缠论小应用" && python main.py`（或项目实际启动方式）
Expected: 服务启动，浏览器可访问

- [ ] **Step 2: 图1 验收**

- [ ] 主数字旁无独立 "倍" 文字
- [ ] hover "中位PE/平均PE/行业PE" 标签看到 tooltip 定义
- [ ] 卡片底部出现 "调出−调入 = +XX.X 倍" 差值徽章
- [ ] 差值正/负/近零三种颜色对应正确（emerald/rose/sky）
- [ ] 调入或调出某侧 0 只时显示 "本次调整无...标的" 空态

- [ ] **Step 3: 图2 验收**

- [ ] 4 档进度条 + 数字 + 百分比正常
- [ ] 点击某档，下方内联展开 1 张 mini 表（≤10 行）
- [ ] mini 表 5 列（名称/PE/分位/行业/状态）数据正确
- [ ] 再点同一档收起
- [ ] 点击其他档直接切换
- [ ] 缓存缺失时显示空态卡片 + "复制命令" 按钮（点击应触发 ui.notify）

- [ ] **Step 4: 图3 验收**

- [ ] 静态 PE 列无 "Invalid Number"，None 时显示 `—`
- [ ] 列名更新为新名字（PE（动态）/PE（TTM）/行业PE/行业历史分位/估值档位/分位档位/市净率/所属行业）
- [ ] 表头下方有图例说明
- [ ] 表头上方有 4 个档位徽章（低估/偏低/偏高/高估）
- [ ] 点击徽章过滤生效（仅显示对应档位行）
- [ ] 重置徽章恢复全部

- [ ] **Step 5: 回归验证**

- [ ] 顶部 4 个 select 筛选仍正常工作
- [ ] 顶部「核心洞察」文本正常更新
- [ ] 导出 Excel 仍能下载，列名为新名字
- [ ] 「刷新数据」按钮仍能触发 Tushare 拉取
- [ ] 移动端（缩窄窗口）布局不破

- [ ] **Step 6: 若有问题，本地修复后跑测试 + 单独 commit**

```bash
cd "d:/缠论小应用"
python -m pytest tests/test_pe_tracker_component.py -v
# 如有 fix:
git add pages/pe_tracker_component.py
git commit -m "fix(pe-tracker): <具体描述>"
```

- [ ] **Step 7: 验收完成，签发最终 commit（如果 Step 6 没改动可跳过）**

```bash
cd "d:/缠论小应用"
git log --oneline -10   # 检查所有 commit
```

---

## Self-Review

**1. Spec 覆盖检查**：

| Spec 章节 | 对应 Task |
|---|---|
| §3.1 图1 卡片 | Task 5 |
| §3.2 图2 内联展开 | Task 6 |
| §3.3.1 静态 PE bug | Task 3 |
| §3.3.2 列重命名 | Task 4 |
| §3.3.3 PE 分位数据补齐 | Task 6（空态升级） |
| §3.3.4 档位联动筛选 | Task 7 |
| §4 state 字典 | Task 2 |
| §5 错误处理 | Task 3（静态 PE None）+ Task 5（图1 空态）+ Task 6（档位空态） |
| §6 测试清单 | Task 1（自动化部分）+ Task 9（手动部分） |

**2. 占位符扫描**：✅ 无 TBD/TODO/"类似"/"适当处理"等
**3. 类型一致性**：
- `state['expanded_percentile_band']` 在 Task 2 定义、Task 6 读写、Task 6 handler 中重渲染 → 一致
- `state['table_level_filter']` 在 Task 2 定义、Task 7 读写 → 一致
- `on_percentile_band_toggle` 唯一在 Task 6 定义和调用 → 一致
- `on_table_level_filter` 唯一在 Task 7 定义和调用 → 一致
- `chart_container` / `table_container` 沿用现有 closure 变量，未重新定义 → 一致
