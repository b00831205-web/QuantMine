"""Create a login user (the seed/admin script for multi-user auth).

This project exposes no registration endpoint; an administrator seeds users into
the auth_users table with this script.

Usage:
    python scripts/create_user.py <username> <password> [display_name]
    python scripts/create_user.py <username> '' [display_name]   # generate and print a password

Passing an empty password generates a random one, which keeps fixed default
passwords out of deployment scripts -- exactly the entry point that mass
scanning takes over. A generated password is printed once, and only when the
account is really created: if the account already exists that password was never
written to the database.

Requires the QUANTMINE_DATABASE_URL environment variable (the same database as
the web backend). The database and tables must already exist (scripts/setup.py,
or the first `docker compose` start).
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

# 让 `app.security` 可被解析：把 webapi 目录加入 sys.path（app 包在 webapi/ 下）
_WEBAPI_DIR = Path(__file__).resolve().parent.parent / "webapi"
if str(_WEBAPI_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBAPI_DIR))

from quantmine.storage.database import get_engine
from sqlalchemy import MetaData, Table, select

from _credentials import emit

from app.security import hash_password

DEFAULT_WEB_URL = "http://localhost:5173"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    username = argv[1]
    password = argv[2] if len(argv) > 2 else ""
    display_name = argv[3] if len(argv) > 3 else None

    generated = not password
    if generated:
        password = secrets.token_urlsafe(18)

    engine = get_engine()
    table = Table("auth_users", MetaData(), autoload_with=engine)

    with engine.connect() as connection:
        exists = connection.execute(
            select(table.c.id).where(table.c.username == username)
        ).first()
    if exists:
        print(f"user already exists: {username}", file=sys.stderr)
        return 1

    from sqlalchemy import insert

    with engine.begin() as connection:
        connection.execute(
            insert(table).values(
                username=username,
                password_hash=hash_password(password),
                display_name=display_name,
            )
        )
    print(f"user created: {username}")
    if generated:
        emit([{
            "service": "quantmine",
            "url": DEFAULT_WEB_URL,
            "username": username,
            "password": password,
        }])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
