# OFSD

Offshore fund management system: a Flask + SQLAlchemy API with a React + TypeScript frontend.
It tracks funds, batches, investors, investments, NAV valuations, withdrawals, and reports.

## Project layout

| Path | What's there |
| --- | --- |
| `main.py` | Flask app factory and blueprint registration |
| `config.py` | `TestingConfig`, `DevelopmentConfig`, `ProductionConfig` (reads `.env`) |
| `app/` | Feature modules (`Admin`, `Batch`, `Funds`, `Investments`, `Valuation`, `Reports`, ...) |
| `migrations/` | Alembic migrations (Flask-Migrate) |
| `tests/` | Backend pytest suite |
| `ofds-frontend/` | React 19 + Vite frontend |

## Backend

Requires Python 3.11 and PostgreSQL.

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file next to `config.py`. At minimum, set:

```
DATABASE_URI=postgresql://<user>:<password>@localhost/offshore
SECRET_KEY=<at least 32 bytes>
MAIL_PASSWORD=<smtp password>
```

`config.py` lists the other supported variables (mail, email queue, DB backups).

Run the dev server (listens on `http://127.0.0.1:4455`):

```bash
python main.py
```

## Frontend

```bash
cd ofds-frontend
cp .env.example .env
npm install
npm run dev
```

The Vite dev server runs on `http://localhost:5173` and proxies `/api` to the backend on port 4455.

## Tests

Backend tests use `TestingConfig`, which expects a local PostgreSQL database named `test-offshore`:

```bash
pytest tests
```

Frontend unit tests:

```bash
cd ofds-frontend
npm test
```

## Deployment

The `Dockerfile` builds a Gunicorn image that serves `main:app` on port 5000.
