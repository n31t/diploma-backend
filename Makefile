dev-backend:
	uv run uvicorn src.main:app --reload --port 3838

prod-backend:
	uv run uvicorn src.main:app --host 0.0.0.0 --port 8000

# Database migrations
migrate:
	uv run alembic revision --autogenerate -m "$(msg)"

migrate-upgrade:
	uv run alembic upgrade head

migrate-downgrade:
	uv run alembic downgrade -1

migrate-current:
	uv run alembic current

migrate-history:
	uv run alembic history --verbose