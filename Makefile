.PHONY: db gen check-gen test-backend lint-backend fmt-backend up down

db:
	docker compose up -d db

gen:
	cd backend && uv run python -m app.export_schemas
	cd web && pnpm run gen:api

check-gen: gen
	git diff --exit-code -- backend/openapi.json schemas web/src/lib/api/schema.d.ts

test-backend:
	cd backend && uv run pytest

lint-backend:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app

fmt-backend:
	cd backend && uv run ruff format . && uv run ruff check --fix .

up:
	docker compose --profile app up --build -d

down:
	docker compose --profile app down

.PHONY: migrate
migrate:
	cd backend && uv run alembic upgrade head

.PHONY: seed simulate
seed:
	cd backend && uv run python -m seeds.load --api $${API_BASE_URL:-http://localhost:8000}

simulate:
	cd backend && uv run python -m seeds.simulate_cohort --n 200
