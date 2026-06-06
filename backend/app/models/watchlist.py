import uuid
from sqlalchemy import Column, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.sql import func

from app.db.database import Base

class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    description = Column(Text)
    weight_technical = Column(Float, default=0.30)
    weight_fundamental = Column(Float, default=0.25)
    weight_sentiment = Column(Float, default=0.15)
    weight_risk = Column(Float, default=0.15)
    weight_catalyst = Column(Float, default=0.15)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship("WatchlistItem", back_populates="watchlist", cascade="all, delete-orphan")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    watchlist_id = Column(String(36), ForeignKey("watchlists.id"), primary_key=True)
    ticker = Column(String(10), ForeignKey("stocks.ticker"), primary_key=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text)

    watchlist = relationship("Watchlist", back_populates="items")
    stock = relationship("Stock")


class WatchlistScore(Base):
    __tablename__ = "watchlist_scores"

    ticker = Column(String(10), ForeignKey("stocks.ticker"), primary_key=True)
    score_date = Column(DateTime, primary_key=True)
    total_score = Column(Float)
    technical_score = Column(Float)
    fundamental_score = Column(Float)
    sentiment_score = Column(Float)
    risk_score = Column(Float)
    catalyst_score = Column(Float)
    classification = Column(String(20)) # Strong, Good, Neutral, Weak, Avoid
    score_details = Column(JSON)

    stock = relationship("Stock")
