#!/usr/bin/env python3
import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROUTES = {
    "belfast-inverness": [
        {
            "latitude": 54.5973,
            "longitude": -5.9301,
            "name": "Belfast",
        },
        {
            "latitude": 57.4778,
            "longitude": -4.2247,
            "name": "Inverness",
        },
    ],
    "inverness-applecross": [
        {
            "latitude": 57.4778,
            "longitude": -4.2247,
            "name": "Inverness",
        },
        {
            "latitude": 57.4329,
            "longitude": -5.8111,
            "name": "Applecross",
        },
    ],
    "inverness-ullapool": [
        {
            "latitude": 57.4778,
            "longitude": -4.2247,
            "name": "Inverness",
        },
        {
            "latitude": 57.8983,
            "longitude": -5.1600,
            "name": "Ullapool",
        },
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test Rallyify API route calculation against live API/Valhalla.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("RALLYIFY_API_BASE_URL", "http://127.0.0.1:8000"),
        help="Rallyify API base URL. Defaults to RALLYIFY_API_BASE_URL or localhost.",
    )
    parser.add_argument(
        "--route",
        choices=sorted(ROUTES),
        default="belfast-inverness",
        help="Sample route to calculate.",
    )
    parser.add_argument(
        "--road-priority",
        default="balanced",
        choices=[
            "fastest",
            "balanced",
            "scenic",
            "avoid_motorways",
            "prefer_b_roads",
        ],
        help="Rallyify roadPriority value.",
    )
    parser.add_argument(
        "--vehicle-profile",
        default="car",
        choices=["car", "motorbike", "caravan"],
        help="Rallyify vehicleProfile value.",
    )
    parser.add_argument(
        "--units",
        default="imperial",
        choices=["metric", "imperial"],
        help="Rallyify units value.",
    )
    parser.add_argument(
        "--avoid-motorways",
        action="store_true",
        help="Set avoidMotorways=true in the route request.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full raw JSON responses.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    print(f"Rallyify API: {base_url}")

    health_status, health_body = get_json(f"{base_url}/health")
    print_health_summary(health_status, health_body)
    if args.json:
        print("Health JSON:")
        print(json.dumps(health_body, indent=2))

    route_request = {
        "waypoints": ROUTES[args.route],
        "vehicleProfile": args.vehicle_profile,
        "roadPriority": args.road_priority,
        "units": args.units,
        "avoidMotorways": args.avoid_motorways,
    }

    route_status, route_body = post_json(
        f"{base_url}/routes/calculate",
        route_request,
    )
    print_route_header(args.route, route_status)

    if args.json:
        print("Route JSON:")
        print(json.dumps(route_body, indent=2))

    if route_status == 200:
        print_success_summary(route_body)
        return 0

    if (
        route_status == 502
        and isinstance(route_body, dict)
        and route_body.get("code") == "VALHALLA_UNAVAILABLE"
    ):
        print("Valhalla is unavailable. This is expected when it is not running.")
        return 0

    print("Unexpected smoke-test response.", file=sys.stderr)
    return 1


def get_json(url: str) -> tuple[int, object]:
    request = Request(url, method="GET")
    return request_json(request)


def post_json(url: str, payload: dict) -> tuple[int, object]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return request_json(request)


def request_json(request: Request) -> tuple[int, object]:
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return response.status, parse_json(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, parse_json(body)
    except URLError as exc:
        print(f"Could not reach Rallyify API: {exc}", file=sys.stderr)
        return 0, {"error": "Rallyify API is unavailable."}


def parse_json(body: str) -> object:
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}


def print_health_summary(status: int, health_body: object) -> None:
    print(f"GET /health -> {status}")

    if not isinstance(health_body, dict):
        return

    valhalla = health_body.get("valhalla")
    if not isinstance(valhalla, dict):
        return

    reachable = valhalla.get("reachable")
    version = valhalla.get("version")
    summary = f"Valhalla reachable: {reachable}"
    if version:
        summary = f"{summary} (version {version})"
    print(summary)


def print_route_header(route_key: str, status: int) -> None:
    print(f"Route: {format_route_name(route_key)}")
    print(f"POST /routes/calculate -> {status}")


def print_success_summary(route_body: object) -> None:
    if not isinstance(route_body, dict):
        return

    distance_metres = route_body.get("distanceMetres")
    duration_seconds = route_body.get("durationSeconds")
    polyline = route_body.get("polyline")
    legs = route_body.get("legs")
    print("Route calculated.")
    print(f"distance: {format_distance(distance_metres)}")
    print(f"duration: {format_duration(duration_seconds)}")
    print(f"polyline points: {len(polyline) if isinstance(polyline, list) else 0}")
    print(f"legs: {len(legs) if isinstance(legs, list) else 0}")
    print(f"first manoeuvre: {first_manoeuvre_instruction(legs)}")


def format_route_name(route_key: str) -> str:
    waypoints = ROUTES[route_key]
    return " -> ".join(waypoint["name"] for waypoint in waypoints)


def format_distance(distance_metres: object) -> str:
    if not isinstance(distance_metres, int | float):
        return "unknown"

    miles = distance_metres / 1609.344
    kilometres = distance_metres / 1000
    return f"{miles:.1f} mi / {kilometres:.1f} km"


def format_duration(duration_seconds: object) -> str:
    if not isinstance(duration_seconds, int | float):
        return "unknown"

    total_minutes = round(duration_seconds / 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def first_manoeuvre_instruction(legs: object) -> str:
    if not isinstance(legs, list):
        return "none"

    for leg in legs:
        if not isinstance(leg, dict):
            continue
        maneuvers = leg.get("maneuvers")
        if not isinstance(maneuvers, list):
            continue
        for maneuver in maneuvers:
            if not isinstance(maneuver, dict):
                continue
            instruction = maneuver.get("instruction")
            if instruction:
                return str(instruction)

    return "none"


if __name__ == "__main__":
    raise SystemExit(main())
