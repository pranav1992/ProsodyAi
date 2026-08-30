import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, verify_password
from app.database import get_db
from app.models import User
from app.rate_limit import limiter
from app.schemas import Token, UserLogin

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
def login(request: Request, payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        logger.warning("failed login attempt for %s", payload.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return Token(access_token=create_access_token(user.id))
