from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import (
    create_access_token,
    get_current_user,
    verify_password,
)
from backend.app.db.database import get_db
from backend.app.models.user import User


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(
            User.username == form_data.username
        )
    )

    if (
        user is None
        or not verify_password(
            form_data.password,
            user.password_hash,
        )
        or not user.is_active
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password.",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    token = create_access_token(user)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
        },
    }


@router.get("/me")
def current_user(
    user: User = Depends(
        get_current_user
    ),
):
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
    }
