# FastAPI Template

A minimal, layered FastAPI starter.

## Structure

```
app/
├── main.py              # app factory + lifespan + /health
├── core/
│   └── config.py        # pydantic-settings config (reads .env)
├── api/
│   ├── router.py        # aggregates routers
│   └── endpoints/       # route handlers (items.py)
├── schemas/             # pydantic request/response models
├── services/            # business logic (item_service.py)
└── models/              # ORM / domain models (empty stub)
tests/                   # pytest + TestClient
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run

```bash
uvicorn app.main:app --reload
```

Docs at http://127.0.0.1:8000/docs · health at `/health`.

## Test

```bash
pip install pytest httpx
pytest
```
