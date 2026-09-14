install:
	pip install -e ".[dev]"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(m)"

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

run:
	uvicorn app.main:app --reload

worker:
	python -m app.workers.source_worker


scheduler:
	python -m app.workers.job_scheduler


outbox:
	python -m app.outbox.dispatcher

prod-up:
	docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

purge:
	python -m app.retention.purge

marinecadastre:
	python -m scripts.ingest_marinecadastre $(FILE)

osm-etl:
	python -m app.osm.etl --west $(W) --south $(S) --east $(E) --north $(N)