"""
Auth router — Clerk-based.

Clerk owns sign-in/sign-up, sessions, and the user list. Our backend only:
  - verifies Clerk-signed JWTs (in services.auth)
  - exposes /me so the frontend can read approval / admin state from claims

Endpoints:
  GET  /api/auth/me   — return the current user's identity + approval state.
                        Uses get_current_user (NOT get_approved_user) so a
                        pending user can still call this and learn they're
                        pending instead of getting a 403.

There is no /login, /logout, /config, or /google endpoint — Clerk handles
all of that on the frontend.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.services.auth import ClerkUser, get_current_user


router = APIRouter()


class UserMeResponse(BaseModel):
    id: str
    email: str
    name: str = ""
    approved: bool = False
    admin: bool = False


@router.get("/me", response_model=UserMeResponse)
def get_me(current_user: ClerkUser = Depends(get_current_user)):
    """Return the currently authenticated user. 401 if no/invalid JWT.

    Returns approval state in the response so the frontend can route between
    the app and the Pending Approval screen.
    """
    return UserMeResponse(
        id=current_user.sub,
        email=current_user.email,
        name=current_user.name,
        approved=current_user.approved,
        admin=current_user.admin,
    )
