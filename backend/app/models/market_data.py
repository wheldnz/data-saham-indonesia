from sqlalchemy import Column, String, Date, Float, BigInteger, Integer, ForeignKey
from sqlalchemy.orm import relationship

from app.db.database import Base

class DailyOHLCV(Base):
    __tablename__ = "daily_ohlcv"

    ticker = Column(String(10), ForeignKey("stocks.ticker"), primary_key=True)
    date = Column(Date, primary_key=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    adj_close = Column(Float)
    volume = Column(BigInteger) # dalam lembar
    value = Column(Float) # dalam Rupiah
    frequency = Column(Integer) # jumlah transaksi
    foreign_buy = Column(Float)
    foreign_sell = Column(Float)

    stock = relationship("Stock")


class TechnicalFeature(Base):
    __tablename__ = "technical_features"

    ticker = Column(String(10), ForeignKey("stocks.ticker"), primary_key=True)
    date = Column(Date, primary_key=True)
    sma_5 = Column(Float)
    sma_20 = Column(Float)
    sma_50 = Column(Float)
    sma_200 = Column(Float)
    rsi_7 = Column(Float)
    rsi_14 = Column(Float)
    stoch_k = Column(Float)
    stoch_d = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    macd_histogram = Column(Float)
    bb_upper = Column(Float)
    bb_middle = Column(Float)
    bb_lower = Column(Float)
    atr_14 = Column(Float)
    adx_14 = Column(Float)
    obv = Column(BigInteger)
    volume_sma_20 = Column(BigInteger)
    
    stock = relationship("Stock")


class BrokerSummary(Base):
    __tablename__ = "broker_summaries"

    ticker = Column(String(10), ForeignKey("stocks.ticker"), primary_key=True)
    date = Column(Date, primary_key=True)
    top_buyers = Column(String)  # JSON string of top buyers: [{"broker": "YP", "net_value": 1500000000}, ...]
    top_sellers = Column(String)  # JSON string of top sellers: [{"broker": "PD", "net_value": -1200000000}, ...]
    net_foreign_value = Column(Float)  # Net foreign flow in IDR
    acum_ratio = Column(Float)  # Ratio of top 3 buyers' net value to total trade value
    acum_status = Column(String(30))  # Big Accumulation, Accumulation, Neutral, Distribution, Big Distribution
    acum_score = Column(Float)  # Score 0 to 100 representing strength of accumulation

    stock = relationship("Stock")
