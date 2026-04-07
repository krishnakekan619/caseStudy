"""
Unit tests for stock-listing service.
Uses an in-memory SQLite database — no real PostgreSQL needed in CI.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

SQLITE_URL = "sqlite:///./test.db"

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


# ── Health ────────────────────────────────────────────────────────────────────

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["service"] == "stock-listing"


# ── List stocks (empty) ───────────────────────────────────────────────────────

def test_list_stocks_empty():
    resp = client.get("/stocks/")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Create a stock ────────────────────────────────────────────────────────────

def test_create_stock():
    payload = {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "sector": "Technology",
        "current_price": 189.50,
        "change_pct": 1.2,
        "volume": 54321000,
        "market_cap": 2940000.0,
    }
    resp = client.post("/stocks/", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert data["current_price"] == 189.50


def test_create_stock_duplicate_returns_409():
    payload = {"symbol": "AAPL", "name": "Apple", "current_price": 189.0}
    client.post("/stocks/", json=payload)
    resp = client.post("/stocks/", json=payload)
    assert resp.status_code == 409


# ── Get single stock ──────────────────────────────────────────────────────────

def test_get_stock():
    client.post("/stocks/", json={"symbol": "MSFT", "name": "Microsoft", "current_price": 415.0})
    resp = client.get("/stocks/MSFT")
    assert resp.status_code == 200
    assert resp.json()["symbol"] == "MSFT"


def test_get_stock_case_insensitive():
    client.post("/stocks/", json={"symbol": "TSLA", "name": "Tesla", "current_price": 175.0})
    resp = client.get("/stocks/tsla")
    assert resp.status_code == 200
    assert resp.json()["symbol"] == "TSLA"


def test_get_stock_not_found():
    resp = client.get("/stocks/ZZZZ")
    assert resp.status_code == 404


# ── Get price ─────────────────────────────────────────────────────────────────

def test_get_price():
    client.post("/stocks/", json={"symbol": "NVDA", "name": "NVIDIA", "current_price": 875.0, "change_pct": 3.2})
    resp = client.get("/stocks/NVDA/price")
    assert resp.status_code == 200
    assert resp.json()["current_price"] == 875.0
    assert resp.json()["change_pct"] == 3.2


# ── Update price ──────────────────────────────────────────────────────────────

def test_update_price():
    client.post("/stocks/", json={"symbol": "AMZN", "name": "Amazon", "current_price": 185.0})
    resp = client.put("/stocks/AMZN/price?price=191.0&change_pct=3.2")
    assert resp.status_code == 200
    assert resp.json()["current_price"] == 191.0


# ── Sector filter ─────────────────────────────────────────────────────────────

def test_filter_by_sector():
    client.post("/stocks/", json={"symbol": "JPM", "name": "JPMorgan", "sector": "Finance", "current_price": 198.0})
    client.post("/stocks/", json={"symbol": "GOOGL", "name": "Alphabet", "sector": "Technology", "current_price": 175.0})
    resp = client.get("/stocks/?sector=Finance")
    assert resp.status_code == 200
    symbols = [s["symbol"] for s in resp.json()]
    assert "JPM" in symbols
    assert "GOOGL" not in symbols
