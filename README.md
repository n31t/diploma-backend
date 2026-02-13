# FastAPI Application with Telegram Bot

## Features

- **FastAPI** - Modern, fast web framework for building APIs
- **JWT Authentication** - Secure token-based authentication with refresh tokens
- **PostgreSQL** - Robust relational database with async support
- **SQLAlchemy 2.0** - Modern ORM with async/await support
- **Alembic** - Database migrations
- **Structured Logging** - JSON logs with correlation IDs
- **Docker & Docker Compose** - Full containerization support
- **Layered Architecture** - Clean separation: API � Service � Repository � Database


## Architecture

This project contains two separate processes:
1. **FastAPI API** (`src/main.py`) - HTTP REST API
2. **Telegram Bot** (`src/bot_main.py`) - Long-polling Telegram bot

Both share the same:
- Database (PostgreSQL)
- Redis cache
- Domain logic (services, repositories, models)
- Configuration

## Running Locally

### Option 1: Using Makefile (recommended for development)
```bash
# Copy environment file
cp .env.example .env

# Terminal 1: Run API
make dev-backend

# Terminal 2: Run Bot
make dev-bot
```

### Option 2: Using Docker Compose
```bash
# Copy environment file
cp .env.example .env

# Start everything
docker-compose up --build


```

## Production Deployment

### Using Docker Compose
```bash
docker-compose -f docker-compose.prod.yml up -d --build
```

### Using Separate Processes
```bash
# Run migrations first
alembic upgrade head

# Start API (use process manager like systemd/supervisor)
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4

# Start Bot (separate process)
python -m src.bot_main
```
