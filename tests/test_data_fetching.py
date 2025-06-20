import unittest
import time
import datetime
from app.backend.data_fetching.models import OptionData, MarketData, OptionChain
from app.backend.data_fetching.mock_data_source import MockDataSource
from app.backend.data_fetching.data_store import DataStore

class TestDataFetching(unittest.TestCase):

    def test_option_data_creation(self):
        """Test basic OptionData creation and validation."""
        opt = OptionData(strike_price=20000, option_type="CE", premium=150.0, delta=0.5)
        self.assertEqual(opt.strike_price, 20000)
        self.assertEqual(opt.option_type, "CE")
        with self.assertRaises(ValueError):
            OptionData(strike_price=20000, option_type="XX", premium=150.0)

    def test_market_data_creation(self):
        """Test basic MarketData creation."""
        ts = datetime.datetime.now()
        md = MarketData(timestamp=ts, index_name="NIFTY", spot_price=21000.0)
        self.assertEqual(md.index_name, "NIFTY")
        self.assertEqual(md.spot_price, 21000.0)

    def test_mock_data_source(self):
        """Test that MockDataSource returns data in the expected format."""
        source = MockDataSource(index_name="TEST_INDEX", initial_spot=10000)
        market_data = source.fetch_live_market_data()

        self.assertIsInstance(market_data, MarketData)
        self.assertEqual(market_data.index_name, "TEST_INDEX")
        self.assertGreater(market_data.spot_price, 0)
        self.assertIsNotNone(market_data.vwap)
        self.assertIsNotNone(market_data.atr)
        self.assertTrue(len(market_data.option_chains) > 0)

        # Check structure of one option chain
        first_expiry = next(iter(market_data.option_chains.keys()))
        option_chain = market_data.option_chains[first_expiry]
        self.assertIsInstance(option_chain, OptionChain)
        self.assertTrue(len(option_chain.options) > 0)

        first_option = option_chain.options[0]
        self.assertIsInstance(first_option, OptionData)
        self.assertIn(first_option.option_type, ["CE", "PE"])
        self.assertIsNotNone(first_option.delta)

    def test_data_store_singleton(self):
        """Test that DataStore is a singleton."""
        store1 = DataStore()
        store2 = DataStore()
        self.assertIs(store1, store2)

    def test_data_store_initialization_and_retrieval(self):
        """Test initializing data source in DataStore and retrieving data."""
        store = DataStore()
        # Use a unique index name for this test to avoid conflicts if tests run in parallel or with other instances
        test_index_name = "TEST_DS_NIFTY"
        store.initialize_data_source(index_name=test_index_name, initial_spot=15000, refresh_interval=1)

        time.sleep(0.2) # Allow some time for initial fetch

        market_data = store.get_market_data(test_index_name)
        self.assertIsNotNone(market_data)
        self.assertEqual(market_data.index_name, test_index_name)
        self.assertGreater(market_data.spot_price, 0)

        # Test that data refreshes (spot price should ideally change)
        # This is hard to guarantee with pure random mock, but we can check timestamp
        initial_timestamp = market_data.timestamp
        time.sleep(1.5) # Wait for refresh

        market_data_refreshed = store.get_market_data(test_index_name)
        self.assertIsNotNone(market_data_refreshed)
        self.assertNotEqual(market_data_refreshed.timestamp, initial_timestamp, "Data should have refreshed with a new timestamp.")

        store.stop_refresh() # Clean up threads for this specific instance if possible (or rely on global stop)

    @classmethod
    def tearDownClass(cls):
        """Ensure all data store threads are stopped after tests in this class."""
        # This is important if the DataStore singleton's threads persist across test classes/files
        ds = DataStore()
        ds.stop_refresh()
        time.sleep(0.1) # Give a moment for threads to actually stop

if __name__ == '__main__':
    unittest.main()
