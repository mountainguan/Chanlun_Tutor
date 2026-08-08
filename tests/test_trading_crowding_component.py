"""成交集中度拥挤度组件渲染冒烟测试（headless，mock ui）。"""

import unittest
from unittest.mock import MagicMock, patch
import sys
import os
from types import SimpleNamespace

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fake_industry_history():
    dates = pd.to_datetime(['2026-01-05', '2026-01-06', '2026-01-07'])
    rows = []
    for d in dates:
        for ind, vol_conc, amt_conc in (('软件服务', 46.5, 40.0),
                                        ('银行', 30.0, 35.0)):
            rows.append({
                'trade_date': d, 'industry': ind, 'stock_count': 100,
                'total_vol': 1e8, 'top5_vol': 4.65e7,
                'vol_concentration_pct': vol_conc,
                'total_amount': 1e7, 'top5_amount': 4e6,
                'amount_concentration_pct': amt_conc,
            })
    return pd.DataFrame(rows)


def _fake_index_history():
    dates = pd.to_datetime(['2026-01-05', '2026-01-06', '2026-01-07'])
    rows = []
    for d in dates:
        rows.append({
            'trade_date': d, 'index_code': '000300', 'index_name': '沪深300',
            'stock_count': 288, 'coverage': 100.0,
            'total_vol': 1e9, 'top5_vol': 3e8, 'vol_concentration_pct': 30.0,
            'total_amount': 1e8, 'top5_amount': 3e7,
            'amount_concentration_pct': 30.0,
        })
        rows.append({
            'trade_date': d, 'index_code': 'ALL', 'index_name': '全A',
            'stock_count': 5000, 'coverage': 100.0,
            'total_vol': 1e10, 'top5_vol': 4.6e9,
            'vol_concentration_pct': 46.0,
            'total_amount': 1e9, 'top5_amount': 4.5e8,
            'amount_concentration_pct': 45.0,
        })
    return pd.DataFrame(rows)


def _fake_pre(fake):
    dates = sorted(fake['trade_date'].unique())
    latest = dates[-1]
    prev = dates[0]
    return {
        'df': fake,
        'dates': dates,
        'latest_date': latest,
        'prev_date': prev,
        'latest_df': fake[fake['trade_date'] == latest].copy(),
        'prev_df': fake[fake['trade_date'] == prev].set_index('industry')[
            ['vol_concentration_pct', 'amount_concentration_pct']],
        'by_industry': {
            ind: g.sort_values('trade_date')[
                ['trade_date', 'vol_concentration_pct', 'amount_concentration_pct']
            ].reset_index(drop=True)
            for ind, g in fake.groupby('industry', sort=False)
        },
    }


class TestTradingCrowdingComponent(unittest.TestCase):

    @patch('pages.sector_crowding_component.ui')
    @patch('pages.sector_crowding_component.SectorCrowding')
    @patch('pages.sector_crowding_component.TradingCrowding')
    def test_render_trading_content(self, mock_tc_cls, mock_sc_cls, mock_ui):
        fake = _fake_industry_history()
        fake_idx = _fake_index_history()
        mock_tc = mock_tc_cls.return_value
        # load_view() 内部会 pre.clear() 后重新 update，必须每次返回新对象
        mock_tc.precompute.side_effect = lambda: _fake_pre(fake)
        mock_tc.precompute_indices.side_effect = (
            lambda: {'000300': ('沪深300',
                                fake_idx[fake_idx['index_code'] == '000300']),
                     'ALL': ('全A', fake_idx[fake_idx['index_code'] == 'ALL'])}
        )
        mock_sc = mock_sc_cls.return_value
        mock_sc.get_industry_hierarchy.return_value = {
            'l1_list': ['全部'],
            'l1_to_l2_to_csrc': {},
        }
        mock_sc_cls.percentile_rank.return_value = 80.0
        mock_sc.filter_industries_by_hierarchy.side_effect = (
            lambda l1=None, l2=None, industries=None: industries
        )

        for name in ('row', 'column', 'card', 'element'):
            getattr(mock_ui, name).return_value.__enter__.return_value = MagicMock()

        renderer = MagicMock()
        from pages.sector_crowding_component import render_trading_content
        render_trading_content(plotly_renderer=renderer, is_mobile=False,
                               dimension='vol')

        self.assertTrue(mock_ui.card.called)
        self.assertTrue(mock_ui.html.called)
        self.assertTrue(renderer.called)
        print('成交集中度拥挤度组件渲染成功')


class TestTradingCrowdingListeners(unittest.TestCase):
    """回归测试：成交集中度面板的事件监听必须按客户端注册并路由。
    之前用全局只注册一次，浏览器刷新（新客户端）后点击行业/指数图表不再切换。"""

    def test_listeners_register_per_client(self):
        import pages.sector_crowding_component as m
        m._tc_listener_clients.clear()
        m._tc_client_states.clear()
        with patch('pages.sector_crowding_component.ui') as mock_ui:
            cids = iter(['client-a', 'client-a', 'client-b'])
            with patch.object(m, '_tc_current_client_id',
                              side_effect=lambda: next(cids)):
                m._register_tc_listeners()  # client-a 首次 -> 注册
                m._register_tc_listeners()  # client-a 重复 -> 跳过
                m._register_tc_listeners()  # client-b -> 再次注册
            event_types = [c.args[0] for c in mock_ui.on.call_args_list]
            self.assertEqual(event_types.count('tc_row_click'), 2)
            self.assertEqual(event_types.count('tc_index_click'), 2)

    def test_client_state_routing(self):
        import pages.sector_crowding_component as m
        m._tc_listener_clients.clear()
        m._tc_client_states.clear()
        with patch('pages.sector_crowding_component.ui') as mock_ui:
            with patch.object(m, '_tc_current_client_id',
                              return_value='client-a'):
                m._register_tc_listeners()
            row_handler = None
            for args in mock_ui.on.call_args_list:
                if args.args[0] == 'tc_row_click':
                    row_handler = args.args[1]
            self.assertIsNotNone(row_handler)

            calls = []
            m._set_tc_client_state(
                'client-a',
                lambda ind, scroll=False: calls.append(('a', ind, scroll)),
                lambda code: None,
            )
            row_handler(SimpleNamespace(args={'industry': '软件服务'}))
            self.assertEqual(calls, [('a', '软件服务', True)])

            # 该客户端无渲染状态时，点击静默跳过（不抛错）
            m._tc_client_states.pop('client-a', None)
            row_handler(SimpleNamespace(args={'industry': '银行'}))
            self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
