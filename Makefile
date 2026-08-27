.PHONY: install check lint types imports test test-int up down demo world tick migrate

install:
	uv sync --extra dev

check: lint types imports test

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
	uv run pytest -q -m integration

up:
	docker compose up -d

down:
	docker compose down -v

demo:
	uv run python -m frontier.demo

migrate:
	uv run alembic upgrade head

world:
	uv run python -m frontier.cli.world

tick:
	uv run python -m frontier.cli.tick
