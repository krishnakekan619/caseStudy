from sqlalchemy import Column, Integer, String, Float, DateTime, func
from app.database import Base


class Stock(Base):
    __tablename__ = "stocks"

    id            = Column(Integer, primary_key=True, index=True)
    symbol        = Column(String(10), unique=True, nullable=False, index=True)
    name          = Column(String(100), nullable=False)
    sector        = Column(String(50))
    current_price = Column(Float, nullable=False)
    change_pct    = Column(Float, default=0.0)   # % change from previous close
    volume        = Column(Integer, default=0)
    market_cap    = Column(Float, default=0.0)   # in millions USD
    updated_at    = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
