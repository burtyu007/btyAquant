from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PolicyFile, User
from ..schemas import MessageResponse, PolicyDisplayColumn, PolicyFileDetail, PolicyFileListItem, PolicyFileUpsert, PolicyResultsOut
from ..security import get_current_user


POLICY_ROOT = Path(__file__).resolve().parents[3] / "policy"

router = APIRouter(prefix="/policies", tags=["policies"], dependencies=[Depends(get_current_user)])


def _split_fields(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _can_manage_policy(current_user: User, row: PolicyFile) -> bool:
    return current_user.is_admin or row.created_user_id == current_user.id


def _resolve_created_user_id(payload: PolicyFileUpsert, current_user: User, existing_row: PolicyFile | None = None) -> int:
    if payload.created_user_id is None:
        return existing_row.created_user_id if existing_row else current_user.id
    if current_user.is_admin:
        return payload.created_user_id
    if payload.created_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="普通用户只能将策略归属到自己名下")
    return payload.created_user_id


def _ensure_user_exists(db: Session, user_id: int) -> None:
    exists = db.query(User.id).filter(User.id == user_id).first()
    if not exists:
        raise HTTPException(status_code=400, detail="created_user_id 对应的用户不存在")


def _get_created_user_name(db: Session, user_id: int) -> str | None:
    user = db.query(User.username).filter(User.id == user_id).first()
    return user[0] if user else None


def _safe_policy_dir(folder: str | None) -> Path | None:
    if not folder:
        return None
    resolved = (POLICY_ROOT / folder).resolve()
    try:
        resolved.relative_to(POLICY_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"策略目录非法: {folder}") from exc
    return resolved


def _safe_file_path(policy_dir: Path | None, filename: str | None) -> Path | None:
    if not policy_dir or not filename:
        return None
    resolved = (policy_dir / filename).resolve()
    try:
        resolved.relative_to(policy_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"策略文件路径非法: {filename}") from exc
    return resolved


def _load_results(results_path: Path | None) -> tuple[dict[str, str], list[dict]]:
    if not results_path or not results_path.exists():
        return {}, []
    try:
        payload = json.loads(results_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"结果文件读取失败: {results_path.name}") from exc
    fields = payload.get("fields") or {}
    rows = payload.get("lists") or []
    if not isinstance(fields, dict) or not isinstance(rows, list):
        raise HTTPException(status_code=500, detail=f"结果文件结构不符合约定: {results_path.name}")
    return fields, rows


def _detect_results_format(results_path: Path | None) -> str:
    if not results_path or not results_path.exists():
        return "none"
    suffix = results_path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".html", ".htm"}:
        return "html"
    return "unknown"


def _load_html_results(results_path: Path | None) -> str | None:
    if not results_path or not results_path.exists():
        return None
    try:
        return results_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"HTML 结果文件读取失败: {results_path.name}") from exc


def _list_display_columns(fields: dict[str, str], list_show_fields: list[str], rows: list[dict]) -> list[PolicyDisplayColumn]:
    reverse_fields = {value: key for key, value in fields.items()}
    ordered_keys: list[str] = []
    for key in list_show_fields:
        if key not in ordered_keys:
            ordered_keys.append(key)
    return [PolicyDisplayColumn(key=key, label=reverse_fields.get(key, key)) for key in ordered_keys]


def _detail_display_columns(fields: dict[str, str], list_show_fields: list[str], rows: list[dict]) -> list[PolicyDisplayColumn]:
    reverse_fields = {value: key for key, value in fields.items()}
    ordered_keys: list[str] = []
    if rows:
        for key in rows[0].keys():
            if key not in ordered_keys:
                ordered_keys.append(key)
    for key in list_show_fields:
        if key not in ordered_keys:
            ordered_keys.append(key)
    return [PolicyDisplayColumn(key=key, label=reverse_fields.get(key, key)) for key in ordered_keys]


def _serialize_policy(row: PolicyFile, db: Session, current_user: User, include_detail: bool = False) -> PolicyFileListItem | PolicyFileDetail:
    policy_dir = _safe_policy_dir(row.folder)
    readme_path = _safe_file_path(policy_dir, row.readme)
    results_path = _safe_file_path(policy_dir, row.results)
    results_format = _detect_results_format(results_path)
    fields, rows = ({}, [])
    if results_format == "json":
        fields, rows = _load_results(results_path)
    base_payload = {
        "id": row.id,
        "name": row.name,
        "folder": row.folder,
        "readme": row.readme,
        "path": row.path,
        "results": row.results,
        "list_show_fields": _split_fields(row.list_show_fields),
        "script_language": Path(row.path).suffix.lstrip(".").lower() or "text",
        "script_filename": Path(row.path).name,
        "readme_exists": bool(readme_path and readme_path.exists()),
        "results_exists": bool(results_path and results_path.exists()),
        "result_count": len(rows),
        "created_user_id": row.created_user_id,
        "created_user_name": _get_created_user_name(db, row.created_user_id),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "can_edit": _can_manage_policy(current_user, row),
        "can_delete": _can_manage_policy(current_user, row),
        "results_format": results_format,
    }
    if not include_detail:
        return PolicyFileListItem(**base_payload)

    readme_content = None
    if readme_path and readme_path.exists():
        try:
            readme_content = readme_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"README 读取失败: {readme_path.name}") from exc

    results_data = None
    results_html_content = None
    if results_format == "json" and results_path and results_path.exists():
        results_data = PolicyResultsOut(fields=fields, lists=rows)
    elif results_format == "html":
        results_html_content = _load_html_results(results_path)

    return PolicyFileDetail(
        **base_payload,
        readme_content=readme_content,
        results_data=results_data,
        results_html_content=results_html_content,
        list_display_columns=_list_display_columns(fields, _split_fields(row.list_show_fields), rows),
        detail_display_columns=_detail_display_columns(fields, _split_fields(row.list_show_fields), rows),
    )


@router.get("", response_model=list[PolicyFileListItem])
def list_policy_files(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = db.query(PolicyFile).order_by(PolicyFile.updated_at.desc(), PolicyFile.id.desc()).all()
    return [_serialize_policy(row, db=db, current_user=current_user) for row in rows]


@router.get("/{policy_id}", response_model=PolicyFileDetail)
def get_policy_file(policy_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = db.query(PolicyFile).filter(PolicyFile.id == policy_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="策略不存在")
    return _serialize_policy(row, db=db, current_user=current_user, include_detail=True)


@router.post("", response_model=PolicyFileListItem)
def create_policy_file(payload: PolicyFileUpsert, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    created_user_id = _resolve_created_user_id(payload, current_user)
    _ensure_user_exists(db, created_user_id)
    row = PolicyFile(
        name=payload.name.strip(),
        folder=_normalize_optional_text(payload.folder),
        readme=payload.readme.strip(),
        path=payload.path.strip(),
        results=_normalize_optional_text(payload.results),
        list_show_fields=",".join(_split_fields(payload.list_show_fields)),
        created_user_id=created_user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_policy(row, db=db, current_user=current_user)


@router.put("/{policy_id}", response_model=PolicyFileListItem)
def update_policy_file(
    policy_id: int,
    payload: PolicyFileUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.query(PolicyFile).filter(PolicyFile.id == policy_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="策略不存在")
    if not _can_manage_policy(current_user, row):
        raise HTTPException(status_code=403, detail="当前账号不能修改这条策略")
    created_user_id = _resolve_created_user_id(payload, current_user, existing_row=row)
    _ensure_user_exists(db, created_user_id)

    row.name = payload.name.strip()
    row.folder = _normalize_optional_text(payload.folder)
    row.readme = payload.readme.strip()
    row.path = payload.path.strip()
    row.results = _normalize_optional_text(payload.results)
    row.list_show_fields = ",".join(_split_fields(payload.list_show_fields))
    row.created_user_id = created_user_id
    db.commit()
    db.refresh(row)
    return _serialize_policy(row, db=db, current_user=current_user)


@router.delete("/{policy_id}", response_model=MessageResponse)
def delete_policy_file(policy_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = db.query(PolicyFile).filter(PolicyFile.id == policy_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="策略不存在")
    if not _can_manage_policy(current_user, row):
        raise HTTPException(status_code=403, detail="当前账号不能删除这条策略")
    db.delete(row)
    db.commit()
    return MessageResponse(message="策略记录已删除")
