from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import MessageResponse, UserCreate, UserManageOut
from ..security import get_current_user, get_password_hash


router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(get_current_user)])


def _visible_users_query(db: Session, current_user: User):
    query = db.query(User)
    if current_user.is_super_admin:
        return query.order_by(User.created_at.desc())
    if current_user.is_admin:
        return query.filter(User.is_super_admin.is_(False)).order_by(User.created_at.desc())
    return query.filter(User.id == current_user.id).order_by(User.created_at.desc())


def _can_delete_user(current_user: User, target_user: User) -> bool:
    if target_user.id == current_user.id:
        return False
    if target_user.is_super_admin:
        return False
    if current_user.is_super_admin:
        return True
    if current_user.is_admin:
        return not target_user.is_admin
    return False


def _to_user_manage_out(current_user: User, target_user: User) -> UserManageOut:
    return UserManageOut(
        id=target_user.id,
        username=target_user.username,
        is_admin=target_user.is_admin,
        is_super_admin=target_user.is_super_admin,
        has_mx_api_key=target_user.has_mx_api_key,
        masked_mx_api_key=target_user.masked_mx_api_key,
        role_label=target_user.role_label,
        created_at=target_user.created_at,
        can_delete=_can_delete_user(current_user, target_user),
        can_copy_mx_key=target_user.id == current_user.id and target_user.has_mx_api_key,
        can_delete_mx_key=target_user.id == current_user.id and target_user.has_mx_api_key,
    )


@router.get("", response_model=list[UserManageOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    users = _visible_users_query(db, current_user).all()
    return [_to_user_manage_out(current_user, item) for item in users]


@router.post("", response_model=UserManageOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只有管理员才能创建账号")
    if payload.is_admin and not current_user.is_super_admin:
        raise HTTPException(status_code=403, detail="只有超级管理员才能设置管理员")

    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=payload.username,
        password_hash=get_password_hash(payload.password),
        is_admin=bool(payload.is_admin and current_user.is_super_admin),
        is_super_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_user_manage_out(current_user, user)


@router.delete("/{user_id}", response_model=MessageResponse)
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="只有管理员才能删除账号")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.username == "admin" or user.is_super_admin:
        raise HTTPException(status_code=400, detail="超级管理员不能删除")
    if not _can_delete_user(current_user, user):
        raise HTTPException(status_code=403, detail="当前权限不允许删除该账号")

    db.delete(user)
    db.commit()
    return MessageResponse(message="用户已删除")
