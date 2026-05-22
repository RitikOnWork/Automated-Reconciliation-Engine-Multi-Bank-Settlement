from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import Token, UserCreate, UserResponse
from app.security import (
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from app.services.audit import AuditService

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Registers a new administrative analyst or system administrator.
    """
    existing_user = db.query(User).filter(User.username == user_in.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
        
    hashed_password = get_password_hash(user_in.password)
    user = User(
        username=user_in.username,
        hashed_password=hashed_password,
        role=user_in.role,
        is_active=True
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Audit log this action
    AuditService.log_action(
        db=db,
        action="USER_REGISTRATION",
        performed_by="system",
        table_name="users",
        record_id=user.id,
        new_value={"username": user.username, "role": user.role},
        comments=f"Registered operator: {user.username}"
    )
    
    return user


@router.post("/token", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Validates credentials and generates standard JWT Bearer access token.
    """
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Inactive user account"
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.username,
        role=user.role,
        expires_delta=access_token_expires
    )
    
    # Audit log login
    AuditService.log_action(
        db=db,
        action="USER_LOGIN",
        performed_by=user.username,
        comments=f"Operator logged in: {user.username}"
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Returns the profile details of the currently authorized operator.
    """
    return current_user
