from fastapi import FastAPI, HTTPException, Query
from typing import Optional, List
import datetime

# Assuming your project structure allows these imports
# If you have issues, you might need to adjust PYTHONPATH or use relative imports differently
from app.backend.data_fetching.data_store import DataStore
from app.backend.data_fetching.models import MarketData, OptionData # For response models
from app.backend.strategy_engine.strategy import StrategyEngine

# Initialize FastAPI app
app = FastAPI(
    title="Quantitative Trading Analysis API",
    description="API for fetching market data and getting trading strategy recommendations.",
    version="0.1.0"
)

# Initialize DataStore globally or manage its lifecycle as appropriate
# For simplicity, we'll get the instance here.
# In a production app, you might initialize it in startup events.
data_store = DataStore()

# --- API Lifespan Events ---
@app.on_event("startup")
async def startup_event():
    """
    Actions to perform on API startup.
    Initializes data sources for NIFTY and BANKNIFTY.
    """
    # Initialize data sources you want to use.
    # These will start their respective refresh threads.
    # Using shorter refresh intervals for demonstration.
    print("API Startup: Initializing data sources...")
    data_store.initialize_data_source(index_name="NIFTY", initial_spot=21500, refresh_interval=10)
    data_store.initialize_data_source(index_name="BANKNIFTY", initial_spot=45000, refresh_interval=12)
    print("API Startup: Data sources initialized.")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Actions to perform on API shutdown.
    Stops data refresh threads.
    """
    print("API Shutdown: Stopping data refresh threads...")
    data_store.stop_refresh()
    print("API Shutdown: Data refresh threads stopped.")

# --- API Endpoints ---

@app.get("/live-data/{index_name}", response_model=Optional[MarketData])
async def get_live_data(index_name: str):
    """
    Fetches the latest live market data for the specified index (NIFTY or BANKNIFTY).
    Includes spot price, VWAP, ATR, and option chains.
    """
    if index_name.upper() not in ["NIFTY", "BANKNIFTY"]:
        raise HTTPException(status_code=400, detail="Invalid index name. Use 'NIFTY' or 'BANKNIFTY'.")

    market_data = data_store.get_market_data(index_name.upper())
    if not market_data:
        raise HTTPException(status_code=404, detail=f"Market data not yet available for {index_name.upper()}. Please try again shortly.")
    return market_data

@app.get("/recommendation/{index_name}")
async def get_strategy_recommendation(
    index_name: str,
    option_type: str = Query(..., description="Option type: 'CE' for Call or 'PE' for Put", pattern="^(CE|PE)$"),
    risk_profile: str = Query("moderate", description="Risk profile: 'low', 'moderate', or 'high'", pattern="^(low|moderate|high)$"),
    expiry_preference: str = Query("weekly", description="Preferred expiry: 'weekly' or 'monthly'", pattern="^(weekly|monthly)$")
):
    """
    Provides a trading recommendation based on the implemented strategy.

    - **index_name**: Name of the index (e.g., "NIFTY", "BANKNIFTY").
    - **option_type**: "CE" (Call) or "PE" (Put).
    - **risk_profile**: "low", "moderate", or "high". Affects Delta selection.
    - **expiry_preference**: "weekly" or "monthly". For selecting the option chain.
    """
    if index_name.upper() not in ["NIFTY", "BANKNIFTY"]:
        raise HTTPException(status_code=400, detail="Invalid index name. Use 'NIFTY' or 'BANKNIFTY'.")

    current_market_data = data_store.get_market_data(index_name.upper())
    if not current_market_data:
        raise HTTPException(status_code=404, detail=f"Market data not available for {index_name.upper()} to generate recommendation.")

    # Ensure timestamp is recent enough, otherwise data might be stale
    # This check can be more sophisticated
    if (datetime.datetime.now() - current_market_data.timestamp).total_seconds() > 120: # 2 minutes
         raise HTTPException(status_code=503, detail=f"Market data for {index_name.upper()} is stale. Please try again.")


    strategy_engine = StrategyEngine(current_market_data)

    suggestion = strategy_engine.suggest_strike(
        option_type=option_type.upper(),
        risk_profile=risk_profile
    ) # expiry_preference is handled within suggest_strike for now

    if not suggestion or not suggestion.get("option"):
        justification = suggestion.get("justification", "No suitable option found based on current strategy rules.")
        raise HTTPException(status_code=404, detail=justification)

    return suggestion

@app.get("/spread-recommendation/{index_name}")
async def get_spread_recommendation(
    index_name: str,
    strike_price: float = Query(..., description="Strike price of the bought option"),
    option_type: str = Query(..., description="Option type of the bought option: 'CE' or 'PE'", pattern="^(CE|PE)$"),
    premium: float = Query(..., description="Premium of the bought option"),
    delta: float = Query(..., description="Delta of the bought option"),
    theta: float = Query(..., description="Theta of the bought option"),
    risk_tolerance_loss: float = Query(1500, description="Maximum acceptable loss for the spread in currency units (e.g., rupees).")
):
    """
    (Placeholder) Recommends a spread trade to accompany a primary bought option,
    aiming for Theta neutralisation for overnight positions.

    This endpoint currently uses placeholder logic for spread selection.
    """
    if index_name.upper() not in ["NIFTY", "BANKNIFTY"]:
        raise HTTPException(status_code=400, detail="Invalid index name. Use 'NIFTY' or 'BANKNIFTY'.")

    current_market_data = data_store.get_market_data(index_name.upper())
    if not current_market_data:
        raise HTTPException(status_code=404, detail=f"Market data not available for {index_name.upper()} to generate spread recommendation.")

    # Create a mock OptionData object from query parameters for the base leg
    # In a real app, you might pass an ID of an option or more complete details
    base_option = OptionData(
        strike_price=strike_price,
        option_type=option_type.upper(),
        premium=premium,
        delta=delta,
        theta=theta
        # OI and Volume are not strictly needed for this specific spread logic, but could be
    )

    strategy_engine = StrategyEngine(current_market_data)
    spread_suggestion = strategy_engine.recommend_spread_trade(
        base_option=base_option,
        risk_tolerance_loss=risk_tolerance_loss
    )

    if not spread_suggestion:
        raise HTTPException(status_code=404, detail="Could not generate a spread recommendation.")

    return spread_suggestion


# To run the app (from the root directory of the project):
# uvicorn app.backend.api.main:app --reload --port 8000
#
# Example URLs once running:
# http://localhost:8000/docs (for Swagger UI)
# http://localhost:8000/live-data/NIFTY
# http://localhost:8000/live-data/BANKNIFTY
# http://localhost:8000/recommendation/NIFTY?option_type=CE&risk_profile=moderate
# http://localhost:8000/recommendation/BANKNIFTY?option_type=PE&risk_profile=low&expiry_preference=monthly
# http://localhost:8000/spread-recommendation/NIFTY?strike_price=21500&option_type=CE&premium=150&delta=0.5&theta=12&risk_tolerance_loss=2000

if __name__ == "__main__":
    # This block is for direct execution if needed, but uvicorn is preferred for serving.
    import uvicorn
    print("Starting Uvicorn server for FastAPI app. Access at http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
