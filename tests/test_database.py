import unittest
import os
import datetime
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session

# Adjust imports based on your project structure.
from app.backend.database import (
    Base,
    StrategyRecommendationLog,
    log_recommendation_to_db
)
from app.backend.risk_assessment.risk_models import RiskAssessmentOutput
from app.backend.data_fetching.models import OptionData

# Test Database Configuration
TEST_DATABASE_URL = "sqlite:///./test_trading_analysis.db"

class TestDatabaseOperations(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if os.path.exists("./test_trading_analysis.db"):
            os.remove("./test_trading_analysis.db")

        cls.engine = create_engine(
            TEST_DATABASE_URL,
            connect_args={"check_same_thread": False}
        )
        cls.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)
        print(f"Test database tables created at {TEST_DATABASE_URL}")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'engine') and cls.engine:
             cls.engine.dispose()

        if os.path.exists("./test_trading_analysis.db"):
            os.remove("./test_trading_analysis.db")
            print("\nTest database file './test_trading_analysis.db' removed.")
        else:
            print("\nTest database file './test_trading_analysis.db' not found for removal.")

    def setUp(self):
        self.db: Session = self.TestingSessionLocal()
        self._clear_tables()

    def _clear_tables(self):
        self.db.query(StrategyRecommendationLog).delete()
        self.db.commit()

    def tearDown(self):
        if hasattr(self, 'db') and self.db:
            self.db.close()

    def test_01_create_db_and_tables_verification(self):
        inspector = inspect(self.engine)
        self.assertTrue(inspector.has_table(StrategyRecommendationLog.__tablename__))
        print(f"Verified: Table '{StrategyRecommendationLog.__tablename__}' exists in test DB.")

    def test_02_log_single_recommendation(self):
        print("Running test_log_single_recommendation...")
        mock_original_option = OptionData(strike_price=21000, option_type="CE", premium=100.0, delta=0.5, theta=10.0)
        test_assessment_output = RiskAssessmentOutput(
            original_suggestion=mock_original_option,
            adjusted_suggestion=None,
            is_trade_recommended=True,
            max_loss_on_suggestion=5000.0,
            warnings=["High Theta", "Market ATR is high"],
            notes=["Initial checks passed", "Within risk limits"]
        )
        logged_entry = log_recommendation_to_db(
            db=self.db, index_name="NIFTY_TEST", option_type="CE",
            strategy_risk_profile="moderate", max_loss_amount=1500.0,
            expiry_preference="weekly", assessment_output=test_assessment_output
        )
        self.assertIsNotNone(logged_entry, "Logging function returned None, indicating an error.")
        self.assertIsNotNone(logged_entry.id, "Logged entry should have an ID.")
        retrieved_entry = self.db.query(StrategyRecommendationLog).filter(StrategyRecommendationLog.id == logged_entry.id).first()
        self.assertIsNotNone(retrieved_entry)
        self.assertEqual(retrieved_entry.index_name, "NIFTY_TEST")
        self.assertEqual(retrieved_entry.is_trade_recommended, "True")
        self.assertEqual(retrieved_entry.original_strike, 21000)
        self.assertEqual(retrieved_entry.warnings, "High Theta|Market ATR is high")
        self.assertEqual(retrieved_entry.notes, "Initial checks passed|Within risk limits")
        self.assertTrue(isinstance(retrieved_entry.timestamp, datetime.datetime))
        print(f"Passed: test_log_single_recommendation (ID: {logged_entry.id})")

    def test_03_log_recommendation_with_adjusted_option(self):
        print("Running test_log_recommendation_with_adjusted_option...")
        mock_original_option = OptionData(strike_price=21000, option_type="CE", premium=120.0, delta=0.6, theta=12.0)
        mock_adjusted_option = OptionData(strike_price=21100, option_type="CE", premium=80.0, delta=0.4, theta=15.0)
        test_assessment_output = RiskAssessmentOutput(
            original_suggestion=mock_original_option,
            adjusted_suggestion=mock_adjusted_option,
            is_trade_recommended=True,
            max_loss_on_suggestion=4000.0,
            warnings=["Original too risky"], notes=["Adjusted to OTM"]
        )
        logged_entry = log_recommendation_to_db(
            db=self.db, index_name="NIFTY_TEST_ADJ", option_type="CE",
            strategy_risk_profile="high", max_loss_amount=1000.0,
            expiry_preference="monthly", assessment_output=test_assessment_output
        )
        self.assertIsNotNone(logged_entry)
        retrieved_entry = self.db.query(StrategyRecommendationLog).get(logged_entry.id)
        self.assertIsNotNone(retrieved_entry)
        self.assertEqual(retrieved_entry.adjusted_strike, 21100)
        self.assertEqual(retrieved_entry.warnings, "Original too risky")
        print(f"Passed: test_log_recommendation_with_adjusted_option (ID: {logged_entry.id})")

    def test_04_log_trade_not_recommended(self):
        print("Running test_log_trade_not_recommended...")
        mock_original_option = OptionData(strike_price=22000, option_type="PE", premium=200.0, delta=0.7, theta=20.0)
        test_assessment_output = RiskAssessmentOutput(
            original_suggestion=mock_original_option, adjusted_suggestion=None,
            is_trade_recommended=False, max_loss_on_suggestion=10000.0,
            warnings=["Exceeds max loss", "No suitable alternative"], notes=[]
        )
        logged_entry = log_recommendation_to_db(
            db=self.db, index_name="BANKNIFTY_TEST", option_type="PE",
            strategy_risk_profile="moderate", max_loss_amount=500.0,
            expiry_preference="weekly", assessment_output=test_assessment_output
        )
        self.assertIsNotNone(logged_entry)
        retrieved_entry = self.db.query(StrategyRecommendationLog).get(logged_entry.id)
        self.assertIsNotNone(retrieved_entry)
        self.assertEqual(retrieved_entry.is_trade_recommended, "False")
        self.assertEqual(retrieved_entry.warnings, "Exceeds max loss|No suitable alternative")
        self.assertTrue(retrieved_entry.notes is None or retrieved_entry.notes == "")
        print(f"Passed: test_log_trade_not_recommended (ID: {logged_entry.id})")

if __name__ == '__main__':
    unittest.main()
