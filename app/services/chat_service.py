"""
Chat service — orchestrates conversation persistence + AI calls.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.models.models import Conversation, Message, User
from app.schemas.schemas import (
    ChatRequest,
    ChatResponse,
    CreateConversationRequest,
    MessageResponse,
    UpdateConversationRequest,
)
from app.services.ai_provider import AIMessage, get_ai_provider

logger = get_logger(__name__)

_MAX_HISTORY_MESSAGES = 20  # messages sent to the AI


class ConversationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Conversations ─────────────────────────────────────────────────────────
    async def create_conversation(
        self, user_id: str, req: CreateConversationRequest
    ) -> Conversation:
        from app.core.config import settings

        model = req.ai_model or (
            settings.openai_model
            if req.ai_provider == "openai"
            else settings.anthropic_model
        )
        conv = Conversation(
            user_id=user_id,
            title=req.title,
            ai_provider=req.ai_provider,
            ai_model=model,
            system_prompt=req.system_prompt,
        )
        self.db.add(conv)
        await self.db.flush()
        logger.info("conversation_created", conversation_id=conv.id, user_id=user_id)
        return conv

    async def get_conversation(self, conversation_id: str, user_id: str) -> Conversation:
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(selectinload(Conversation.messages))
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise NotFoundError(f"Conversation {conversation_id} not found")
        if conv.user_id != user_id:
            raise ForbiddenError("You don't have access to this conversation")
        return conv

    async def list_conversations(
        self, user_id: str, page: int = 1, page_size: int = 20
    ) -> tuple[list[Conversation], int]:
        offset = (page - 1) * page_size

        total_result = await self.db.execute(
            select(func.count()).where(
                Conversation.user_id == user_id,
                Conversation.is_archived.is_(False),
            )
        )
        total = total_result.scalar_one()

        result = await self.db.execute(
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.is_archived.is_(False),
            )
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        conversations = list(result.scalars().all())
        return conversations, total

    async def update_conversation(
        self, conversation_id: str, user_id: str, req: UpdateConversationRequest
    ) -> Conversation:
        conv = await self.get_conversation(conversation_id, user_id)
        for field, value in req.model_dump(exclude_none=True).items():
            setattr(conv, field, value)
        await self.db.flush()
        return conv

    async def delete_conversation(self, conversation_id: str, user_id: str) -> None:
        conv = await self.get_conversation(conversation_id, user_id)
        await self.db.delete(conv)

    # ── Messages ──────────────────────────────────────────────────────────────
    async def get_messages(
        self, conversation_id: str, user_id: str
    ) -> list[Message]:
        conv = await self.get_conversation(conversation_id, user_id)
        return conv.messages

    # ── Chat ──────────────────────────────────────────────────────────────────
    async def chat(self, user_id: str, req: ChatRequest) -> ChatResponse:
        conv = await self.get_conversation(req.conversation_id, user_id)

        # Persist the user message
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content=req.message,
        )
        self.db.add(user_msg)
        await self.db.flush()

        # Build AI message history (most recent N messages)
        history = conv.messages[-_MAX_HISTORY_MESSAGES:]
        ai_messages = [AIMessage(role=m.role, content=m.content) for m in history]

        # Call AI provider
        provider = get_ai_provider(conv.ai_provider)
        ai_response = await provider.chat(
            messages=ai_messages,
            system_prompt=conv.system_prompt,
        )

        # Persist assistant response
        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=ai_response.content,
            tokens_used=ai_response.tokens_used,
        )
        self.db.add(assistant_msg)
        await self.db.flush()

        # Auto-title after first exchange
        if len(conv.messages) <= 2 and conv.title == "New Conversation":
            conv.title = req.message[:80]

        logger.info(
            "chat_completed",
            conversation_id=conv.id,
            tokens=ai_response.tokens_used,
            provider=conv.ai_provider,
        )

        return ChatResponse(
            conversation_id=conv.id,
            user_message=MessageResponse.model_validate(user_msg),
            assistant_message=MessageResponse.model_validate(assistant_msg),
            tokens_used=ai_response.tokens_used,
        )

    async def stream_chat(
        self, user_id: str, req: ChatRequest
    ) -> AsyncGenerator[str, None]:
        conv = await self.get_conversation(req.conversation_id, user_id)

        # Persist user message
        user_msg = Message(
            conversation_id=conv.id, role="user", content=req.message
        )
        self.db.add(user_msg)
        await self.db.flush()

        history = conv.messages[-_MAX_HISTORY_MESSAGES:]
        ai_messages = [AIMessage(role=m.role, content=m.content) for m in history]

        provider = get_ai_provider(conv.ai_provider)
        full_response = []

        async for chunk in provider.stream_chat(
            messages=ai_messages,
            system_prompt=conv.system_prompt,
        ):
            full_response.append(chunk)
            yield chunk

        # Persist full response after streaming completes
        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="".join(full_response),
        )
        self.db.add(assistant_msg)
        await self.db.flush()
