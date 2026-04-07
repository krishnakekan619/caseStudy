from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional
from app.models import TradeAction, TradeStatus


class TradeRequest(BaseModel):
    user_id:  str
    symbol:   str
    quantity: int
    price:    float  # caller passes current market price fetched from stock-listing service

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v):
        if v <= 0:
            raise ValueError("quantity must be greater than 0")
        return v

    @field_validator("price")
    @classmethod
    def price_positive(cls, v):
        if v <= 0:
            raise ValueError("price must be greater than 0")
        return v


class TradeResponse(BaseModel):
    id:         int
    user_id:    str
    symbol:     str
    action:     TradeAction
    quantity:   int
    price:      float
    total:      float
    status:     TradeStatus
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class PortfolioItem(BaseModel):
    symbol:    str
    quantity:  int
    avg_price: float
    value:     Optional[float] = None    # quantity * current market price (enriched by caller)

    class Config:
        from_attributes = True
