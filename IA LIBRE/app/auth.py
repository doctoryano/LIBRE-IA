from __future__ import annotations
import os
import time
import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from typing import Optional

from app.db import get_db, fetch_user_by_username

# Config
SECRET_KEY = os.environ.get("IJL_SECRET_KEY") or os.environ.get("SECRET_KEY") or "change_this_to_a_random_secret_in_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # 12h

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": int(expire.timestamp()), "iat": int(now.timestamp())})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception as e:
        raise Exception("Invalid token") from e

def auth_required(token: Optional[str]) -> str:
    if not token:
        raise Exception("Missing token")
    payload = decode_token(token)
    username = payload.get("sub") or payload.get("username")
    if not username:
        raise Exception("Invalid token payload")
    # Optionally verify user exists
    user = fetch_user_by_username(get_db(), username)
    if not user:
        raise Exception("User not found")
    return username