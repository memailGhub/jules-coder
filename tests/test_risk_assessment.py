import unittest
import datetime
from app.backend.data_fetching.models import MarketData, OptionData, OptionChain
from app.backend.risk_assessment.risk_models import UserRiskProfile, RiskAssessmentOutput
from app.backend.risk_assessment.assessment import RiskAssessor, INDEX_LOT_SIZES, HIGH_THETA_THRESHOLD

class TestRiskAssessment(unittest.TestCase):

    def _create_mock_market_data(
        self,
        index_name="TEST_NIFTY",
        spot=21000,
        atr=100,
        options=None
    ):
        """Helper to create MarketData for risk assessment tests."""
        if options is None:
            options = [ # Default options for a chain
                OptionData(strike_price=20800, option_type="CE", premium=200, delta=0.8, theta=8),
                OptionData(strike_price=20900, option_type="CE", premium=150, delta=0.65, theta=10),
                OptionData(strike_price=21000, option_type="CE", premium=100, delta=0.5, theta=12), # ATM CE
                OptionData(strike_price=21100, option_type="CE", premium=60, delta=0.35, theta=15), # OTM CE
                OptionData(strike_price=21200, option_type="CE", premium=30, delta=0.2, theta=18),  # Far OTM CE
                OptionData(strike_price=21300, option_type="CE", premium=15, delta=0.12, theta=10), # Cheaper Far OTM CE
                OptionData(strike_price=21400, option_type="CE", premium=8, delta=0.05, theta=8),   # Too low delta

                OptionData(strike_price=20800, option_type="PE", premium=50, delta=0.25, theta=16), # OTM PE
                OptionData(strike_price=20900, option_type="PE", premium=90, delta=0.4, theta=13),  # Near OTM PE
                OptionData(strike_price=21000, option_type="PE", premium=130, delta=0.52, theta=11),# ATM PE
            ]

        option_chain = OptionChain(expiry_date="2024-01-25", options=options)
        return MarketData(
            timestamp=datetime.datetime.now(),
            index_name=index_name,
            spot_price=spot,
            vwap=spot + 5, # Assume VWAP is close
            atr=atr,
            option_chains={"2024-01-25": option_chain}
        )

    def test_calculate_max_loss(self):
        """Test the _calculate_max_loss method."""
        market_data = self._create_mock_market_data(index_name="NIFTY") # Lot size 50
        user_profile = UserRiskProfile(max_loss_per_trade=1000) # Not used directly here
        assessor = RiskAssessor(market_data, user_profile)

        option1 = OptionData(strike_price=21000, option_type="CE", premium=50, delta=0.5)
        self.assertEqual(assessor._calculate_max_loss(option1), 50 * INDEX_LOT_SIZES["NIFTY"])

        market_data_bn = self._create_mock_market_data(index_name="BANKNIFTY") # Lot size 15
        assessor_bn = RiskAssessor(market_data_bn, user_profile)
        option2 = OptionData(strike_price=45000, option_type="PE", premium=100, delta=0.5)
        self.assertEqual(assessor_bn._calculate_max_loss(option2), 100 * INDEX_LOT_SIZES["BANKNIFTY"])

        market_data_default = self._create_mock_market_data(index_name="UNKNOWN_INDEX") # Lot size 1 (default)
        assessor_default = RiskAssessor(market_data_default, user_profile)
        option3 = OptionData(strike_price=100, option_type="CE", premium=10, delta=0.5)
        self.assertEqual(assessor_default._calculate_max_loss(option3), 10 * INDEX_LOT_SIZES["DEFAULT"])


    def test_suggestion_within_risk_tolerance(self):
        """Test when initial suggestion is within user's max loss tolerance."""
        market_data = self._create_mock_market_data() # TEST_NIFTY, lot 50
        user_profile = UserRiskProfile(max_loss_per_trade=5000) # Max loss 5000
        assessor = RiskAssessor(market_data, user_profile)

        # Premium 100 * lot 50 = 5000. Max loss equals tolerance.
        initial_opt = OptionData(strike_price=21000, option_type="CE", premium=100, delta=0.5, theta=12)
        assessment = assessor.assess_trade_risk(initial_opt)

        self.assertTrue(assessment.is_trade_recommended)
        self.assertEqual(assessment.original_suggestion, initial_opt)
        self.assertIsNone(assessment.adjusted_suggestion)
        self.assertEqual(assessment.max_loss_on_suggestion, 100 * INDEX_LOT_SIZES["TEST_NIFTY"])
        self.assertTrue(any(f"Max loss for suggestion ({assessment.max_loss_on_suggestion:.2f}) is within user's tolerance" in n for n in assessment.notes))
        self.assertTrue(any(f"High Theta ({initial_opt.theta:.2f})" in w for w in assessment.warnings))


    def test_suggestion_exceeds_risk_finds_alternative(self):
        """Test when initial suggestion exceeds max loss, but a suitable alternative is found."""
        market_data = self._create_mock_market_data() # TEST_NIFTY, lot 50. Spot 21000
        # Options include: 21100 CE @ 60 (3000 loss), 21200 CE @ 30 (1500 loss), 21300 CE @ 15 (750 loss)
        user_profile = UserRiskProfile(max_loss_per_trade=1000) # Max loss 1000 (i.e. premium <= 20)
        assessor = RiskAssessor(market_data, user_profile)

        # Initial suggestion: Premium 60 (3000 loss) - too high
        initial_opt = OptionData(strike_price=21100, option_type="CE", premium=60, delta=0.35, theta=15)
        assessment = assessor.assess_trade_risk(initial_opt)

        self.assertTrue(assessment.is_trade_recommended)
        self.assertEqual(assessment.original_suggestion, initial_opt)
        self.assertIsNotNone(assessment.adjusted_suggestion)
        self.assertEqual(assessment.adjusted_suggestion.strike_price, 21300) # CE @ 15
        self.assertEqual(assessment.adjusted_suggestion.premium, 15)
        self.assertEqual(assessment.max_loss_on_suggestion, 15 * INDEX_LOT_SIZES["TEST_NIFTY"]) # 750
        self.assertTrue(any("Original suggestion (Strike: 21100 CE, Premium: 60.00) has max loss of 3000.00" in w for w in assessment.warnings))
        self.assertTrue(any("Adjusted to alternative: Strike 21300 CE, Premium 15.00, Max Loss 750.00" in w for w in assessment.warnings))

    def test_suggestion_exceeds_risk_no_alternative_delta_too_low(self):
        """Test risky suggestion, alternative exists but its delta is too low (based on internal threshold)."""
        market_data = self._create_mock_market_data() # TEST_NIFTY, lot 50. Spot 21000
        # Cheaper options: 21300 CE @ 15 (delta 0.12), 21400 CE @ 8 (delta 0.05)
        user_profile = UserRiskProfile(max_loss_per_trade=500) # Max loss 500 (premium <= 10)
        assessor = RiskAssessor(market_data, user_profile)

        initial_opt = OptionData(strike_price=21200, option_type="CE", premium=30, delta=0.2, theta=18) # 1500 loss
        assessment = assessor.assess_trade_risk(initial_opt)

        # _find_alternative_option searches for options with delta >= 0.1
        # 21300 CE @ 15 (delta 0.12) -> 750 loss (still too high)
        # 21400 CE @ 8 (delta 0.05) -> 400 loss (OK by budget, but delta < 0.1, so rejected by _find_alternative_option)
        # So, no *valid* alternative should be found.

        self.assertFalse(assessment.is_trade_recommended)
        self.assertEqual(assessment.original_suggestion, initial_opt)
        self.assertIsNone(assessment.adjusted_suggestion) # No valid alternative found
        self.assertEqual(assessment.max_loss_on_suggestion, initial_opt.premium * INDEX_LOT_SIZES["TEST_NIFTY"])
        self.assertTrue(any("No suitable alternative option found within risk budget." in w for w in assessment.warnings))


    def test_suggestion_exceeds_risk_no_alternative_premium_still_high(self):
        """Test risky suggestion, OTM alternatives exist but still exceed max_loss_per_trade."""
        # Options: 21100 CE @ 60 (3000), 21200 CE @ 30 (1500), 21300 CE @ 15 (750)
        market_data = self._create_mock_market_data()
        user_profile = UserRiskProfile(max_loss_per_trade=700) # Max loss 700 (premium <= 14)
        assessor = RiskAssessor(market_data, user_profile)

        initial_opt = OptionData(strike_price=21000, option_type="CE", premium=100, delta=0.5, theta=12) # 5000 loss
        assessment = assessor.assess_trade_risk(initial_opt)

        # _find_alternative_option will check 21100 (3000 loss), 21200 (1500 loss), 21300 (750 loss).
        # All are > 700. So no alternative should be chosen.
        self.assertFalse(assessment.is_trade_recommended)
        self.assertEqual(assessment.original_suggestion, initial_opt)
        self.assertIsNone(assessment.adjusted_suggestion)
        self.assertTrue(any("No suitable alternative option found within risk budget." in w for w in assessment.warnings))


    def test_atr_warning(self):
        """Test that ATR warning is generated if ATR is high."""
        # ATR > spot * 0.005 (21000 * 0.005 = 105)
        market_data_high_atr = self._create_mock_market_data(atr=150)
        user_profile = UserRiskProfile(max_loss_per_trade=10000) # High tolerance
        assessor = RiskAssessor(market_data_high_atr, user_profile)

        initial_opt = OptionData(strike_price=21000, option_type="CE", premium=100, delta=0.5, theta=8)
        assessment = assessor.assess_trade_risk(initial_opt)
        self.assertTrue(assessment.is_trade_recommended)
        self.assertTrue(any(f"Market ATR ({market_data_high_atr.atr:.2f}) is relatively high" in w for w in assessment.warnings))

        market_data_low_atr = self._create_mock_market_data(atr=50)
        assessor_low_atr = RiskAssessor(market_data_low_atr, user_profile)
        assessment_low_atr = assessor_low_atr.assess_trade_risk(initial_opt)
        self.assertFalse(any(f"Market ATR" in w for w in assessment_low_atr.warnings))


    def test_no_initial_suggestion(self):
        """Test handling when no initial suggestion is provided."""
        market_data = self._create_mock_market_data()
        user_profile = UserRiskProfile(max_loss_per_trade=1000)
        assessor = RiskAssessor(market_data, user_profile)

        assessment = assessor.assess_trade_risk(None) # type: ignore

        self.assertFalse(assessment.is_trade_recommended)
        self.assertIsNone(assessment.original_suggestion)
        self.assertEqual(assessment.max_loss_on_suggestion, 0)
        self.assertTrue(any("No initial suggestion provided" in w for w in assessment.warnings))

    def test_theta_warning(self):
        """Test theta warning generation."""
        market_data = self._create_mock_market_data(atr=50) # Low ATR to avoid that warning
        user_profile = UserRiskProfile(max_loss_per_trade=10000) # High tolerance
        assessor = RiskAssessor(market_data, user_profile)

        # Theta > HIGH_THETA_THRESHOLD (10.0)
        opt_high_theta = OptionData(strike_price=21000, option_type="CE", premium=100, delta=0.5, theta=15)
        assessment_high = assessor.assess_trade_risk(opt_high_theta)
        self.assertTrue(assessment_high.is_trade_recommended)
        self.assertTrue(any(f"High Theta ({opt_high_theta.theta:.2f})" in w for w in assessment_high.warnings))

        # Theta <= HIGH_THETA_THRESHOLD
        opt_low_theta = OptionData(strike_price=21000, option_type="CE", premium=100, delta=0.5, theta=8)
        assessment_low = assessor.assess_trade_risk(opt_low_theta)
        self.assertTrue(assessment_low.is_trade_recommended)
        self.assertFalse(any("High Theta" in w for w in assessment_low.warnings))


if __name__ == '__main__':
    unittest.main()
