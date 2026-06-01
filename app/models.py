from sqlalchemy import Column, Integer, String, Text
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