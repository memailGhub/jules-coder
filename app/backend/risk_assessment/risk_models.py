from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from app.backend.data_fetching.models import OptionData, MarketData

class UserRiskProfile(BaseModel):
    """
    Defines the user's risk tolerance parameters.
    """
    max_loss_per_trade: float = Field(..., gt=0, description="Maximum acceptable loss per trade in currency units (e.g., Rupees).")
    # Example: For Nifty, lot size is 50. If max_loss_per_trade is 1500, then max points loss is 30.
    # This can be further refined by considering lot sizes per index, but for now, it's a total currency amount.

    # Predefined risk levels could map to different delta preferences or aggressiveness.
    # For now, max_loss_per_trade is the primary input.
    # We can add things like:
    # preferred_delta_range: Optional[Tuple[float, float]] = None
    # max_trades_per_day: Optional[int] = None

    class Config:
        extra = "forbid" # Disallow extra fields

class RiskAssessmentInput(BaseModel):
    """
    Input for the risk assessment process, including the initial strategy suggestion
    and the user's risk profile.
    """
    raw_suggestion: Dict[str, Any] # Output from StrategyEngine.suggest_strike
    user_profile: UserRiskProfile
    market_data: MarketData # Current market data to access other options if needed

    class Config:
        arbitrary_types_allowed = True # To allow MarketData (which is a dataclass)

class RiskAssessmentOutput(BaseModel):
    """
    Output from the risk assessment process, including adjusted recommendations and warnings.
    """
    original_suggestion: Optional[OptionData] = Field(None, description="The initially suggested option by the core strategy engine, if any.")
    adjusted_suggestion: Optional[OptionData] = Field(None, description="A risk-adjusted option suggestion, if different from original.")
    is_trade_recommended: bool = Field(description="Whether a trade is recommended after risk assessment.")
    max_loss_on_suggestion: float = Field(description="Calculated maximum potential loss for the suggested/adjusted option (typically its premium).")
    warnings: List[str] = Field(default_factory=list, description="List of warnings or risk highlights.")
    # Example warnings:
    # - "Original suggestion exceeds max loss tolerance."
    # - "Adjusted to a lower premium OTM option to meet risk tolerance."
    # - "High Theta value (X), consider spread for overnight."
    # - "Market ATR (Y) is high, expect increased volatility."

    notes: List[str] = Field(default_factory=list, description="Additional notes or justifications.")

    # Position sizing can be complex and depends on account size, margin, etc.
    # For now, we'll focus on whether the trade itself fits the per-trade risk.
    # suggested_lot_size: Optional[int] = None

    class Config:
        arbitrary_types_allowed = True # To allow OptionData (which is a dataclass)

if __name__ == '__main__':
    # Example Usage:
    from app.backend.data_fetching.mock_data_source import MockDataSource

    # 1. User Profile
    user_profile_moderate = UserRiskProfile(max_loss_per_trade=1500.00) # Max loss of Rs. 1500
    print(f"User Profile: {user_profile_moderate}")

    # 2. Mock initial suggestion (from StrategyEngine)
    mock_option = OptionData(
        strike_price=21000,
        option_type="CE",
        premium=35.0, # Nifty lot size 50, so 35*50 = 1750 loss (exceeds 1500)
        delta=0.5,
        theta=10
    )
    raw_suggestion_example = {
        "option": mock_option,
        "justification": "ATM CE option based on moderate volatility.",
        "type": "ATM"
    }
    print(f"Raw Suggestion (Option Premium): {mock_option.premium}")


    # 3. Risk Assessment Output (Example of what might be produced)
    assessment_output_example = RiskAssessmentOutput(
        original_suggestion=mock_option,
        adjusted_suggestion=None, # Assume it was rejected
        is_trade_recommended=False,
        max_loss_on_suggestion=mock_option.premium * 50, # Assuming Nifty lot size 50 for calculation
        warnings=[
            f"Original suggestion premium ({mock_option.premium}) leads to max loss of {mock_option.premium * 50}, which exceeds user's max loss of {user_profile_moderate.max_loss_per_trade}.",
            "Consider a lower premium option or skip the trade."
        ]
    )
    print(f"Example Risk Assessment Output: {assessment_output_example}")

    # Example of an accepted trade
    mock_option_accepted = OptionData(
        strike_price=21100,
        option_type="CE",
        premium=25.0, # 25 * 50 = 1250 loss (within 1500)
        delta=0.3,
        theta=12
    )
    assessment_output_accepted = RiskAssessmentOutput(
        original_suggestion=mock_option_accepted, # assume this was the original
        adjusted_suggestion=mock_option_accepted, # or this was the adjusted one
        is_trade_recommended=True,
        max_loss_on_suggestion=mock_option_accepted.premium * 50,
        warnings=[
            f"Theta is {mock_option_accepted.theta}. Consider a spread if holding overnight."
        ],
        notes=["Option meets max loss criteria."]
    )
    print(f"Example Accepted Risk Assessment Output: {assessment_output_accepted}")

    # Test with MarketData for RiskAssessmentInput (conceptual)
    # In a real scenario, MarketData would be live
    try:
        md_src = MockDataSource()
        current_market_data = md_src.fetch_live_market_data()

        risk_input = RiskAssessmentInput(
            raw_suggestion=raw_suggestion_example,
            user_profile=user_profile_moderate,
            market_data=current_market_data
        )
        print(f"RiskAssessmentInput (conceptual): {risk_input.user_profile.max_loss_per_trade}, original option premium: {risk_input.raw_suggestion['option'].premium}")
    except Exception as e:
        print(f"Error creating RiskAssessmentInput: {e}")
