from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from .database import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)




class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer)
    rating = Column(String)
    recommendation = Column(String)
    suggestion = Column(Text)
    sentiment = Column(String)
    recording_path = Column(String)



class CallRecord(Base):
    __tablename__ = "call_records"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(100), default="Unknown Customer")
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50))            # e.g., "Resolved", "Escalated"
    final_sentiment = Column(String(50))   # e.g., "Positive", "Negative", "Neutral"
    turns = Column(Integer, default=0)
    
    # Store complete dialogue JSON history directly as text
    transcript_json = Column(Text, nullable=True) 

    def __repr__(self):
        return f"<CallRecord id={self.id} customer={self.customer_name} status={self.status}>"