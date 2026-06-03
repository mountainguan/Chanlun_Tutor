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
        # 必须出现在 state 字典定义块里（不是注释/docstring/str 字面量）
        # 使用 re.search + DOTALL（assertRegex 不支持 flags 参数）
        self.assertIsNotNone(
            re.search(r"state\s*=\s*\{[^}]*?'expanded_percentile_band'", src, re.DOTALL),
            "'expanded_percentile_band' 不在 state 字典定义块中",
        )

    def test_state_has_table_level_filter(self):
        src = read_source()
        self.assertIsNotNone(
            re.search(r"state\s*=\s*\{[^}]*?'table_level_filter'", src, re.DOTALL),
            "'table_level_filter' 不在 state 字典定义中",
        )

    def test_no_show_percentile_detail_function(self):
        """重构后应删除弹窗函数（容忍 def 与名字之间的任意空白）。"""
        src = read_source()
        self.assertNotRegex(src, r'def\s+show_percentile_detail')

    def test_columns_renamed(self):
        src = read_source()
        # 新列名必须出现（静态 PE 列已被用户 WIP 移除，不再要求 PE（TTM））
        for name in ['PE（动态）', '行业PE', '行业历史分位', '估值档位', '分位档位', '所属行业', '市净率']:
            self.assertIn(name, src, f'列名 "{name}" 未找到')

    def test_old_column_names_removed(self):
        src = read_source()
        # Task 4 will rename 板块PE -> 行业PE 等
        self.assertNotIn('板块PE', src, '旧列名 板块PE 仍存在，应已重命名为 行业PE')

    def test_pb_field_handles_none(self):
        """rows.append 块中 pb 字段必须有显式 None 规范化。

        当前代码是 `round(row.get('PB', 0), 2) if row.get('PB', 0) else 0`，
        当 PB 缺失时 round(0,2) == 0.0 然后被 aggrid 当作合法数值 0 显示，
        缺少 None 兜底会导致未来 PB 字段语义错误时无信号。
        """
        src = read_source()
        # 必须有显式的 None 规范化，Task 3 约定字段名为 pb / pb_val
        self.assertRegex(
            src,
            r"['\"]pb['\"]\s*:\s*pb_val"
        )

    def test_diff_badge_appears(self):
        """差值徽章文案应出现（f-string 模板 + 差值公式 + 三种语义标签）。"""
        src = read_source()
        # 模板用 f-string 插值，源码里只有占位符 {other_action}−{action}
        self.assertRegex(
            src,
            r"\{other_action\}−\{action\}",
            "差值徽章 f-string 模板未找到",
        )
        # 差值公式 = 另一侧中位PE - 当前中位PE
        self.assertRegex(
            src,
            r"diff\s*=\s*other_median\s*-\s*median_pe",
            "差值公式 other_median - median_pe 未找到",
        )
        # 三种语义标签（高剔低纳 / 差异不大 / 反向）
        for phrase in ['高剔低纳', '差异不大', '反向']:
            self.assertIn(phrase, src, f"差值徽章语义文案 '{phrase}' 未找到")

    def test_no_unit_in_main_number(self):
        """主数字旁的 '倍' 标签应降为辅助样式（不与主数字争夺视觉）。"""
        src = read_source()
        # 旧的显式 '倍'（text-sm text-slate-500）应已替换为低饱和样式或置于 tooltip 内
        self.assertNotRegex(
            src,
            r"ui\.label\(\s*['\"]倍['\"]\s*\)\.classes\(\s*['\"][^'\"]*text-slate-500[^'\"]*['\"]\s*\)"
        )

    def test_cell_renderer_uses_colon_prefix(self):
        """cellRenderer 字符串需 ':' 前缀才会被 NiceGUI 转换为 JS 函数。

        不带 ':' 时，aggrid 收到的是字符串而不是函数，回退到默认 valueFormatter，
        导致数字列出现 'Invalid Number'、level/percentile 等彩色徽章列退化为空或 'Invalid Number'。
        修复：所有 6 处 cellRenderer 都必须使用 ':cellRenderer'。
        """
        src = read_source()
        # 没有任何不带 ':' 前缀的 cellRenderer（注释里的不算，但本源码无该注释）
        self.assertNotRegex(
            src,
            r"['\"]cellRenderer['\"]\s*:",
            "发现不带 ':' 前缀的 cellRenderer——NiceGUI 不会把它当函数传给 aggrid，"
            "会导致表格回退到默认 valueFormatter（数字列出现 'Invalid Number'）。",
        )
        # 至少出现 6 次 ':cellRenderer'（状态/PE（动态）/估值档位/行业历史分位/分位档位/市净率）
        self.assertGreaterEqual(
            src.count("':cellRenderer'"),
            6,
            "':cellRenderer' 数量不足，6 个有渲染器的列都必须带 ':' 前缀",
        )

    def test_pe_dynamic_has_cell_renderer(self):
        """PE（动态）列必须有 cellRenderer 以处理 None/NaN（显示 '—'）。

        否则默认 valueFormatter 对 None 返回空字符串，导致前几页（按 PE 升序排，None 排到末尾）
        和 NaN 行（PE Tushare 缺失时返回 NaN）显示为空。
        """
        src = read_source()
        # PE（动态）columnDefs 块中紧邻必须出现 ':cellRenderer'（assertRegex 不支持 flags，用 re.search+DOTALL）
        self.assertIsNotNone(
            re.search(
                r"['\"]headerName['\"]\s*:\s*['\"]PE（动态）['\"].*?:cellRenderer",
                src,
                re.DOTALL,
            ),
            "PE（动态）列缺少 :cellRenderer，无法处理 None/NaN 兜底",
        )


if __name__ == '__main__':
    unittest.main()
