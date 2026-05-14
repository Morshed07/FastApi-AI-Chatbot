"""Chat endpoint integration tests (AI calls are mocked)."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.ai_provider import AIResponse


@pytest.mark.asyncio
async def test_create_conversation(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/conversations/",
        json={"title": "Test Chat", "ai_provider": "openai"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test Chat"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_conversations(client: AsyncClient, auth_headers):
    # Create two conversations
    for i in range(2):
        await client.post(
            "/api/v1/conversations/",
            json={"title": f"Conv {i}"},
            headers=auth_headers,
        )

    resp = await client.get("/api/v1/conversations/", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_chat_message(client: AsyncClient, auth_headers):
    # Create conversation first
    conv_resp = await client.post(
        "/api/v1/conversations/",
        json={"title": "AI Test"},
        headers=auth_headers,
    )
    conversation_id = conv_resp.json()["id"]

    # Mock the AI provider
    mock_response = AIResponse(content="Hello! How can I help?", tokens_used=25, model="gpt-4o", provider="openai")

    with patch(
        "app.services.chat_service.get_ai_provider"
    ) as mock_provider_factory:
        mock_provider = AsyncMock()
        mock_provider.chat.return_value = mock_response
        mock_provider_factory.return_value = mock_provider

        resp = await client.post(
            "/api/v1/conversations/chat",
            json={"conversation_id": conversation_id, "message": "Hello!", "stream": False},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["assistant_message"]["content"] == "Hello! How can I help?"
    assert data["tokens_used"] == 25


@pytest.mark.asyncio
async def test_get_messages(client: AsyncClient, auth_headers):
    conv_resp = await client.post(
        "/api/v1/conversations/",
        json={"title": "Msgs Test"},
        headers=auth_headers,
    )
    conv_id = conv_resp.json()["id"]

    mock_response = AIResponse(content="Response", tokens_used=10, model="gpt-4o", provider="openai")

    with patch("app.services.chat_service.get_ai_provider") as mock_provider_factory:
        mock_provider = AsyncMock()
        mock_provider.chat.return_value = mock_response
        mock_provider_factory.return_value = mock_provider

        await client.post(
            "/api/v1/conversations/chat",
            json={"conversation_id": conv_id, "message": "Hi", "stream": False},
            headers=auth_headers,
        )

    msgs_resp = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    assert msgs_resp.status_code == 200
    messages = msgs_resp.json()
    assert len(messages) == 2  # user + assistant
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_delete_conversation(client: AsyncClient, auth_headers):
    conv_resp = await client.post(
        "/api/v1/conversations/",
        json={"title": "To Delete"},
        headers=auth_headers,
    )
    conv_id = conv_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/conversations/{conv_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers)
    assert get_resp.status_code == 404
