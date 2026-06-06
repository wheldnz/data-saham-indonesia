from sqlalchemy import Column, String, Date, Boolean, BigInteger
from sqlalchemy.dialects.sqlite import JSON

from app.db.database import Base

class Stock(Base):
    __tablename__ = "stocks"

    ticker = Column(String(10), primary_key=True, index=True)
    yahoo_ticker = Column(String(15), unique=True, index=True)
    company_name = Column(String(255), nullable=False)
    sector = Column(String(100))
    sub_sector = Column(String(100))
    listing_date = Column(Date)
    market_cap_category = Column(String(20)) # mega, large, mid, small, micro
    shares_outstanding = Column(BigInteger)
    is_active = Column(Boolean, default=True)
    index_membership = Column(JSON) # e.g. ["LQ45", "IDX30"]
