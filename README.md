# Env Management

Manage environments (dev, staging, prod, …) and their configuration variables.

- **Frontend:** React 18 + Vite (`frontend/`)
- **Backend:** Python, FastAPI + SQLAlchemy 2, SQLite by default (`backend/`)

## Project structure

```
env-management/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, CORS, router registration
│   │   ├── config.py          # Settings (env vars / .env)
│   │   ├── database.py        # Engine, session, Base
│   │   ├── models.py          # Environment, Variable ORM models
│   │   ├── schemas.py         # Pydantic request/response schemas
│   │   └── routers/
│   │       ├── health.py
│   │       ├── environments.py
│   │       └── variables.py
│   ├── tests/                 # pytest API tests (in-memory SQLite)
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── api/client.js      # fetch wrapper for the backend API
    │   ├── components/        # EnvironmentSidebar, VariableTable, VariableRow
    │   ├── App.jsx
    │   └── main.jsx
    ├── vite.config.js         # dev proxy: /api -> http://localhost:8000
    └── package.json
```

## Getting started

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

Run tests:

```bash
pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. In development, Vite proxies `/api` to the backend on port 8000.

## API

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/health` | Health check |
| GET / POST | `/api/environments` | List / create environments |
| GET / PATCH / DELETE | `/api/environments/{id}` | Read / update / delete an environment |
| GET / POST | `/api/environments/{id}/variables` | List / create variables |
| PATCH / DELETE | `/api/environments/{id}/variables/{var_id}` | Update / delete a variable |
| GET | `/api/environments/{id}/variables/export/dotenv` | Download variables as a `.env` file |

## Configuration

Backend settings (see `backend/.env.example`):

| Variable | Default |
| -------- | ------- |
| `DATABASE_URL` | `sqlite:///./env_management.db` |
| `CORS_ORIGINS` | `["http://localhost:5173"]` |

## Next steps

- Authentication and per-user/role access
- Encrypt secret values at rest
- Alembic migrations (tables are currently auto-created on startup)
- Audit history of variable changes
- Compare / promote variables between environments
- Docker / docker-compose setup
