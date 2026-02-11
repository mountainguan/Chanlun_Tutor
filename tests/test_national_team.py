import datetime
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from utils.national_team import NationalTeamSelector


class TestNationalTeamSelector(unittest.TestCase):
    def test_selection_and_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            selector = NationalTeamSelector(data_dir=tmpdir, cache_ttl=3600)
            holdings = pd.DataFrame([
                {'股票代码': '000001', '股票简称': '平安银行', '持股市值': 2000000000},
                {'股票代码': '000002', '股票简称': '万科A', '持股市值': 1000000000},
            ])
            sectors = pd.DataFrame([
                {'名称': '白色家电', '净流入': 5.2},
                {'名称': '医药医疗', '净流入': -1.0},
            ])
            info_df1 = pd.DataFrame([{'item': '所属行业', 'value': '白色家电'}])
            info_df2 = pd.DataFrame([{'item': '所属行业', 'value': '医药医疗'}])
            dates = pd.date_range(end=datetime.date(2026, 2, 11), periods=30, freq='D')
            hist_df = pd.DataFrame({'日期': dates, '收盘': list(range(1, 31))})
            with patch('utils.national_team.SocialSecurityFund.get_latest_holdings', return_value=holdings), \
                 patch('utils.national_team.FundRadar.get_multi_day_data', return_value=(sectors, ['THS 5日直取'])), \
                 patch('utils.national_team.ak.stock_individual_info_em', side_effect=[info_df1, info_df2]) as mock_info, \
                 patch('utils.national_team.ak.stock_zh_a_daily', return_value=hist_df) as mock_hist:
                df, meta = selector.get_selection(days=5, fund_type='social_security', date_str='2026-02-11')
                self.assertEqual(len(df), 1)
                self.assertEqual(df.iloc[0]['股票代码'], '000001')
                self.assertTrue(mock_info.call_count >= 2)
                # 现在无论是否过滤，都会获取所有持仓股票的行情数据（2只）
                self.assertTrue(mock_hist.call_count >= 2) 
                
                df2, _ = selector.get_selection(days=5, fund_type='social_security', date_str='2026-02-11')
                self.assertEqual(len(df2), 1)
                self.assertEqual(mock_info.call_count, 2)
                # 第二次调用时应该使用缓存，所以调用次数不应该增加
                self.assertEqual(mock_hist.call_count, 2)
                self.assertIn('date', meta)
