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
        # 新列名必须出现
        for name in ['PE（动态）', 'PE（TTM）', '行业PE', '行业历史分位', '估值档位', '分位档位', '所属行业', '市净率']:
            self.assertIn(name, src, f'列名 "{name}" 未找到')

    def test_old_column_names_removed(self):
        src = read_source()
        # Task 3/4 will rename 静态PE -> PE（TTM） and related
        self.assertNotIn('静态PE', src, '旧列名 静态PE 仍存在，应已重命名为 PE（TTM）')

    def test_static_pe_none_handled(self):
        """rows.append 块中 pe_static 字段必须有显式 None 规范化。"""
        src = read_source()
        # pe_static 字段的 None 规范化（Task 3 约定字段名为 pe_static / pe_static_val）
        self.assertRegex(
            src,
            r"['\"]pe_static['\"]\s*:\s*pe_static_val"
        )

    def test_diff_badge_appears(self):
        """差值徽章文案应出现。"""
        src = read_source()
        self.assertIn('调出−调入', src)

    def test_no_unit_in_main_number(self):
        """主数字旁不应再独立出现 '倍' 标签。"""
        src = read_source()
        self.assertNotRegex(src, r"ui\.label\(\s*['\"]倍['\"]\s*\)")


if __name__ == '__main__':
    unittest.main()
