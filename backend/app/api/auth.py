from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_visitor_session, hash_password, verify_password
from app.db import get_db
from app.models.session import VisitorSession
from app.models.user import User
from app.schemas.auth import LoginRequest, MeOut, RegisterRequest, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
def register(
    body: RegisterRequest,
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(400, "An account with that email already exists")
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    visitor_session.user_id = user.id
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    visitor_session.user_id = user.id
    db.commit()
    return user


@router.post("/logout")
def logout(
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    # Clear the user, keep the session row itself -- it may still own
    # sandbox projects from before login, and deleting it would dangle
    # their sandbox_session_id until the TTL sweep catches it anyway.
    visitor_session.user_id = None
    db.commit()
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(user: User | None = Depends(get_current_user)):
    return MeOut(user=user)
