.PHONY: help up down logs ps clean test

help:
	@echo "Options Analytics Backend - Commands"
	@echo ""
	@echo "  make up      - Start all services"
	@echo "  make down    - Stop all services"
	@echo "  make logs    - View logs"
	@echo "  make ps      - Check running services"
	@echo "  make clean   - Remove all containers and volumes"
	@echo "  make test    - Run tests"
	@echo "  make shell   - Open API container shell"
	@echo "  make db      - Access PostgreSQL"
	@echo "  make redis   - Access Redis CLI"

up:
	docker-compose up -d
	@echo "✅ Services started"
	@echo "API: http://localhost:8000"
	@echo "Grafana: http://localhost:3000"

down:
	docker-compose down

logs:
	docker-compose logs -f api

ps:
	docker-compose ps

clean:
	docker-compose down -v
	docker system prune -f

test:
	docker-compose exec api pytest tests/ -v

shell:
	docker-compose exec api /bin/sh

db:
	docker-compose exec postgres psql -U options_user -d options_analytics

redis:
	docker-compose exec redis redis-cli
