import unittest
import datetime
from app.backend.data_fetching.models import MarketData, OptionData, OptionChain
from app.backend.strategy_engine.strategy import StrategyEngine, MIN_ENTRY_TIME

class TestStrategyEngine(unittest.TestCase):

    def _create_mock_market_data(
        self,
        spot=21000,
        vwap=21005,
        atr=100,
        current_dt=None,
        ce_options=None,
        pe_options=None
    ):
        """Helper to create MarketData for tests."""
        if current_dt is None:
            current_dt = datetime.datetime.now()

        # Default options if none provided
        if ce_options is None:
            ce_options = [
                OptionData(strike_price=20900, option_type="CE", premium=180, delta=0.7, theta=10), # ITM
                OptionData(strike_price=21000, option_type="CE", premium=120, delta=0.5, theta=12), # ATM
                OptionData(strike_price=21100, option_type="CE", premium=80, delta=0.35, theta=15), # OTM
            ]
        if pe_options is None:
            pe_options = [
                OptionData(strike_price=20900, option_type="PE", premium=70, delta=0.3, theta=14),  # OTM
                OptionData(strike_price=21000, option_type="PE", premium=110, delta=0.55, theta=11),# ATM
                OptionData(strike_price=21100, option_type="PE", premium=170, delta=0.75, theta=9), # ITM
            ]

        all_options = ce_options + pe_options
        option_chain = OptionChain(expiry_date="2023-12-28", options=all_options)

        return MarketData(
            timestamp=current_dt,
            index_name="TEST_NIFTY",
            spot_price=spot,
            vwap=vwap,
            atr=atr,
            option_chains={"2023-12-28": option_chain}
        )

    def test_entry_time_check(self):
        """Test the _is_entry_time_valid method."""
        # Time before 11:15 AM
        dt_early = datetime.datetime(2023, 1, 1, 10, 0, 0) # 10:00 AM
        md_early = self._create_mock_market_data(current_dt=dt_early)
        engine_early = StrategyEngine(md_early)
        self.assertFalse(engine_early._is_entry_time_valid())

        # Time at 11:15 AM
        dt_exact = datetime.datetime(2023, 1, 1, MIN_ENTRY_TIME.hour, MIN_ENTRY_TIME.minute, 0)
        md_exact = self._create_mock_market_data(current_dt=dt_exact)
        engine_exact = StrategyEngine(md_exact)
        self.assertTrue(engine_exact._is_entry_time_valid())

        # Time after 11:15 AM
        dt_late = datetime.datetime(2023, 1, 1, 14, 0, 0) # 02:00 PM
        md_late = self._create_mock_market_data(current_dt=dt_late)
        engine_late = StrategyEngine(md_late)
        self.assertTrue(engine_late._is_entry_time_valid())

    def test_price_near_vwap_check(self):
        """Test the _is_price_near_vwap method."""
        # Price very near VWAP
        md_near = self._create_mock_market_data(spot=21000, vwap=21005) # 0.023% diff
        engine_near = StrategyEngine(md_near)
        self.assertTrue(engine_near._is_price_near_vwap())

        # Price at VWAP
        md_at = self._create_mock_market_data(spot=21000, vwap=21000)
        engine_at = StrategyEngine(md_at)
        self.assertTrue(engine_at._is_price_near_vwap())

        # Price far from VWAP (default threshold is 0.2%)
        # spot=21000, vwap=20900. Threshold = 20900 * 0.002 = 41.8. Diff = 100.
        md_far = self._create_mock_market_data(spot=21000, vwap=20900)
        engine_far = StrategyEngine(md_far)
        self.assertFalse(engine_far._is_price_near_vwap())

        # VWAP is None
        md_no_vwap = self._create_mock_market_data(spot=21000, vwap=None)
        engine_no_vwap = StrategyEngine(md_no_vwap)
        self.assertFalse(engine_no_vwap._is_price_near_vwap())


    def test_strike_suggestion_time_rejection(self):
        """Test strike suggestion is rejected if time is before 11:15 AM."""
        dt_early = datetime.datetime(2023, 1, 1, 10, 0, 0) # 10:00 AM
        md = self._create_mock_market_data(current_dt=dt_early, vwap=21000, spot=21000) # VWAP ok
        engine = StrategyEngine(md)
        suggestion = engine.suggest_strike(option_type="CE")
        self.assertIsNone(suggestion["option"])
        self.assertIn("not recommended before", suggestion["justification"])

    def test_strike_suggestion_vwap_rejection(self):
        """Test strike suggestion is rejected if price not near VWAP."""
        dt_valid = datetime.datetime(2023, 1, 1, 12, 0, 0) # Valid time
        md = self._create_mock_market_data(current_dt=dt_valid, spot=21000, vwap=20900) # VWAP not ok
        engine = StrategyEngine(md)
        suggestion = engine.suggest_strike(option_type="CE")
        self.assertIsNone(suggestion["option"])
        self.assertIn("Price is not near VWAP", suggestion["justification"])

    def test_strike_suggestion_low_volatility(self):
        """Test CE strike suggestion for low volatility (expects ~0.5-0.6 Delta)."""
        dt_valid = datetime.datetime(2023, 1, 1, 12, 0, 0)
        # ATR = 80, Spot = 21000. ATR/Spot = 0.0038, which is < 0.005 (our threshold for high vol) -> low vol
        # Expected Delta range for low vol: (0.5, 0.6)
        ce_opts = [
            OptionData(strike_price=20900, option_type="CE", premium=180, delta=0.7), # Too high delta
            OptionData(strike_price=21000, option_type="CE", premium=120, delta=0.52),# Expected
            OptionData(strike_price=21100, option_type="CE", premium=80, delta=0.35)  # Too low delta
        ]
        md = self._create_mock_market_data(current_dt=dt_valid, spot=21000, vwap=21000, atr=80, ce_options=ce_opts)
        engine = StrategyEngine(md)
        suggestion = engine.suggest_strike(option_type="CE", risk_profile="moderate")

        self.assertIsNotNone(suggestion["option"])
        self.assertEqual(suggestion["option"].strike_price, 21000)
        self.assertEqual(suggestion["option"].delta, 0.52)
        self.assertIn("Market volatility assessed as low to moderate", suggestion["justification"])

    def test_strike_suggestion_high_volatility(self):
        """Test PE strike suggestion for high volatility (expects ~0.3-0.35 Delta)."""
        dt_valid = datetime.datetime(2023, 1, 1, 12, 0, 0)
        # ATR = 150, Spot = 21000. ATR/Spot = 0.0071, which is > 0.005 -> high vol
        # Expected Delta range for high vol: (0.3, 0.35)
        pe_opts = [
            OptionData(strike_price=20800, option_type="PE", premium=60, delta=0.33), # Expected (abs delta)
            OptionData(strike_price=20900, option_type="PE", premium=90, delta=0.45), # Too high delta
            OptionData(strike_price=21000, option_type="PE", premium=120, delta=0.55) # Too high delta
        ]
        md = self._create_mock_market_data(current_dt=dt_valid, spot=21000, vwap=21000, atr=150, pe_options=pe_opts)
        engine = StrategyEngine(md)
        # Note: StrategyEngine uses abs(delta) for PE as well for range checks,
        # but the stored delta on OptionData might be positive or negative based on convention.
        # Our mock_data_source currently provides positive deltas for PEs.
        suggestion = engine.suggest_strike(option_type="PE", risk_profile="moderate")

        self.assertIsNotNone(suggestion["option"])
        self.assertEqual(suggestion["option"].strike_price, 20800)
        self.assertEqual(suggestion["option"].delta, 0.33)
        self.assertIn("Market volatility assessed as high", suggestion["justification"])

    def test_no_suitable_option_found(self):
        """Test scenario where no option meets the delta criteria."""
        dt_valid = datetime.datetime(2023, 1, 1, 12, 0, 0)
        ce_opts = [ # All deltas are too low for "low volatility" criteria
            OptionData(strike_price=21100, option_type="CE", premium=20, delta=0.22),
            OptionData(strike_price=21200, option_type="CE", premium=10, delta=0.15), # Delta < MIN_DELTA_THRESHOLD
        ]
        md = self._create_mock_market_data(current_dt=dt_valid, spot=21000, vwap=21000, atr=80, ce_options=ce_opts) # Low vol
        engine = StrategyEngine(md)
        suggestion = engine.suggest_strike(option_type="CE")

        self.assertIsNone(suggestion["option"])
        self.assertIn("No option found matching Delta criteria", suggestion["justification"])

    def test_spread_recommendation_placeholder(self):
        """Test the placeholder spread recommendation logic."""
        dt_valid = datetime.datetime(2023, 1, 1, 12, 0, 0)
        md = self._create_mock_market_data(current_dt=dt_valid)
        engine = StrategyEngine(md)

        # Option with high theta
        base_opt_high_theta = OptionData(strike_price=21000, option_type="CE", premium=120, delta=0.5, theta=15)
        spread_rec_high = engine.recommend_spread_trade(base_opt_high_theta, risk_tolerance_loss=1000)
        self.assertTrue(spread_rec_high["spread_needed"])
        self.assertIn("placeholder", spread_rec_high["message"].lower())

        # Option with low theta
        base_opt_low_theta = OptionData(strike_price=20900, option_type="PE", premium=70, delta=0.3, theta=5) # Theta <= 10
        spread_rec_low = engine.recommend_spread_trade(base_opt_low_theta, risk_tolerance_loss=1000)
        self.assertFalse(spread_rec_low["spread_needed"])
        self.assertIn("Theta is not high enough", spread_rec_low["message"])

if __name__ == '__main__':
    unittest.main()
