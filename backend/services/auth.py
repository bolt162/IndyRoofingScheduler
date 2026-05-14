"""
Auth service — Clerk JWT verification.

Architecture: Clerk owns identity, approval, and admin metadata. Our backend
just verifies Clerk-signed JWTs and reads the custom claims. No User table.

Flow:
  1. Frontend obtains a Clerk session token via the Clerk React SDK
  2. Frontend sends `Authorization: Bearer <clerk-jwt>` on every API call
  3. We verify the JWT signature against Clerk's JWKS (cached)
  4. We check the `iss` claim matches our configured CLERK_JWT_ISSUER
  5. We read the user's email, approved flag, and admin flag from the claims
  6. If approved=false, /api/auth/me still returns OK (so frontend can show
     the Pending Approval screen) but other endpoints require approval=true.

The "approved" and "admin" custom claims come from a Clerk JWT Template
that injects user.public_metadata fields. Set this up in Clerk dashboard
under Sessions → JWT Templates.
"""
import logging
import time
from typing import Any

import httpx
import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient

from backend.config import settings


logger = logging.getLogger("auth")


# ---------------------------------------------------------------------------
# JWKS cache — Clerk's public keys for verifying JWT signatures.
# PyJWKClient handles caching + refresh internally; we hold one instance.
# ---------------------------------------------------------------------------

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        if not settings.CLERK_JWKS_URL:
            raise HTTPException(
                status_code=500,
                detail="Server not configured: CLERK_JWKS_URL missing",
            )
        # 24h cache; pyjwt refreshes on signing-key miss automatically
        _jwks_client = PyJWKClient(settings.CLERK_JWKS_URL, cache_keys=True, lifespan=86400)
    return _jwks_client


# ---------------------------------------------------------------------------
# User identity (lightweight — derived from JWT claims, no DB)
# ---------------------------------------------------------------------------

def _truthy(v: Any) -> bool:
    """Coerce a JWT claim value to bool.

    Clerk's JWT template substitutes `{{user.public_metadata.approved}}` as a
    STRING ("true"/"false") when wrapped in quotes in the template JSON. A
    naive `bool(v)` returns True for both "true" AND "false" (non-empty
    strings are truthy in Python), which would silently approve everyone.
    Handle string, bool, int, and missing-value cases explicitly.
    """
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "yes", "y"}
    return bool(v)


class ClerkUser:
    """Authenticated user identity, materialized from Clerk JWT claims."""

    def __init__(self, claims: dict[str, Any]):
        self.claims = claims
        self.sub: str = claims.get("sub", "")  # Clerk user ID
        # Email may come from a custom JWT template claim; fall back to standard 'email'
        self.email: str = (claims.get("email") or "").lower()
        self.name: str = claims.get("name") or claims.get("given_name") or ""
        # Approval flag — set via Clerk public_metadata + JWT template.
        # Use _truthy because Clerk often substitutes the value as the STRING "true"/"false".
        self.approved: bool = _truthy(claims.get("approved"))
        self.admin: bool = _truthy(claims.get("admin"))

    def to_dict(self) -> dict:
        return {
            "id": self.sub,
            "email": self.email,
            "name": self.name,
            "approved": self.approved,
            "admin": self.admin,
        }


# ---------------------------------------------------------------------------
# JWT verification
# ---------------------------------------------------------------------------

def _verify_clerk_jwt(token: str) -> dict:
    """Verify a Clerk-signed JWT and return its claims. Raises 401 on any failure."""
    try:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token).key

        # We don't enforce audience because Clerk doesn't always set one — relying
        # on issuer + signature is sufficient since Clerk is the only signer.
        options = {"verify_aud": False}

        decoded = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=settings.CLERK_JWT_ISSUER if settings.CLERK_JWT_ISSUER else None,
            options=options,
        )
        return decoded
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidIssuerError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token issuer",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except httpx.HTTPError as e:
        # JWKS fetch failure — surface as a 503 so client retries gracefully
        logger.error(f"JWKS fetch failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service temporarily unavailable",
        )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth_header.split(" ", 1)[1].strip()


def get_current_user(request: Request) -> ClerkUser:
    """
    FastAPI dependency: verifies the Clerk JWT and returns the user identity.
    Does NOT check approval — used by /api/auth/me so the frontend can show
    a 'Pending Approval' screen instead of a hard 401.
    """
    token = _extract_bearer_token(request)
    claims = _verify_clerk_jwt(token)
    return ClerkUser(claims)


def get_approved_user(request: Request) -> ClerkUser:
    """
    FastAPI dependency for all protected app endpoints.
    Verifies JWT AND requires approved=true in claims. Pending users get 403.
    """
    user = get_current_user(request)
    if not user.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account pending approval. Please contact the administrator.",
        )
    return user


def get_admin_user(request: Request) -> ClerkUser:
    """FastAPI dependency for admin-only endpoints. Requires admin=true."""
    user = get_approved_user(request)
    if not user.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
