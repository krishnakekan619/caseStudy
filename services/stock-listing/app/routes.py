from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models import Stock
from app.schemas import StockCreate, StockResponse

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/", response_model=List[StockResponse])
def list_stocks(
    sector: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Return all listed stocks, optionally filtered by sector."""
    q = db.query(Stock)
    if sector:
        q = q.filter(Stock.sector.ilike(f"%{sector}%"))
    return q.offset(skip).limit(limit).all()


@router.get("/{symbol}", response_model=StockResponse)
def get_stock(symbol: str, db: Session = Depends(get_db)):
    """Return details for a single stock by ticker symbol."""
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not found")
    return stock


@router.get("/{symbol}/price")
def get_price(symbol: str, db: Session = Depends(get_db)):
    """Return only the current price and change % for a ticker."""
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not found")
    return {
        "symbol":        stock.symbol,
        "current_price": stock.current_price,
        "change_pct":    stock.change_pct,
        "updated_at":    stock.updated_at,
    }


@router.post("/", response_model=StockResponse, status_code=201)
def create_stock(payload: StockCreate, db: Session = Depends(get_db)):
    """Seed / add a new stock entry (admin / internal use)."""
    existing = db.query(Stock).filter(Stock.symbol == payload.symbol.upper()).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Stock '{payload.symbol}' already exists")
    stock = Stock(**payload.model_dump())
    stock.symbol = stock.symbol.upper()
    db.add(stock)
    db.commit()
    db.refresh(stock)
    return stock


@router.put("/{symbol}/price")
def update_price(symbol: str, price: float, change_pct: float = 0.0, db: Session = Depends(get_db)):
    """Update the live price of a stock (called by market-data feed)."""
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not found")
    stock.current_price = price
    stock.change_pct    = change_pct
    db.commit()
    db.refresh(stock)
    return {"symbol": stock.symbol, "current_price": stock.current_price, "change_pct": stock.change_pct}
