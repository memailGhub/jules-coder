import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.orm import sessionmaker, declarative_base, Session # Ensure Session is imported
from sqlalchemy.ext.declarative import DeclarativeMeta

# --- Database Configuration ---
DATABASE_URL = "sqlite:///./trading_analysis.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base: DeclarativeMeta = declarative_base()

# --- Database Models ---

class StrategyRecommendationLog(Base):
    __tablename__ = "strategy_recommendations_log"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    index_name = Column(String, index=True)
    option_type = Column(String)
    strategy_risk_profile = Column(String)
    max_loss_amount = Column(Float)
    expiry_preference = Column(String)

    is_trade_recommended = Column(String)

    original_strike = Column(Float, nullable=True)
    original_option_type = Column(String, nullable=True)
    original_premium = Column(Float, nullable=True)
    original_delta = Column(Float, nullable=True)
    original_theta = Column(Float, nullable=True)

    adjusted_strike = Column(Float, nullable=True)
    adjusted_option_type = Column(String, nullable=True)
    adjusted_premium = Column(Float, nullable=True)
    adjusted_delta = Column(Float, nullable=True)
    adjusted_theta = Column(Float, nullable=True)

    max_loss_on_suggestion = Column(Float, nullable=True)

    warnings = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<StrategyRecommendationLog(id={self.id}, index='{self.index_name}', recommended='{self.is_trade_recommended}')>"

# --- Database Setup Function ---
def create_db_and_tables():
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully (if they didn't exist).")
        print(f"Database file should be at: {DATABASE_URL}")
    except Exception as e:
        print(f"Error creating database tables: {e}")
        raise

# --- Dependency for getting a DB session ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- CRUD Operations (Example for logging) ---

def log_recommendation_to_db(
    db: Session,
    index_name: str,
    option_type: str,
    strategy_risk_profile: str,
    max_loss_amount: float,
    expiry_preference: str,
    assessment_output # Assuming this is the RiskAssessmentOutput Pydantic model
):
    """Logs a strategy recommendation event to the database."""
    try:
        # Helper to safely get attributes from Pydantic models that might be None
        def get_optional_attr(obj, attr, default=None):
            return getattr(obj, attr, default) if obj else default

        original_option = assessment_output.original_suggestion
        adjusted_option = assessment_output.adjusted_suggestion

        # Join lists into strings for Text columns
        warnings_str = '|'.join(assessment_output.warnings) if assessment_output.warnings else None
        notes_str = '|'.join(assessment_output.notes) if assessment_output.notes else None

        log_entry = StrategyRecommendationLog(
            index_name=index_name,
            option_type=option_type,
            strategy_risk_profile=strategy_risk_profile,
            max_loss_amount=max_loss_amount,
            expiry_preference=expiry_preference,
            is_trade_recommended=str(assessment_output.is_trade_recommended),
            original_strike=get_optional_attr(original_option, 'strike_price'),
            original_option_type=get_optional_attr(original_option, 'option_type'),
            original_premium=get_optional_attr(original_option, 'premium'),
            original_delta=get_optional_attr(original_option, 'delta'),
            original_theta=get_optional_attr(original_option, 'theta'),
            adjusted_strike=get_optional_attr(adjusted_option, 'strike_price'),
            adjusted_option_type=get_optional_attr(adjusted_option, 'option_type'),
            adjusted_premium=get_optional_attr(adjusted_option, 'premium'),
            adjusted_delta=get_optional_attr(adjusted_option, 'delta'),
            adjusted_theta=get_optional_attr(adjusted_option, 'theta'),
            max_loss_on_suggestion=assessment_output.max_loss_on_suggestion,
            warnings=warnings_str,
            notes=notes_str
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry) # To get the ID and default values like timestamp
        print(f'Successfully logged recommendation ID: {log_entry.id}')
        return log_entry
    except Exception as e:
        db.rollback()
        print(f'Error logging recommendation to DB: {e}')
        # Depending on policy, you might want to re-raise or handle silently
        return None

if __name__ == "__main__":
    print("Creating database and tables directly...")
    create_db_and_tables()

    # Example of adding a log (for testing purposes)
    # from app.backend.risk_assessment.risk_models import OptionData

    # db = SessionLocal()
    # test_log = StrategyRecommendationLog(
    #     index_name="NIFTY",
    #     option_type="CE",
    #     strategy_risk_profile="moderate",
    #     max_loss_amount=1500.0,
    #     expiry_preference="weekly",
    #     is_trade_recommended="True",
    #     original_strike=21000,
    #     original_option_type="CE",
    #     original_premium=100.0,
    #     original_delta=0.5,
    #     original_theta=10.0,
    #     max_loss_on_suggestion=5000.0,
    #     warnings="High Theta|Market ATR is high",
    #     notes="Initial checks passed|Within risk limits"
    # )
    # db.add(test_log)
    # try:
    #     db.commit()
    #     print("Test log entry added.")
    # except Exception as e:
    #     db.rollback()
    #     print(f"Error adding test log: {e}")
    # finally:
    #     db.close()

    print("Database module script finished.")
