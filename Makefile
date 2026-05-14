.PHONY: help install dev test lint format migrate docker-up docker-down clean

help:
	@echo "Available commands:"
	@echo "  make install      Install dependencies"
	@echo "  make dev          Start development server with hot-reload"
	@echo "  make test         Run test suite with coverage"
	@echo "  make lint         Run ruff + mypy"
	@echo "  make format       Auto-format with ruff"
	@echo "  make migrate      Run pending Alembic migrations"
	@echo "  make revision     Create new Alembic migration (MSG=...)"
	@echo "  make docker-up    Start all services with docker-compose"
	@echo "  make docker-down  Stop all services"
	@echo "  make clean        Remove cache files"

install:
	pip install --upgrade pip
	pip install -r requirements.txt

dev:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug

test:
	pytest

test-fast:
	pytest -x -q --no-cov

lint:
	ruff check app tests
	mypy app

format:
	ruff check --fix app tests
	ruff format app tests

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(MSG)"

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .mypy_cache .ruff_cache .pytest_cache htmlcov .coverage
