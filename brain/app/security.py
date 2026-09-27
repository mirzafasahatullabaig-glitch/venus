"""API-key check ONLY. A FastAPI dependency that enforces the Bearer key.

Protected routes declare `dependencies=[Depends(require_api_key)]`; /health does
not, so it stays open.
"""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.config import get_config


async def require_api_key(authorization: str = Header(default="")) -> None:
    """Reject the request unless the Authorization header is `Bearer <api_key>`."""
    expected = get_config().api_key
    scheme, _, token = authorization.partition(" ")

    ok = scheme.lower() == "bearer" and secrets.compare_digest(token, expected)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
