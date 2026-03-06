from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.user import UserCreate, UserLogin, UserResponse, LoginResponse, UserInfo
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    """회원가입"""
    service = AuthService(db)

    # 이메일 중복 확인
    if service.get_user_by_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미 등록된 이메일입니다."
        )

    user = service.create_user(user_data)
    return user


@router.post("/login", response_model=LoginResponse)
async def login(login_data: UserLogin, db: Session = Depends(get_db)):
    """로그인"""
    service = AuthService(db)
    user = service.authenticate_user(login_data.email, login_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = service.create_token(user.id)

    # 프론트엔드 형식에 맞게 응답
    return LoginResponse(
        token=access_token,
        user=UserInfo(
            id=user.id,
            email=user.email,
            name=user.name,
            plan=user.plan or "free"
        )
    )


@router.put("/password")
async def change_password(
    data: dict,
    db: Session = Depends(get_db),
    current_user=Depends(AuthService.get_current_user_dependency),
):
    """비밀번호 변경 (로그인 상태)"""
    current_pw = data.get("current_password", "")
    new_pw = data.get("new_password", "")

    if not current_pw or not new_pw:
        raise HTTPException(status_code=400, detail="현재 비밀번호와 새 비밀번호를 입력해주세요.")
    if len(new_pw) < 6:
        raise HTTPException(status_code=400, detail="새 비밀번호는 6자 이상이어야 합니다.")

    from app.core.security import verify_password, get_password_hash
    if not verify_password(current_pw, current_user.password):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")

    current_user.password = get_password_hash(new_pw)
    db.commit()
    return {"message": "비밀번호가 변경되었습니다."}


@router.post("/forgot-password")
async def forgot_password(data: dict, db: Session = Depends(get_db)):
    """비밀번호 재설정 이메일 발송"""
    email = data.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이메일을 입력해주세요."
        )

    # TODO: 실제 이메일 발송 로직 구현
    # 현재는 성공 응답만 반환
    return {"message": "비밀번호 재설정 링크가 이메일로 전송되었습니다."}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    db: Session = Depends(get_db),
    current_user = Depends(AuthService.get_current_user_dependency)
):
    """현재 로그인한 사용자 정보"""
    return current_user


@router.post("/check-email")
async def check_email(data: dict, db: Session = Depends(get_db)):
    """이메일 중복 확인"""
    email = data.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이메일을 입력해주세요."
        )

    service = AuthService(db)
    existing_user = service.get_user_by_email(email)

    if existing_user:
        return {
            "available": False,
            "reason": "already_exists",
            "message": "이미 사용 중인 이메일입니다."
        }

    return {
        "available": True,
        "reason": None,
        "message": "사용 가능한 이메일입니다."
    }


@router.post("/reset-password")
async def reset_password(data: dict, db: Session = Depends(get_db)):
    """비밀번호 재설정 요청"""
    email = data.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이메일을 입력해주세요."
        )

    service = AuthService(db)
    user = service.get_user_by_email(email)

    # 보안상 사용자 존재 여부와 관계없이 동일한 응답 반환
    # TODO: 실제 이메일 발송 로직 구현
    return {
        "success": True,
        "message": "비밀번호 재설정 이메일이 발송되었습니다."
    }
