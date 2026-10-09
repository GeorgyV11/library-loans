"""Авторизация: учётные записи библиотекарей, сессия в подписанной куке."""
import hashlib
import hmac
import os

from fastapi import HTTPException, Request


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return f"{salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), stored)


def authenticate(db, login: str, password: str):
    user = db.one("SELECT * FROM app_user WHERE login = %s", (login,))
    if user and check_password(password, user["password_hash"]):
        return user
    return None


def current_user(request: Request) -> dict:
    """Зависимость для API: без сессии - 401."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="требуется вход")
    return user
