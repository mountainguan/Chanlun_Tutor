# PE 跟踪模块 UX 重构设计

**日期**: 2026-06-03
**作者**: Claude (brainstorming)
**范围**: 修复 3 处具体 UI/数据呈现问题（不重构模块结构）
**涉及文件**: `pages/pe_tracker_component.py`（主） · 数据层 `utils/pe_tracker.py` 不动

---

## 1. 背景与目标

当前 PE 跟踪页面（`pe_tracker_component.py`）的 3 个核心区域存在可读性问题：

1. **图1 调入/调出 估值对比卡片**：主数字用 "X.X 倍" 表述，3 个副指标（中位/平均/板块）含义不清；徽章档位易造成"高剔低纳"反直觉误读。
2. **图2 行业历史 PE 分位**：4 档进度条只显示计数和百分比，缺该档位的「行业平均 PE / 最高 PE / 代表股票」等上下文；明细查看走 dialog 弹窗，与表格体验割裂。
3. **图3 成分股估值明细**：静态 PE 列出现 `Invalid Number`（`pe_static` 为 None 时未处理）；列名 `P. 2` 含义不明；PE 分位档位整列 `—`（缓存未生成时未与正常档位区分）；表格未与档位筛选联动。

目标：**让 3 个区域各自承担清晰的信息职责，可读、可信、可联动**。

---

## 2. 非目标

- 不重构模块结构（不拆 `pe_tracker_card.py` / `pe_tracker_table.py`）
- 不动数据层 `utils/pe_tracker.py`（PE 分位计算逻辑已正确，问题是缓存未生成）
- 不新增数据源 / 不改 Tushare 调用方式
- 不动指数样本名单来源（`data/指数样本调整名单.xlsx`）

---

## 3. 设计

### 3.1 图1 调入/调出 估值对比卡片

**保留字段**（每张卡片）：
- **中位 PE**：主数字，最稳健（4 张卡片正中位置）
- **平均 PE**：副指标 1
- **行业 PE**（原"板块PE"）：副指标 2（来自申万一级行业市值加权）
- **数量**：副指标 3
- **档位徽章**：低估(emerald) / 合理(sky) / 偏高(amber) / 高估(rose)

**修改点**：

| 项目 | 原设计 | 新设计 |
|---|---|---|
| 主数字 | `79.6 倍`（`label` + 紧跟 `label('倍')`） | `79.6`，单位"倍" 放入 tooltip 避免反直觉 |
| 副指标 1 标题 | `平均PE` | `平均PE` 不变 |
| 副指标 2 标题 | `板块PE` | `行业PE`（用"行业"更准确：申万一级） |
| 副指标 3 标题 | `数量` | `数量` 不变 |
| 标签 tooltip | 无 | 每个标签 hover 显示含义：<br>· `中位PE` → "样本中位数，不受极值影响"<br>· `平均PE` → "样本算术平均"<br>· `行业PE` → "所属申万一级行业市值加权平均" |
| 差值徽章 | 无 | 卡片底部加 `调出−调入 = +XX.X 倍` 徽章<br>· 正值（调出 > 调入）→ emerald + "高剔低纳"<br>· 负值（调出 < 调入）→ rose + "反向：调入更贵"<br>· 绝对值 < 5 → sky + "差异不大" |
| 提示文字 | `低估值标的进入` | 保留 |
| 装饰圆 | 右上角圆形 | 保留 |

**关键代码改动**：`_render_action_card` 函数。

---

### 3.2 图2 行业历史 PE 分位 — 内联展开

**结构变化**：4 档进度条 + 计数 + 百分比保持不变。**移除 dialog 弹窗**，改为每档下方"内联展开" 1 张表。

**状态机**：
- `state['expanded_percentile_band'] = None | '低估' | '偏低' | '偏高' | '高估'`
- 初始 None
- 点击某档 → 切换为该档名；点击同一档 → 收起（变 None）

**内联展开表列**（精简，10 行，按 PE 分位降序）：
| 名称 | 个股PE | 行业历史分位 | 所属行业 | 状态 |
|---|---|---|---|---|
| 上汽集团 | 13.9 | 8.5% | 汽车 | 调入 |

**关键实现**：
- 用 nicegui `bind_visibility` 控制展开区显隐
- 行内 mini table 用 `aggrid` 子配置（关闭分页、关闭过滤、只保留 sortable）
- 仍只显示 10 行（避免长表格破坏卡片节奏），要更多则给一个"查看全部"按钮跳转图3的筛选态

**保留**：4 档进度条 + 数字 + 百分比 + 底部 "共 N 只股票有分位数据" 提示。

**新增**：缓存缺失时的空态卡片（如果 `pe_valid.empty`）。当前已有文案 `'请在终端运行：python scripts/build_sector_pe_history.py'`，保留即可。

**关键代码改动**：
- 删除 `show_percentile_detail` 函数（dialog 路径）
- 修改 `_render_percentile_distribution`：4 档循环里增加 `with ui.element('div').bind_visibility(...)` 内联区
- 增加 `on_percentile_band_toggle(band)` 处理函数
- 在 state 里增加 `expanded_percentile_band` 字段

---

### 3.3 图3 成分股估值明细

#### 3.3.1 Bug 修复：静态 PE 列 "Invalid Number"

**根因**：`render_table` 中 `round(pe_static, 2) if pe_static else 0`，当 `pe_static == 0` 时（合法值或非法值未区分），aggrid 收到 0 → 显示 OK；但当 `pe_static is None` 时，行构造抛 TypeError → aggrid 显示原始错误字符串 "Invalid Number"。

**修复**：
```python
# 原来
'pe_static': round(row.get('pe_static', 0), 2) if row.get('pe_static', 0) else 0,
# 新增判断
pe_static_raw = row.get('静态PE', None)
pe_static = round(float(pe_static_raw), 2) if pe_static_raw is not None and pe_static_raw > 0 else None
# 在 cellRenderer 里判 None → '—'（与 PE分位 档位的 None 处理对齐）
```

PE 分位档位同样在缓存缺失时全部 None，表格里也应用 `—` 兜底，但视觉上要**和"PE分位=有效但极小"区分**——这点保留当前实现（用 `pct_level_color` 为灰色即可）。

#### 3.3.2 列重命名 / 重排

| # | 原列名 | 新列名 | 备注 |
|---|---|---|---|
| 1 | 代码 | 代码 | 不变 |
| 2 | 名称 | 名称 | 不变 |
| 3 | 指数 | 指数 | 不变 |
| 4 | 状态 | 状态 | 不变 |
| 5 | 最新价 | 最新价 | 不变 |
| 6 | 动态PE | **PE（动态）** | 加"动态" |
| 7 | 档位 | **估值档位** | 明确归属"动态PE" |
| 8 | 所属板块 | 所属行业 | 与"行业PE"呼应 |
| 9 | 板块PE | **行业PE** | 用"行业"更准确 |
| 10 | 静态PE | **PE（TTM）** | 去"P. 2"，标准财务术语 |
| 11 | PE分位 | **行业历史分位** | 明确"行业历史"语境 |
| 12 | 档位 | **分位档位** | 加"分位"前缀 |
| 13 | PB | **市净率** | 财务全称 |
| 14 | 总市值(亿) | **总市值(亿)** | 不变 |

> 顺序调整：原 11/12 在 10 之后导致 PE 估值列被分位打断；新顺序按"个股估值（动态）→ 行业对比 → 静态辅助 → 历史分位 → 估值辅助"组织：1-7、8-9、10、11-12、13-14。

**tooltip 增强**：在表格容器外增加一段小字图例（`text-[10px] text-slate-400`），逐项解释：
- 估值档位：基于动态PE分4档
- 行业PE：所属申万一级行业市值加权动态PE
- PE（TTM）：滚动12个月静态PE
- 行业历史分位：当前动态PE在所属申万一级过去10年日频PE序列中的位置
- 分位档位：基于行业历史分位的4档
- 市净率（PB）：股价 / 每股净资产

#### 3.3.3 PE 分位数据补齐

**诊断**：
- 数据层 `utils/pe_tracker.py` 计算逻辑已正确
- `PE分位 == None` 的原因：缓存 `data/sector_pe_history_cache.json` 不存在或行业样本不足
- 当前 UI 已有提示（`update_insights` 函数里的 `if pct_valid.empty` 分支），保留

**不做的**：
- 不在 UI 加"一键构建缓存"按钮（重操作，跨进程；现有"刷新数据"按钮触发的也是 daily_basic 拉取，不触发历史脚本）
- 不改 `scripts/build_sector_pe_history.py`

**做的**：
- 缓存缺失时，在图2 空态卡片里加大字号提示 + 复制命令的快捷方式（用 `ui.button('复制命令', ...)` 调用 nicegui `clipboard.write()`）
- 提示文案增加预估耗时："首次构建约 5-10 分钟（拉取申万一级行业 10 年日频数据）"

#### 3.3.4 表格与档位筛选联动

**当前状态**：上方 select 下拉是"按动态 PE 区间"和"按 PE 分位区间"两类筛选，未与表格交互。

**新设计**：
- 保留顶部 select 筛选
- **新增** aggrid 客户端侧档位徽章快捷过滤：表头右上方加 4 个小徽章（低估/偏低/偏高/高估），点击切换 active 状态，aggrid 内置 filter 应用到对应列
- 状态保存在 `state['table_level_filter']`，重置按钮恢复全部
- 选中的徽章加 `ring-2 ring-indigo-400`

**关键代码改动**：
- `render_table` 增加 `state['table_level_filter']` 引用
- 渲染时根据该 state 决定 aggrid 是否预设 filter
- 在 `render_charts` 之外但同一卡片内，增加档位徽章行

---

## 4. 数据流与状态

**state 字典变更**：
```python
state = {
    'df': None,
    'selected_index': 'all',
    'selected_action': 'all',
    'selected_level': 'all',
    'selected_percentile': 'all',
    'selected_level_view': '低估',
    'expanded_percentile_band': None,   # 新增：图2 档位展开状态
    'table_level_filter': None,         # 新增：图3 档位徽章过滤
    'loading': False,
}
```

**事件处理**：
- 图1 卡片：纯展示，不新增事件
- 图2 档位点击：触发 `on_percentile_band_toggle(band)`，更新 state，重新渲染 `_render_percentile_distribution`（仅本卡片）
- 图3 档位徽章：触发 `on_table_level_filter(level)`，更新 state，重新调用 aggrid filter API（不重渲染整个表格）

---

## 5. 错误处理

| 场景 | 当前行为 | 新行为 |
|---|---|---|
| `pe_static is None` | "Invalid Number" 错误 | 单元格显示 `—` |
| `pe_percentile is None` | 表格列显示 `—`，但分位档位列也是 `—`，与正常档位混淆 | 分位档位列在 `—` 时用 `pct_level_color='#94a3b8'`（浅灰），并加 tooltip "需构建历史PE缓存" |
| 缓存文件不存在 | 图2 显示空态卡片 | 保留并升级：增加复制命令按钮 |
| 图2 档位内联展开时该档位 0 只股票 | 当前弹窗有 "暂无股票" 提示 | 内联区显示 "该档位暂无股票" + "共 0 只" 文字 |
| 调入/调出某侧 0 只股票 | 当前 `_render_action_card` 静默 return | 改：渲染空态卡片 "本次调整无调入/调出标的"（用户可见） |

---

## 6. 测试

### 6.1 手动验证清单

启动服务后访问 PE 跟踪页，依次验证：

1. **图1 卡片**：
   - [ ] 主数字无 "倍" 字，hover 看到 "倍" 提示
   - [ ] 三个副指标 hover 显示定义
   - [ ] 卡片底部出现差值徽章 "调出−调入 = +XX.X"
   - [ ] 差值正/负/近零三种颜色对应正确
   - [ ] 调入或调出某侧 0 只时显示空态而非静默

2. **图2 分位**：
   - [ ] 4 档进度条 + 数字 + 百分比正常
   - [ ] 点击某档，下方内联展开 1 张 mini 表（≤10 行）
   - [ ] mini 表 5 列数据正确
   - [ ] 再点同一档收起
   - [ ] 点击其他档直接切换（不先收起）
   - [ ] 缓存缺失时显示空态卡片 + 复制命令按钮

3. **图3 明细**：
   - [ ] 静态 PE 列无 "Invalid Number"，None 时显示 `—`
   - [ ] 列名更新为新名字
   - [ ] 表头下方有图例说明
   - [ ] 表头右上方有 4 个档位徽章
   - [ ] 点击徽章过滤生效
   - [ ] 重置徽章恢复全部

### 6.2 回归验证

- [ ] 顶部 4 个 select 筛选仍正常工作
- [ ] 顶部「核心洞察」文本正常更新
- [ ] 导出 Excel 仍能下载（列名变化后导出表头需同步更新）
- [ ] 「刷新数据」按钮仍能触发 Tushare 拉取
- [ ] 移动端（`is_mobile=True`）布局不破

---

## 7. 实施步骤

1. 修改 `_render_action_card`（图1）：加 tooltip、加差值徽章、改主数字单位
2. 修改 `state` 字典加 2 个新键
3. 修改 `_render_percentile_distribution`（图2）：删 dialog 路径，加内联展开
4. 删除 `show_percentile_detail` 函数
5. 修改 `render_table`（图3）：修静态 PE bug、改列名、调整列顺序、加图例
6. 修改 `export_to_excel`：列名同步更新
7. 在 `render_charts` 之外、表格区之内，新增档位徽章行
8. 缓存缺失空态卡片升级：加复制命令按钮
9. 手动验证清单逐项过

---

## 8. 风险与回退

| 风险 | 缓解 |
|---|---|
| `bind_visibility` 在 nicegui 不同版本 API 不一致 | 优先尝试 `bind_visibility`，失败回退到 `set_visibility` 或重建 DOM |
| aggrid 客户端 filter API 与 v29+ 不兼容 | 退而求其次：用 `setFilterModel` 字符串配置 |
| 列重命名后用户旧截图/分享链接识别不到列 | 不属于线上模块，重命名可接受 |
| 图2 内联展开破坏移动端布局 | 增加 `is_mobile` 分支：移动端折叠成可滚动 mini table |

**回退方案**：git revert 即可。改动集中在 1 个文件，影响面可控。

---

## 9. 已确认的设计决策（来自 brainstorming 阶段）

- 图1：保留中位 PE / 平均 PE / 行业 PE / 数量，**加 tooltip 和差值徽章解释清楚**
- 图2：改为**点击档位内联展开**股票（去掉 dialog 弹窗）
- 图3：①修 "Invalid Number" bug ②**重命名/合并**难懂列 ③PE 分位数据补齐 ④表格**按档位联动**筛选
- 数据层 `utils/pe_tracker.py`：**不动**
