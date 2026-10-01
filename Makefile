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
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app pipeline evals seeds/ai_players.py

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

# ---- LLM pipeline evals + AI players (plan 02) ----
EVAL_MODELS ?= gemini/gemini-3.8-flash,claude/claude-sonnet-5,claude/claude-opus-4-8,claude/claude-opus-5-5

.PHONY: eval eval-offline eval-fake sync-evals prewarm ai-players

eval:  ## live run (GCP_PROJECT + ADC); resumable: rerun the same command
	cd backend && uv run python -m evals.run --models $(EVAL_MODELS)

eval-offline:  ## CI-safe: re-score the committed recordings, no keys, no network
	cd backend && uv run python -m evals.run --offline

eval-fake:  ## refresh the fake recording behind the CI floor test
	cd backend && uv run python -m evals.run --models fake/fake-gold --reports-dir evals/.cache/fake-report

sync-evals:  ## copy the report into the web build (/evals)
	mkdir -p web/src/data && cp backend/evals/reports/latest.json web/src/data/eval-report.json

prewarm:  ## after deploy: API_URL=https://api-... INTERNAL_API_KEY=... make prewarm
	cd backend && uv run python -m pipeline.cli prewarm --api $(API_URL)

ai-players:  ## after seeding prod: API_URL=... INTERNAL_API_KEY=... make ai-players
	cd backend && uv run python -m seeds.ai_players --api $(API_URL)
