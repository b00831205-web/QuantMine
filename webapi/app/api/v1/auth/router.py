"""Auth endpoints: login / logout / me.

这些端点**不**挂全局 require_user 网关（否则没登录就永远登不进来）；
其中 /auth/me 自身声明 require_user，用来做前端路由守卫的探针。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine

from ....dependencies import get_request_engine
from ....security import (
    clear_session_cookie,
    create_session_token,
    require_user,
    set_session_cookie,
    verify_password,
)
from .db import get_user_by_username, touch_last_login

router = APIRouter()


class LoginBody(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


def _public_user(user: dict) -> dict:
    return {"username": user["username"], "displayName": user["displayName"]}


@router.post("/auth/login")
def login(
    body: LoginBody,
    response: Response,
    engine: Engine = Depends(get_request_engine),
) -> dict:
    user = get_user_by_username(engine, body.username)
    # 统一 401，不区分“用户不存在”和“密码错误”，避免用户名枚举
    if user is None or not user["isActive"] or not verify_password(body.password, user["passwordHash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_session_token(user["id"], user["username"])
    set_session_cookie(response, token)
    touch_last_login(engine, user["id"])
    return _public_user(user)


@router.post("/auth/logout")
def logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/auth/me")
def me(user: dict = Depends(require_user)) -> dict:
    return {"username": user["username"], "displayName": None}
