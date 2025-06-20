import time
import threading
from typing import Optional, Dict
from app.backend.data_fetching.models import MarketData
from app.backend.data_fetching.mock_data_source import MockDataSource

class DataStore:
    """
    In-memory store for market data, with periodic refresh.
    """
    _instance = None
    _lock = threading.Lock()

    # Using a dictionary to store data for multiple indices if needed
    _market_data_cache: Dict[str, MarketData] = {}
    _data_sources: Dict[str, MockDataSource] = {}
    _refresh_interval_seconds: int = 60  # Refresh every 60 seconds
    _stop_event = threading.Event()
    _refresh_threads: Dict[str, threading.Thread] = {}


    def __new__(cls, *args, **kwargs):
        # Singleton pattern to ensure only one instance of DataStore
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(DataStore, cls).__new__(cls)
        return cls._instance

    def initialize_data_source(self, index_name: str, initial_spot: float, refresh_interval: int = 60):
        """
        Initializes a data source for a given index and starts its refresh thread.
        Args:
            index_name (str): The name of the index (e.g., "NIFTY", "BANKNIFTY").
            initial_spot (float): The initial spot price for the mock data source.
            refresh_interval (int): How often to refresh data in seconds.
        """
        if index_name not in self._data_sources:
            self._data_sources[index_name] = MockDataSource(index_name=index_name, initial_spot=initial_spot)
            self._refresh_interval_seconds = refresh_interval
            print(f"Data source for {index_name} initialized. Refreshing every {refresh_interval}s.")
            # Perform an initial fetch
            self._fetch_and_cache_data(index_name)
            # Start the refresh thread for this index
            self._stop_event.clear() # Ensure it's not set if previously stopped
            thread = threading.Thread(target=self._refresh_data_loop, args=(index_name,), daemon=True)
            self._refresh_threads[index_name] = thread
            thread.start()
        else:
            print(f"Data source for {index_name} already initialized.")


    def _fetch_and_cache_data(self, index_name: str):
        """Fetches data from the source and updates the cache for a specific index."""
        if index_name in self._data_sources:
            try:
                data = self._data_sources[index_name].fetch_live_market_data()
                with self._lock:
                    self._market_data_cache[index_name] = data
                # print(f"Data refreshed for {index_name} at {data.timestamp}")
            except Exception as e:
                print(f"Error fetching data for {index_name}: {e}")
        else:
            print(f"No data source configured for {index_name}.")

    def _refresh_data_loop(self, index_name: str):
        """Periodically fetches and caches data for a specific index until stop event is set."""
        print(f"Refresh loop started for {index_name}...")
        while not self._stop_event.is_set():
            self._fetch_and_cache_data(index_name)
            time.sleep(self._refresh_interval_seconds)
        print(f"Refresh loop stopped for {index_name}.")

    def get_market_data(self, index_name: str) -> Optional[MarketData]:
        """
        Retrieves the latest cached market data for a specific index.
        Returns None if no data is available for that index.
        """
        with self._lock:
            return self._market_data_cache.get(index_name)

    def stop_refresh(self):
        """Stops all refresh threads."""
        print("Stopping all data refresh threads...")
        self._stop_event.set()
        for index_name, thread in self._refresh_threads.items():
            if thread.is_alive():
                thread.join(timeout=5) # Wait for thread to finish
                if thread.is_alive():
                     print(f"Warning: Refresh thread for {index_name} did not terminate gracefully.")
        self._refresh_threads.clear()
        print("All data refresh threads stopped.")

    @classmethod
    def get_instance(cls):
        """Provides access to the singleton instance."""
        if not cls._instance:
            # This default initialization can be modified or removed if explicit init is always preferred
            print("DataStore not initialized. Call initialize_data_source() first or get_instance will create a default one.")
            # For now, let's not auto-init. User must call initialize_data_source.
            # cls._instance = cls() # Basic initialization if needed
            pass
        return cls._instance


if __name__ == '__main__':
    # Example Usage:
    # Get the singleton instance
    data_store = DataStore()

    # Initialize for NIFTY
    data_store.initialize_data_source(index_name="NIFTY", initial_spot=21500, refresh_interval=5)

    # Initialize for BANKNIFTY
    data_store.initialize_data_source(index_name="BANKNIFTY", initial_spot=45000, refresh_interval=7)

    try:
        for i in range(3): # Let it run for a few refreshes
            time.sleep(10)
            nifty_data = data_store.get_market_data("NIFTY")
            if nifty_data:
                print(f"Fetched NIFTY Spot: {nifty_data.spot_price} at {nifty_data.timestamp}")
                # print(f"NIFTY ATR: {nifty_data.atr}, VWAP: {nifty_data.vwap}")
                # weekly_expiry = next(iter(nifty_data.option_chains.keys())) # Get first expiry
                # if weekly_expiry:
                #    print(f"NIFTY {weekly_expiry} CE options (first 2): {nifty_data.option_chains[weekly_expiry].get_ce_options()[:2]}")

            banknifty_data = data_store.get_market_data("BANKNIFTY")
            if banknifty_data:
                print(f"Fetched BANKNIFTY Spot: {banknifty_data.spot_price} at {banknifty_data.timestamp}")

    except KeyboardInterrupt:
        print("User interrupted.")
    finally:
        data_store.stop_refresh()
        print("Program finished.")
