# FastAPI Application with JWT Authentication

A production-ready FastAPI application with PostgreSQL, SQLAlchemy 2.0 async, JWT authentication, structured logging, and comprehensive Docker support.

## Features

- **FastAPI** - Modern, fast web framework for building APIs
- **JWT Authentication** - Secure token-based authentication with refresh tokens
- **PostgreSQL** - Robust relational database with async support
- **SQLAlchemy 2.0** - Modern ORM with async/await support
- **Alembic** - Database migrations
- **Structured Logging** - JSON logs with correlation IDs
- **Docker & Docker Compose** - Full containerization support
- **Layered Architecture** - Clean separation: API � Service � Repository � Database

## Quick Start

### Option 1: Using the Start Script (Recommended)



The script will guide you through:
1. Setting up environment variables
2. Choosing development or production mode
3. Building Docker images
4. Starting services
5. Running migrations

### Option 2: Using Docker Compose

```bash
# Development mode
docker compose up --build

# Production mode
docker compose -f docker-compose.prod.yml up -d --build

# Run migrations
docker compose run --rm migrate
```

### Option 4: Local Development (without Docker)

```bash
# Install dependencies
uv sync

# Copy environment file
cp .env.example .env

# Edit .env with your configuration

# Run migrations
alembic upgrade head

# Start server
uvicorn src.main:app --reload
```
