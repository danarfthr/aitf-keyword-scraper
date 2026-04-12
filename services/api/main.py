import os
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from services.api.routes import router

app = FastAPI(
    title="AITF Keyword Manager API",
    version="2.0.0",
)

app.include_router(router)
