import datetime
import random
from typing import List, Dict
from app.backend.data_fetching.models import OptionData, OptionChain, MarketData

class MockDataSource:
    """
    Simulates a real-time options data source.
    In a real application, this module would connect to broker APIs or data vendors.
    """

    def __init__(self, index_name: str = "NIFTY", initial_spot: float = 20000.0):
        self.index_name = index_name
        self.current_spot = initial_spot
        self.current_vwap = initial_spot * (1 + random.uniform(-0.002, 0.002))
        self.current_atr = initial_spot * random.uniform(0.003, 0.008) # ATR as a percentage of spot

    def _generate_mock_delta(self, strike_price: float, option_type: str) -> float:
        """Generates a somewhat realistic Delta based on moneyness."""
        atm_threshold = self.current_spot * 0.01 # 1% around spot is ATM
        if option_type == "CE":
            if strike_price < self.current_spot - atm_threshold: # ITM
                return round(random.uniform(0.6, 0.95), 2)
            elif strike_price > self.current_spot + atm_threshold: # OTM
                return round(random.uniform(0.1, 0.4), 2)
            else: # ATM
                return round(random.uniform(0.4, 0.6), 2)
        elif option_type == "PE":
            if strike_price > self.current_spot + atm_threshold: # ITM
                return round(random.uniform(0.6, 0.95), 2)
            elif strike_price < self.current_spot - atm_threshold: # OTM
                return round(random.uniform(0.1, 0.4), 2)
            else: # ATM
                return round(random.uniform(0.4, 0.6), 2)
        return 0.5 # Should not happen

    def _generate_mock_premium(self, strike_price: float, option_type: str, delta: float) -> float:
        """Generates a mock premium loosely based on Delta and distance from spot."""
        base_premium = self.current_spot * 0.005 # Base premium factor
        distance_factor = abs(self.current_spot - strike_price) / self.current_spot
        premium = base_premium + (delta * self.current_spot * 0.01) - (distance_factor * base_premium * 0.5)
        return round(max(5.0, premium + random.uniform(-2, 2)), 1)


    def fetch_live_market_data(self) -> MarketData:
        """
        Fetches the latest (mock) market data including spot price, option chain, VWAP, and ATR.
        """
        # Simulate spot price movement
        self.current_spot *= (1 + random.uniform(-0.001, 0.001)) # Tiny fluctuation
        self.current_vwap = self.current_spot * (1 + random.uniform(-0.002, 0.002))
        self.current_atr *= (1 + random.uniform(-0.01, 0.01)) # ATR can fluctuate a bit more

        now = datetime.datetime.now()
        # For simplicity, mock one weekly expiry and one monthly expiry
        today = datetime.date.today()
        # Next Thursday (common weekly expiry)
        days_to_thursday = (3 - today.weekday() + 7) % 7
        days_to_thursday = 7 if days_to_thursday == 0 and now.hour > 15 else days_to_thursday # if today is Thurs past market, take next
        days_to_thursday = 7 if days_to_thursday == 0 and today.weekday() == 3 else days_to_thursday
        if days_to_thursday == 0: days_to_thursday = 7 # if it's thursday, take next week's

        weekly_expiry_date = today + datetime.timedelta(days=days_to_thursday)

        # Last Thursday of current month (common monthly expiry)
        month = today.month
        year = today.year
        if today.day > 20 : # if too close to end of month, take next month's last thursday
            month +=1
            if month > 12:
                month = 1
                year +=1

        last_day_of_month = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1) if month < 12 else datetime.date(year, 12, 31)
        days_to_last_thursday = (3 - last_day_of_month.weekday() + 7) % 7
        monthly_expiry_date = last_day_of_month - datetime.timedelta(days=days_to_last_thursday)

        expiry_dates = [weekly_expiry_date.strftime("%Y-%m-%d"), monthly_expiry_date.strftime("%Y-%m-%d")]

        option_chains: Dict[str, OptionChain] = {}

        num_strikes_atm = 10 # Number of strikes around ATM to generate
        strike_interval = 50 if self.index_name == "NIFTY" else 100 # Nifty 50, BankNifty 100

        for expiry in expiry_dates:
            options: List[OptionData] = []
            base_strike = round(self.current_spot / strike_interval) * strike_interval

            for i in range(-num_strikes_atm, num_strikes_atm + 1):
                strike = base_strike + (i * strike_interval)

                # Call option
                ce_delta = self._generate_mock_delta(strike, "CE")
                ce_premium = self._generate_mock_premium(strike, "CE", ce_delta)
                options.append(OptionData(
                    strike_price=strike,
                    option_type="CE",
                    premium=round(ce_premium,1),
                    delta=ce_delta,
                    theta=round(random.uniform(5, 20),1), # Mock theta
                    oi=random.randint(10000, 500000),
                    volume=random.randint(100, 10000)
                ))

                # Put option
                pe_delta = self._generate_mock_delta(strike, "PE")
                pe_premium = self._generate_mock_premium(strike, "PE", pe_delta)
                options.append(OptionData(
                    strike_price=strike,
                    option_type="PE",
                    premium=round(pe_premium,1),
                    delta=pe_delta, # Typically negative, but strategy uses absolute or convention
                    theta=round(random.uniform(5, 20),1), # Mock theta
                    oi=random.randint(10000, 500000),
                    volume=random.randint(100, 10000)
                ))
            option_chains[expiry] = OptionChain(expiry_date=expiry, options=options)

        return MarketData(
            timestamp=now,
            index_name=self.index_name,
            spot_price=round(self.current_spot, 2),
            vwap=round(self.current_vwap, 2),
            atr=round(self.current_atr, 2),
            option_chains=option_chains
        )

if __name__ == '__main__':
    # Example usage:
    mock_nifty_source = MockDataSource(index_name="NIFTY", initial_spot=21500)
    nifty_data = mock_nifty_source.fetch_live_market_data()
    print(f"Index: {nifty_data.index_name}, Spot: {nifty_data.spot_price}, VWAP: {nifty_data.vwap}, ATR: {nifty_data.atr}")

    for expiry, chain in nifty_data.option_chains.items():
        print(f"--- Expiry: {expiry} ---")
        ce_options = chain.get_ce_options()
        pe_options = chain.get_pe_options()
        print(f"  CE Options (Sample):")
        for opt in ce_options[:3]: # Print first 3 CEs
             print(f"    Strike: {opt.strike_price}, Premium: {opt.premium}, Delta: {opt.delta}, OI: {opt.oi}")
        print(f"  PE Options (Sample):")
        for opt in pe_options[:3]: # Print first 3 PEs
             print(f"    Strike: {opt.strike_price}, Premium: {opt.premium}, Delta: {opt.delta}, OI: {opt.oi}")

    mock_banknifty_source = MockDataSource(index_name="BANKNIFTY", initial_spot=45000)
    banknifty_data = mock_banknifty_source.fetch_live_market_data()
    print(f"\nIndex: {banknifty_data.index_name}, Spot: {banknifty_data.spot_price}, VWAP: {banknifty_data.vwap}, ATR: {banknifty_data.atr}")
