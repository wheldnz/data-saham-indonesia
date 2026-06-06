import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, Text
from sqlalchemy.sql import func
from app.db.database import Base

class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticker = Column(String(10), nullable=False)
    action = Column(String(10), nullable=False)  # BUY or SELL
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    date = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text, nullable=True)
