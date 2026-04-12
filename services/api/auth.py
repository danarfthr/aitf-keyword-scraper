"""Authentication for pipeline control endpoints."""

import os
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(key: str = Security(api_key_header)) -> None:
    """FastAPI dependency. Validates X-API-Key header against API_SECRET_KEY env var."""
    if not key or key != os.environ.get("API_SECRET_KEY"):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
