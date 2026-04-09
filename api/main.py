"""
api/main.py
===========
FastAPI application factory with lifespan management.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from database import engine, Base
from api.routes import scrape, keywords, filter as filter_router, classify, expand


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Keyword Scraper API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(scrape.router, prefix="/scrape", tags=["Scrape"])
    app.include_router(keywords.router, prefix="/keywords", tags=["Keywords"])
    app.include_router(filter_router.router, prefix="/keywords", tags=["Filter"])
    app.include_router(classify.router, prefix="/keywords", tags=["Classify"])
    app.include_router(expand.router, prefix="/keywords", tags=["Expand"])

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
