"""FastAPI application entry point for Keyword Manager API."""

import os
import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger

from shared.shared.db import get_session
from sqlalchemy import text
from .routers import keywords, pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run Alembic migrations on startup, then verify DB connection. Log graceful stop on shutdown."""
    try:
        subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            env={**os.environ, "PYTHONPATH": "/app"},
        )
        logger.info("Alembic migrations applied successfully")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Alembic migration failed (may already be up-to-date): {e.stderr.decode() if e.stderr else e}")
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        logger.info("Database connection verified on startup")
    except Exception as e:
        logger.error(f"Database connection failed on startup: {e}")
    yield
    logger.info("Shutting down Keyword Manager API")


app = FastAPI(
    title="Keyword Manager API",
    version="2.1.0",
    description="AITF Tim 1 — Keyword Manager for Dashboard Monev Komdigi",
    lifespan=lifespan,
)

app.include_router(keywords.router, prefix="/keywords", tags=["Keywords"])
app.include_router(pipeline.router, prefix="/pipeline", tags=["Pipeline"])
