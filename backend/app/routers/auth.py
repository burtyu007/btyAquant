from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import LoginRequest, MXKeyRevealRequest, MXKeyRevealResponse, MXKeyUpdateRequest, TokenResponse, UserOut
from ..security import authenticate_user, create_access_token, get_current_user, verify_password
from ..services.crypto import encrypt_text


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user.username)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user=Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.post("/mx-key", response_model=UserOut)
def update_mx_key(payload: MXKeyUpdateRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    current_user.mx_api_key_encrypted = encrypt_text(payload.api_key.strip())
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.post("/mx-key/reveal", response_model=MXKeyRevealResponse)
def reveal_mx_key(payload: MXKeyRevealRequest, current_user=Depends(get_current_user)):
    if not current_user.mx_api_key_encrypted:
        raise HTTPException(status_code=404, detail="当前用户还没有配置 MX Key")
    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(status_code=403, detail="登录密码错误，无法复制 MX Key")
    from ..services.crypto import decrypt_text

    return MXKeyRevealResponse(api_key=decrypt_text(current_user.mx_api_key_encrypted))
