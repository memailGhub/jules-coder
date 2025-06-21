from fastapi import FastAPI, HTTPException, Query
from sqlalchemy.orm import Session
from fastapi import Depends
from typing import Optional, List, Dict, Any
import datetime

from app.backend.data_fetching.data_store import DataStore
from app.backend.database import create_db_and_tables # For startup
from app.backend.data_fetching.models import MarketData, OptionData
from app.backend.strategy_engine.strategy import StrategyEngine
from app.backend.risk_assessment.assessment import RiskAssessor
from app.backend.risk_assessment.risk_models import UserRiskProfile, RiskAssessmentOutput, RiskAssessmentInput
from app.backend.database import get_db, log_recommendation_to_db # For logging

# Initialize FastAPI app
app = FastAPI(
    title="Quantitative Trading Analysis API",
    description="API for fetching market data and getting trading strategy recommendations.",
    version="0.3.0" # Version updated for DB logging
)

data_store = DataStore()

@app.on_event("startup")
async def startup_event():
    print("API Startup: Initializing database...")
    create_db_and_tables()
    print("API Startup: Initializing data sources...")
    data_store.initialize_data_source(index_name="NIFTY", initial_spot=21500, refresh_interval=10)
    data_store.initialize_data_source(index_name="BANKNIFTY", initial_spot=45000, refresh_interval=12)
    data_store.initialize_data_source(index_name="TEST_NIFTY", initial_spot=20000, refresh_interval=15)
    print("API Startup: Data sources initialized.")

@app.on_event("shutdown")
async def shutdown_event():
    print("API Shutdown: Stopping data refresh threads...")
    data_store.stop_refresh()
    print("API Shutdown: Data refresh threads stopped.")

@app.get("/live-data/{index_name}", response_model=Optional[MarketData])
async def get_live_data(index_name: str):
    if index_name.upper() not in ["NIFTY", "BANKNIFTY", "TEST_NIFTY"]:
        raise HTTPException(status_code=400, detail="Invalid index name. Use 'NIFTY', 'BANKNIFTY', or 'TEST_NIFTY'.")

    market_data = data_store.get_market_data(index_name.upper())
    if not market_data:
        raise HTTPException(status_code=404, detail=f"Market data not yet available for {index_name.upper()}. Please try again shortly.")
    return market_data

@app.get("/recommendation/{index_name}", response_model=RiskAssessmentOutput)
async def get_strategy_recommendation(
    index_name: str,
    option_type: str = Query(..., description="Option type: 'CE' for Call or 'PE' for Put", pattern="^(CE|PE)$"),
    strategy_risk_profile: str = Query("moderate", description="Strategy risk profile for option selection style: 'low', 'moderate', or 'high'", pattern="^(low|moderate|high)$"),
    max_loss_amount: float = Query(..., description="User's maximum acceptable loss for this trade in currency units (e.g., 1500 for Rs. 1500). Must be positive."),
    expiry_preference: str = Query("weekly", description="Preferred expiry: 'weekly' or 'monthly'", pattern="^(weekly|monthly)$"),
    db: Session = Depends(get_db)
):
    """
    Provides a trading recommendation based on the implemented strategy,
    adjusted for the user's risk tolerance. Logs the event to the database.
    """
    if index_name.upper() not in ["NIFTY", "BANKNIFTY", "TEST_NIFTY"]:
        raise HTTPException(status_code=400, detail="Invalid index name. Use 'NIFTY', 'BANKNIFTY', or 'TEST_NIFTY'.")
    if max_loss_amount <= 0:
        raise HTTPException(status_code=400, detail="max_loss_amount must be positive.")

    current_market_data = data_store.get_market_data(index_name.upper())
    if not current_market_data:
        raise HTTPException(status_code=404, detail=f"Market data not available for {index_name.upper()} to generate recommendation.")

    if (datetime.datetime.now() - current_market_data.timestamp).total_seconds() > 120: # 2 minutes stale
         raise HTTPException(status_code=503, detail=f"Market data for {index_name.upper()} is stale. Please try again.")

    strategy_engine = StrategyEngine(current_market_data)
    raw_suggestion_dict = strategy_engine.suggest_strike(
        option_type=option_type.upper(),
        risk_profile=strategy_risk_profile
    )

    initial_option_suggested = raw_suggestion_dict.get("option") if raw_suggestion_dict else None
    assessment_result: RiskAssessmentOutput

    if not initial_option_suggested:
        justification = raw_suggestion_dict.get("justification", "No suitable option found by core strategy.")
        assessment_result = RiskAssessmentOutput(
            original_suggestion=None,
            is_trade_recommended=False,
            max_loss_on_suggestion=0,
            warnings=[justification],
            notes=["Core strategy engine did not find a suitable initial option."]
        )
    else:
        user_profile = UserRiskProfile(max_loss_per_trade=max_loss_amount)
        risk_assessor = RiskAssessor(market_data=current_market_data, user_profile=user_profile)
        assessment_result = risk_assessor.assess_trade_risk(initial_suggestion=initial_option_suggested)
        assessment_result.notes.append(f"Initial strategy justification: {raw_suggestion_dict.get('justification', 'N/A')}")

    try:
        log_recommendation_to_db(
            db=db,
            index_name=index_name.upper(),
            option_type=option_type.upper(),
            strategy_risk_profile=strategy_risk_profile,
            max_loss_amount=max_loss_amount,
            expiry_preference=expiry_preference,
            assessment_output=assessment_result
        )
    except Exception as log_error:
        print(f"Failed to log recommendation to DB: {log_error}")
        # assessment_result.notes.append("Note: Failed to save this recommendation to the log.")

    return assessment_result


@app.get("/spread-recommendation/{index_name}")
async def get_spread_recommendation(
    index_name: str,
    strike_price: float = Query(..., description="Strike price of the bought option"),
    option_type: str = Query(..., description="Option type of the bought option: 'CE' or 'PE'", pattern="^(CE|PE)$"),
    premium: float = Query(..., description="Premium of the bought option"),
    delta: float = Query(..., description="Delta of the bought option"),
    theta: float = Query(..., description="Theta of the bought option"),
    risk_tolerance_loss: float = Query(1500, description="Maximum acceptable loss for the spread in currency units (e.g., rupees).") # Removed extra parenthesis here
):
    if index_name.upper() not in ["NIFTY", "BANKNIFTY", "TEST_NIFTY"]:
        raise HTTPException(status_code=400, detail="Invalid index name. Use 'NIFTY', 'BANKNIFTY', or 'TEST_NIFTY'.")

    current_market_data = data_store.get_market_data(index_name.upper())
    if not current_market_data:
        raise HTTPException(status_code=404, detail=f"Market data not available for {index_name.upper()} to generate spread recommendation.")

    base_option = OptionData(
        strike_price=strike_price,
        option_type=option_type.upper(),
        premium=premium,
        delta=delta,
        theta=theta
    )

    strategy_engine = StrategyEngine(current_market_data)
    spread_suggestion = strategy_engine.recommend_spread_trade(
        base_option=base_option,
        risk_tolerance_loss=risk_tolerance_loss
    )

    if not spread_suggestion:
        raise HTTPException(status_code=404, detail="Could not generate a spread recommendation.")

    return spread_suggestion

if __name__ == "__main__":
    import uvicorn
    print("Starting Uvicorn server for FastAPI app. Access at http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
