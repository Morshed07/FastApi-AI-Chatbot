"""
Conversation management + chat endpoints.
Supports both regular JSON responses and SSE streaming.
"""
import json

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.db.session import get_db
from app.schemas.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationResponse,
    CreateConversationRequest,
    MessageResponse,
    UpdateConversationRequest,
)
from app.services.chat_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ── Conversations ─────────────────────────────────────────────────────────────
@router.post("/", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    req: CreateConversationRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Create a new conversation thread."""
    svc = ConversationService(db)
    conv = await svc.create_conversation(user_id, req)
    return ConversationResponse.model_validate(conv)


@router.get("/", response_model=dict)
async def list_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Paginated list of the user's conversations."""
    svc = ConversationService(db)
    conversations, total = await svc.list_conversations(user_id, page, page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [ConversationResponse.model_validate(c) for c in conversations],
    }


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    svc = ConversationService(db)
    conv = await svc.get_conversation(conversation_id, user_id)
    return ConversationResponse.model_validate(conv)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    req: UpdateConversationRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    svc = ConversationService(db)
    conv = await svc.update_conversation(conversation_id, user_id, req)
    return ConversationResponse.model_validate(conv)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = ConversationService(db)
    await svc.delete_conversation(conversation_id, user_id)


# ── Messages ──────────────────────────────────────────────────────────────────
@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    svc = ConversationService(db)
    messages = await svc.get_messages(conversation_id, user_id)
    return [MessageResponse.model_validate(m) for m in messages]


# ── Chat ──────────────────────────────────────────────────────────────────────
@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse | StreamingResponse:
    """
    Send a message and receive an AI response.
    Set `stream: true` in the request body to get a Server-Sent Events stream.
    """
    svc = ConversationService(db)

    if req.stream:
        async def event_generator():
            async for chunk in svc.stream_chat(user_id, req):
                data = json.dumps({"delta": chunk, "done": False})
                yield f"data: {data}\n\n"
            yield f"data: {json.dumps({'delta': '', 'done': True})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return await svc.chat(user_id, req)
