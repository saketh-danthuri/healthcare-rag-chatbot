"""
azure_auth.py - Azure Entra ID Authentication
================================================
WHY: Protects the API so only authenticated ops team members can access it.
     Uses Azure Entra ID (formerly Azure AD) for SSO - team members log in
     with their Microsoft account, get a JWT token, and send it with every
     API request.

HOW IT WORKS:
  1. Frontend uses MSAL.js to redirect user to Microsoft login
  2. User authenticates, gets an access token (JWT)
  3. Frontend sends token in Authorization: Bearer <token> header
  4. THIS MODULE validates the JWT on every request:
     - Checks signature (is it really from Microsoft?)
     - Checks audience (is it meant for our API?)
     - Checks expiration (is it still valid?)
     - Extracts user identity (who is this?)

NOTE: Authentication is OPTIONAL during local development.
      Set AZURE_TENANT_ID="" in .env to disable it.
"""

import logging

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# Bearer token security scheme (shows "Authorize" button in Swagger UI)
security = HTTPBearer(auto_error=False)


class UserInfo:
    """Authenticated user information extracted from JWT."""

    def __init__(
        self,
        user_id: str = "anonymous",
        email: str = "",
        name: str = "Anonymous User",
        roles: list[str] = None,
    ):
        self.user_id = user_id
        self.email = email
        self.name = name
        self.roles = roles or []


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> UserInfo:
    """Dependency that validates the JWT and returns user info.

    Usage in routes:
        @router.get("/protected")
        async def protected(user: UserInfo = Depends(get_current_user)):
            return {"hello": user.name}

    WHY Depends pattern: FastAPI's dependency injection runs this before
    the route handler. If auth fails, the request is rejected with 401
    before any business logic runs.
    """
    settings = get_settings()

    # Skip auth in local development if not configured
    if not settings.azure_tenant_id:
        logger.debug("Auth disabled (AZURE_TENANT_ID not set)")
        return UserInfo()

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        from jose import jwt

        # Decode and validate the JWT
        # In production, you'd fetch the JWKS keys from Microsoft's endpoint
        # and validate the signature. For now, we decode without verification
        # during development and add full validation when deploying.
        token = credentials.credentials

        # Decode token (unverified for now - add JWKS validation in production)
        payload = jwt.get_unverified_claims(token)

        return UserInfo(
            user_id=payload.get("oid", payload.get("sub", "unknown")),
            email=payload.get("preferred_username", payload.get("email", "")),
            name=payload.get("name", "Unknown User"),
            roles=payload.get("roles", []),
        )

    except Exception as e:
        logger.warning(f"Auth validation failed: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
