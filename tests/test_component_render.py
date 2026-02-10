
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import sys
import os
import asyncio

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages.social_security_component import render_social_security_panel

class TestSocialSecurityComponent(unittest.TestCase):
    
    @patch('pages.social_security_component.ui')
    @patch('pages.social_security_component.SocialSecurityFund')
    def test_render_logic(self, mock_ssf_cls, mock_ui):
        # Mock SSF instance and method
        mock_ssf = mock_ssf_cls.return_value
        
        # Create dummy dataframe
        df = pd.DataFrame({
            '股票代码': ['000001', '000002'],
            '股票简称': ['平安银行', '万科A'],
            '持股市值': [100000000.0, 50000000.0],
            '持股总数': [1000000, 500000],
            '持股变动比例': [10.5, -2.1]
        })
        mock_ssf.get_latest_holdings.return_value = df
        mock_ssf.get_new_positions.return_value = pd.DataFrame()

        # Mock UI elements
        mock_ui.row.return_value.__enter__.return_value = MagicMock()
        mock_ui.column.return_value.__enter__.return_value = MagicMock()
        mock_ui.card.return_value.__enter__.return_value = MagicMock()
        mock_ui.element.return_value.__enter__.return_value = MagicMock() # For containers
        
        # Call the render function
        # Note: This won't execute the async load_data inside the timer unless we simulate it
        # But it will execute the layout construction code
        plotly_renderer = MagicMock()
        render_social_security_panel(plotly_renderer)
        
        # Check if UI elements were called (basic layout check)
        self.assertTrue(mock_ui.row.called)
        self.assertTrue(mock_ui.card.called)
        self.assertTrue(mock_ui.element.called)

        print("✅ Components Layout rendered successfully")

        # Now let's try to test the load_data logic by extracting it or simulating the timer callback
        # Since load_data is internal, we can't call it directly easily.
        # But we can verify that ui.timer was called with a lambda/function
        self.assertTrue(mock_ui.timer.called)
        args, kwargs = mock_ui.timer.call_args
        callback = args[1]
        
        # We can't easily run the async callback here without an event loop and un-nesting.
        # For now, layout verification is good enough for a "smoke test".

if __name__ == '__main__':
    unittest.main()
