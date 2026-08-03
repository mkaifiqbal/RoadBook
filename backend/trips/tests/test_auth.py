"""Authentication, approval workflow, and trip-ownership API tests."""

from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from trips.models import DriverProfile, Trip


class AuthenticationWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_signup_creates_pending_driver_and_blocks_login(self):
        signup = self.client.post("/api/auth/signup/", {
            "name": "Pending Driver", "email": "pending@example.com", "password": "Roadbook!9362"
        }, content_type="application/json")
        self.assertEqual(signup.status_code, 201)
        profile = DriverProfile.objects.get(user__email="pending@example.com")
        self.assertEqual(profile.status, DriverProfile.Status.PENDING)

        login = self.client.post("/api/auth/login/", {
            "email": "pending@example.com", "password": "Roadbook!9362"
        }, content_type="application/json")
        self.assertEqual(login.status_code, 403)
        self.assertIn("approval", login.json()["detail"].lower())

    def test_admin_can_approve_then_driver_can_login(self):
        admin = User.objects.create_superuser("admin@example.com", "admin@example.com", "password123")
        driver = User.objects.create_user("driver@example.com", "driver@example.com", "password123")
        profile = DriverProfile.objects.create(user=driver, status=DriverProfile.Status.PENDING)
        self.client.force_authenticate(admin)

        response = self.client.patch(f"/api/admin/drivers/{driver.id}/status/", {"status": "active"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.client.logout()

        login = self.client.post("/api/auth/login/", {"email": driver.email, "password": "password123"}, content_type="application/json")
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["user"]["role"], "driver")

    def test_driver_cannot_access_admin_directory(self):
        driver = User.objects.create_user("driver@example.com", password="password123")
        DriverProfile.objects.create(user=driver, status=DriverProfile.Status.ACTIVE)
        self.client.force_authenticate(driver)
        self.assertEqual(self.client.get("/api/admin/drivers/").status_code, 403)


class DriverHourSummaryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.driver = User.objects.create_user(
            "hours@example.com", email="hours@example.com", password="password123"
        )
        DriverProfile.objects.create(user=self.driver, status=DriverProfile.Status.ACTIVE)
        self.client.force_authenticate(self.driver)

    def make_trip(self, start_time, end_time, driving, on_duty):
        return Trip.objects.create(
            driver=self.driver,
            current_location="A",
            pickup_location="B",
            dropoff_location="C",
            current_cycle_used_hours=0,
            total_miles=100,
            driving_hours=driving,
            on_duty_hours=on_duty,
            total_days=1,
            start_time=start_time,
            plan={"summary": {"end_time": end_time.isoformat()}},
        )

    def test_profile_splits_completed_and_scheduled_driving(self):
        now = timezone.now()
        self.make_trip(now - timedelta(days=2), now - timedelta(days=1), 5, 6)
        self.make_trip(now + timedelta(days=1), now + timedelta(days=2), 7, 8)

        body = self.client.get("/api/auth/profile/").json()

        self.assertEqual(body["completed_driving_hours"], 5.0)
        self.assertEqual(body["scheduled_driving_hours"], 7.0)
        self.assertEqual(body["total_driving_hours"], 12.0)
        self.assertEqual(body["total_on_duty_hours"], 14.0)

    def test_profile_never_reports_duty_below_driving(self):
        now = timezone.now()
        self.make_trip(now - timedelta(days=1), now - timedelta(hours=1), 4.5, 0)

        body = self.client.get("/api/auth/profile/").json()

        self.assertEqual(body["total_driving_hours"], 4.5)
        self.assertEqual(body["total_on_duty_hours"], 4.5)
        self.assertGreaterEqual(body["total_on_duty_hours"], body["total_driving_hours"])


class TripOwnershipTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.first = User.objects.create_user("first@example.com", password="password123")
        self.second = User.objects.create_user("second@example.com", password="password123")
        DriverProfile.objects.create(user=self.first, status=DriverProfile.Status.ACTIVE)
        DriverProfile.objects.create(user=self.second, status=DriverProfile.Status.ACTIVE)
        self.trip = Trip.objects.create(
            driver=self.first, current_location="A", pickup_location="B", dropoff_location="C",
            current_cycle_used_hours=0, total_miles=10, driving_hours=1, total_days=1,
            start_time=datetime(2026, 1, 1, 8), plan={"summary": {}}
        )

    def test_driver_only_sees_own_trips(self):
        self.client.force_authenticate(self.second)
        self.assertEqual(self.client.get("/api/trips/").json(), [])
        self.assertEqual(self.client.get(f"/api/trips/{self.trip.id}/").status_code, 404)

    def test_admin_can_filter_and_open_driver_trips(self):
        admin = User.objects.create_superuser("admin@example.com", password="password123")
        self.client.force_authenticate(admin)
        listing = self.client.get(f"/api/trips/?driver={self.first.id}")
        self.assertEqual(len(listing.json()), 1)
        self.assertEqual(self.client.get(f"/api/trips/{self.trip.id}/").status_code, 200)