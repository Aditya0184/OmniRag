"""Single-owner authentication for the loopback Mac installation."""

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from contextlib import closing, contextmanager
from pathlib import Path

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

COOKIE = "omnirag_session"
ORIGINS = {
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
}


def password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=2**17,
        r=8,
        p=1,
        maxmem=256 * 1024 * 1024,
    )


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def denied(status: int, code: str, message: str):
    return JSONResponse({"detail": {"code": code, "message": message}}, status)


class AuthStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "auth.sqlite3"
        self.lock = threading.Lock()

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.row_factory = sqlite3.Row
            yield db

    def initialize(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS owner (
                    id INTEGER PRIMARY KEY CHECK(id=1), salt BLOB NOT NULL, hash BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, csrf TEXT NOT NULL,
                    expires REAL NOT NULL, touched REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_attempts (at REAL NOT NULL);
            """)
        self.path.chmod(0o600)

    def configured(self):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM owner").fetchone() is not None

    def set_password(self, password: str, *, replace=False):
        if not 15 <= len(password) <= 128:
            raise ValueError("Use a password between 15 and 128 characters.")
        salt = secrets.token_bytes(32)
        hashed = password_hash(password, salt)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM owner").fetchone() and not replace:
                raise ValueError("Owner already exists; use the explicit reset command.")
            db.execute("INSERT OR REPLACE INTO owner VALUES(1,?,?)", (salt, hashed))
            db.execute("DELETE FROM sessions")

    def verify(self, password):
        with self.connect() as db:
            row = db.execute("SELECT * FROM owner WHERE id=1").fetchone()
        return bool(row and hmac.compare_digest(password_hash(password, row["salt"]), row["hash"]))

    def login(self, password):
        # One expensive hash at a time; the persistent global budget also spans restarts.
        with self.lock:
            now = time.time()
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM login_attempts WHERE at < ?", (now - 60,))
                if db.execute("SELECT count(*) FROM login_attempts").fetchone()[0] >= 5:
                    return None, "limited"
                db.execute("INSERT INTO login_attempts VALUES(?)", (now,))
            if not self.verify(password):
                return None, "invalid"
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            with self.connect() as db:
                db.execute(
                    "DELETE FROM sessions WHERE expires < ? OR touched < ?", (now, now - 1800)
                )
                # Bound retained sessions; signing in replaces the owner's earlier sessions.
                db.execute("DELETE FROM sessions")
                db.execute(
                    "INSERT INTO sessions VALUES(?,?,?,?)",
                    (token_hash(token), csrf, now + 28800, now),
                )
            return {"token": token, "csrf": csrf}, None

    def session(self, token):
        if not token or len(token) > 128:
            return None
        now = time.time()
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE token=?", (token_hash(token),)
            ).fetchone()
            if not row or row["expires"] <= now or row["touched"] <= now - 1800:
                return None
            db.execute("UPDATE sessions SET touched=? WHERE token=?", (now, row["token"]))
            return dict(row)

    def logout(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token=?", (token_hash(token),))


class OwnerGuard:
    def __init__(self, app, store):
        self.app, self.store = app, store

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = scope["path"]
        protected = path.startswith("/api/") or path in {
            "/docs",
            "/redoc",
            "/openapi.json",
            "/docs/oauth2-redirect",
        }
        public = path in {"/api/v1/auth/session", "/api/v1/auth/login", "/api/v1/health"}
        if protected and not public:
            session = self.store.session(request.cookies.get(COOKIE))
            if not session:
                return await denied(401, "AUTH_REQUIRED", "Sign in to open your workspace.")(
                    scope, receive, send
                )
            if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
                csrf = request.headers.get("x-csrf-token", "")
                if not hmac.compare_digest(csrf.encode(), session["csrf"].encode()):
                    return await denied(403, "CSRF_DENIED", "Refresh your session and try again.")(
                        scope, receive, send
                    )

        async def no_cache(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"SAMEORIGIN"),
                    (b"referrer-policy", b"no-referrer"),
                    (
                        b"content-security-policy",
                        b"frame-ancestors 'self'; base-uri 'self'; form-action 'self'",
                    ),
                ]
                if protected:
                    message["headers"].append((b"cache-control", b"no-store"))
            await send(message)

        return await self.app(scope, receive, no_cache)


class LoginInput(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class PasswordInput(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=15, max_length=128)


def install_auth(app, settings, store):
    if settings.auth_enabled:
        app.add_middleware(OwnerGuard, store=store)

    @app.get("/api/v1/auth/session")
    def session(request: Request):
        if not settings.auth_enabled:
            return JSONResponse(
                {"enabled": False, "authenticated": True}, headers={"Cache-Control": "no-store"}
            )
        row = store.session(request.cookies.get(COOKIE))
        return JSONResponse(
            {
                "enabled": True,
                "authenticated": bool(row),
                "configured": store.configured(),
                "csrf": row["csrf"] if row else None,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/v1/auth/login")
    def login(body: LoginInput, request: Request):
        if not settings.auth_enabled:
            raise HTTPException(404)
        # Mandatory JSON custom header also protects clients without an Origin header.
        if (
            request.headers.get("origin") not in ORIGINS | {None}
            or request.headers.get("x-omnirag-login") != "1"
        ):
            return denied(403, "ORIGIN_DENIED", "Sign in from the local workspace.")
        row, error = store.login(body.password)
        if error:
            return denied(
                429 if error == "limited" else 401,
                "LOGIN_FAILED",
                "Too many attempts. Wait one minute."
                if error == "limited"
                else "Password not accepted.",
            )
        response = JSONResponse({"authenticated": True, "csrf": row["csrf"]})
        response.set_cookie(
            COOKIE,
            row["token"],
            max_age=28800,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
        )
        return response

    @app.post("/api/v1/auth/logout")
    def logout(request: Request):
        if not settings.auth_enabled:
            raise HTTPException(404)
        store.logout(request.cookies.get(COOKIE, ""))
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(COOKIE, path="/")
        return response

    @app.post("/api/v1/auth/password")
    def change_password(body: PasswordInput):
        if not settings.auth_enabled:
            raise HTTPException(404)
        with store.lock:
            if not store.verify(body.current_password):
                return denied(401, "PASSWORD_INCORRECT", "Current password not accepted.")
            store.set_password(body.new_password, replace=True)
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(COOKIE, path="/")
        return response
