import time
from typing import Optional, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.connection import SessionLocal
from app.models.user import User
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user_id,
    revoke_token,
    revoke_all_user_sessions
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class AuthRequest(BaseModel):
    username: str
    password: str

class ResetPasswordRequest(BaseModel):
    username: Optional[str] = None
    new_password: Optional[str] = None

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

# Login rate limiting tracking (Issue 17.10)
_FAILED_LOGIN_ATTEMPTS: Dict[str, List[float]] = {}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 60


def _check_login_rate_limit(key: str) -> None:
    now = time.time()
    attempts = _FAILED_LOGIN_ATTEMPTS.get(key, [])
    attempts = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
    _FAILED_LOGIN_ATTEMPTS[key] = attempts
    if len(attempts) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later."
        )


def _record_failed_login(key: str) -> None:
    now = time.time()
    attempts = _FAILED_LOGIN_ATTEMPTS.get(key, [])
    attempts.append(now)
    _FAILED_LOGIN_ATTEMPTS[key] = attempts


def _clear_failed_logins(key: str) -> None:
    _FAILED_LOGIN_ATTEMPTS.pop(key, None)


def clear_login_rate_limits_for_testing() -> None:
    """Helper for test suites to reset rate limit states."""
    _FAILED_LOGIN_ATTEMPTS.clear()


@router.post("/signup")
def signup(req: AuthRequest, db: Session = Depends(get_db)):
    username = req.username.strip().lower()
    if not username or not req.password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    
    if len(req.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long"
        )
    if len(req.password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password exceeds maximum length of 72 UTF-8 bytes"
        )
     
    # Check if user already exists
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # Create new user
    hashed = hash_password(req.password)
    user = User(username=username, password_hash=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Generate token
    token = create_access_token(user.id)
    user_id_str = f"usr_{user.id}"
    
    return {
        "success": True,
        "token": token,
        "user_id": user_id_str,
        "username": user.username,
        "message": "Registration successful"
    }


@router.post("/reset-password")
def reset_password(req: Optional[ResetPasswordRequest] = None):
    """
    Disabled unauthenticated password reset endpoint (Issue 17.1).
    Prevents account-takeover vulnerabilities by rejecting unverified username-only resets.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Unverified password reset is disabled. Please use authenticated password change."
    )


@router.post("/change-password")
def change_password(
    req: ChangePasswordRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Authenticated password change endpoint (Issue 17.1).
    Requires active authentication, current password verification, and enforces password strength rules.
    Invalidates all prior sessions/tokens upon success.
    """
    try:
        numeric_id = int(user_id.split("_")[1])
    except (IndexError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid user identifier")

    user = db.query(User).filter(User.id == numeric_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify current password in constant time
    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )

    # Validate new password rules
    if len(req.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long"
        )
    if len(req.new_password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password exceeds maximum length of 72 UTF-8 bytes"
        )

    # Update password
    user.password_hash = hash_password(req.new_password)
    db.commit()

    # Invalidate all prior sessions/tokens for this user
    revoke_all_user_sessions(user.id)

    # Issue fresh access token for the active session
    new_token = create_access_token(user.id)
    return {
        "success": True,
        "message": "Password changed successfully",
        "token": new_token
    }


@router.post("/login")
def login(req: AuthRequest, db: Session = Depends(get_db)):
    username = req.username.strip().lower()
    
    # 1. Check rate limit
    _check_login_rate_limit(username)

    if not username or not req.password:
        _record_failed_login(username)
        raise HTTPException(status_code=400, detail="Username and password are required")
    
    # Reject passwords exceeding bcrypt's 72-byte limit to prevent truncation bypass
    if len(req.password.encode("utf-8")) > 72:
        _record_failed_login(username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
        
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(req.password, user.password_hash):
        _record_failed_login(username)
        raise HTTPException(status_code=401, detail="Invalid username or password")
        
    _clear_failed_logins(username)
    token = create_access_token(user.id)
    user_id_str = f"usr_{user.id}"
    
    return {
        "success": True,
        "token": token,
        "user_id": user_id_str,
        "username": user.username,
        "message": "Login successful"
    }


@router.get("/me")
def get_me(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    try:
        numeric_id = int(user_id.split("_")[1])
    except (IndexError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid user identifier")
    user = db.query(User).filter(User.id == numeric_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "success": True,
        "user_id": user_id,
        "username": user.username
    }


@router.post("/logout")
def logout(
    authorization: Optional[str] = Header(None),
    user_id: str = Depends(get_current_user_id)
):
    """
    Session revocation logout (Issue 17.10).
    Explicitly revokes the bearer token server-side.
    """
    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            revoke_token(parts[1])
    return {
        "success": True,
        "message": "Logged out successfully"
    }
