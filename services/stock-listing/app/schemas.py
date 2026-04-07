from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class StockBase(BaseModel):
    symbol:        str
    name:          str
    sector:        Optional[str] = None
    current_price: float
    change_pct:    float = 0.0
    volume:        int   = 0
    market_cap:    float = 0.0


class StockCreate(StockBase):
    pass


class StockResponse(StockBase):
    id:         int
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
