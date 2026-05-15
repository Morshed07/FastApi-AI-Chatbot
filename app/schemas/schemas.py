"""
Pydantic v2 schemas — request bodies, response models, shared types.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ── Shared ────────────────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list


# ── Auth ──────────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(
        ..., 
        min_length=3, 
        max_length=50, 
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    password: str = Field(..., min_length=8, max_length=128)
    re_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Individual field validation for complexity."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    @model_validator(mode="after")
    def check_passwords_match(self) -> Self:
        """Cross-field validation to ensure password confirmation matches."""
        if self.password != self.re_password:
            raise ValueError("Passwords do not match")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


# ── User ──────────────────────────────────────────────────────────────────────
class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Conversation ──────────────────────────────────────────────────────────────
class CreateConversationRequest(BaseModel):
    title: str = Field(default="New Conversation", max_length=500)
    ai_provider: Literal["openai", "anthropic"] = "openai"
    ai_model: str | None = None
    system_prompt: str | None = Field(default=None, max_length=4000)


class UpdateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    system_prompt: str | None = Field(default=None, max_length=4000)
    is_archived: bool | None = None


class ConversationResponse(BaseModel):
    id: str
    user_id: str
    title: str
    ai_provider: str
    ai_model: str
    system_prompt: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


# ── Message ───────────────────────────────────────────────────────────────────
class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    tokens_used: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Chat ──────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    conversation_id: str
    message: str = Field(min_length=1, max_length=32_000)
    stream: bool = False


class ChatResponse(BaseModel):
    conversation_id: str
    user_message: MessageResponse
    assistant_message: MessageResponse
    tokens_used: int | None = None


class StreamChunk(BaseModel):
    """Server-sent event payload for streaming responses."""
    conversation_id: str
    delta: str
    done: bool = False
    tokens_used: int | None = None
