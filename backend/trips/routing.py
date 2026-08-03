"""
Geocoding + truck routing.

Default provider stack is key-free so the project runs with zero setup:

    geocoding  -> Nominatim (OpenStreetMap)
    routing    -> OSRM public demo server
    tiles      -> OpenStreetMap raster (frontend)

If ``ORS_API_KEY`` is set the OpenRouteService provider is used instead --
it has an HGV (heavy goods vehicle) profile, which is the more correct
routing profile for a Class 8 truck, and a far better rate limit than the
OSRM demo box.

If the network is unavailable the module degrades to a great-circle estimate
so the HOS engine and log sheets can still be demonstrated.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_URL = "https://photon.komoot.io/api/"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
ORS_GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"

USER_AGENT = os.environ.get("GEOCODER_USER_AGENT", "eld-trip-planner/1.0 (assessment project)")
TIMEOUT = float(os.environ.get("ROUTING_TIMEOUT", "20"))

METERS_PER_MILE = 1609.344
# Straight-line distance under-reports road distance; this is the usual
# rule-of-thumb correction for the US interstate network.
CROW_FLIES_FACTOR = 1.21
FALLBACK_SPEED_MPH = 55.0

_geocode_cache: dict[str, "Place"] = {}
_search_cache: dict[str, list["Place"]] = {}


class RoutingError(Exception):
    pass


@dataclass
class Place:
    query: str
    name: str
    lat: float
    lon: float

    def to_dict(self) -> dict:
        return {"query": self.query, "name": self.name, "lat": self.lat, "lon": self.lon}


def _ors_key() -> str | None:
    key = os.environ.get("ORS_API_KEY", "").strip()
    return key or None


# --------------------------------------------------------------------------
# Geocoding
# --------------------------------------------------------------------------
def geocode(query: str) -> Place:
    query = (query or "").strip()
    if not query:
        raise RoutingError("Empty location")
    if query.lower() in _geocode_cache:
        return _geocode_cache[query.lower()]

    place = _geocode_ors(query) if _ors_key() else _geocode_nominatim(query)
    _geocode_cache[query.lower()] = place
    return place


def search_places(query: str, limit: int = 5) -> list[Place]:
    """Return real place suggestions for the dispatch form.

    Requests are proxied through Django so provider credentials stay private and
    browsers do not need cross-origin access to Nominatim/OpenRouteService.
    """
    query = (query or "").strip()
    if len(query) < 3:
        return []
    cache_key = f"{query.lower()}:{limit}"
    if cache_key in _search_cache:
        return _search_cache[cache_key]

    places = _search_ors(query, limit) if _ors_key() else _search_nominatim(query, limit)
    _search_cache[cache_key] = places
    return places


def _search_nominatim(query: str, limit: int) -> list[Place]:
    try:
        response = requests.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "jsonv2",
                "limit": max(1, min(limit, 6)),
                "addressdetails": 1,
                "dedupe": 1,
            },
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        results = response.json()
    except requests.RequestException as exc:
        raise RoutingError(f"Location search is unavailable ({exc.__class__.__name__})") from exc
    except ValueError as exc:
        raise RoutingError("Location search returned an invalid response") from exc

    places = [
        Place(query=query, name=item.get("display_name", query), lat=float(item["lat"]), lon=float(item["lon"]))
        for item in results
        if item.get("lat") and item.get("lon")
    ]
    # Photon often recovers misspellings that Nominatim cannot, while still
    # returning OpenStreetMap-backed place names and coordinates.
    return places or _search_photon(query, limit)


def _search_photon(query: str, limit: int) -> list[Place]:
    try:
        response = requests.get(
            PHOTON_URL,
            params={"q": query, "limit": max(1, min(limit, 6))},
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        features = response.json().get("features", [])
    except (requests.RequestException, ValueError):
        return []

    places = []
    for feature in features:
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if len(coordinates) < 2:
            continue
        props = feature.get("properties", {})
        label = ", ".join(str(props[key]) for key in ("name", "city", "state", "country") if props.get(key))
        places.append(Place(query=query, name=label or query, lat=float(coordinates[1]), lon=float(coordinates[0])))
    return places


def _search_ors(query: str, limit: int) -> list[Place]:
    try:
        response = requests.get(
            ORS_GEOCODE_URL,
            params={"api_key": _ors_key(), "text": query, "size": max(1, min(limit, 6))},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        features = response.json().get("features", [])
    except (requests.RequestException, ValueError) as exc:
        raise RoutingError(f"Location search is unavailable ({exc.__class__.__name__})") from exc

    places = []
    for feature in features:
        lon, lat = feature["geometry"]["coordinates"][:2]
        places.append(Place(query=query, name=feature["properties"].get("label", query), lat=lat, lon=lon))
    return places


def _geocode_nominatim(query: str) -> Place:
    try:
        response = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "addressdetails": 0},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        results = response.json()
    except requests.RequestException as exc:
        raise RoutingError(f"Geocoding service unavailable ({exc.__class__.__name__})") from exc
    except ValueError as exc:
        raise RoutingError("Geocoding service returned an invalid response") from exc

    if not results:
        raise RoutingError(f"Could not find a location matching '{query}'")

    top = results[0]
    return Place(
        query=query,
        name=top.get("display_name", query),
        lat=float(top["lat"]),
        lon=float(top["lon"]),
    )


def _geocode_ors(query: str) -> Place:
    try:
        response = requests.get(
            ORS_GEOCODE_URL,
            params={"api_key": _ors_key(), "text": query, "size": 1},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        features = response.json().get("features", [])
    except (requests.RequestException, ValueError) as exc:
        raise RoutingError(f"Geocoding service unavailable ({exc.__class__.__name__})") from exc

    if not features:
        raise RoutingError(f"Could not find a location matching '{query}'")

    top = features[0]
    lon, lat = top["geometry"]["coordinates"][:2]
    return Place(query=query, name=top["properties"].get("label", query), lat=lat, lon=lon)


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------
def route(places: list[Place]) -> dict:
    """Route through the given waypoints in order.

    Returns geometry as [[lat, lon], ...] plus a cumulative-mileage array
    parallel to it, so any point on the trip can be located by mileage.
    """
    if len(places) < 2:
        raise RoutingError("At least two waypoints are required")

    provider = "openrouteservice-hgv" if _ors_key() else "osrm"
    router = _route_ors if _ors_key() else _route_osrm
    try:
        result = router(places)
    except RoutingError as combined_error:
        # A provider can occasionally reject a multi-waypoint request even
        # though both individual road legs are routable. Recover each leg
        # separately and stitch their real road polylines together.
        try:
            result = _route_by_legs(places, router)
        except RoutingError as leg_error:
            raise RoutingError(
                "No drivable road route was found for this trip. Check each "
                "selected location and make sure the truck can reach them by road."
            ) from leg_error

    result["provider"] = provider
    result["estimated"] = False
    result["road_route_available"] = True
    result["cumulative_miles"] = _cumulative_miles(result["geometry"])
    return result


def _route_by_legs(places: list[Place], router) -> dict:
    geometry = []
    legs = []
    total_miles = 0.0
    total_minutes = 0.0

    for origin, destination in zip(places, places[1:]):
        routed = router([origin, destination])
        leg_geometry = routed["geometry"]
        if len(leg_geometry) < 2 or not routed.get("legs"):
            raise RoutingError("Routing service returned an incomplete road leg")
        geometry.extend(leg_geometry if not geometry else leg_geometry[1:])
        leg = routed["legs"][0]
        legs.append(leg)
        total_miles += leg["miles"]
        total_minutes += leg["minutes"]

    return {
        "geometry": geometry,
        "total_miles": total_miles,
        "total_minutes": total_minutes,
        "legs": legs,
    }


def _route_osrm(places: list[Place]) -> dict:
    coords = ";".join(f"{p.lon},{p.lat}" for p in places)
    try:
        response = requests.get(
            f"{OSRM_URL}/{coords}",
            params={"overview": "full", "geometries": "geojson", "steps": "false"},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RoutingError(f"Routing service unavailable ({exc.__class__.__name__})") from exc

    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise RoutingError(payload.get("message", "No route found between those locations"))

    best = payload["routes"][0]
    return {
        "geometry": [[lat, lon] for lon, lat in best["geometry"]["coordinates"]],
        "total_miles": best["distance"] / METERS_PER_MILE,
        "total_minutes": best["duration"] / 60.0,
        "legs": [
            {"miles": leg["distance"] / METERS_PER_MILE, "minutes": leg["duration"] / 60.0}
            for leg in best["legs"]
        ],
    }


def _route_ors(places: list[Place]) -> dict:
    body = {"coordinates": [[p.lon, p.lat] for p in places], "units": "mi"}
    try:
        response = requests.post(
            ORS_DIRECTIONS_URL,
            json=body,
            headers={"Authorization": _ors_key(), "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RoutingError(f"Routing service unavailable ({exc.__class__.__name__})") from exc

    features = payload.get("features") or []
    if not features:
        raise RoutingError("No route found between those locations")

    feature = features[0]
    summary = feature["properties"]["summary"]
    return {
        "geometry": [[lat, lon] for lon, lat in feature["geometry"]["coordinates"]],
        "total_miles": summary["distance"],
        "total_minutes": summary["duration"] / 60.0,
        "legs": [
            {"miles": seg["distance"], "minutes": seg["duration"] / 60.0}
            for seg in feature["properties"]["segments"]
        ],
    }


def _route_fallback(places: list[Place]) -> dict:
    """Great-circle estimate, used only when the routing API is unreachable."""
    legs = []
    geometry = [[places[0].lat, places[0].lon]]
    total_miles = 0.0
    for a, b in zip(places, places[1:]):
        miles = haversine_miles(a.lat, a.lon, b.lat, b.lon) * CROW_FLIES_FACTOR
        legs.append({"miles": miles, "minutes": miles / FALLBACK_SPEED_MPH * 60.0})
        geometry.append([b.lat, b.lon])
        total_miles += miles
    return {
        "geometry": geometry,
        "total_miles": total_miles,
        "total_minutes": total_miles / FALLBACK_SPEED_MPH * 60.0,
        "legs": legs,
        "estimated": True,
        "road_route_available": False,
        "notices": [
            "No road route was available from the routing provider, so this is a straight-line estimate only.",
            "Do not dispatch this plan as a truck navigation route until a drivable road route is available.",
        ],
    }


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------
def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def _cumulative_miles(geometry: list[list[float]]) -> list[float]:
    cumulative = [0.0]
    for (lat1, lon1), (lat2, lon2) in zip(geometry, geometry[1:]):
        cumulative.append(cumulative[-1] + haversine_miles(lat1, lon1, lat2, lon2))
    return cumulative


def point_at_miles(
    geometry: list[list[float]],
    cumulative: list[float],
    miles: float,
    road_total_miles: float | None = None,
) -> list[float]:
    """Interpolate a lat/lon along the polyline at the given trip mileage.

    ``cumulative`` is measured great-circle along the polyline, which differs
    slightly from the provider's reported road distance. Pass
    ``road_total_miles`` to rescale so the two agree end to end.
    """
    if not geometry:
        return [0.0, 0.0]
    total = cumulative[-1] or 1.0
    if road_total_miles:
        miles = miles * (total / road_total_miles)
    target = max(0.0, min(miles, total))

    lo, hi = 0, len(cumulative) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cumulative[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    if lo == 0:
        return list(geometry[0])

    before, after = cumulative[lo - 1], cumulative[lo]
    span = after - before
    ratio = 0.0 if span <= 0 else (target - before) / span
    lat1, lon1 = geometry[lo - 1]
    lat2, lon2 = geometry[lo]
    return [lat1 + (lat2 - lat1) * ratio, lon1 + (lon2 - lon1) * ratio]
