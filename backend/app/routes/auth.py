from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel #checks user input like the datatype is correct or not

from app.database.connection import SessionLocal
from app.models.user import User
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user_id
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

@router.post("/signup")
def signup(req: AuthRequest, db: Session = Depends(get_db)):
    username = req.username.strip().lower()
    if not username or not req.password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    
    if len(req.password) < 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 12 characters long"
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

@router.post("/login")
def login(req: AuthRequest, db: Session = Depends(get_db)):
    username = req.username.strip().lower()
    if not username or not req.password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    
    # Reject passwords exceeding bcrypt's 72-byte limit to prevent truncation bypass
    if len(req.password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
        
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
        
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
def logout(user_id: str = Depends(get_current_user_id)):
    return {
        "success": True,
        "message": "Logged out successfully"
    }
