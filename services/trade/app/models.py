from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, func
from app.database import Base
import enum


class TradeAction(str, enum.Enum):
    buy  = "buy"
    sell = "sell"


class TradeStatus(str, enum.Enum):
    pending   = "pending"
    executed  = "executed"
    failed    = "failed"
    cancelled = "cancelled"


class Trade(Base):
    __tablename__ = "trades"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(String(50), nullable=False, index=True)
    symbol     = Column(String(10), nullable=False, index=True)
    action     = Column(Enum(TradeAction), nullable=False)
    quantity   = Column(Integer, nullable=False)
    price      = Column(Float, nullable=False)      # price at time of trade
    total      = Column(Float, nullable=False)      # quantity * price
    status     = Column(Enum(TradeStatus), default=TradeStatus.executed)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Portfolio(Base):
    __tablename__ = "portfolio"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(String(50), nullable=False, index=True)
    symbol     = Column(String(10), nullable=False)
    quantity   = Column(Integer, nullable=False, default=0)
    avg_price  = Column(Float, nullable=False, default=0.0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
