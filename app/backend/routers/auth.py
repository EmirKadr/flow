import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import demo_session
from ..audit import log as audit_log
from ..deps import get_current_user, get_db
from ..login_rate_limit import client_ip_from_request, login_rate_limiter
from ..models import Person, User
from ..schemas import LoginRequest, PasswordSetRequest, UserOut
from ..security import hash_password, verify_password
from ..user_access import PERSON_ROLE, is_demo_user, user_needs_password_setup, user_out

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _auto_create_person_user(db: Session, username: str) -> User | None:
    cleaned = username.strip()
    if not cleaned:
        return None
    matches = (
        db.query(Person)
        .filter(Person.is_active, func.lower(func.trim(Person.noman)) == cleaned.lower())
        .order_by(Person.id.asc())
        .all()
    )
    if not matches:
        return None
    if len(matches) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Flera personer har samma Noman-namn. Be en administratör rätta personregistret.",
        )

    person = matches[0]
    user = User(
        username=cleaned,
        password_hash=None,
        display_name=person.name,
        role=PERSON_ROLE,
        roles=[PERSON_ROLE],
        business_id=person.business_id,
        area_id=person.home_area_id,
        person_id=person.id,
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    audit_log(
        db,
        entity_type="user",
        entity_id=user.id,
        action="auto_create_person_user",
        old_value=None,
        new_value={
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "roles": user.roles,
            "business_id": user.business_id,
            "area_id": user.area_id,
            "person_id": user.person_id,
        },
        user_id=None,
        business_id=user.business_id,
    )
    db.commit()
    db.refresh(user)
    return user


def _audit_failed_login(db: Session, username: str, client_ip: str, attempts: int) -> None:
    """Auditrad för misslyckad inloggning — samma rad oavsett om kontot finns."""
    audit_log(
        db,
        entity_type="auth",
        entity_id=0,
        action="login_failed",
        old_value=None,
        new_value={"username": str(username or "")[:120], "ip": client_ip, "attempts_in_window": attempts},
        user_id=None,
        business_id=None,
    )
    db.commit()


def _register_login_failure(db: Session, username: str, client_ip: str, detail: str) -> HTTPException:
    attempts = login_rate_limiter.register_failure(username, client_ip)
    _audit_failed_login(db, username, client_ip, attempts)
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> UserOut:
    client_ip = client_ip_from_request(request)
    retry_after = login_rate_limiter.retry_after_seconds(payload.username, client_ip)
    if retry_after is not None:
        audit_log(
            db,
            entity_type="auth",
            entity_id=0,
            action="login_rate_limited",
            old_value=None,
            new_value={
                "username": str(payload.username or "")[:120],
                "ip": client_ip,
                "retry_after_seconds": retry_after,
            },
            user_id=None,
            business_id=None,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="För många inloggningsförsök. Vänta en stund och försök igen.",
            headers={"Retry-After": str(retry_after)},
        )
    user = db.query(User).filter_by(username=payload.username).one_or_none()
    if user is None:
        user = _auto_create_person_user(db, payload.username)
    if user is None or not user.is_active:
        raise _register_login_failure(db, payload.username, client_ip, "Felaktigt användarnamn eller lösenord")
    if user.password_hash is None:
        if payload.password:
            raise _register_login_failure(
                db, payload.username, client_ip, "Lämna lösenordet tomt vid första inloggningen"
            )
    elif not verify_password(payload.password, user.password_hash):
        raise _register_login_failure(db, payload.username, client_ip, "Felaktigt användarnamn eller lösenord")
    login_rate_limiter.reset(payload.username, client_ip)
    request.session["user_id"] = user.id
    if is_demo_user(user):
        try:
            demo_session.start_demo_session(request, user)
        except Exception:
            logger.exception("Kunde inte starta demo-session")
            request.session.clear()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Demo-läget kunde inte starta just nu. Försök igen om en stund.",
            )
    return user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> None:
    demo_session.end_demo_session(request)
    request.session.clear()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return user_out(user)


@router.post("/set-password", response_model=UserOut)
def set_password(
    payload: PasswordSetRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    if not user_needs_password_setup(user):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lösenord är redan skapat")
    before = {
        "id": user.id,
        "username": user.username,
        "must_change_password": True,
        "password_hash_set": user.password_hash is not None,
    }
    user.password_hash = hash_password(payload.password)
    user.must_change_password = False
    audit_log(
        db,
        entity_type="user",
        entity_id=user.id,
        action="set_password",
        old_value=before,
        new_value={
            "id": user.id,
            "username": user.username,
            "must_change_password": False,
            "password_hash_set": True,
        },
        user_id=user.id,
    )
    db.commit()
    db.refresh(user)
    return user_out(user)
