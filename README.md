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
| `VALHALLA_TIMEOUT_SECONDS` | `10` | Outbound Valhalla request timeout. |

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

Validates a Rallyify route request, forwards it to Valhalla's `/route` API, and returns a normalized response.

Request:

```json
{
  "waypoints": [
    {
      "latitude": 54.123,
      "longitude": -5.123,
      "name": "Start"
    },
    {
      "latitude": 54.456,
      "longitude": -5.456,
      "name": "Finish"
    }
  ],
  "vehicleProfile": "car",
  "roadPriority": "balanced",
  "units": "imperial",
  "avoidMotorways": false
}
```

`roadPriority` accepts `fastest`, `balanced`, `scenic`, `avoid_motorways`, and `prefer_b_roads`. The separate `avoidMotorways` boolean is still supported as an explicit override.

Current first-pass Valhalla preference mapping:

| Rallyify setting | Valhalla costing options |
| --- | --- |
| `fastest` | default options |
| `balanced` | default options |
| `scenic` | `use_highways: 0.25` |
| `avoid_motorways` | `use_highways: 0.05` |
| `prefer_b_roads` | `use_highways: 0.35` |
| `avoidMotorways: true` | forces `use_highways: 0.05` |

These route preference values are intentionally conservative until they can be refined against a live Valhalla instance and real Rallyify route examples.

Response:

```json
{
  "encodedPolyline": "...",
  "polyline": [
    [-5.123, 54.123],
    [-5.456, 54.456]
  ],
  "distanceMetres": 12345,
  "durationSeconds": 1234,
  "legs": [
    {
      "distanceMetres": 12345,
      "durationSeconds": 1234,
      "summary": "Start to Finish",
      "maneuvers": [
        {
          "instruction": "Drive north.",
          "distanceMetres": 805,
          "type": "1",
          "bearing_after": 15,
          "beginShapeIndex": 0,
          "endShapeIndex": 1,
          "streetNames": ["Main Street"]
        }
      ]
    }
  ],
  "waypoints": [
    {
      "latitude": 54.123,
      "longitude": -5.123,
      "name": "Start"
    },
    {
      "latitude": 54.456,
      "longitude": -5.456,
      "name": "Finish"
    }
  ],
  "provider": "valhalla",
  "generatedAt": "2026-06-28T12:00:00+00:00"
}
```

The `polyline` field is a decoded array of `[longitude, latitude]` pairs for the current Rallyify mobile app `RouteResult` contract. `encodedPolyline` is retained as the raw Valhalla shape where available for diagnostics or future clients. The API does not return `bounds`; the app currently derives bounds from `polyline`.

## Planned Next Step

Run the endpoint against a live local Valhalla instance and refine the route options once Rallyify's first route preferences are tested on real map data.
