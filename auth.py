from datetime import datetime
from hashlib import sha256
from secrets import token_urlsafe
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from pydantic import BaseModel, Field, SecretStr, StringConstraints, field_validator

from db import connect

router = APIRouter()
passwords = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
Username = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9_.-]{3,50}$")
]


class Credentials(BaseModel):
    username: Username
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, username: str) -> str:
        return username.lower()


class Registration(Credentials):
    password: SecretStr = Field(min_length=12, max_length=128)


class Account(BaseModel):
    id: int
    username: str
    role: Literal["user", "teacher", "admin"]
    status: Literal["pending", "approved", "rejected"]
    created_at: datetime
    reviewed_at: datetime | None
    reviewed_by: int | None


class Review(BaseModel):
    status: Literal["approved", "rejected"]


class TeacherRole(BaseModel):
    role: Literal["teacher"]


class LoginToken(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


class Room(BaseModel):
    id: int
    code: str
    name: str
    capacity: int | None


def unauthorized(detail: str = "登入已失效或尚未登入") -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def session_hash(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> bytes:
    if credentials is None:
        raise unauthorized()
    return sha256(credentials.credentials.encode()).digest()


SessionHash = Annotated[bytes, Depends(session_hash)]


def current_user(token_hash: SessionHash) -> Account:
    with connect() as db:
        row = db.execute(
            """
            SELECT u.id, u.username, u.role, u.status, u.created_at, u.reviewed_at, u.reviewed_by
            FROM auth_sessions AS s JOIN users AS u ON u.id = s.user_id
            WHERE s.token_hash = %s AND s.expires_at > now() AND u.status = 'approved'
            """,
            (token_hash,),
        ).fetchone()
    if row is None:
        raise unauthorized()
    return Account.model_validate(row)


CurrentUser = Annotated[Account, Depends(current_user)]


def require_admin(account: CurrentUser) -> Account:
    if account.role != "admin":
        raise HTTPException(403, "需要管理員權限")
    return account


Admin = Annotated[Account, Depends(require_admin)]


@router.post("/auth/register", response_model=Account, status_code=201)
def register(account: Registration):
    password_hash = passwords.hash(account.password.get_secret_value())
    with connect() as db:
        row = db.execute(
            """
            INSERT INTO users (username, password_hash) VALUES (%s, %s)
            ON CONFLICT (username) DO NOTHING
            RETURNING id, username, role, status, created_at, reviewed_at, reviewed_by
            """,
            (account.username, password_hash),
        ).fetchone()
    if row is None:
        raise HTTPException(409, "帳號已存在")
    return row


@router.post("/auth/login", response_model=LoginToken)
def login(credentials: Credentials, response: Response):
    with connect() as db:
        account = db.execute(
            "SELECT id, password_hash, status FROM users WHERE username = %s",
            (credentials.username,),
        ).fetchone()
        password = credentials.password.get_secret_value()
        if account is None:
            passwords.hash(password)
            raise unauthorized("帳號或密碼錯誤")
        if not passwords.verify(password, account["password_hash"]):
            raise unauthorized("帳號或密碼錯誤")
        if account["status"] != "approved":
            detail = "帳號尚待審核" if account["status"] == "pending" else "帳號審核未通過"
            raise HTTPException(403, detail)

        token = token_urlsafe(32)
        db.execute("DELETE FROM auth_sessions WHERE expires_at <= now()")
        session = db.execute(
            """
            INSERT INTO auth_sessions (token_hash, user_id)
            SELECT %s, id FROM users WHERE id = %s AND status = 'approved'
            RETURNING expires_at
            """,
            (sha256(token.encode()).digest(), account["id"]),
        ).fetchone()
        if session is None:
            raise HTTPException(403, "帳號目前無法登入")
    response.headers["Cache-Control"] = "no-store"
    return LoginToken(access_token=token, expires_at=session["expires_at"])


@router.get("/auth/me", response_model=Account)
def me(account: CurrentUser):
    return account


@router.post("/auth/logout", status_code=204)
def logout(token_hash: SessionHash):
    with connect() as db:
        db.execute("DELETE FROM auth_sessions WHERE token_hash = %s", (token_hash,))


@router.get("/admin/users/pending", response_model=list[Account])
def pending_users(admin: Admin):
    with connect() as db:
        return db.execute(
            """
            SELECT id, username, role, status, created_at, reviewed_at, reviewed_by
            FROM users WHERE role = 'user' AND status = 'pending' ORDER BY id
            """
        ).fetchall()


@router.patch("/admin/users/{user_id}/review", response_model=Account)
def review_user(user_id: Annotated[int, Path(gt=0, le=2**63 - 1)], review: Review, admin: Admin):
    with connect() as db:
        row = db.execute(
            """
            UPDATE users SET status = %s, reviewed_at = now(), reviewed_by = %s
            WHERE id = %s AND role = 'user' AND status = 'pending'
            RETURNING id, username, role, status, created_at, reviewed_at, reviewed_by
            """,
            (review.status, admin.id, user_id),
        ).fetchone()
        if row is None:
            existing = db.execute("SELECT id FROM users WHERE id = %s", (user_id,)).fetchone()
            if existing is None:
                raise HTTPException(404, "找不到帳號")
            raise HTTPException(409, "此帳號目前無法審核")
    return row


@router.patch("/admin/users/{user_id}/role", response_model=Account)
def set_teacher(
    user_id: Annotated[int, Path(gt=0, le=2**63 - 1)],
    change: TeacherRole,
    admin: Admin,
):
    with connect() as db:
        row = db.execute(
            """
            UPDATE users SET role = %s
            WHERE id = %s AND role = 'user' AND status = 'approved'
            RETURNING id, username, role, status, created_at, reviewed_at, reviewed_by
            """,
            (change.role, user_id),
        ).fetchone()
        if row is None:
            existing = db.execute("SELECT id FROM users WHERE id = %s", (user_id,)).fetchone()
            if existing is None:
                raise HTTPException(404, "找不到帳號")
            raise HTTPException(409, "只有已核准的一般帳號可設為教師")
    return row


@router.get("/rooms", response_model=list[Room])
def rooms(account: CurrentUser):
    with connect() as db:
        return db.execute("SELECT id, code, name, capacity FROM rooms ORDER BY code").fetchall()
