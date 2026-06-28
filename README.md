# Rallyify API

Minimal Django REST Framework service for Rallyify route calculation. The API is initially scaffolded to sit in front of a self-hosted Valhalla service.

## Local Setup

```bash
cd rallyify-api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run The API

```bash
python manage.py runserver
```

The local API will be available at `http://127.0.0.1:8000`.

## Run Tests

```bash
pytest
python manage.py check
ruff check .
```

## Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

The `docker-compose.yml` file includes a commented Valhalla service placeholder. Building Valhalla tiles is intentionally left for a later task.

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `DEBUG` | `true` | Enables Django debug mode for local development. |
| `SECRET_KEY` | Dev fallback | Django secret key. Set a real value outside local development. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,0.0.0.0` | Comma-separated Django allowed hosts. |
| `VALHALLA_URL` | `http://localhost:8002` | Base URL for the Valhalla service. |

## Endpoints

### `GET /health`

Returns service health without failing when Valhalla is unavailable.

```json
{
  "ok": true,
  "service": "rallyify-routing-api",
  "valhalla": {
    "configured": true,
    "reachable": false
  }
}
```

### `POST /routes/calculate`

Route calculation is scaffolded but not implemented yet.

```json
{
  "error": "Route calculation is not implemented yet.",
  "code": "NOT_IMPLEMENTED"
}
```

## Planned Next Step

Implement `POST /routes/calculate` by validating route requests and forwarding them to the configured Valhalla adapter in `routing/valhalla.py`.
