"""API tests. Routing is stubbed so the suite never touches the network."""

from __future__ import annotations

from unittest import mock

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from trips.models import DriverProfile, Trip
from trips.routing import Place, RoutingError

CHICAGO = Place("Chicago, IL", "Chicago, Cook County, Illinois, USA", 41.8781, -87.6298)
STLOUIS = Place("St. Louis, MO", "St. Louis, Missouri, USA", 38.6270, -90.1994)
DALLAS = Place("Dallas, TX", "Dallas, Dallas County, Texas, USA", 32.7767, -96.7970)

FAKE_ROUTE = {
    "geometry": [[41.8781, -87.6298], [38.6270, -90.1994], [32.7767, -96.7970]],
    "total_miles": 1100.0,
    "total_minutes": 1100.0 / 55 * 60,
    "legs": [
        {"miles": 300.0, "minutes": 300.0 / 55 * 60},
        {"miles": 800.0, "minutes": 800.0 / 55 * 60},
    ],
}

PAYLOAD = {
    "current_location": "Chicago, IL",
    "pickup_location": "St. Louis, MO",
    "dropoff_location": "Dallas, TX",
    "current_cycle_used": 20,
    "start_time": "2026-03-02T06:00:00",
    "driver_name": "A. Driver",
    "carrier_name": "Blue Line Freight",
    "truck_number": "TRK-114",
}


def fake_geocode(query: str) -> Place:
    return {"Chicago, IL": CHICAGO, "St. Louis, MO": STLOUIS, "Dallas, TX": DALLAS}[query]


def fake_route(places):
    result = dict(FAKE_ROUTE)
    result["provider"] = "test"
    result["cumulative_miles"] = [0.0, 300.0, 1100.0]
    return result


@mock.patch("trips.services.routing.route", side_effect=fake_route)
@mock.patch("trips.services.routing.geocode", side_effect=fake_geocode)
class PlanTripEndpointTests(TestCase):
    url = "/api/plan-trip/"

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="driver@example.com", email="driver@example.com", password="password123")
        DriverProfile.objects.create(user=self.user, status=DriverProfile.Status.ACTIVE)
        self.client.force_authenticate(self.user)

    def test_returns_route_stops_and_logs(self, _geo, _route):
        response = self.client.post(self.url, PAYLOAD, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        body = response.json()

        for key in ("route", "stops", "logs", "summary", "events", "waypoints", "assumptions"):
            self.assertIn(key, body)

        self.assertEqual(body["route"]["total_miles"], 1100.0)
        self.assertEqual(len(body["route"]["legs"]), 2)
        self.assertEqual(len(body["waypoints"]), 3)
        self.assertGreater(len(body["logs"]), 1)

    def test_every_stop_has_map_coordinates(self, _geo, _route):
        body = self.client.post(self.url, PAYLOAD, content_type="application/json").json()
        self.assertTrue(body["stops"])
        for stop in body["stops"]:
            self.assertIn("lat", stop)
            self.assertIn("lon", stop)
            self.assertTrue(-90 <= stop["lat"] <= 90)
            self.assertTrue(-180 <= stop["lon"] <= 180)

    def test_pickup_and_dropoff_stops_are_present(self, _geo, _route):
        body = self.client.post(self.url, PAYLOAD, content_type="application/json").json()
        kinds = {stop["type"] for stop in body["stops"]}
        self.assertIn("pickup", kinds)
        self.assertIn("dropoff", kinds)

    def test_log_headers_carry_driver_metadata(self, _geo, _route):
        body = self.client.post(self.url, PAYLOAD, content_type="application/json").json()
        self.assertEqual(body["logs"][0]["carrier_name"], "Blue Line Freight")
        self.assertEqual(body["logs"][0]["truck_number"], "TRK-114")

    def test_trip_is_persisted_and_listable(self, _geo, _route):
        body = self.client.post(self.url, PAYLOAD, content_type="application/json").json()
        self.assertEqual(Trip.objects.count(), 1)
        self.assertIn("trip_id", body)

        listing = self.client.get("/api/trips/").json()
        self.assertEqual(len(listing), 1)

        detail = self.client.get(f"/api/trips/{body['trip_id']}/").json()
        self.assertEqual(detail["pickup_location"], "St. Louis, MO")
        self.assertEqual(detail["plan"]["summary"]["total_miles"], body["summary"]["total_miles"])
        self.assertAlmostEqual(
            detail["on_duty_hours"],
            body["summary"]["driving_hours"] + body["summary"]["on_duty_not_driving_hours"],
            delta=0.02,
        )

    def test_second_trip_uses_saved_driver_cycle_history(self, _geo, _route):
        first = self.client.post(self.url, PAYLOAD, content_type="application/json").json()
        payload = dict(PAYLOAD, start_time="2026-03-04T12:00:00", current_cycle_used=0)
        second = self.client.post(self.url, payload, content_type="application/json")

        self.assertEqual(second.status_code, 200)
        body = second.json()
        self.assertEqual(body["summary"]["cycle_source"], "driver_history")
        self.assertAlmostEqual(
            body["summary"]["cycle_used_at_start"],
            first["summary"]["cycle_used_at_end"],
            delta=0.02,
        )

    def test_trip_can_be_scheduled_in_free_gap_before_upcoming_trip(self, _geo, _route):
        future_start = timezone.datetime(2026, 8, 21, 8, 0)
        future_end = timezone.datetime(2026, 8, 23, 8, 0)
        Trip.objects.create(
            driver=self.user,
            current_location="Chicago, IL",
            pickup_location="St. Louis, MO",
            dropoff_location="Dallas, TX",
            current_cycle_used_hours=0,
            start_time=future_start,
            total_miles=1100,
            total_days=2,
            driving_hours=20,
            on_duty_hours=22,
            plan={
                "summary": {
                    "end_time": future_end.isoformat(),
                    "cycle_state": {"end_time": future_end.isoformat()},
                }
            },
        )

        response = self.client.post(
            self.url,
            dict(PAYLOAD, start_time="2026-08-10T06:00:00"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Trip.objects.count(), 2)

    def test_trip_is_rejected_when_generated_interval_overlaps_existing_trip(self, _geo, _route):
        existing_start = timezone.datetime(2026, 8, 11, 8, 0)
        existing_end = timezone.datetime(2026, 8, 13, 8, 0)
        Trip.objects.create(
            driver=self.user,
            current_location="Chicago, IL",
            pickup_location="St. Louis, MO",
            dropoff_location="Dallas, TX",
            current_cycle_used_hours=0,
            start_time=existing_start,
            total_miles=1100,
            total_days=2,
            driving_hours=20,
            on_duty_hours=22,
            plan={"summary": {"end_time": existing_end.isoformat()}},
        )

        response = self.client.post(
            self.url,
            dict(PAYLOAD, start_time="2026-08-10T06:00:00"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("overlaps an existing trip", response.json()["detail"])
        self.assertEqual(Trip.objects.count(), 1)

    def test_save_false_skips_persistence(self, _geo, _route):
        payload = dict(PAYLOAD, save=False)
        self.client.post(self.url, payload, content_type="application/json")
        self.assertEqual(Trip.objects.count(), 0)

    def test_rejects_out_of_range_cycle_hours(self, _geo, _route):
        payload = dict(PAYLOAD, current_cycle_used=80)
        response = self.client.post(self.url, payload, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("current_cycle_used", response.json())

    def test_rejects_identical_pickup_and_dropoff(self, _geo, _route):
        payload = dict(PAYLOAD, dropoff_location="St. Louis, MO")
        response = self.client.post(self.url, payload, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_missing_fields_are_reported(self, _geo, _route):
        response = self.client.post(self.url, {}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("current_location", response.json())


class TripLifecycleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="lifecycle@example.com", password="password123")
        DriverProfile.objects.create(user=self.user, status=DriverProfile.Status.ACTIVE)
        self.client.force_authenticate(self.user)

    def create_trip(self, *, start_time, end_time):
        return Trip.objects.create(
            driver=self.user,
            current_location="Chicago, IL",
            pickup_location="St. Louis, MO",
            dropoff_location="Dallas, TX",
            current_cycle_used_hours=0,
            start_time=start_time,
            total_miles=640,
            total_days=1,
            driving_hours=10,
            on_duty_hours=12,
            plan={"summary": {"end_time": end_time.isoformat()}},
        )

    def test_list_exposes_completed_and_upcoming_status(self):
        now = timezone.now()
        self.create_trip(start_time=now - timezone.timedelta(days=2), end_time=now - timezone.timedelta(days=1))
        self.create_trip(start_time=now + timezone.timedelta(hours=25), end_time=now + timezone.timedelta(days=2))

        response = self.client.get("/api/trips/")

        self.assertEqual(response.status_code, 200)
        by_status = {trip["status"]: trip for trip in response.json()}
        self.assertFalse(by_status["completed"]["can_delete"])
        self.assertTrue(by_status["upcoming"]["can_delete"])
        self.assertIn("end_time", by_status["upcoming"])

    def test_driver_can_delete_an_upcoming_trip(self):
        now = timezone.now()
        trip = self.create_trip(start_time=now + timezone.timedelta(hours=25), end_time=now + timezone.timedelta(days=2))

        response = self.client.delete(f"/api/trips/{trip.id}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Trip.objects.filter(id=trip.id).exists())

    def test_driver_cannot_delete_within_24_hours_of_departure(self):
        now = timezone.now()
        trip = self.create_trip(
            start_time=now + timezone.timedelta(hours=23, minutes=59),
            end_time=now + timezone.timedelta(days=2),
        )

        listing = self.client.get("/api/trips/").json()[0]
        response = self.client.delete(f"/api/trips/{trip.id}/")

        self.assertFalse(listing["can_delete"])
        self.assertIn("24 hours", listing["delete_restriction"])
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Trip.objects.filter(id=trip.id).exists())

    def test_driver_cannot_delete_completed_or_started_trip(self):
        now = timezone.now()
        completed = self.create_trip(start_time=now - timezone.timedelta(days=2), end_time=now - timezone.timedelta(days=1))
        active = self.create_trip(start_time=now - timezone.timedelta(hours=1), end_time=now + timezone.timedelta(hours=5))

        completed_response = self.client.delete(f"/api/trips/{completed.id}/")
        active_response = self.client.delete(f"/api/trips/{active.id}/")

        self.assertEqual(completed_response.status_code, 400)
        self.assertEqual(active_response.status_code, 400)
        self.assertEqual(Trip.objects.filter(id__in=[completed.id, active.id]).count(), 2)


class RoutingFailureTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user = User.objects.create_user(username="routing@example.com", password="password123")
        DriverProfile.objects.create(user=user, status=DriverProfile.Status.ACTIVE)
        self.client.force_authenticate(user)

    @mock.patch("trips.services.routing.geocode", side_effect=RoutingError("Could not find 'Narnia'"))
    def test_unresolvable_location_returns_400_with_a_readable_message(self, _geo):
        payload = dict(PAYLOAD, pickup_location="Narnia")
        response = self.client.post("/api/plan-trip/", payload, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Narnia", response.json()["detail"])


class HealthTests(TestCase):
    def test_health(self):
        self.assertEqual(self.client.get("/api/health/").json(), {"status": "ok"})


class LocationSearchTests(TestCase):
    @mock.patch("trips.views.search_places", return_value=[CHICAGO, STLOUIS])
    def test_returns_real_place_suggestions(self, search):
        response = self.client.get("/api/locations/?q=Chi")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 2)
        self.assertEqual(response.json()["results"][0]["name"], CHICAGO.name)
        search.assert_called_once_with("Chi")

    @mock.patch("trips.views.search_places")
    def test_short_query_does_not_call_provider(self, search):
        response = self.client.get("/api/locations/?q=Ch")
        self.assertEqual(response.json(), {"results": []})
        search.assert_not_called()

    @mock.patch("trips.views.search_places", side_effect=RoutingError("provider busy"))
    def test_provider_failure_is_readable(self, _search):
        response = self.client.get("/api/locations/?q=Chicago")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "provider busy")
