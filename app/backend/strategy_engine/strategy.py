import datetime
from typing import List, Dict, Optional, Tuple, Any
from app.backend.data_fetching.models import MarketData, OptionData, OptionChain

# Define constants for strategy rules based on the problem description
MIN_ENTRY_TIME = datetime.time(11, 15)
VWAP_PROXIMITY_THRESHOLD_PERCENT = 0.002 # e.g., 0.2% of spot price for "near VWAP"
MIN_DELTA_THRESHOLD = 0.2

# Delta ranges based on volatility (ATR)
VOLATILE_MARKET_ATR_MULTIPLIER = 1.5 # Example: if ATR is X, high ATR could be > 1.5*X (needs proper definition)
DELTA_RANGE_VOLATILE = (0.3, 0.35)
DELTA_RANGE_LOW_VOLATILITY = (0.5, 0.6)

# Theta threshold for spread recommendation
THETA_THRESHOLD_FOR_SPREAD = 10.0 # If option Theta > 10, consider spread for overnight

class StrategyEngine:
    """
    Implements the core trading strategy logic based on Nitin Murarka's rules.
    """

    def __init__(self, market_data: MarketData):
        """
        Initializes the StrategyEngine with the latest market data.

        Args:
            market_data (MarketData): The current market data snapshot.
        """
        if not market_data:
            raise ValueError("MarketData cannot be None for StrategyEngine initialization.")
        self.market_data = market_data
        self.current_time = market_data.timestamp.time()
        self.spot_price = market_data.spot_price
        self.vwap = market_data.vwap
        self.atr = market_data.atr

    def _is_entry_time_valid(self) -> bool:
        """
        Checks if the current time is past the minimum entry time (11:15 AM).
        """
        return self.current_time >= MIN_ENTRY_TIME

    def _is_price_near_vwap(self) -> bool:
        """
        Checks if the spot price is near VWAP within a defined threshold.
        Returns False if VWAP is not available.
        """
        if self.vwap is None:
            return False # Cannot determine proximity if VWAP is missing
        return abs(self.spot_price - self.vwap) <= (self.vwap * VWAP_PROXIMITY_THRESHOLD_PERCENT)

    def _get_relevant_option_chain(self, expiry_preference: str = "weekly") -> Optional[OptionChain]:
        """
        Selects the most relevant option chain (e.g., nearest weekly expiry).
        For simplicity, this mock will try to find a key containing "weekly" or pick the first one.
        A more robust implementation would parse dates and find the actual nearest expiry.

        Args:
            expiry_preference (str): "weekly" or "monthly" or "nearest".

        Returns:
            Optional[OptionChain]: The selected option chain, or None if not found.
        """
        if not self.market_data.option_chains:
            return None

        # Attempt to find a weekly expiry first if preferred
        if expiry_preference == "weekly":
            for expiry_date, chain in self.market_data.option_chains.items():
                # This is a simplistic check. Real logic would parse expiry_date
                # and compare with current date to find nearest weekly.
                # For now, we assume mock data source provides meaningful keys.
                # Or, we could sort by date if keys are actual dates.
                # Let's assume the first key is the nearest weekly for mock.
                return chain # Simplified: take the first available chain as "weekly"

        # Fallback or if other preference
        return next(iter(self.market_data.option_chains.values()), None)


    def suggest_strike(self, option_type: str, risk_profile: str = "moderate") -> Optional[Dict[str, Any]]:
        """
        Suggests an ideal strike price based on ATR, Delta, and strategy rules.

        Args:
            option_type (str): "CE" for Call options, "PE" for Put options.
            risk_profile (str): "low", "moderate", "high" - can influence Delta preference.

        Returns:
            Optional[Dict[str, Any]]: A dictionary with the suggested option and justification,
                                       or None if no suitable option is found.
            Example:
            {
                "option": OptionData(...),
                "justification": "ATM strike with Delta 0.55, suitable for moderate volatility.",
                "type": "ATM/OTM/ITM"
            }
        """
        if not self._is_entry_time_valid():
            return {"option": None, "justification": f"Entry not recommended before {MIN_ENTRY_TIME}.", "type": None}

        if not self._is_price_near_vwap():
            return {"option": None, "justification": "Price is not near VWAP.", "type": None}

        if self.atr is None:
            return {"option": None, "justification": "ATR data is not available.", "type": None}

        option_chain = self._get_relevant_option_chain()
        if not option_chain:
            return {"option": None, "justification": "No option chain data available.", "type": None}

        options_to_consider = option_chain.get_ce_options() if option_type == "CE" else option_chain.get_pe_options()

        if not options_to_consider:
            return {"option": None, "justification": f"No {option_type} options found in the chain.", "type": None}

        # Determine volatility level (this is a simplified check)
        # A more robust ATR check would compare current ATR to its historical average/stddev
        # For now, let's assume a fixed ATR value defines "high" volatility for simplicity
        # Or use the provided ATR directly and select Delta range based on that.
        # The problem states: "Volatile market (high ATR): Recommend 0.3–0.35 Delta options."
        # "Low volatility: Prefer 0.5–0.6 Delta."
        # We need a way to define "high ATR". Let's use a placeholder logic.
        # Assume self.atr is the current ATR value.
        # A better approach would be to have a benchmark ATR or historical ATR.
        # For this example, let's say if ATR > 0.5% of spot, it's "volatile".
        is_volatile_market = self.atr > (self.spot_price * 0.005) # Example: 0.5% of spot price

        preferred_delta_min, preferred_delta_max = DELTA_RANGE_LOW_VOLATILITY
        volatility_condition = "low to moderate"
        if is_volatile_market:
            preferred_delta_min, preferred_delta_max = DELTA_RANGE_VOLATILE
            volatility_condition = "high"

        # Adjust delta preference based on risk_profile (simplified)
        if risk_profile == "low":
            # Prefer lower delta for lower risk, could be more OTM
            preferred_delta_max = preferred_delta_min + 0.1 # Narrower, lower band
        elif risk_profile == "high":
            # Might accept slightly wider range or higher delta if ITM is goal
            preferred_delta_min = preferred_delta_max - 0.15


        best_option: Optional[OptionData] = None
        min_delta_diff = float('inf')

        for opt in options_to_consider:
            if opt.delta is None or opt.delta < MIN_DELTA_THRESHOLD:
                continue

            # Check if delta is within the preferred range
            if preferred_delta_min <= abs(opt.delta) <= preferred_delta_max:
                # Among options in range, pick the one closest to center of range, or just first one for now
                # A more sophisticated selection could consider OI, volume, or exact delta match.
                # For now, let's try to find one closest to the middle of the preferred delta range.
                current_delta_diff = abs(abs(opt.delta) - (preferred_delta_min + preferred_delta_max) / 2)
                if current_delta_diff < min_delta_diff:
                    min_delta_diff = current_delta_diff
                    best_option = opt

        if best_option:
            option_moneyness = self._determine_moneyness(best_option)
            justification = (f"Suggested {option_type} strike {best_option.strike_price} ({option_moneyness}). "
                             f"Market volatility assessed as {volatility_condition} (ATR: {self.atr}). "
                             f"Target Delta range: ({preferred_delta_min:.2f}-{preferred_delta_max:.2f}). "
                             f"Selected option Delta: {best_option.delta:.2f}. "
                             f"Entry time valid (after {MIN_ENTRY_TIME}). Price near VWAP.")
            return {
                "option": best_option,
                "justification": justification,
                "type": option_moneyness
            }

        # Fallback: If no option in ideal delta range, find closest ATM/near-OTM
        # This part can be expanded. For now, if no strict match, return None.
        return {"option": None, "justification": f"No option found matching Delta criteria ({preferred_delta_min:.2f}-{preferred_delta_max:.2f}) for {volatility_condition} volatility.", "type": None}

    def _determine_moneyness(self, option: OptionData) -> str:
        """Determines if an option is ITM, ATM, or OTM."""
        atm_buffer = self.spot_price * 0.005 # 0.5% around spot for ATM

        if option.option_type == "CE":
            if option.strike_price < self.spot_price - atm_buffer:
                return "ITM"
            elif option.strike_price > self.spot_price + atm_buffer:
                return "OTM"
            else:
                return "ATM"
        elif option.option_type == "PE":
            if option.strike_price > self.spot_price + atm_buffer:
                return "ITM"
            elif option.strike_price < self.spot_price - atm_buffer:
                return "OTM"
            else:
                return "ATM"
        return "Unknown"

    def recommend_spread_trade(self, base_option: OptionData, risk_tolerance_loss: float) -> Optional[Dict[str, Any]]:
        """
        Recommends a spread trade (Bull Call Spread or Bear Put Spread) for overnight safety (Zero Theta).
        This is a placeholder and needs more sophisticated logic for selecting the second leg.

        Args:
            base_option (OptionData): The primary option leg bought.
            risk_tolerance_loss (float): Max acceptable loss, to guide spread width.

        Returns:
            Optional[Dict[str, Any]]: Details of the spread or None.
        """
        if base_option.theta is None or base_option.theta <= THETA_THRESHOLD_FOR_SPREAD:
            return {"spread_needed": False, "message": "Theta is not high enough to warrant a spread for overnight holding."}

        # Placeholder logic for spread recommendation
        # A real implementation would search for a suitable option to sell:
        # - Same expiry, same type (CE/PE)
        # - Higher strike for Bull Call (lower for Bear Call if that was the base)
        # - Lower strike for Bear Put (higher for Bull Put if that was the base)
        # - Aim to make Theta of spread close to zero or positive.
        # - Consider the risk_tolerance_loss to manage max loss of spread.

        spread_type = ""
        if base_option.option_type == "CE":
            spread_type = "Bull Call Spread"
            # Example: Sell a higher strike CE
        elif base_option.option_type == "PE":
            spread_type = "Bear Put Spread"
            # Example: Sell a lower strike PE

        # This requires searching the option chain for a suitable short leg.
        # For now, returning a placeholder.
        return {
            "spread_needed": True,
            "type": spread_type,
            "message": "Spread recommendation logic is a placeholder.",
            "bought_leg": base_option,
            "sold_leg_placeholder": "Requires selection of another option to neutralize Theta and manage risk."
        }

# Example Usage (for testing purposes, if run directly)
if __name__ == '__main__':
    from app.backend.data_fetching.mock_data_source import MockDataSource

    print(f"Minimum entry time: {MIN_ENTRY_TIME}")

    # 1. Fetch mock market data
    mock_src = MockDataSource(index_name="NIFTY_TEST", initial_spot=21000)
    # Ensure the mock data source can provide a timestamp that we can control for testing entry times

    # Scenario 1: Before 11:15 AM
    print("\n--- Scenario 1: Before 11:15 AM ---")
    market_data_early = mock_src.fetch_live_market_data()
    market_data_early.timestamp = datetime.datetime.combine(market_data_early.timestamp.date(), datetime.time(10, 30)) # Force time
    market_data_early.vwap = 21010 # Assume near VWAP

    engine_early = StrategyEngine(market_data_early)
    suggestion_early_ce = engine_early.suggest_strike(option_type="CE")
    print(f"CE Suggestion (Early): {suggestion_early_ce}")

    # Scenario 2: After 11:15 AM, price NOT near VWAP
    print("\n--- Scenario 2: After 11:15 AM, Price NOT near VWAP ---")
    market_data_far_vwap = mock_src.fetch_live_market_data()
    market_data_far_vwap.timestamp = datetime.datetime.combine(market_data_far_vwap.timestamp.date(), datetime.time(11, 30))
    market_data_far_vwap.spot_price = 21000
    market_data_far_vwap.vwap = 20900 # Price is > 0.2% away from VWAP

    engine_far_vwap = StrategyEngine(market_data_far_vwap)
    suggestion_far_vwap_ce = engine_far_vwap.suggest_strike(option_type="CE")
    print(f"CE Suggestion (Far VWAP): {suggestion_far_vwap_ce}")

    # Scenario 3: After 11:15 AM, Price near VWAP, "Low Volatility"
    print("\n--- Scenario 3: Valid Entry Time, Near VWAP, Low Volatility ---")
    market_data_valid = mock_src.fetch_live_market_data()
    market_data_valid.timestamp = datetime.datetime.combine(market_data_valid.timestamp.date(), datetime.time(12, 0))
    market_data_valid.spot_price = 21005
    market_data_valid.vwap = 21000
    market_data_valid.atr = 80 # Assuming this implies "low volatility" (e.g. < 0.005 * spot)
                               # (21000 * 0.005 = 105, so 80 is low)

    engine_valid = StrategyEngine(market_data_valid)
    suggestion_valid_ce = engine_valid.suggest_strike(option_type="CE", risk_profile="moderate")
    print(f"CE Suggestion (Valid, Low Vol): {suggestion_valid_ce}")
    if suggestion_valid_ce and suggestion_valid_ce.get("option"):
        spread_rec = engine_valid.recommend_spread_trade(suggestion_valid_ce["option"], risk_tolerance_loss=1000)
        print(f"Spread Recommendation: {spread_rec}")

    suggestion_valid_pe = engine_valid.suggest_strike(option_type="PE", risk_profile="moderate")
    print(f"PE Suggestion (Valid, Low Vol): {suggestion_valid_pe}")

    # Scenario 4: After 11:15 AM, Price near VWAP, "High Volatility"
    print("\n--- Scenario 4: Valid Entry Time, Near VWAP, High Volatility ---")
    market_data_high_atr = mock_src.fetch_live_market_data()
    market_data_high_atr.timestamp = datetime.datetime.combine(market_data_high_atr.timestamp.date(), datetime.time(12, 30))
    market_data_high_atr.spot_price = 21005
    market_data_high_atr.vwap = 21000
    market_data_high_atr.atr = 150 # Assuming this implies "high volatility" (e.g. > 0.005 * spot)

    engine_high_atr = StrategyEngine(market_data_high_atr)
    suggestion_high_atr_ce = engine_high_atr.suggest_strike(option_type="CE", risk_profile="moderate")
    print(f"CE Suggestion (Valid, High Vol): {suggestion_high_atr_ce}")

    # Scenario 5: Risk Profile Influence
    print("\n--- Scenario 5: Risk Profile Influence (Low Volatility Data) ---")
    suggestion_low_risk_ce = engine_valid.suggest_strike(option_type="CE", risk_profile="low")
    print(f"CE Suggestion (Low Risk, Low Vol): {suggestion_low_risk_ce}")
    suggestion_high_risk_ce = engine_valid.suggest_strike(option_type="CE", risk_profile="high")
    print(f"CE Suggestion (High Risk, Low Vol): {suggestion_high_risk_ce}")

    # Scenario 6: No matching delta
    print("\n--- Scenario 6: No matching delta (forcing high delta range for low vol data) ---")
    # Temporarily modify DELTA_RANGE_LOW_VOLATILITY for this test case in a new engine instance
    original_delta_range_low_vol = DELTA_RANGE_LOW_VOLATILITY
    DELTA_RANGE_LOW_VOLATILITY = (0.9, 0.95) # Unrealistic range to force no match
    engine_no_match = StrategyEngine(market_data_valid) # market_data_valid is low vol
    suggestion_no_match = engine_no_match.suggest_strike(option_type="CE")
    print(f"CE Suggestion (No Match): {suggestion_no_match}")
    DELTA_RANGE_LOW_VOLATILITY = original_delta_range_low_vol # Reset
