"""
Shared pytest fixtures.
Uses an in-memory SQLite database for fast, isolated tests.
"""
import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import Base, get_db
from app.main import create_app

# ── Event loop ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Test database (SQLite in-memory) ─────────────────────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    TestSession = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with TestSession() as session:
        yield session
        await session.rollback()


# ── App + HTTP client ─────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_db] = lambda: db_session
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── Auth helpers ──────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "username": "testuser", "password": "Secret123"},
    )
    assert resp.status_code == 201
    return resp.json()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, registered_user) -> dict:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "Secret123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
