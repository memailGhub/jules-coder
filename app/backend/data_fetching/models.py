from dataclasses import dataclass, field
from typing import List, Dict, Optional
import datetime

@dataclass
class OptionData:
    """Represents data for a single option contract."""
    strike_price: float
    option_type: str  # "CE" or "PE"
    premium: float
    delta: Optional[float] = None
    theta: Optional[float] = None
    oi: Optional[int] = None
    volume: Optional[int] = None

    def __post_init__(self):
        if self.option_type not in ["CE", "PE"]:
            raise ValueError("option_type must be 'CE' or 'PE'")

@dataclass
class OptionChain:
    """Represents an option chain for a specific expiry."""
    expiry_date: str  # e.g., "2023-12-28"
    options: List[OptionData] = field(default_factory=list)

    def get_ce_options(self) -> List[OptionData]:
        """Returns all Call options from the chain."""
        return [opt for opt in self.options if opt.option_type == "CE"]

    def get_pe_options(self) -> List[OptionData]:
        """Returns all Put options from the chain."""
        return [opt for opt in self.options if opt.option_type == "PE"]

@dataclass
class MarketData:
    """Represents the overall market data at a point in time."""
    timestamp: datetime.datetime
    index_name: str  # e.g., "NIFTY", "BANKNIFTY"
    spot_price: float
    vwap: Optional[float] = None
    atr: Optional[float] = None # 5 or 15 min ATR
    option_chains: Dict[str, OptionChain] = field(default_factory=dict) # Keyed by expiry_date

    def get_option_chain(self, expiry_date: str) -> Optional[OptionChain]:
        return self.option_chains.get(expiry_date)
