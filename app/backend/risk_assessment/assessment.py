from typing import Optional, List, Dict, Any
from app.backend.data_fetching.models import OptionData, MarketData, OptionChain
from app.backend.risk_assessment.risk_models import UserRiskProfile, RiskAssessmentOutput

# It's often necessary to know the lot size for an index to calculate actual monetary loss from premium.
# This should ideally come from a configuration or a more dynamic source.
INDEX_LOT_SIZES: Dict[str, int] = {
    "NIFTY": 50,
    "BANKNIFTY": 15,
    "TEST_NIFTY": 50, # For testing
    "DEFAULT": 1 # Fallback, assumes premium is direct monetary loss if index not found
}

# Threshold for considering Theta "high"
HIGH_THETA_THRESHOLD = 10.0 # As defined in strategy requirements

class RiskAssessor:
    """
    Assesses the risk of a given trading suggestion based on user's profile
    and current market conditions.
    """

    def __init__(self, market_data: MarketData, user_profile: UserRiskProfile):
        """
        Initializes the RiskAssessor.

        Args:
            market_data (MarketData): Current market data.
            user_profile (UserRiskProfile): User's risk tolerance parameters.
        """
        if not market_data:
            raise ValueError("MarketData cannot be None for RiskAssessor.")
        if not user_profile:
            raise ValueError("UserRiskProfile cannot be None for RiskAssessor.")

        self.market_data = market_data
        self.user_profile = user_profile
        self.lot_size = INDEX_LOT_SIZES.get(self.market_data.index_name.upper(), INDEX_LOT_SIZES["DEFAULT"])

    def _calculate_max_loss(self, option: OptionData) -> float:
        """
        Calculates the maximum potential loss for buying a single lot of the given option.
        For long calls/puts, this is the premium paid * lot_size.
        Assumes 1 lot for now. Position sizing is a separate step.
        """
        if not option:
            return 0.0
        return option.premium * self.lot_size

    def assess_trade_risk(self, initial_suggestion: OptionData) -> RiskAssessmentOutput:
        """
        Assesses a single option trade suggestion against the user's risk profile.

        Args:
            initial_suggestion (OptionData): The option suggested by the StrategyEngine.

        Returns:
            RiskAssessmentOutput: The outcome of the risk assessment.
        """
        warnings: List[str] = []
        notes: List[str] = []
        is_trade_recommended = True
        adjusted_suggestion: Optional[OptionData] = initial_suggestion

        if not initial_suggestion:
            warnings.append("No initial suggestion provided to assess.")
            return RiskAssessmentOutput(
                original_suggestion=initial_suggestion, # Will be None
                is_trade_recommended=False,
                max_loss_on_suggestion=0,
                warnings=warnings
            )

        max_loss_initial = self._calculate_max_loss(initial_suggestion)

        # 1. Check against max loss tolerance
        if max_loss_initial > self.user_profile.max_loss_per_trade:
            is_trade_recommended = False # Initially reject if too risky
            warnings.append(
                f"Original suggestion (Strike: {initial_suggestion.strike_price} {initial_suggestion.option_type}, "
                f"Premium: {initial_suggestion.premium:.2f}) has max loss of {max_loss_initial:.2f} "
                f"(Lot: {self.lot_size}), exceeding user's max loss of {self.user_profile.max_loss_per_trade:.2f}."
            )

            # Attempt to find an alternative, cheaper option (more OTM)
            # This is a simplified search: look for same type, further OTM, within risk budget
            adjusted_suggestion = self._find_alternative_option(initial_suggestion)

            if adjusted_suggestion:
                max_loss_adjusted = self._calculate_max_loss(adjusted_suggestion)
                if max_loss_adjusted <= self.user_profile.max_loss_per_trade:
                    is_trade_recommended = True # New suggestion is within budget
                    warnings.append(
                        f"Adjusted to alternative: Strike {adjusted_suggestion.strike_price} {adjusted_suggestion.option_type}, "
                        f"Premium {adjusted_suggestion.premium:.2f}, Max Loss {max_loss_adjusted:.2f}."
                    )
                    notes.append("Original suggestion was too risky; found a cheaper alternative.")
                else:
                    # This case should ideally not happen if _find_alternative_option works correctly
                    adjusted_suggestion = None # Stick with no recommendation
                    warnings.append("Could not find a suitable alternative within the risk budget.")
            else:
                warnings.append("No suitable alternative option found within risk budget.")
        else:
            notes.append(f"Max loss for suggestion ({max_loss_initial:.2f}) is within user's tolerance ({self.user_profile.max_loss_per_trade:.2f}).")

        current_suggestion_for_warnings = adjusted_suggestion if is_trade_recommended and adjusted_suggestion else initial_suggestion

        # 2. Check for high Theta (relevant if trade is recommended)
        if is_trade_recommended and current_suggestion_for_warnings and current_suggestion_for_warnings.theta is not None:
            if current_suggestion_for_warnings.theta > HIGH_THETA_THRESHOLD:
                warnings.append(
                    f"High Theta ({current_suggestion_for_warnings.theta:.2f}) for suggested option. "
                    "Consider a spread trade if planning to hold overnight to mitigate time decay."
                )

        # 3. Add ATR warning (general market condition)
        if self.market_data.atr is not None:
            # This threshold for "high ATR" is arbitrary; could be more sophisticated
            # (e.g., ATR % of spot price, or vs historical ATR)
            # Using the same logic as in StrategyEngine for consistency for now.
            is_volatile_market = self.market_data.atr > (self.market_data.spot_price * 0.005)
            if is_volatile_market:
                warnings.append(
                    f"Market ATR ({self.market_data.atr:.2f}) is relatively high, indicating increased volatility. "
                    "Manage position size and stop-loss accordingly."
                )

        # Determine final suggestion and its max loss
        final_suggested_option = adjusted_suggestion if is_trade_recommended and adjusted_suggestion else initial_suggestion
        if not is_trade_recommended : # if trade not recommended, adjusted_suggestion might be None from failed search
            final_suggested_option = initial_suggestion # report risk on original if no alternative found/taken
            if not adjusted_suggestion and not warnings[-1].startswith("No suitable alternative"):
                 warnings.append("Trade not recommended due to risk/reward profile after assessment.")


        max_loss_final = self._calculate_max_loss(final_suggested_option if final_suggested_option else initial_suggestion)


        return RiskAssessmentOutput(
            original_suggestion=initial_suggestion,
            adjusted_suggestion=adjusted_suggestion if adjusted_suggestion != initial_suggestion else None,
            is_trade_recommended=is_trade_recommended,
            max_loss_on_suggestion=max_loss_final,
            warnings=warnings,
            notes=notes
        )

    def _find_alternative_option(self, rejected_option: OptionData) -> Optional[OptionData]:
        """
        Tries to find a cheaper (further OTM) option of the same type if the
        initial suggestion was too expensive.

        Args:
            rejected_option (OptionData): The option that was rejected due to high premium.

        Returns:
            Optional[OptionData]: A cheaper alternative, or None if not found.
        """
        # This requires access to the full option chain.
        # We assume current market_data in self.market_data has relevant chains.
        # A simple strategy: iterate OTM from the rejected_option's strike.

        relevant_chain: Optional[OptionChain] = None
        # Try to find the chain for the same expiry as rejected_option if that info were available.
        # For now, just pick the first chain (e.g. weekly)
        if self.market_data.option_chains:
            relevant_chain = next(iter(self.market_data.option_chains.values()), None)

        if not relevant_chain:
            return None

        options_of_type = [
            opt for opt in relevant_chain.options
            if opt.option_type == rejected_option.option_type
        ]

        if not options_of_type:
            return None

        # Sort by "OTM-ness":
        # For CEs, higher strike is more OTM.
        # For PEs, lower strike is more OTM.
        # And we want cheaper, so sort by premium ascending.
        if rejected_option.option_type == "CE":
            # Further OTM = higher strike price
            # We want strikes > rejected_option.strike_price, sorted by premium
            candidates = sorted(
                [opt for opt in options_of_type if opt.strike_price > rejected_option.strike_price],
                key=lambda o: o.premium
            )
        else: # PE
            # Further OTM = lower strike price
            # We want strikes < rejected_option.strike_price, sorted by premium
            candidates = sorted(
                [opt for opt in options_of_type if opt.strike_price < rejected_option.strike_price],
                key=lambda o: o.premium
            )

        for candidate_opt in candidates:
            if self._calculate_max_loss(candidate_opt) <= self.user_profile.max_loss_per_trade:
                # Also ensure it has some minimum delta, e.g. not too far OTM to be meaningless
                # This threshold can be part of UserRiskProfile or a global setting
                MIN_DELTA_FOR_ALTERNATIVE = 0.1
                if candidate_opt.delta and abs(candidate_opt.delta) >= MIN_DELTA_FOR_ALTERNATIVE:
                    return candidate_opt

        return None


if __name__ == '__main__':
    from app.backend.data_fetching.mock_data_source import MockDataSource
    import datetime

    # Setup
    mock_src = MockDataSource(index_name="TEST_NIFTY", initial_spot=21000)
    market_data_now = mock_src.fetch_live_market_data()
    # Ensure we have some options in the chain for testing _find_alternative_option
    # Let's add more OTM options manually to the first chain for testing
    first_chain_key = next(iter(market_data_now.option_chains.keys()))
    first_chain = market_data_now.option_chains[first_chain_key]

    # Add some cheaper CE options
    first_chain.options.append(OptionData(strike_price=21500, option_type="CE", premium=10, delta=0.15, theta=5))
    first_chain.options.append(OptionData(strike_price=21600, option_type="CE", premium=5, delta=0.08, theta=3)) # delta too low
     # Add some cheaper PE options
    first_chain.options.append(OptionData(strike_price=20500, option_type="PE", premium=12, delta=0.18, theta=6))
    first_chain.options.append(OptionData(strike_price=20400, option_type="PE", premium=7, delta=0.09, theta=4)) # delta too low


    # Scenario 1: Initial suggestion is too risky, alternative found
    print("\n--- Scenario 1: Risky suggestion, alternative found ---")
    user_profile1 = UserRiskProfile(max_loss_per_trade=1000) # Max loss Rs. 1000 (20 points on Nifty 50 lot)
    assessor1 = RiskAssessor(market_data_now, user_profile1)
    # Initial suggestion: Premium 30 (1500 loss), Strike 21000 CE
    initial_opt1 = OptionData(strike_price=21000, option_type="CE", premium=30, delta=0.5, theta=12)
    assessment1 = assessor1.assess_trade_risk(initial_opt1)
    print(f"Trade Recommended: {assessment1.is_trade_recommended}")
    print(f"Original Suggestion: {assessment1.original_suggestion.strike_price} CE @ {assessment1.original_suggestion.premium}")
    if assessment1.adjusted_suggestion:
        print(f"Adjusted Suggestion: {assessment1.adjusted_suggestion.strike_price} CE @ {assessment1.adjusted_suggestion.premium}")
    print(f"Max Loss on Final: {assessment1.max_loss_on_suggestion}")
    print(f"Warnings: {assessment1.warnings}")
    print(f"Notes: {assessment1.notes}")
    assert assessment1.is_trade_recommended
    assert assessment1.adjusted_suggestion is not None
    assert assessment1.adjusted_suggestion.premium == 10 # Should pick 21500 CE @ 10


    # Scenario 2: Initial suggestion is too risky, NO suitable alternative found
    print("\n--- Scenario 2: Risky suggestion, NO alternative ---")
    user_profile2 = UserRiskProfile(max_loss_per_trade=400) # Max loss Rs. 400 (8 points on Nifty 50 lot) - very low
    assessor2 = RiskAssessor(market_data_now, user_profile2)
    initial_opt2 = OptionData(strike_price=21000, option_type="CE", premium=30, delta=0.5, theta=12)
    assessment2 = assessor2.assess_trade_risk(initial_opt2)
    print(f"Trade Recommended: {assessment2.is_trade_recommended}")
    if assessment2.original_suggestion:
        print(f"Original Suggestion: {assessment2.original_suggestion.strike_price} CE @ {assessment2.original_suggestion.premium}")
    if assessment2.adjusted_suggestion:
        print(f"Adjusted Suggestion: {assessment2.adjusted_suggestion.strike_price} CE @ {assessment2.adjusted_suggestion.premium}")
    print(f"Max Loss on Final: {assessment2.max_loss_on_suggestion}") # Should be on original
    print(f"Warnings: {assessment2.warnings}")
    print(f"Notes: {assessment2.notes}")
    assert not assessment2.is_trade_recommended
    assert assessment2.adjusted_suggestion is None

    # Scenario 3: Initial suggestion is within risk limits
    print("\n--- Scenario 3: Suggestion within risk limits ---")
    user_profile3 = UserRiskProfile(max_loss_per_trade=2000) # Max loss Rs. 2000 (40 points)
    assessor3 = RiskAssessor(market_data_now, user_profile3)
    initial_opt3 = OptionData(strike_price=21000, option_type="CE", premium=30, delta=0.5, theta=12) # 1500 loss
    assessment3 = assessor3.assess_trade_risk(initial_opt3)
    print(f"Trade Recommended: {assessment3.is_trade_recommended}")
    print(f"Original Suggestion: {assessment3.original_suggestion.strike_price} CE @ {assessment3.original_suggestion.premium}")
    print(f"Adjusted Suggestion: {assessment3.adjusted_suggestion}") # Should be None
    print(f"Max Loss on Final: {assessment3.max_loss_on_suggestion}")
    print(f"Warnings: {assessment3.warnings}") # Should include Theta warning
    print(f"Notes: {assessment3.notes}")
    assert assessment3.is_trade_recommended
    assert assessment3.adjusted_suggestion is None
    assert any("High Theta" in w for w in assessment3.warnings)

    # Scenario 4: PE trade, alternative found
    print("\n--- Scenario 4: PE Risky suggestion, alternative found ---")
    user_profile4 = UserRiskProfile(max_loss_per_trade=800) # Max loss Rs. 800 (16 points)
    assessor4 = RiskAssessor(market_data_now, user_profile4)
    initial_opt4 = OptionData(strike_price=20900, option_type="PE", premium=20, delta=0.4, theta=11) # 1000 loss
    assessment4 = assessor4.assess_trade_risk(initial_opt4)
    print(f"Trade Recommended: {assessment4.is_trade_recommended}")
    print(f"Original Suggestion: {assessment4.original_suggestion.strike_price} PE @ {assessment4.original_suggestion.premium}")
    if assessment4.adjusted_suggestion:
        print(f"Adjusted Suggestion: {assessment4.adjusted_suggestion.strike_price} PE @ {assessment4.adjusted_suggestion.premium}")
    print(f"Max Loss on Final: {assessment4.max_loss_on_suggestion}")
    print(f"Warnings: {assessment4.warnings}")
    print(f"Notes: {assessment4.notes}")
    assert assessment4.is_trade_recommended
    assert assessment4.adjusted_suggestion is not None
    assert assessment4.adjusted_suggestion.premium == 12 # Should pick 20500 PE @ 12
