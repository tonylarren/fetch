from fastapi import Header, HTTPException, status
from app.core.config import settings


async def require_api_key(x_api_key: str = Header(default="")) -> str:
    """Simple per-client API key auth. One key per consumer so you can revoke
    a single client without breaking the others."""
    keys = settings.api_key_set
    if not keys:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No API keys configured on the server (set API_KEYS).",
        )
    if x_api_key not in keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key."
        )
    return x_api_key
