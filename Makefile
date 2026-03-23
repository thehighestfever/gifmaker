DEV = docker-compose.dev.yaml

dev:
	docker compose -f $(DEV) down
	docker compose -f $(DEV) build --no-cache
	docker compose -f $(DEV) up -d

up:
	docker compose -f $(DEV) up -d

down:
	docker compose -f $(DEV) down

rebuild:
	docker compose -f $(DEV) build --no-cache

logs:
	docker compose -f $(DEV) logs -f

shell:
	docker compose -f $(DEV) exec app /bin/bash
