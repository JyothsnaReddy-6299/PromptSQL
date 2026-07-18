from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.connection import SessionLocal
from app.models.user import User
from app.services.auth_service import hash_password, verify_password, create_access_token

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
