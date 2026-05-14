"""
Auth service — registration, login, token refresh.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.models import User
from app.schemas.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.core.config import settings

logger = get_logger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, req: RegisterRequest) -> User:
        # Check uniqueness
        existing = await self.db.execute(
            select(User).where(
                (User.email == req.email) | (User.username == req.username)
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError("Email or username already taken")

        user = User(
            email=req.email,
            username=req.username,
            hashed_password=hash_password(req.password),
        )
        self.db.add(user)
        await self.db.flush()
        logger.info("user_registered", user_id=user.id, email=user.email)
        return user

    async def login(self, req: LoginRequest) -> TokenResponse:
        result = await self.db.execute(select(User).where(User.email == req.email))
        user = result.scalar_one_or_none()

        if not user or not verify_password(req.password, user.hashed_password):
            raise UnauthorizedError("Invalid email or password")
        if not user.is_active:
            raise UnauthorizedError("Account is deactivated")

        tokens = self._issue_tokens(user.id)
        logger.info("user_login", user_id=user.id)
        return tokens

    async def refresh(self, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type")

        user_id: str = payload.get("sub", "")
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise UnauthorizedError("User not found or deactivated")

        return self._issue_tokens(user.id)

    def _issue_tokens(self, user_id: str) -> TokenResponse:
        return TokenResponse(
            access_token=create_access_token(user_id),
            refresh_token=create_refresh_token(user_id),
            expires_in=settings.access_token_expire_minutes * 60,
        )
