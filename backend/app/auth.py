import secrets
from datetime import datetime, timezone

import bcrypt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session as DbSession

from app.config import SESSION_COOKIE_NAME, SESSION_COOKIE_SECURE, SESSION_TTL_DAYS
from app.db import get_db
from app.models.session import VisitorSession
from app.models.user import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def get_visitor_session(
    request: Request, response: Response, db: DbSession = Depends(get_db)
) -> VisitorSession:
    """The current browser's session row, identified by an httpOnly cookie
    -- issued here on first contact, logged in or not, so anonymous/sandbox
    visitors and signed-in users share one mechanism (see
    app.models.session.VisitorSession)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    session = db.get(VisitorSession, token) if token else None
    if session is None:
        token = secrets.token_urlsafe(32)
        session = VisitorSession(id=token)
        db.add(session)
        db.commit()
        db.refresh(session)
    else:
        session.last_seen_at = datetime.now(timezone.utc)
        db.commit()

    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
        max_age=SESSION_TTL_DAYS * 86400,
    )
    return session


def get_current_user(
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: DbSession = Depends(get_db),
) -> User | None:
    if not visitor_session.user_id:
        return None
    return db.get(User, visitor_session.user_id)


def require_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(401, "Login required")
    return user
