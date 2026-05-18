from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import User
from .user_access import can_admin, can_edit_planning, can_use_allocation_tools, is_super_user, user_needs_password_setup


PASSWORD_SETUP_ALLOWED_PATHS = {
    "/api/auth/me",
    "/api/auth/logout",
    "/api/auth/set-password",
}


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    if user_needs_password_setup(user) and request.url.path not in PASSWORD_SETUP_ALLOWED_PATHS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="password_setup_required")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not can_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user


def require_planning_editor(user: User = Depends(get_current_user)) -> User:
    if not can_edit_planning(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Visningsrollen kan inte ändra bemanningen")
    return user


def require_super_user(user: User = Depends(get_current_user)) -> User:
    if not is_super_user(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super User required")
    return user


def require_allocation_tools_user(user: User = Depends(get_current_user)) -> User:
    if not can_use_allocation_tools(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lagerkontorist required")
    return user
