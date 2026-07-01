#!/usr/bin/env python3
import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROUTES = {
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

ROAD_PRIORITIES = [
    "fastest",
    "balanced",
    "scenic",
    "avoid_motorways",
    "prefer_b_roads",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare Rallyify route outputs across roadPriority values.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("RALLYIFY_API_BASE_URL", "http://127.0.0.1:8000"),
        help="Rallyify API base URL. Defaults to RALLYIFY_API_BASE_URL or localhost.",
    )
    parser.add_argument(
        "--route",
        choices=sorted(ROUTES),
        default="inverness-ullapool",
        help="Preset route to compare.",
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
        help="Set avoidMotorways=true for every comparison request.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    route_name = format_route_name(args.route)

    print(f"Rallyify API: {base_url}")
    print(f"Route: {route_name}")
    print()

    results = [
        calculate_priority(
            base_url=base_url,
            route_key=args.route,
            road_priority=road_priority,
            vehicle_profile=args.vehicle_profile,
            units=args.units,
            avoid_motorways=args.avoid_motorways,
        )
        for road_priority in ROAD_PRIORITIES
    ]

    balanced = next(
        (
            result
            for result in results
            if result["roadPriority"] == "balanced" and result["status"] == 200
        ),
        None,
    )

    for result in results:
        print_result(result, balanced)
        print()

    unexpected_failures = [
        result
        for result in results
        if result["status"] not in {200, 502}
        or (
            result["status"] == 502
            and result.get("code") != "VALHALLA_UNAVAILABLE"
        )
    ]

    if unexpected_failures:
        print("One or more priority checks returned unexpected responses.", file=sys.stderr)
        return 1

    return 0


def calculate_priority(
    base_url: str,
    route_key: str,
    road_priority: str,
    vehicle_profile: str,
    units: str,
    avoid_motorways: bool,
) -> dict:
    route_request = {
        "waypoints": ROUTES[route_key],
        "vehicleProfile": vehicle_profile,
        "roadPriority": road_priority,
        "units": units,
        "avoidMotorways": avoid_motorways,
    }
    status, body = post_json(f"{base_url}/routes/calculate", route_request)

    result = {
        "roadPriority": road_priority,
        "status": status,
        "body": body,
    }

    if isinstance(body, dict):
        result["code"] = body.get("code")

    return result


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
        with urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
            return response.status, parse_json(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, parse_json(body)
    except URLError as exc:
        return 0, {"error": f"Rallyify API is unavailable: {exc}"}


def parse_json(body: str) -> object:
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}


def print_result(result: dict, balanced: dict | None) -> None:
    body = result["body"]
    print(f"roadPriority: {result['roadPriority']}")
    print(f"HTTP status: {result['status']}")

    if result["status"] != 200 or not isinstance(body, dict):
        print(f"code: {result.get('code', 'n/a')}")
        print("distance: n/a")
        print("duration: n/a")
        print("polyline points: 0")
        print("first manoeuvre: none")
        print("diff vs balanced: n/a")
        return

    print(f"distance: {format_distance(body.get('distanceMetres'))}")
    print(f"duration: {format_duration(body.get('durationSeconds'))}")
    print(f"polyline points: {polyline_count(body)}")
    print(f"legs: {leg_count(body)}")
    print(f"first manoeuvre: {first_manoeuvre_instruction(body.get('legs'))}")
    print(f"diff vs balanced: {format_balanced_diff(body, balanced)}")


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


def polyline_count(body: dict) -> int:
    polyline = body.get("polyline")
    return len(polyline) if isinstance(polyline, list) else 0


def leg_count(body: dict) -> int:
    legs = body.get("legs")
    return len(legs) if isinstance(legs, list) else 0


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


def format_balanced_diff(body: dict, balanced: dict | None) -> str:
    if balanced is None or not isinstance(balanced.get("body"), dict):
        return "n/a"

    balanced_body = balanced["body"]
    distance_delta = numeric_delta(
        body.get("distanceMetres"),
        balanced_body.get("distanceMetres"),
    )
    duration_delta = numeric_delta(
        body.get("durationSeconds"),
        balanced_body.get("durationSeconds"),
    )

    if distance_delta is None or duration_delta is None:
        return "n/a"

    distance_label = format_signed_distance(distance_delta)
    duration_label = format_signed_duration(duration_delta)
    differs = abs(distance_delta) >= 1 or abs(duration_delta) >= 1
    return f"{'differs' if differs else 'same'} ({distance_label}, {duration_label})"


def numeric_delta(value: object, baseline: object) -> float | None:
    if not isinstance(value, int | float):
        return None
    if not isinstance(baseline, int | float):
        return None
    return value - baseline


def format_signed_distance(distance_delta_metres: float) -> str:
    sign = "+" if distance_delta_metres > 0 else ""
    miles = distance_delta_metres / 1609.344
    kilometres = distance_delta_metres / 1000
    return f"{sign}{miles:.1f} mi / {sign}{kilometres:.1f} km"


def format_signed_duration(duration_delta_seconds: float) -> str:
    sign = "+" if duration_delta_seconds > 0 else ""
    minutes = duration_delta_seconds / 60
    return f"{sign}{minutes:.1f} min"


if __name__ == "__main__":
    raise SystemExit(main())
