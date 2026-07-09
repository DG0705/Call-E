import os
import json
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Define path for local SQLite database file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'call_e.db')}"

# Create the SQLite engine
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False}  # Required for SQLite in multi-threaded contexts
)

# Create a configured Session class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for our database models
Base = declarative_base()

def get_db():
    """Dependency provider to yield database sessions per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- ADD THIS FUNCTION TO RESOLVE THE IMPORT ERROR ---
async def save_call_log(customer_name: str, status: str, final_sentiment: str, turns: int, transcript: list):
    """
    Saves a complete call log record into the SQLite database.
    This replaces the old MongoDB implementation seamlessly.
    """
    # Import locally inside the function to avoid circular dependency issues
    from .models import CallRecord
    
    db = SessionLocal()
    try:
        # Convert transcript list/dict to a JSON string for storage in Text column
        transcript_str = json.dumps(transcript) if isinstance(transcript, (list, dict)) else str(transcript)
        
        record = CallRecord(
            customer_name=customer_name or "Unknown Customer",
            timestamp=datetime.utcnow(),
            status=status,
            final_sentiment=final_sentiment,
            turns=turns,
            transcript_json=transcript_str
        )
        
        db.add(record)
        db.commit()
        db.refresh(record)
        print(f"💾 [Database] Successfully logged call ID {record.id} for {customer_name}")
        return record.id
    except Exception as e:
        db.rollback()
        print(f"❌ [Database Error] Failed to save call log: {e}")
        return None
    finally:
        db.close()