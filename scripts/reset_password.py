"""Reset an existing user's password (the only recovery path when it is lost).

auth_users stores scrypt/bcrypt hashes, one-way by design, so "look up the old
password" does not exist -- it can only be replaced. By default this script
generates a random password, writes it to .initial-credentials.json and prints
it once.

Usage:
    python scripts/reset_password.py admin                # generate one
    python scripts/reset_password.py admin 'my password'  # set an explicit one

An explicit password travels through argv, where other users on the same machine
can read it from `ps`. Prefer the generated form unless you have a reason not to.

Requires the QUANTMINE_DATABASE_URL environment variable (the same database as
the web backend).
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

# 让 `app.security` 可被解析：app 包在 webapi/ 下
_WEBAPI_DIR = Path(__file__).resolve().parent.parent / "webapi"
if str(_WEBAPI_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBAPI_DIR))

from sqlalchemy import MetaData, Table, select, update

from quantmine.storage.database import get_engine

from _credentials import emit

from app.security import hash_password

DEFAULT_WEB_URL = "http://localhost:5173"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    username = argv[1]
    password = argv[2] if len(argv) > 2 else ""
    generated = not password
    if generated:
        password = secrets.token_urlsafe(18)

    engine = get_engine()
    table = Table("auth_users", MetaData(), autoload_with=engine)

    with engine.connect() as connection:
        row = connection.execute(
            select(table.c.id).where(table.c.username == username)
        ).first()
    if row is None:
        # 不建新号：拼错用户名却静默建一个，只会让人对着登录页更困惑
        print(
            f"no such user: {username}. Create it first with scripts/create_user.py.",
            file=sys.stderr,
        )
        return 1

    with engine.begin() as connection:
        connection.execute(
            update(table)
            .where(table.c.username == username)
            .values(password_hash=hash_password(password))
        )
    print(f"password reset: {username}")

    if generated:
        emit([{
            "service": "quantmine",
            "url": DEFAULT_WEB_URL,
            "username": username,
            "password": password,
        }])
    else:
        print("(explicit password used; not written to the credentials file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
