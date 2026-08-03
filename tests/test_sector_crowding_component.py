"""板块拥挤度组件渲染冒烟测试（headless，mock ui）。"""

import unittest
from unittest.mock import MagicMock, patch
import sys
import os

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.sector_crowding import SectorCrowding as RealSectorCrowding


def _fake_history():
    dates = pd.bdate_range('2023-08-01', periods=25)
    rows = []
    for t, d in enumerate(dates):
        # 软件服务：两融按日 1% 增长、市值按日 0.3% 增长 -> 升温；
        # 银行：两融不变、市值按日 0.5% 增长 -> 降温。
        for ind, mv0, rz0, g_rz, g_mv in (
                ('软件服务', 1e12, 4e10, 0.01, 0.003),
                ('银行', 1.5e13, 5e10, 0.0, 0.005)):
            rz = rz0 * (1 + g_rz) ** t
            mv = mv0 * (1 + g_mv) ** t
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
        fake = _fake_history()
        mock_sc.load_history.return_value = fake
        mock_sc.get_latest.return_value = (
            fake.sort_values('trade_date').groupby('industry').tail(1)
        )
        mock_sc.percentile_rank.return_value = 80.0
        mock_sc.get_industry_series.return_value = _fake_history()
        mock_sc.filter_industries_by_hierarchy.side_effect = (
            lambda l1=None, l2=None, industries=None: industries
        )
        # 与真实 SectorCrowding.precompute() 的返回结构一致
        def _precompute_result():
            # load_view() 内部会 pre.clear() 后重新 update，必须每次返回新 dict
            return {
                'df': fake,
                'dates': sorted(fake['trade_date'].unique()),
                'latest_date': fake['trade_date'].max(),
                'prev_date': fake['trade_date'].min(),
                'latest_df': (
                    fake.sort_values('trade_date').groupby('industry').tail(1)
                ),
                'prev_df': (
                    fake.sort_values('trade_date').groupby('industry').head(1)
                    .set_index('industry')[['crowding_pct']]
                ),
                'by_industry': {
                    ind: g[['trade_date', 'crowding_pct', 'financing_pct']]
                         .reset_index(drop=True)
                    for ind, g in fake.groupby('industry', sort=False)
                },
                'margin_speed': RealSectorCrowding().compute_margin_speed(df=fake),
            }
        mock_sc.precompute.side_effect = _precompute_result
        mock_sc.precompute_all_indices.return_value = {}

        # 让容器类支持 with 语法
        for name in ('row', 'column', 'card', 'element'):
            getattr(mock_ui, name).return_value.__enter__.return_value = MagicMock()

        renderer = MagicMock()
        from pages.sector_crowding_component import render_sector_crowding_panel
        render_sector_crowding_panel(plotly_renderer=renderer, is_mobile=False)

        self.assertTrue(mock_ui.card.called)
        self.assertTrue(mock_ui.html.called)
        self.assertTrue(renderer.called)
        print('板块拥挤度组件渲染成功')


if __name__ == '__main__':
    unittest.main()
