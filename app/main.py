from fastapi import FastAPI

from app.config import settings

from app.database import (
    engine,
    Base,
)

import app.models

from app.routes import router as wallet_router
from app.auth import router as auth_router


# Create database tables
Base.metadata.create_all(
    bind=engine
)


app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description="Wallet & Ledger Service with PostgreSQL",
)


app.include_router(
    wallet_router
)

app.include_router(
    auth_router
)
