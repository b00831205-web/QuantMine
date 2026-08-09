"""auth_users 表读写。"""

from __future__ import annotations

from sqlalchemy import MetaData, Table, func, select, update
from sqlalchemy.engine import Engine

from ....security import hash_password


def _user_row(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "passwordHash": row["password_hash"],
        "displayName": row["display_name"],
        "isActive": row["is_active"],
    }


def get_user_by_username(engine: Engine, username: str) -> dict | None:
    table = Table("auth_users", MetaData(), autoload_with=engine)
    statement = select(table).where(table.c.username == username)
    with engine.connect() as connection:
        row = connection.execute(statement).mappings().first()
    return _user_row(row) if row else None


def touch_last_login(engine: Engine, user_id: int) -> None:
    table = Table("auth_users", MetaData(), autoload_with=engine)
    statement = (
        update(table).where(table.c.id == user_id).values(last_login_at=func.now())
    )
    with engine.begin() as connection:
        connection.execute(statement)


def create_user(
    engine: Engine,
    *,
    username: str,
    password: str,
    display_name: str | None = None,
) -> dict:
    """新建用户（供 CLI 种子脚本调用）。用户名冲突由 UNIQUE 约束兜底。"""
    from sqlalchemy import insert

    table = Table("auth_users", MetaData(), autoload_with=engine)
    statement = (
        insert(table)
        .values(
            username=username,
            password_hash=hash_password(password),
            display_name=display_name,
        )
        .returning(*table.c)
    )
    with engine.begin() as connection:
        row = connection.execute(statement).mappings().one()
    return _user_row(row)
