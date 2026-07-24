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

`.env.example` is staging-oriented. For local `runserver` development, set
`DEPLOYMENT_ENV=development`, `DEBUG=true`, use a local `SECRET_KEY`, and use
`VALHALLA_URL=http://localhost:8002` when Valhalla is published on your
development machine.

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
# Replace SECRET_KEY and set VALHALLA_IMAGE to the exact tested digest.
docker compose up --build
```

The `docker-compose.yml` file runs Caddy, the API with Gunicorn, and Valhalla on one Docker network. Caddy is the only public service and publishes ports `80` and `443`. The API and Valhalla are internal-only Compose services.

The example intentionally contains an unsafe secret placeholder and no
Valhalla image reference. Protected startup validation and Compose will refuse
to start until both values are replaced.

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `DEPLOYMENT_ENV` | `development` | Runtime profile: `development`, `staging`, or `production`. Protected profiles enforce secure startup settings. |
| `DEBUG` | `true` | Enables Django debug mode for local development. Use `false` for staging. |
| `SECRET_KEY` | Dev fallback | Django secret key. Set a real value outside local development. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,0.0.0.0` | Comma-separated Django allowed hosts. |
| `SECURE_HSTS_SECONDS` | `3600` in protected deployments | HSTS lifetime; increase only after validating the HTTPS deployment. |
| `REQUEST_BODY_MAX_BYTES` | `65536` | Maximum request body size accepted by Django (64 KiB). |
| `ROUTE_RATE_LIMIT_BURST` | `30/minute` | Per-client-IP burst limit for `POST /routes/calculate`. |
| `ROUTE_RATE_LIMIT_SUSTAINED` | `500/day` | Per-client-IP sustained limit for `POST /routes/calculate`. |
| `ROUTE_REPORT_USER_BURST_RATE` | `5/minute` | Per-authenticated-user report burst limit. |
| `ROUTE_REPORT_USER_HOURLY_RATE` | `20/hour` | Per-authenticated-user report hourly limit. |
| `ROUTE_REPORT_USER_DAILY_RATE` | `25/day` | Per-authenticated-user report daily limit. |
| `ROUTE_REPORT_IP_RATE` | `100/hour` | Secondary per-client-IP report limit. |
| `ROUTE_REPORT_IP_DAILY_RATE` | `100/day` | Per-client-IP report daily limit. |
| `ROUTE_REPORT_GLOBAL_RATE` | disabled | Optional global report safety limit. |
| `USER_DATA_USER_BURST_RATE` | `60/minute` | Per-user burst limit for authenticated `/v1` vehicle and drive APIs. |
| `USER_DATA_USER_DAILY_RATE` | `1000/day` | Per-user daily limit for authenticated `/v1` APIs. |
| `USER_DATA_IP_RATE` | `2000/day` | Secondary per-IP limit for authenticated `/v1` APIs. |
| `USER_DATA_MAX_VEHICLES` | `20` | Maximum vehicle profiles per authenticated user. |
| `DRIVE_HISTORY_DEFAULT_PAGE_SIZE` | `25` | Default completed-drive history page size. |
| `DRIVE_HISTORY_MAX_PAGE_SIZE` | `100` | Maximum caller-selectable drive history page size. |
| `ROUTE_DIAGNOSTIC_RETENTION_DAYS` | `14` | Retention for restricted route diagnostics. |
| `ROUTE_REPORT_EXACT_RETENTION_DAYS` | `30` | Retention for explicitly consented exact route details, except active investigations. |
| `ROUTE_REPORT_SUMMARY_RETENTION_DAYS` | `90` | Retention for report summaries. |
| `SUPABASE_URL` | none | HTTPS Supabase project URL used to validate the token issuer. |
| `SUPABASE_JWT_ISSUER` | `${SUPABASE_URL}/auth/v1` | Exact accepted access-token issuer. |
| `SUPABASE_JWKS_CACHE_SECONDS` | `600` | Per-worker public-key-set cache lifetime, capped at 10 minutes. |
| `SUPABASE_JWKS_TIMEOUT_SECONDS` | `3` | Timeout for refreshing Supabase public signing keys. |
| `SUPABASE_JWT_LEEWAY_SECONDS` | `30` | Small JWT clock-skew allowance. |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | SQLite lock wait used with WAL mode. |
| `ROUTE_MAX_ENDPOINT_SNAP_METRES` | `5000` | Maximum accepted start or destination snap distance. |
| `ROUTE_MAX_GEOMETRY_GAP_METRES` | `100000` | Maximum accepted gap between adjacent decoded geometry points. |
| `VALHALLA_URL` | `http://localhost:8002` | Base URL for the Valhalla service. |
| `VALHALLA_TIMEOUT_SECONDS` | `10` | Outbound Valhalla request timeout. |
| `VALHALLA_HEALTH_TIMEOUT_SECONDS` | `1` | Short `/health` probe timeout for Valhalla `/status`. |
| `VALHALLA_ENGINE_VERSION` | status value | Optional explicit engine version when `/status` does not expose it. |
| `VALHALLA_GRAPH_BUILD_ID` | none | Operator-assigned identifier for the deployed graph build. |
| `VALHALLA_OSM_DATA_DATE` | none | Operator-supplied OSM source-data date for the graph. |
| `DATABASE_PATH` | `db.sqlite3` | Diagnostic/report SQLite path; Compose uses `/app/data/db.sqlite3`. |
| `ROUTE_SLOW_WARNING_MS` | `1500` | Logs `/routes/calculate` diagnostics at warning level above this duration. |
| `GUNICORN_WORKERS` | `3` | Gunicorn worker process count. |
| `GUNICORN_TIMEOUT_SECONDS` | `30` | Hard worker timeout in seconds. |
| `GUNICORN_GRACEFUL_TIMEOUT_SECONDS` | `30` | Graceful worker restart timeout in seconds. |
| `GUNICORN_MAX_REQUESTS` | `1000` | Requests handled before recycling a worker. |
| `GUNICORN_MAX_REQUESTS_JITTER` | `100` | Random jitter added to worker recycling. |
| `VALHALLA_IMAGE` | none | Required exact tested Valhalla tag or, preferably, repository digest for Compose. |
| `RALLYIFY_API_BASE_URL` | `http://127.0.0.1:8000` | Base URL used by local smoke-test scripts. |

The route throttle uses Django's cache and the client IP forwarded by the
single Caddy proxy. With the default in-memory cache, each Gunicorn worker has
its own counters, so this is a basic beta guard rather than a precise
distributed quota.

## Staging Deployment

This repo is set up for a single Linux VM staging deployment:

- Caddy is exposed on host ports `80` and `443`.
- `rallyify-api` is internal behind Caddy at `rallyify-api:8000`.
- `valhalla` is internal-only at `valhalla:8002`.
- Django calls Valhalla with `VALHALLA_URL=http://valhalla:8002`.

The API container runs as the unprivileged `rallyify` user and starts Django
with Gunicorn. The equivalent command with default values is:

```bash
gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 30 \
  --graceful-timeout 30 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --access-logfile - \
  --error-logfile -
```

For staging, create an environment file from the example:

```bash
cp .env.staging.example .env
```

Required staging values:

```bash
DEPLOYMENT_ENV=staging
DEBUG=false
SECRET_KEY=<generate-a-long-random-value>
ALLOWED_HOSTS=api-dev.example.com,localhost,127.0.0.1
VALHALLA_IMAGE=ghcr.io/valhalla/valhalla-scripted@sha256:<tested-digest>
VALHALLA_URL=http://valhalla:8002
VALHALLA_TIMEOUT_SECONDS=10
VALHALLA_HEALTH_TIMEOUT_SECONDS=1
REQUEST_BODY_MAX_BYTES=65536
ROUTE_RATE_LIMIT_BURST=30/minute
ROUTE_RATE_LIMIT_SUSTAINED=500/day
ROUTE_REPORT_USER_BURST_RATE=5/minute
ROUTE_REPORT_USER_HOURLY_RATE=20/hour
ROUTE_REPORT_USER_DAILY_RATE=25/day
ROUTE_REPORT_IP_RATE=100/hour
ROUTE_REPORT_IP_DAILY_RATE=100/day
ROUTE_REPORT_GLOBAL_RATE=
ROUTE_DIAGNOSTIC_RETENTION_DAYS=14
ROUTE_REPORT_EXACT_RETENTION_DAYS=30
ROUTE_REPORT_SUMMARY_RETENTION_DAYS=90
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_JWT_ISSUER=https://YOUR_PROJECT.supabase.co/auth/v1
VALHALLA_GRAPH_BUILD_ID=uk-<build-date-or-release-id>
VALHALLA_OSM_DATA_DATE=<source-data-date>
RALLYIFY_API_BASE_URL=https://api-dev.example.com
```

Generate a secret without storing it in shell history:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(64))'
```

For `staging` and `production`, Django refuses to start if `DEBUG` is true,
`SECRET_KEY` is missing or still uses a documented placeholder,
`ALLOWED_HOSTS` is missing or contains `*`, or the deployment environment is
unknown. Protected startup also requires an HTTPS `SUPABASE_URL` and an issuer
that exactly matches `${SUPABASE_URL}/auth/v1`.

The container runs `python manage.py migrate --noinput` before Gunicorn starts.
Compose persists the SQLite diagnostic/report database in the
`route_beta_data` volume. Back up that volume before deployment changes that
touch migrations, then rebuild and restart with:

```bash
docker compose up --build -d
```

Point a DNS `A` record for the staging subdomain, for example `api-dev.example.com`, at the VM public IP. Forward only ports `80` and `443` from the router/firewall to the VM. Caddy will request and renew TLS certificates and reverse proxy to `rallyify-api:8000`.

The included `Caddyfile` is:

```caddy
api-dev.example.com {
    reverse_proxy rallyify-api:8000
}
```

Replace `api-dev.example.com` in `Caddyfile`, `.env`, and DNS when using a different staging domain.

Place Valhalla data/config under the server host path used by Compose:

```bash
/data/valhalla/custom_files
```

The Compose volume mapping is:

```yaml
/data/valhalla/custom_files:/custom_files
```

The Valhalla scripted image reads OSM `.osm.pbf` files from `/custom_files` and writes generated config, hash files, tiles, admin/timezone data, and tar output back into that same mapped directory.

For UK staging tests, place `united-kingdom-latest.osm.pbf` in `/data/valhalla/custom_files`.

Do not expose Valhalla publicly. In the provided Compose file, the `valhalla` service uses `expose: 8002` instead of `ports`, so it is reachable by `rallyify-api` at `http://valhalla:8002` on the internal Docker network but not published to the host. Only add a Valhalla host port temporarily for diagnostics, and remove it before staging use.

Compose requires `VALHALLA_IMAGE` to be an exact tested reference and will
fail before deployment if it is absent. This repository cannot derive the
current staging digest from source because the historical Compose reference
was `latest`. On the VM that already has the tested image, capture its
repository digest before pulling a newer image:

```bash
docker image inspect ghcr.io/valhalla/valhalla-scripted:latest \
  --format '{{index .RepoDigests 0}}'
```

Put the returned
`ghcr.io/valhalla/valhalla-scripted@sha256:...` value in `.env` as
`VALHALLA_IMAGE`. Keep that value with the release record so a rollback uses
the same image and persisted routing data.

All three services use Docker's `json-file` log driver with a maximum of five
10 MiB files per container. Compose healthchecks probe Valhalla `/status` and
the API's strict `/ready` endpoint. Caddy starts after the API is healthy, and
the API starts after Valhalla is healthy.

### Valhalla Tile Build Runbook

Create the Valhalla data directory on the VM:

```bash
sudo mkdir -p /data/valhalla/custom_files
sudo chown -R "$USER":"$USER" /data/valhalla
```

Download the Great Britain/UK OSM extract into the exact host path mounted by Compose:

```bash
cd /data/valhalla/custom_files
curl -L -o united-kingdom-latest.osm.pbf \
  https://download.geofabrik.de/europe/united-kingdom-latest.osm.pbf
```

Check that the file exists and looks plausible before starting Valhalla:

```bash
ls -lh /data/valhalla/custom_files/united-kingdom-latest.osm.pbf
file /data/valhalla/custom_files/united-kingdom-latest.osm.pbf
du -sh /data/valhalla/custom_files
```

Start the stack:

```bash
docker compose up --build -d
```

Watch Valhalla build logs. The first build can take a long time for the UK extract:

```bash
docker compose logs -f valhalla
```

In another shell, watch API/Caddy logs if needed:

```bash
docker compose logs -f rallyify-api caddy
```

When Valhalla is built and serving, `/health` should show `reachable: true`:

```bash
curl https://api-dev.example.com/health
```

Expected shape:

```json
{
  "ok": true,
  "service": "rallyify-routing-api",
  "valhalla": {
    "configured": true,
    "reachable": true,
    "version": "..."
  }
}
```

Smoke-test through the staging domain:

```bash
RALLYIFY_API_BASE_URL=https://api-dev.example.com \
  python scripts/smoke_test_route.py \
  --route inverness-ullapool \
  --road-priority prefer_b_roads
```

Compare priority outputs once basic routing works:

```bash
RALLYIFY_API_BASE_URL=https://api-dev.example.com \
  python scripts/compare_route_priorities.py \
  --route inverness-ullapool
```

### Valhalla Troubleshooting

No PBF files found:

- Confirm the host path is exactly `/data/valhalla/custom_files`.
- Confirm Compose maps `/data/valhalla/custom_files:/custom_files`.
- Confirm the file ends in `.osm.pbf` and is directly inside `/data/valhalla/custom_files`.
- Run `docker compose logs valhalla` and look for messages about `/custom_files`.

Valhalla container exits:

- Check `docker compose logs valhalla`.
- Confirm the PBF download completed and is not an HTML error page: `file /data/valhalla/custom_files/united-kingdom-latest.osm.pbf`.
- Check permissions on `/data/valhalla/custom_files`; the container must be able to write generated files there.
- If the process is killed during build, check memory pressure with `free -h` and disk pressure with `df -h`.

Build taking a long time:

- This is expected for a large UK extract on a small VM.
- Watch progress with `docker compose logs -f valhalla`.
- Use `du -sh /data/valhalla/custom_files` to confirm generated files are growing.
- Avoid restarting repeatedly during the first build unless logs are clearly stuck or the container has exited.

Not enough disk or RAM:

- Check disk with `df -h /data/valhalla/custom_files`.
- Check memory with `free -h`.
- Use a smaller regional extract for a first validation build if the VM is resource constrained.
- Consider increasing VM RAM/disk before building Great Britain/UK data.

Caddy/HTTPS works but `/health` is unreachable:

- Confirm `ALLOWED_HOSTS` includes the staging domain.
- Confirm `Caddyfile` uses the same domain and proxies to `rallyify-api:8000`.
- Check `docker compose ps` for running `caddy` and `rallyify-api` containers.
- Check `docker compose logs -f caddy rallyify-api`.
- If `/health` returns with `valhalla.reachable=false`, Caddy and Django are working; inspect Valhalla logs and the `/data/valhalla/custom_files` contents next.

`/health` works but routes return `502`:

- Confirm `/health` shows `valhalla.reachable=true`. If not, Valhalla is not reachable from Django yet.
- Check `docker compose logs -f valhalla` for tile-build failures or service startup errors.
- Confirm the route area is covered by the loaded extract. Inverness/Ullapool routes require the UK extract to have built successfully.
- Confirm `VALHALLA_URL=http://valhalla:8002` in `.env` and in `docker compose config` on the VM.
- If Valhalla is still building, wait for build logs to settle before rerunning the smoke test.
- If only long routes fail, Valhalla config may need route distance tuning in `/data/valhalla/custom_files/valhalla.json`; document and test that separately before changing staging defaults.

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

Prefer the route-priority staging smoke test after the first successful health check:

```bash
RALLYIFY_API_BASE_URL=https://api-dev.example.com python scripts/smoke_test_route.py --route inverness-ullapool --road-priority prefer_b_roads
RALLYIFY_API_BASE_URL=https://api-dev.example.com python scripts/compare_route_priorities.py --route inverness-ullapool
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
    "version": "3.7.0-d37aa595e"
  }
}
```

`version` is included only when Valhalla's `/status` response provides it. `/health` still returns `200` when Valhalla is unavailable; in that case `reachable` is `false`.

### `GET /ready`

Readiness uses the same summary shape as `/health`, but is strict for
orchestration. It returns `200` with `"ok": true` only when Valhalla `/status`
is reachable. It returns `503` with `"ok": false` while Valhalla is starting
or unavailable. This does not alter the public `/health` contract.

### `GET /routing/graph-info`

Returns non-sensitive information describing the active routing graph and the
API's supported request values:

```json
{
  "routingEngine": "valhalla",
  "engineVersion": "3.7.0-d37aa595e",
  "graphBuildId": "uk-2026-07-20",
  "osmDataDate": "2026-07-19",
  "supportedVehicleProfiles": ["car", "motorbike", "caravan"],
  "supportedRoutePriorities": [
    "fastest", "balanced", "scenic", "avoid_motorways", "prefer_b_roads"
  ]
}
```

Version/build fields are `null` when neither Valhalla `/status` nor the
corresponding environment variable provides them. Assign a graph build ID and
OSM date during each tile-data deployment so issue reports remain reproducible.
Live `/status` metadata takes precedence over configured fallback values. A
warning is logged when `VALHALLA_ENGINE_VERSION` contradicts the live engine,
and staging checks warn when graph build ID or OSM date is absent.

### `POST /routes/calculate`

Validates a Rallyify route request, forwards it to Valhalla's `/route` API, and returns a normalized response.

Requests must contain between 2 and 25 waypoints. Each optional waypoint name
is limited to 100 characters; latitude and longitude retain their existing
geographic bounds. Django rejects request bodies larger than 64 KiB by
default. The endpoint returns `429` when either configured per-client-IP route
limit is exceeded.

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
  "generatedAt": "2026-06-28T12:00:00+00:00",
  "requestId": "8ac93dbd-83a2-46c5-a08f-78e739588606",
  "routingMetadata": {
    "provider": "valhalla",
    "engineVersion": "3.7.0-d37aa595e",
    "graphBuildId": "uk-2026-07-20",
    "osmDataDate": "2026-07-19",
    "costingProfile": "auto",
    "roadPriority": "balanced",
    "units": "imperial",
    "fallbackUsed": false,
    "endpointSnaps": {
      "start": "under_25m",
      "destination": "25_to_100m"
    }
  }
}
```

The `polyline` field is a decoded array of `[longitude, latitude]` pairs for the current Rallyify mobile app `RouteResult` contract. `encodedPolyline` is retained as the raw Valhalla shape where available for diagnostics or future clients. The API does not return `bounds`; the app currently derives bounds from `polyline`.

`requestId` and `routingMetadata` are additive fields; the established route
fields remain unchanged. Routing metadata includes API/provider versions,
graph and data identifiers, costing/profile/priority/units, and fallback state.
Endpoint snap distances are intentionally coarse. Short-lived server
diagnostics retain only counts, timing/result summaries, and coarse snap bands;
they do not retain request coordinates or route geometry.

The API rejects missing/malformed geometry, non-finite or non-positive route
metrics, missing legs, endpoint snaps over the configured limit, severe
geometry discontinuities, and obvious start/end reversal. These checks do not
attempt to infer one-way restrictions from geometry, and the reported one-way
incident is not considered fixed until it is reproduced against a known graph.

### `POST /route-reports`

Accepts the Rallyify app `RouteIssueReport` envelope. The bearer token must be
a valid, unexpired Supabase user access token; issuer, audience, signature and
subject are verified against Supabase public JWKS. The report owner is always
derived from the verified `sub` claim. `/routes/report` remains an alias.

```http
Authorization: Bearer <supabase-access-token>
Idempotency-Key: route_issue_example
Content-Type: application/json
```

```json
{
  "id": "route_issue_example",
  "dedupeKey": "example",
  "category": "unnecessarilyLong",
  "description": "Banbury to Silverstone was unexpectedly long.",
  "diagnostics": {
    "appVersion": "1.0.0",
    "buildProfile": "preview",
    "routeProvider": "rallyify_api",
    "routingMode": "hosted",
    "providerRequestId": "8ac93dbd-83a2-46c5-a08f-78e739588606",
    "graphDataVersion": "uk-2026-07-20",
    "routePreference": "fastest",
    "vehicleProfile": "car",
    "routeDistanceMetres": 74000,
    "routeDurationSeconds": 5100,
    "activeManeuverIndex": null,
    "timestamp": "2026-07-20T12:00:00Z",
    "coarseArea": {
      "latitudeBand": 52.1,
      "longitudeBand": -1.3,
      "precision": "0.1_degree"
    }
  },
  "locationConsent": false,
  "createdAt": "2026-07-20T12:00:00Z",
  "retryCount": 0
}
```

App category values are `wrongWay`, `closedRoad`, `unsafeRoad`,
`unnecessarilyLong`, `wrongEntrance`, `incorrectInstruction`, and `other`.
They are stored under stable server-side category names. A new report returns
`201`. An identical retry for the same authenticated user and idempotency key
returns the original report with `409`, `status: "accepted"`, and
`duplicate: true`. Reusing the key for materially different content is
rejected with `422`, which the mobile queue does not treat as accepted.

`consentedRouteDetails` can contain route geometry, start, destination,
approximate incident location, and current manoeuvre only when
`locationConsent` is `true`; otherwise it is rejected. Description is capped
at 500 characters, road/direction fields have tighter limits, geometry at
5,000 points, and the global 64 KiB request limit also applies. Unknown nested
fields are rejected. Client-supplied user IDs are ignored. Screenshot upload
is not supported by this endpoint yet; preview testers can use the app's
redacted structured export alongside a separately shared screenshot.

### Beta Diagnostic Retention

Successful hosted routes have a 14-day request-ID diagnostic containing only
non-location summaries. Report summaries expire after 90 days. Exact geometry,
endpoints, incident location and manoeuvre details are stored only after
explicit consent and purged after 30 days unless the report is actively marked
`investigating`. There is no public report read endpoint.

Schedule this command daily. Retention cleanup is deliberately kept out of the
request path so concurrent report submissions do not contend with table-wide
deletes:

```bash
docker compose exec -T rallyify-api python manage.py purge_route_beta_data
```

The default Django throttle cache is process-local, so limits are approximate
across multiple Gunicorn workers. Configure a shared Redis-backed Django cache
before opening this endpoint beyond controlled beta testing. Access to Django
admin must be limited to authorised staff; reviewers can change status and
internal notes without exposing reporter email addresses.

Supabase user tokens are verified locally against the project's asymmetric
public keys at `${SUPABASE_JWT_ISSUER}/.well-known/jwks.json`. The key set is
cached in each Gunicorn worker for up to 10 minutes and refreshed for unknown
key IDs, so Supabase is not called for every report. Signature, expiry, issuer,
configured audience and UUID `sub` are validated. The service does not accept
shared beta tokens, JWT secrets or service-role keys for this endpoint. See
the [Supabase JWT verification documentation](https://supabase.com/docs/guides/auth/jwts)
for signing-key rotation timing.

SQLite connections use WAL mode, `synchronous=NORMAL`, and a 5-second busy
timeout by default. Report creation keeps only the individual insert inside a
transaction. This is appropriate for the controlled beta load, but migrate
report/diagnostic storage to PostgreSQL before a wider external beta or any
multi-VM deployment.

## Vehicle And Drive Sync API

The `/v1` API synchronises vehicle profiles and completed-drive summaries. All
endpoints require the same verified Supabase user access token used by route
reports:

```http
Authorization: Bearer <supabase-access-token>
Content-Type: application/json
```

Ownership always comes from the verified JWT `sub`. Request fields such as
`ownerId` or `userId` are rejected as unexpected fields; a client UUID alone
does not establish ownership.

### Endpoints

- `GET|POST /v1/vehicles`
- `GET|PATCH|DELETE /v1/vehicles/{id}`
- `POST /v1/vehicles/{id}/set-default`
- `GET|POST /v1/drives`
- `GET|PATCH|DELETE /v1/drives/{id}`
- `PUT|DELETE /v1/drives/{id}/fuel`

Vehicle responses use camel-case JSON and include `id`, `displayName`,
optional make/model/year/registration, fuel and category values, capacities,
one optional economy baseline, `isDefault`, timestamps, and `schemaVersion`.
At most one vehicle can be default for an owner. Deleting a vehicle sets its
drive/fuel references to null while retaining the historical vehicle-name
snapshots.

Create a completed-drive summary:

```json
{
  "completionId": "019c-drive-completion-1",
  "vehicleId": "36a4d365-7a77-41ba-8657-a09f6ee5e767",
  "routeTitleSnapshot": "NC500 day one",
  "routeId": "saved-route-123",
  "mode": "group",
  "groupId": "group-123",
  "startedAt": "2026-07-24T08:00:00Z",
  "finishedAt": "2026-07-24T10:00:00Z",
  "elapsedSeconds": 7200,
  "movingSeconds": 6300,
  "stoppedSeconds": 900,
  "actualDistanceMetres": 100000,
  "plannedDistanceMetres": 98000,
  "completionReason": "arrived",
  "rerouteCount": 1,
  "offRouteCount": 2
}
```

`averageOverallSpeedMps` and `averageMovingSpeedMps` are calculated and stored
by the API from canonical distance/time inputs. No GPS trace, start
coordinate, destination coordinate, or live tracking sample is accepted or
stored. History is ordered by completion time and paginated with `page` and
`pageSize`; page size defaults to 25 and is capped at 100.

`completionId` is unique per authenticated owner. A retry with identical
canonical content returns the existing drive with `200` and
`duplicate: true`. Reusing it with different content returns
`409 COMPLETION_ID_REUSED`. Different users can independently use the same
completion ID.

Fuel details are optional and are attached one-to-one to a completed drive.
`PUT` creates or replaces that drive's fuel details; it never creates another
drive. Supported methods are `fuel_used_entry`, `fill_to_fill`,
`fuel_level_estimate`, and `vehicle_profile_estimate`. `obd_measured` is
reserved in storage for future compatibility but is rejected by the API;
there is no OBD, Bluetooth, or telemetry ingestion.

UK MPG is calculated as:

```text
distance_miles / (fuel_litres / 4.54609)
```

Metric economy is `(fuel_litres / distance_kilometres) * 100`. Canonical
values are retained to four decimal places while display values are returned
to one decimal place. Fuel-level and profile calculations are always labelled
`estimated`. Profile estimate model `vehicle-profile-v1` uses only an
explicit vehicle baseline, applies modest speed/stopped-time penalties, and
bounds its consumption adjustment to `0.85x-1.25x`. It returns no estimate
when a baseline is absent.

### Limits And Privacy

Vehicle names are limited to 100 characters, make/model to 80, registration
to 32, and route titles to 200. Years must be between 1886 and next year.
Tank/battery capacity is capped at 300, distance at 10,000 km, duration at 31
days, calculated average speed at 100 m/s, and fuel at 1,000 litres. The
existing 64 KiB body limit and strict unknown-field validation apply.

Registration, fuel values, and personal identifiers are not written to
application logs. Admin list pages omit registration, and completion IDs are
read-only. Deleting drive history also deletes its fuel details. A future
account-deletion workflow must remove all `VehicleProfile`, `CompletedDrive`,
and `FuelEconomyRecord` rows for the verified Supabase subject.

The current Django database is separate from Supabase. Migration
`routing/migrations/0003_completeddrive_vehicleprofile_fueleconomyrecord_and_more.py`
applies only to the hosted Rallyify API database; no Supabase SQL or policy
change is involved.

Back up the API database and deploy the migration with:

```bash
docker compose exec -T rallyify-api python manage.py migrate --noinput
```

The container also runs migrations before Gunicorn starts. Creating the
migration in this repository does not mean it has been deployed. SQLite WAL
mode and a busy timeout are suitable for the controlled single-VM beta, but
move user-owned vehicle/history data to PostgreSQL before wider external
testing, multi-VM deployment, or materially higher write concurrency. The
default throttle cache is per Gunicorn process; use a shared Redis cache when
quotas need to be exact across workers.

### `GET /routing/info`

Returns safe provider, graph/data/build identifiers and supported profile and
priority lists. It exposes no credentials, routes, coordinates or user data.

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

Compare route priority outputs for the same waypoints:

```bash
python scripts/compare_route_priorities.py --route inverness-ullapool
python scripts/compare_route_priorities.py --route inverness-applecross
```

The comparison script calls `/routes/calculate` once for each `roadPriority` value, then prints HTTP status, distance, duration, polyline point count, leg count, first manoeuvre, and distance/duration deltas compared with `balanced`. It uses `RALLYIFY_API_BASE_URL` or `http://127.0.0.1:8000` by default.

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
