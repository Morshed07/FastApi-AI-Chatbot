# AI Chatbot API

Production-grade AI chatbot backend built with **FastAPI**, supporting **OpenAI** and **Anthropic** providers, streaming responses, JWT auth, and full observability.

---

## Architecture

```
ai-chatbot/
├── app/
│   ├── api/v1/endpoints/     # HTTP route handlers (thin layer)
│   │   ├── auth.py           # /auth/register, /auth/login, /auth/me
│   │   ├── chat.py           # /conversations/* + /conversations/chat
│   │   └── health.py         # /health, /health/ready
│   ├── core/
│   │   ├── config.py         # Pydantic-settings (all env vars)
│   │   ├── exceptions.py     # Domain errors + global handlers
│   │   ├── logging.py        # Structured JSON logging (structlog)
│   │   └── security.py       # JWT + password hashing
│   ├── db/
│   │   ├── session.py        # Async SQLAlchemy engine + get_db
│   │   └── cache.py          # Redis async client + Cache helper
│   ├── middleware/
│   │   └── middleware.py     # Correlation ID, access log, security headers
│   ├── models/
│   │   └── models.py         # SQLAlchemy ORM: User, Conversation, Message
│   ├── schemas/
│   │   └── schemas.py        # Pydantic v2 request/response models
│   ├── services/
│   │   ├── ai_provider.py    # OpenAI + Anthropic abstraction + factory
│   │   ├── auth_service.py   # Registration, login, token refresh
│   │   └── chat_service.py   # Conversation + message orchestration
│   └── main.py               # App factory, middleware, lifespan
├── tests/
│   ├── conftest.py           # Fixtures (in-memory SQLite, HTTP client)
│   └── integration/          # End-to-end endpoint tests
├── docker/Dockerfile          # Multi-stage: development + production
├── docker-compose.yml         # Postgres + Redis + API + Celery + Flower
├── alembic.ini                # Database migration config
├── requirements.txt
├── pyproject.toml             # Ruff + mypy + coverage config
└── Makefile                   # Developer shortcuts
```

---

## Quick Start

### 1. Clone & configure

```bash
git clone <repo>
cd ai-chatbot
cp .env.example .env
# Edit .env — set your OPENAI_API_KEY / ANTHROPIC_API_KEY and SECRET_KEY
```

### 2. Run with Docker (recommended)

```bash
make docker-up
# API available at http://localhost:8000
# Flower at http://localhost:5555
```

### 3. Run locally

```bash
make install
# Start Postgres + Redis separately, then:
make migrate     # Run DB migrations
make dev         # Hot-reload dev server
```

---

## API Reference

### Auth

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Get tokens |
| POST | `/api/v1/auth/refresh` | Rotate tokens |
| GET  | `/api/v1/auth/me` | Current user |

### Conversations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/conversations/` | Create conversation |
| GET  | `/api/v1/conversations/` | List conversations |
| GET  | `/api/v1/conversations/{id}` | Get conversation |
| PATCH | `/api/v1/conversations/{id}` | Update title/prompt |
| DELETE | `/api/v1/conversations/{id}` | Delete |
| GET  | `/api/v1/conversations/{id}/messages` | Message history |
| POST | `/api/v1/conversations/chat` | Send message (+ `stream: true` for SSE) |

### System

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/health` | Shallow health check |
| `GET /api/v1/health/ready` | Deep readiness (DB + Redis) |
| `GET /metrics` | Prometheus metrics |
| `GET /docs` | Swagger UI (disabled in production) |

---

## Streaming

Send `"stream": true` in the chat request body to receive a Server-Sent Events stream:

```javascript
const response = await fetch('/api/v1/conversations/chat', {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ conversation_id: id, message: 'Hello!', stream: true }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const lines = decoder.decode(value).split('\n');
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const chunk = JSON.parse(line.slice(6));
      if (!chunk.done) process.stdout.write(chunk.delta);
    }
  }
}
```

---

## Testing

```bash
make test          # Full suite with coverage report
make test-fast     # Quick run (no coverage)
```

Tests use an **in-memory SQLite** database — no external services needed.

---

## Adding a New AI Provider

1. Subclass `BaseAIProvider` in `app/services/ai_provider.py`
2. Implement `chat()` and `stream_chat()`
3. Register in the `get_ai_provider()` factory
4. Add the provider name to the `Literal` type in `schemas.py`

---

## Production Checklist

- [ ] Set `APP_ENV=production` and a strong `SECRET_KEY`
- [ ] Configure `SENTRY_DSN` for error tracking
- [ ] Set `ALLOWED_ORIGINS` to your frontend domain
- [ ] Run migrations: `alembic upgrade head`
- [ ] Set `WORKERS` to `2 × CPU_cores + 1`
- [ ] Enable TLS termination at the load balancer
- [ ] Set up log aggregation (Datadog, Loki, CloudWatch)
- [ ] Configure Prometheus + Grafana for metrics
