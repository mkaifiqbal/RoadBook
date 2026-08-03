"""Glue layer: addresses -> route -> HOS simulation -> API payload."""

from __future__ import annotations

from datetime import datetime, timedelta

from . import routing
from .hos_engine import Leg, plan_trip

STOP_STYLES = {
    "pickup": {"icon": "pickup", "title": "Pickup"},
    "dropoff": {"icon": "dropoff", "title": "Drop-off"},
    "fuel": {"icon": "fuel", "title": "Fuel stop"},
    "break": {"icon": "break", "title": "30-min break"},
    "rest": {"icon": "rest", "title": "10-hour reset"},
    "restart": {"icon": "restart", "title": "34-hour restart"},
    "cycle_wait": {"icon": "restart", "title": "Cycle hours roll-off"},
}


def default_start_time() -> datetime:
    """Now, rounded up to the next quarter hour (log sheets use 15-min ticks)."""
    now = datetime.now().replace(second=0, microsecond=0)
    return now + timedelta(minutes=(-now.minute) % 15)


def build_plan(
    current_location: str,
    pickup_location: str,
    dropoff_location: str,
    current_cycle_used: float,
    start_time: datetime | None = None,
    driver_name: str = "",
    carrier_name: str = "",
    truck_number: str = "",
    cycle_state: dict | None = None,
) -> dict:
    start_time = start_time or default_start_time()
    if start_time.tzinfo is not None:
        start_time = start_time.replace(tzinfo=None)

    origin = routing.geocode(current_location)
    pickup = routing.geocode(pickup_location)
    dropoff = routing.geocode(dropoff_location)

    routed = routing.route([origin, pickup, dropoff])
    raw_legs = routed["legs"]
    if len(raw_legs) < 2:
        raise routing.RoutingError("Routing service did not return both trip legs")

    legs = [
        Leg(
            origin=_short(origin.name),
            destination=_short(pickup.name),
            miles=raw_legs[0]["miles"],
            drive_minutes=raw_legs[0]["minutes"],
        ),
        Leg(
            origin=_short(pickup.name),
            destination=_short(dropoff.name),
            miles=raw_legs[1]["miles"],
            drive_minutes=raw_legs[1]["minutes"],
        ),
    ]

    plan = plan_trip(legs, start_time, current_cycle_used, cycle_state=cycle_state)

    # Place every inserted stop on the map by interpolating along the route.
    geometry = routed["geometry"]
    cumulative = routed["cumulative_miles"]
    road_total = routed["total_miles"]
    for stop in plan["stops"]:
        lat, lon = routing.point_at_miles(
            geometry, cumulative, stop["miles_from_origin"], road_total
        )
        style = STOP_STYLES.get(stop["type"], {"icon": "stop", "title": stop["type"].title()})
        stop["lat"] = round(lat, 6)
        stop["lon"] = round(lon, 6)
        stop["icon"] = style["icon"]
        stop["title"] = style["title"]

    plan["route"] = {
        "geometry": geometry,
        "total_miles": round(road_total, 1),
        "total_drive_hours": round(routed["total_minutes"] / 60.0, 2),
        "provider": routed.get("provider", "osrm"),
        "estimated": routed.get("estimated", False),
        "road_route_available": routed.get("road_route_available", True),
        "notices": routed.get("notices", []),
        "legs": [
            {
                "from": legs[0].origin,
                "to": legs[0].destination,
                "miles": round(legs[0].miles, 1),
                "drive_hours": round(legs[0].drive_minutes / 60.0, 2),
            },
            {
                "from": legs[1].origin,
                "to": legs[1].destination,
                "miles": round(legs[1].miles, 1),
                "drive_hours": round(legs[1].drive_minutes / 60.0, 2),
            },
        ],
    }
    plan["waypoints"] = [
        {"role": "current", "label": _short(origin.name), **origin.to_dict()},
        {"role": "pickup", "label": _short(pickup.name), **pickup.to_dict()},
        {"role": "dropoff", "label": _short(dropoff.name), **dropoff.to_dict()},
    ]
    plan["header"] = {
        "driver_name": driver_name,
        "carrier_name": carrier_name,
        "truck_number": truck_number,
        "from_label": _short(origin.name),
        "to_label": _short(dropoff.name),
    }

    # Per-sheet header data the log grid needs but the engine doesn't know.
    for log in plan["logs"]:
        log["driver_name"] = driver_name
        log["carrier_name"] = carrier_name
        log["truck_number"] = truck_number
        log["from_label"] = _short(origin.name)
        log["to_label"] = _short(dropoff.name)

    return plan


def _short(display_name: str, parts: int = 3) -> str:
    """Nominatim returns very long display names; keep the useful head."""
    bits = [b.strip() for b in display_name.split(",")]
    if len(bits) <= parts:
        return display_name
    return ", ".join(bits[:2] + [bits[-2]] if len(bits) > 3 else bits[:parts])
