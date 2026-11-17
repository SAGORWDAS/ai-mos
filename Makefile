.PHONY: help env up down stop logs ps sh-api sh-db test lint fmt migrate psql doctor clean

COMPOSE = docker compose -f infra/docker-compose.yml

help:
	@echo "make env      create .env from .env.example if missing"
	@echo "make up       build and start db, redis, api, worker, web"
	@echo "make down     stop everything"
	@echo "make logs     follow logs"
	@echo "make ps       container status"
	@echo "make test     run backend tests"
	@echo "make lint     ruff check"
	@echo "make fmt      ruff format"
	@echo "make migrate  apply versioned PostgreSQL migrations"
	@echo "make psql     open a psql shell"
	@echo "make doctor   check local prerequisites"

env:
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")

up: env
	$(COMPOSE) up -d --build
	@echo "web  -> http://localhost:3000"
	@echo "api  -> http://localhost:8000/healthz"

down:
	$(COMPOSE) down

stop:
	$(COMPOSE) stop

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

sh-api:
	$(COMPOSE) exec api sh

sh-db:
	$(COMPOSE) exec db psql -U ai_mos -d ai_mos

test:
	$(COMPOSE) run --rm api pytest -q

lint:
	$(COMPOSE) run --rm api ruff check .

fmt:
	$(COMPOSE) run --rm api ruff format .

migrate:
	$(COMPOSE) run --rm migrate

psql:
	$(COMPOSE) exec db psql -U ai_mos -d ai_mos

doctor:
	powershell -ExecutionPolicy Bypass -File scripts/doctor.ps1

clean:
	$(COMPOSE) down -v
