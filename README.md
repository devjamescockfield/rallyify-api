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

`.env.example` is staging-oriented. For local `runserver` development, set `DEBUG=true`, use a local `SECRET_KEY`, and use `VALHALLA_URL=http://localhost:8002` when Valhalla is published on your development machine.

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

The `docker-compose.yml` file runs Caddy, the API with Gunicorn, and Valhalla on one Docker network. Caddy is the only public service and publishes ports `80` and `443`. The API and Valhalla are internal-only Compose services.

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `DEBUG` | `true` | Enables Django debug mode for local development. Use `false` for staging. |
| `SECRET_KEY` | Dev fallback | Django secret key. Set a real value outside local development. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,0.0.0.0` | Comma-separated Django allowed hosts. |
| `VALHALLA_URL` | `http://localhost:8002` | Base URL for the Valhalla service. |
| `VALHALLA_TIMEOUT_SECONDS` | `10` | Outbound Valhalla request timeout. |
| `VALHALLA_HEALTH_TIMEOUT_SECONDS` | `1` | Short `/health` probe timeout for Valhalla `/status`. |
| `RALLYIFY_API_BASE_URL` | `http://127.0.0.1:8000` | Base URL used by local smoke-test scripts. |

## Staging Deployment

This repo is set up for a single Linux VM staging deployment:

- Caddy is exposed on host ports `80` and `443`.
- `rallyify-api` is internal behind Caddy at `rallyify-api:8000`.
- `valhalla` is internal-only at `valhalla:8002`.
- Django calls Valhalla with `VALHALLA_URL=http://valhalla:8002`.

The container image runs Django with Gunicorn:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --access-logfile - --error-logfile -
```

For staging, create an environment file from the example:

```bash
cp .env.staging.example .env
```

Required staging values:

```bash
DEBUG=false
SECRET_KEY=replace-me
ALLOWED_HOSTS=api-dev.example.com,localhost,127.0.0.1
VALHALLA_URL=http://valhalla:8002
VALHALLA_TIMEOUT_SECONDS=10
VALHALLA_HEALTH_TIMEOUT_SECONDS=1
RALLYIFY_API_BASE_URL=https://api-dev.example.com
```

Point a DNS `A` record for the staging subdomain, for example `api-dev.example.com`, at the VM public IP. Forward only ports `80` and `443` from the router/firewall to the VM. Caddy will request and renew TLS certificates and reverse proxy to `rallyify-api:8000`.

The included `Caddyfile` is:

```caddy
api-dev.example.com {
    reverse_proxy rallyify-api:8000
}
```

Replace `api-dev.example.com` in `Caddyfile`, `.env`, and DNS when using a different staging domain.

Place Valhalla data/config under:

```bash
./valhalla
```

For UK staging tests, place `united-kingdom-latest.osm.pbf` in that Valhalla working directory or in the subdirectory expected by the Valhalla image/config you are using. This repo does not yet include a verified tile-build command; keep Valhalla tile generation steps in server runbooks once proven against the chosen image and extract.

Do not expose Valhalla publicly. In the provided Compose file, the `valhalla` service uses `expose: 8002` instead of `ports`, so it is reachable by `rallyify-api` at `http://valhalla:8002` on the internal Docker network but not published to the host. Only add a Valhalla host port temporarily for diagnostics, and remove it before staging use.

Start staging-style services:

```bash
docker compose up --build -d
```

Validate the Compose file before deploy:

```bash
docker compose config
```

After DNS and the reverse proxy are live, smoke-test through the public staging URL:

```bash
RALLYIFY_API_BASE_URL=https://api-dev.example.com python scripts/smoke_test_route.py --route inverness-ullapool
```

Health check:

```bash
curl https://api-dev.example.com/health
```

Local development can still use Django's development server:

```bash
python manage.py runserver
```

## Endpoints

### `GET /health`

Returns service health without failing when Valhalla is unavailable.

```json
{
  "ok": true,
  "service": "rallyify-routing-api",
  "valhalla": {
    "configured": true,
    "reachable": true,
    "version": "3.5.1"
  }
}
```

`version` is included only when Valhalla's `/status` response provides it. `/health` still returns `200` when Valhalla is unavailable; in that case `reachable` is `false`.

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

## Valhalla Smoke Test

The normal test suite uses mocked Valhalla responses. A live Valhalla instance is only needed when manually smoke-testing route calculation end to end.

Start the Django API with `VALHALLA_URL` pointing at the Valhalla service:

```bash
VALHALLA_URL=http://localhost:8002 python manage.py runserver
```

Run the smoke script from another shell:

```bash
python scripts/smoke_test_route.py
```

The script uses `RALLYIFY_API_BASE_URL` or `http://127.0.0.1:8000` by default. It calls `/health`, then `POST /routes/calculate`. By default it prints a compact summary with route name, HTTP status, distance in miles and kilometres, duration, polyline point count, leg count, and the first manoeuvre instruction if present.

Use `--json` to print the full raw JSON responses:

```bash
python scripts/smoke_test_route.py --route inverness-ullapool --json
```

```bash
RALLYIFY_API_BASE_URL=http://127.0.0.1:8000 python scripts/smoke_test_route.py --route belfast-inverness
RALLYIFY_API_BASE_URL=http://127.0.0.1:8000 python scripts/smoke_test_route.py --route inverness-applecross --road-priority scenic
RALLYIFY_API_BASE_URL=http://127.0.0.1:8000 python scripts/smoke_test_route.py --route inverness-ullapool --road-priority prefer_b_roads
```

Expected behaviour:

- Without Valhalla running, `/routes/calculate` returns `502` with `code: "VALHALLA_UNAVAILABLE"`. The smoke script treats this as an understood local-dev outcome.
- With Valhalla running and routed data available, `/routes/calculate` returns `200` with `polyline`, `distanceMetres`, `durationSeconds`, and `legs`.
- `/health` should continue to return `200` even if Valhalla is unavailable.

### Smoke Test Curl Examples

Health:

```bash
curl http://127.0.0.1:8000/health
```

Belfast to Inverness:

```bash
curl -X POST http://127.0.0.1:8000/routes/calculate \
  -H 'Content-Type: application/json' \
  -d '{
    "waypoints": [
      {"latitude": 54.5973, "longitude": -5.9301, "name": "Belfast"},
      {"latitude": 57.4778, "longitude": -4.2247, "name": "Inverness"}
    ],
    "vehicleProfile": "car",
    "roadPriority": "balanced",
    "units": "imperial",
    "avoidMotorways": false
  }'
```

Inverness to Applecross:

```bash
curl -X POST http://127.0.0.1:8000/routes/calculate \
  -H 'Content-Type: application/json' \
  -d '{
    "waypoints": [
      {"latitude": 57.4778, "longitude": -4.2247, "name": "Inverness"},
      {"latitude": 57.4329, "longitude": -5.8111, "name": "Applecross"}
    ],
    "vehicleProfile": "car",
    "roadPriority": "scenic",
    "units": "imperial",
    "avoidMotorways": false
  }'
```

Inverness to Ullapool:

```bash
curl -X POST http://127.0.0.1:8000/routes/calculate \
  -H 'Content-Type: application/json' \
  -d '{
    "waypoints": [
      {"latitude": 57.4778, "longitude": -4.2247, "name": "Inverness"},
      {"latitude": 57.8983, "longitude": -5.1600, "name": "Ullapool"}
    ],
    "vehicleProfile": "car",
    "roadPriority": "prefer_b_roads",
    "units": "imperial",
    "avoidMotorways": false
  }'
```

### OSM Extract Choice

Use the smallest practical OSM extract for early local/server Valhalla tests. This keeps tile-building fast and makes failures easier to diagnose.

- For a first local Valhalla smoke test, use a small regional extract where possible.
- For NC500/server route testing, a Great Britain extract is likely the minimum useful dataset.
- Ireland/Northern Ireland data is optional unless testing Belfast or Northern Ireland routes.

This repo intentionally does not include a verified Valhalla tile-build command yet. Keep Valhalla setup commands in deployment notes once they have been tested against the chosen extract and server environment.

## Planned Next Step

Run the endpoint against a live local Valhalla instance and refine the route options once Rallyify's first route preferences are tested on real map data.
