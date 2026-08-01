"""板块拥挤度组件渲染冒烟测试（headless，mock ui）。"""

import unittest
from unittest.mock import MagicMock, patch
import sys
import os

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fake_history():
    dates = pd.to_datetime(['2023-08-01', '2023-08-02', '2023-08-03'])
    rows = []
    for d in dates:
        for ind, mv, rz in (('软件服务', 1e12, 4e10), ('银行', 1.5e13, 5e10)):
            rows.append({
                'trade_date': d, 'industry': ind,
                'stock_count': 100, 'margin_stock_count': 80,
                'total_mv': mv, 'rzye': rz * 0.98, 'rqye': rz * 0.02,
                'rzrqye': rz,
                'crowding_pct': rz / mv * 100,
                'financing_pct': rz * 0.98 / mv * 100,
                'short_pct': rz * 0.02 / mv * 100,
            })
    return pd.DataFrame(rows)


class TestSectorCrowdingComponent(unittest.TestCase):

    @patch('pages.sector_crowding_component.ui')
    @patch('pages.sector_crowding_component.SectorCrowding')
    def test_render_panel(self, mock_sc_cls, mock_ui):
        mock_sc = mock_sc_cls.return_value
        mock_sc.load_history.return_value = _fake_history()
        mock_sc.get_latest.return_value = (
            _fake_history().sort_values('trade_date').groupby('industry').tail(1)
        )
        mock_sc.percentile_rank.return_value = 80.0
        mock_sc.get_industry_series.return_value = _fake_history()

        # 让容器类支持 with 语法
        for name in ('row', 'column', 'card', 'element'):
            getattr(mock_ui, name).return_value.__enter__.return_value = MagicMock()

        renderer = MagicMock()
        from pages.sector_crowding_component import render_sector_crowding_panel
        render_sector_crowding_panel(plotly_renderer=renderer, is_mobile=False)

        self.assertTrue(mock_ui.card.called)
        self.assertTrue(mock_ui.table.called)
        self.assertTrue(renderer.called)
        print('板块拥挤度组件渲染成功')


if __name__ == '__main__':
    unittest.main()
