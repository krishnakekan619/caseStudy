from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import engine, Base
from app.routes import router
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Trade Service — creating tables if needed")
    Base.metadata.create_all(bind=engine)
    yield
    logger.info("Trade Service shutting down")


app = FastAPI(
    title="Trade Service",
    description="Handles buying and selling of stocks and portfolio management",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "trade"}
