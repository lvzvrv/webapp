from fastapi.responses import RedirectResponse
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models
import hashlib
from app.database import SessionLocal
from fastapi.security import OAuth2PasswordBearer
import jwt

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_password_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password, hashed_password):
    return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password

def get_auth_token(login: str):
    return jwt.encode({"username": login}, "82eb42b3ee0620bd92158b2b7a4c8922d45d1541a67080933ec1e056b6227d91", algorithm="HS256")

def verify_auth_token(token: str):
    return jwt.decode(token, "82eb42b3ee0620bd92158b2b7a4c8922d45d1541a67080933ec1e056b6227d91", algorithms=["HS256"])["username"]

def authenticate_user(db: Session, username: str, password: str):
    user = db.query(models.User).filter(models.User.username == username).first()
    if user and verify_password(password, user.password_hash):
        return user
    return None

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(SessionLocal)):
    user = db.query(models.User).filter(models.User.username == token).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication")
    return user

def check_user(username: str, db: Session = Depends(SessionLocal)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if user:
        return user
    return None

def check_cookies(cookies):
    try:
        return verify_auth_token(cookies)
    except:
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.delete_cookie(key="Authorization")