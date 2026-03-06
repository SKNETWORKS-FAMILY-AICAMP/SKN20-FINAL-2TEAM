from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional

from app.database import get_db
from app.models.project import Project, ProjectSession, ProjectType
from app.models.chat import Chat, Message
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("")
async def create_project(
    data: dict,
    db: Session = Depends(get_db),
    current_user=Depends(AuthService.get_current_user_dependency),
):
    """프로젝트 생성."""
    name = data.get("name", "").strip()
    ptype = data.get("type", "patent")
    if not name:
        raise HTTPException(status_code=400, detail="프로젝트 이름을 입력해주세요.")

    project = Project(
        user_id=current_user.id,
        name=name,
        type=ProjectType(ptype),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return {
        "id": project.id,
        "name": project.name,
        "type": project.type.value,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "session_count": 0,
    }


@router.get("")
async def list_projects(
    type: Optional[str] = "patent",
    db: Session = Depends(get_db),
    current_user=Depends(AuthService.get_current_user_dependency),
):
    """프로젝트 목록 조회."""
    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id, Project.type == type)
        .order_by(Project.updated_at.desc())
        .all()
    )
    result = []
    for p in projects:
        session_count = (
            db.query(ProjectSession)
            .filter(ProjectSession.project_id == p.id)
            .count()
        )
        result.append({
            "id": p.id,
            "name": p.name,
            "type": p.type.value,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            "session_count": session_count,
        })
    return result


@router.post("/{project_id}/sessions")
async def add_session_to_project(
    project_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user=Depends(AuthService.get_current_user_dependency),
):
    """세션을 프로젝트에 추가."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    chat_id = data.get("chat_id")
    thread_id = data.get("thread_id")

    if not chat_id and not thread_id:
        raise HTTPException(status_code=400, detail="chat_id 또는 thread_id를 입력해주세요.")

    # 중복 체크
    existing = db.query(ProjectSession).filter(
        ProjectSession.project_id == project_id,
        or_(
            ProjectSession.chat_id == chat_id if chat_id else False,
            ProjectSession.thread_id == thread_id if thread_id else False,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="이미 프로젝트에 추가된 세션입니다.")

    ps = ProjectSession(
        project_id=project_id,
        chat_id=chat_id,
        thread_id=thread_id,
    )
    db.add(ps)
    db.commit()
    return {"message": "세션이 프로젝트에 추가되었습니다."}


@router.get("/{project_id}/sessions")
async def get_project_sessions(
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(AuthService.get_current_user_dependency),
):
    """프로젝트 내 세션 목록."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    sessions = (
        db.query(ProjectSession)
        .filter(ProjectSession.project_id == project_id)
        .order_by(ProjectSession.added_at.desc())
        .all()
    )

    result = []
    for ps in sessions:
        title = None
        if ps.chat_id:
            chat = db.query(Chat).filter(Chat.id == ps.chat_id).first()
            if chat:
                title = chat.title
        result.append({
            "id": ps.id,
            "chat_id": ps.chat_id,
            "thread_id": ps.thread_id,
            "title": title,
            "added_at": ps.added_at.isoformat() if ps.added_at else None,
        })
    return result


@router.get("/{project_id}/search")
async def search_project_sessions(
    project_id: int,
    q: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(AuthService.get_current_user_dependency),
):
    """프로젝트 내 대화 검색."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    if not q.strip():
        return []

    # 프로젝트에 속한 chat_id들
    chat_ids = [
        ps.chat_id for ps in
        db.query(ProjectSession.chat_id)
        .filter(ProjectSession.project_id == project_id, ProjectSession.chat_id.isnot(None))
        .all()
    ]

    if not chat_ids:
        return []

    messages = (
        db.query(Message)
        .filter(Message.chat_id.in_(chat_ids), Message.content.like(f"%{q}%"))
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )

    return [
        {
            "chat_id": m.chat_id,
            "content": m.content[:200],
            "role": m.role.value,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(AuthService.get_current_user_dependency),
):
    """프로젝트 삭제."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    db.delete(project)
    db.commit()
    return {"message": "프로젝트가 삭제되었습니다."}


@router.delete("/{project_id}/sessions/{session_id}")
async def remove_session_from_project(
    project_id: int,
    session_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(AuthService.get_current_user_dependency),
):
    """프로젝트에서 세션 제거."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    ps = (
        db.query(ProjectSession)
        .filter(ProjectSession.id == session_id, ProjectSession.project_id == project_id)
        .first()
    )
    if not ps:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    db.delete(ps)
    db.commit()
    return {"message": "세션이 프로젝트에서 제거되었습니다."}
