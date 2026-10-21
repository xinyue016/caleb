from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from storage import ChatStorage


USERNAME_RE = re.compile(r"^[\w\u4e00-\u9fff-]{2,24}$", re.UNICODE)


class AuthError(RuntimeError):
    pass


def username_key(username: str) -> str:
    return username.strip().lower()


def hash_password(password: str, salt_hex: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        180_000,
    )
    return digest.hex()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_user(user: dict) -> dict:
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "display_name": user.get("display_name"),
        "created_at": user.get("created_at"),
        "last_login": user.get("last_login"),
    }


class AuthService:
    def __init__(self, storage: ChatStorage, session_days: int = 180):
        self.storage = storage
        self.session_days = session_days
        self.storage.delete_expired_sessions()

    def _create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(days=self.session_days)
        self.storage.create_session(
            user_id,
            token_hash(token),
            expires.isoformat(timespec="seconds"),
        )
        return token

    def register(self, username: str, password: str, display_name: str = "") -> tuple[str, dict]:
        username = username.strip()
        display_name = (display_name or username).strip()
        if not USERNAME_RE.match(username):
            raise AuthError("账号名需为 2 到 24 位中文、字母、数字、下划线或连字符")
        if len(password) < 4:
            raise AuthError("密码至少需要 4 位")
        if len(password) > 72:
            raise AuthError("密码不能超过 72 位")
        key = username_key(username)
        if self.storage.get_user_by_key(key):
            raise AuthError("该账号已经存在")

        user_id = "u_" + secrets.token_hex(12)
        salt_hex = secrets.token_bytes(16).hex()
        password_hash = hash_password(password, salt_hex)
        try:
            user = self.storage.create_user(
                user_id,
                username,
                key,
                display_name,
                password_hash,
                salt_hex,
            )
        except Exception as error:
            raise AuthError("账号创建失败，请更换账号名后重试") from error
        token = self._create_session(user_id)
        return token, public_user(user)

    def login(self, username: str, password: str) -> tuple[str, dict]:
        key = username_key(username)
        user = self.storage.get_user_by_key(key)
        if not user:
            raise AuthError("账号不存在")
        expected = hash_password(password, user["password_salt"])
        if not hmac.compare_digest(expected, user["password_hash"]):
            raise AuthError("密码错误")
        self.storage.update_last_login(user["id"])
        user = self.storage.get_user_by_id(user["id"])
        token = self._create_session(user["id"])
        return token, public_user(user)

    def authenticate(self, token: str) -> dict | None:
        if not token:
            return None
        record = self.storage.get_session(token_hash(token))
        if not record:
            return None
        expires_at = datetime.fromisoformat(record["expires_at"])
        if expires_at <= datetime.now(timezone.utc):
            self.storage.delete_session(token_hash(token))
            return None
        return public_user(record)

    def logout(self, token: str) -> None:
        if token:
            self.storage.delete_session(token_hash(token))
