
import logfire

from dataclasses import dataclass
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import get_settings


# --------------------------------------------------
# Configuration
# --------------------------------------------------

s = get_settings()

ADMIN_EMAILS = {
    email.strip().lower()
    for email in s.ADMIN_EMAILS.split(",")
    if email.strip()
}

CLOCK_SKEW_SECONDS = 30

_bearer = HTTPBearer(auto_error=False)
_google_request = google_requests.Request()


# --------------------------------------------------
# User model
# --------------------------------------------------

@dataclass
class User:
    email: str
    name: str
    role: str


# --------------------------------------------------
# Authentication
# --------------------------------------------------

def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> User:

    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    if not s.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GOOGLE_CLIENT_ID is not configured on the backend.",
        )

    try:
        claims = id_token.verify_oauth2_token(
            creds.credentials,
            _google_request,
            s.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=CLOCK_SKEW_SECONDS,
        )

    except ValueError as exc:
        logfire.warning(
    "Google token verification failed: {error}",
    error=str(exc),
)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Google ID token",
        )

    # Verify Google email
    if not claims.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Google email is not verified",
        )

    email = claims["email"].strip().lower()

    # Role-based access control
    role = "admin" if email in ADMIN_EMAILS else "user"

    name = claims.get("name", email)

    logfire.info(
        "Authenticated user {email} with role {role}",
        email=email,
        role=role,
    )

    return User(
        email=email,
        name=name,
        role=role,
    )


# --------------------------------------------------
# Authorization
# --------------------------------------------------

def require_admin(
    user: User = Depends(get_current_user)
) -> User:

    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return user
