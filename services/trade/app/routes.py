from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import Trade, Portfolio, TradeAction, TradeStatus
from app.schemas import TradeRequest, TradeResponse, PortfolioItem

router = APIRouter(tags=["trades"])


# ─── Helpers ────────────────────────────────────────────────────────────────

def _get_or_create_position(db: Session, user_id: str, symbol: str) -> Portfolio:
    pos = (
        db.query(Portfolio)
        .filter(Portfolio.user_id == user_id, Portfolio.symbol == symbol)
        .first()
    )
    if not pos:
        pos = Portfolio(user_id=user_id, symbol=symbol, quantity=0, avg_price=0.0)
        db.add(pos)
    return pos


# ─── Trade endpoints ─────────────────────────────────────────────────────────

@router.post("/trades/buy", response_model=TradeResponse, status_code=201)
def buy_stock(payload: TradeRequest, db: Session = Depends(get_db)):
    """Execute a buy order and update the user's portfolio position."""
    total = payload.quantity * payload.price

    trade = Trade(
        user_id  = payload.user_id,
        symbol   = payload.symbol.upper(),
        action   = TradeAction.buy,
        quantity = payload.quantity,
        price    = payload.price,
        total    = total,
        status   = TradeStatus.executed,
    )
    db.add(trade)

    pos = _get_or_create_position(db, payload.user_id, payload.symbol.upper())
    # Weighted-average cost basis
    total_qty   = pos.quantity + payload.quantity
    pos.avg_price = ((pos.avg_price * pos.quantity) + (payload.price * payload.quantity)) / total_qty
    pos.quantity  = total_qty

    db.commit()
    db.refresh(trade)
    return trade


@router.post("/trades/sell", response_model=TradeResponse, status_code=201)
def sell_stock(payload: TradeRequest, db: Session = Depends(get_db)):
    """Execute a sell order. Fails if the user does not hold enough shares."""
    pos = (
        db.query(Portfolio)
        .filter(Portfolio.user_id == payload.user_id, Portfolio.symbol == payload.symbol.upper())
        .first()
    )
    if not pos or pos.quantity < payload.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient holdings: have {pos.quantity if pos else 0}, need {payload.quantity}",
        )

    total = payload.quantity * payload.price

    trade = Trade(
        user_id  = payload.user_id,
        symbol   = payload.symbol.upper(),
        action   = TradeAction.sell,
        quantity = payload.quantity,
        price    = payload.price,
        total    = total,
        status   = TradeStatus.executed,
    )
    db.add(trade)

    pos.quantity -= payload.quantity
    if pos.quantity == 0:
        pos.avg_price = 0.0

    db.commit()
    db.refresh(trade)
    return trade


@router.get("/trades", response_model=List[TradeResponse])
def list_trades(user_id: str, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """Return trade history for a user."""
    return (
        db.query(Trade)
        .filter(Trade.user_id == user_id)
        .order_by(Trade.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/trades/{trade_id}", response_model=TradeResponse)
def get_trade(trade_id: int, db: Session = Depends(get_db)):
    """Return a single trade by ID."""
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


# ─── Portfolio endpoint ──────────────────────────────────────────────────────

@router.get("/portfolio/{user_id}", response_model=List[PortfolioItem])
def get_portfolio(user_id: str, db: Session = Depends(get_db)):
    """Return all open positions for a user (quantity > 0)."""
    positions = (
        db.query(Portfolio)
        .filter(Portfolio.user_id == user_id, Portfolio.quantity > 0)
        .all()
    )
    return positions
