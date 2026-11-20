"""Admin CLI.

  uv run python -m app.cli create-admin --username admin --full-name "Admin"
  uv run python -m app.cli reset-password --username demo
"""

import argparse
import asyncio
import getpass

from sqlalchemy import func, select

from app.auth.passwords import hash_password, password_ok
from app.auth.sessions import revoke_user_sessions
from app.db.models import AuditLog, User
from app.db.session import sessionmaker


def _ask_password(username: str) -> str:
    while True:
        pw = getpass.getpass("New password: ")
        if not password_ok(pw, username):
            print("Password must be at least 8 characters and different from the username.")
        elif pw != getpass.getpass("Repeat password: "):
            print("Passwords don't match.")
        else:
            return pw


async def create_admin(username: str, full_name: str) -> None:
    async with sessionmaker()() as db:
        if await db.scalar(select(User.id).where(func.lower(User.username) == username.lower())):
            print(f"User {username!r} already exists.")
            return
        user = User(username=username, full_name=full_name, password_hash=hash_password(_ask_password(username)),
                    role="admin", can_view_financials=True)
        db.add(user)
        await db.flush()
        db.add(AuditLog(action="user_created", target_type="user", target_id=str(user.id), details={"source": "cli"}))
        await db.commit()
        print(f"Admin {username!r} created.")


async def reset_password(username: str) -> None:
    async with sessionmaker()() as db:
        user = await db.scalar(select(User).where(func.lower(User.username) == username.lower()))
        if user is None:
            print(f"No user {username!r}.")
            return
        user.password_hash = hash_password(_ask_password(user.username))
        user.failed_login_count, user.locked_until = 0, None
        await revoke_user_sessions(db, user.id)
        db.add(AuditLog(action="password_reset", target_type="user", target_id=str(user.id), details={"source": "cli"}))
        await db.commit()
        print("Password reset.")


def main() -> None:
    p = argparse.ArgumentParser(prog="briha")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("create-admin")
    a.add_argument("--username", required=True)
    a.add_argument("--full-name", default="Administrator")
    r = sub.add_parser("reset-password")
    r.add_argument("--username", required=True)
    args = p.parse_args()
    if args.cmd == "create-admin":
        asyncio.run(create_admin(args.username, args.full_name))
    else:
        asyncio.run(reset_password(args.username))


if __name__ == "__main__":
    main()
