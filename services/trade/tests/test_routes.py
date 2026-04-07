"""
Unit tests for trade service.
Uses an in-memory SQLite database — no real PostgreSQL needed in CI.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

SQLITE_URL = "sqlite:///./test_trade.db"

engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


client = TestClient(app)

BUY_PAYLOAD = {"user_id": "user-001", "symbol": "AAPL", "quantity": 10, "price": 189.50}


# ── Health ────────────────────────────────────────────────────────────────────

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["service"] == "trade"


# ── Buy ───────────────────────────────────────────────────────────────────────

def test_buy_stock():
    resp = client.post("/trades/buy", json=BUY_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["action"] == "buy"
    assert data["symbol"] == "AAPL"
    assert data["quantity"] == 10
    assert data["total"] == pytest.approx(10 * 189.50)
    assert data["status"] == "executed"


def test_buy_updates_portfolio():
    client.post("/trades/buy", json=BUY_PAYLOAD)
    resp = client.get("/portfolio/user-001")
    assert resp.status_code == 200
    positions = resp.json()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "AAPL"
    assert positions[0]["quantity"] == 10


def test_buy_invalid_quantity_rejected():
    payload = {**BUY_PAYLOAD, "quantity": 0}
    resp = client.post("/trades/buy", json=payload)
    assert resp.status_code == 422


def test_buy_invalid_price_rejected():
    payload = {**BUY_PAYLOAD, "price": -5.0}
    resp = client.post("/trades/buy", json=payload)
    assert resp.status_code == 422


# ── Sell ──────────────────────────────────────────────────────────────────────

def test_sell_stock():
    client.post("/trades/buy", json=BUY_PAYLOAD)
    sell_payload = {"user_id": "user-001", "symbol": "AAPL", "quantity": 5, "price": 191.0}
    resp = client.post("/trades/sell", json=sell_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["action"] == "sell"
    assert data["quantity"] == 5


def test_sell_updates_portfolio_quantity():
    client.post("/trades/buy", json=BUY_PAYLOAD)
    client.post("/trades/sell", json={"user_id": "user-001", "symbol": "AAPL", "quantity": 3, "price": 191.0})
    resp = client.get("/portfolio/user-001")
    assert resp.json()[0]["quantity"] == 7


def test_sell_more_than_held_returns_400():
    client.post("/trades/buy", json=BUY_PAYLOAD)
    sell_payload = {"user_id": "user-001", "symbol": "AAPL", "quantity": 99, "price": 191.0}
    resp = client.post("/trades/sell", json=sell_payload)
    assert resp.status_code == 400


def test_sell_without_holding_returns_400():
    sell_payload = {"user_id": "user-999", "symbol": "AAPL", "quantity": 1, "price": 191.0}
    resp = client.post("/trades/sell", json=sell_payload)
    assert resp.status_code == 400


# ── Trade history ─────────────────────────────────────────────────────────────

def test_list_trades():
    client.post("/trades/buy", json=BUY_PAYLOAD)
    client.post("/trades/buy", json={**BUY_PAYLOAD, "quantity": 5})
    resp = client.get("/trades?user_id=user-001")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_trade_by_id():
    resp = client.post("/trades/buy", json=BUY_PAYLOAD)
    trade_id = resp.json()["id"]
    resp2 = client.get(f"/trades/{trade_id}")
    assert resp2.status_code == 200
    assert resp2.json()["id"] == trade_id


def test_get_trade_not_found():
    resp = client.get("/trades/9999")
    assert resp.status_code == 404


# ── Portfolio ─────────────────────────────────────────────────────────────────

def test_portfolio_empty_for_new_user():
    resp = client.get("/portfolio/new-user")
    assert resp.status_code == 200
    assert resp.json() == []


def test_portfolio_sell_all_removes_from_listing():
    client.post("/trades/buy", json=BUY_PAYLOAD)
    client.post("/trades/sell", json={"user_id": "user-001", "symbol": "AAPL", "quantity": 10, "price": 191.0})
    resp = client.get("/portfolio/user-001")
    # quantity=0 positions are excluded from portfolio listing
    assert resp.json() == []


# ── Average cost basis ────────────────────────────────────────────────────────

def test_weighted_average_cost_basis():
    client.post("/trades/buy", json={"user_id": "user-001", "symbol": "AAPL", "quantity": 10, "price": 100.0})
    client.post("/trades/buy", json={"user_id": "user-001", "symbol": "AAPL", "quantity": 10, "price": 200.0})
    resp = client.get("/portfolio/user-001")
    # avg = (10*100 + 10*200) / 20 = 150.0
    assert resp.json()[0]["avg_price"] == pytest.approx(150.0)
