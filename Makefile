.PHONY: install check lint types imports test test-int up down world tick demo serve client migrate relay soak antileak

install:
	uv sync

check: lint types imports test antileak

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

types:
	uv run mypy

imports:
	uv run lint-imports

test:
	uv run pytest -q -m "not integration"

test-int:
	uv run pytest -q -m "integration and not soak"

soak:
	uv run pytest -q -m soak

antileak:
	uv run pytest -q tests/antileak

up:
	docker compose up -d

down:
	docker compose down -v

migrate:
	uv run alembic upgrade head

world:
	uv run python -m frontier.cli.world

demo:
	uv run python -m frontier.cli.demo

serve:
	uv run uvicorn frontier.adapters.api.app:app --port 8000

client:
	cd client && npm install && npm run dev

tick:
	uv run python -m frontier.cli.tick

relay:
	uv run python -m frontier.cli.relay
