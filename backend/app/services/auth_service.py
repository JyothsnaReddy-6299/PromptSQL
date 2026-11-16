import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Set
from fastapi import Header, HTTPException, status

from app.core.config import get_settings

MAX_PASSWORD_BYTES = 72  # Maximum length supported natively by bcrypt

# Session revocation registry (Issue 17.1 & Part 5)
_REVOKED_TOKENS: Set[str] = set()
_USER_MIN_IAT: Dict[str, int] = {}  # user_id -> min_valid_iat timestamp


def revoke_token(token: str) -> None:
    """Marks a specific JWT token as revoked."""
    if token:
        _REVOKED_TOKENS.add(token.strip())


def revoke_all_user_sessions(user_id: int) -> None:
    """Invalidates all tokens issued for this user prior to the current timestamp."""
    _USER_MIN_IAT[str(user_id)] = int(datetime.now(timezone.utc).timestamp())


def is_token_revoked(token: str, payload: Dict[str, Any]) -> bool:
    """Checks whether the token or user session has been revoked."""
    clean_token = token.strip() if token else ""
    if clean_token in _REVOKED_TOKENS:
        return True
    sub = payload.get("sub")
    iat = payload.get("iat", 0)
    if sub and str(sub) in _USER_MIN_IAT:
        if iat < _USER_MIN_IAT[str(sub)]:
            return True
    return False


def clear_revocation_registry_for_testing() -> None:
    """Clears the revocation registry for isolated test runs."""
    _REVOKED_TOKENS.clear()
    _USER_MIN_IAT.clear()


def hash_password(password: str) -> str:
    """
    Hashes a plaintext password using bcrypt with automated work-factor salting.
    Rejects passwords exceeding bcrypt's 72-byte truncation boundary to avoid truncation surprises.
    """
    if not password:
        raise ValueError("Password cannot be empty.")
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password exceeds maximum allowed length of {MAX_PASSWORD_BYTES} bytes.")
    
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verifies a plaintext password against a stored bcrypt hash in constant time.
    """
    if not password or not hashed_password:
        return False
    try:
        pwd_bytes = password.encode("utf-8")
        if len(pwd_bytes) > MAX_PASSWORD_BYTES:
            return False
        return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: int) -> str:
    """
    Creates a cryptographically signed, tamper-proof JWT access token.
    Enforces UTC timestamping, issued-at ('iat'), explicit token type, and expiration.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access"
    }
    
    return jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM
    )


def decode_and_validate_token(token: str) -> Dict[str, Any]:
    """
    Decodes and strictly validates a JWT token against the configured algorithm and secret.
    Enforces signature validity, expiration, issued-at, subject format, and token type.
    Rejects unsigned tokens, algorithm confusion, expired tokens, and wrong types.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "require": ["exp", "sub", "iat"]
            }
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again."
        )
    except (jwt.InvalidSignatureError, jwt.InvalidAlgorithmError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature or algorithm."
        )
    except jwt.DecodeError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token. Please log in again."
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token."
        )

    # Check if token or session has been revoked (Issue 17.1 & Part 5)
    if is_token_revoked(token, payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked or invalidated. Please log in again."
        )

    # Validate token type claim
    token_type = payload.get("type")
    if token_type and token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type."
        )

    # Validate subject (must be a valid integer user ID)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject missing."
        )
    try:
        int(sub)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject must identify a valid numeric user ID."
        )

    return payload


def get_user_id_from_token(token: str) -> Optional[str]:
    """
    Safely retrieves the user ID string from a token if valid, otherwise returns None.
    Maintains backward compatibility for non-raising token checks.
    """
    try:
        payload = decode_and_validate_token(token)
        return payload.get("sub")
    except Exception:
        return None


def get_current_user_id(authorization: Optional[str] = Header(None)) -> str:
    """
    FastAPI dependency to extract and verify the JWT access token from Authorization header.
    Returns usr_<id> on success; raises HTTP 401 Unauthorized on failure.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing. Please log in."
        )
    
    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format. Must be Bearer <token>."
        )
    
    token = parts[1]
    payload = decode_and_validate_token(token)
    user_id = payload["sub"]
    return f"usr_{user_id}"
