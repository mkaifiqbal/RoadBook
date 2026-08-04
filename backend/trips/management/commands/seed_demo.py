"""Seed the database with the demo accounts and trips.

Run on every Render deploy so a freshly provisioned Postgres instance is
immediately loginable. The command is idempotent: existing users keep their
password, and a trip is only inserted when the same driver does not already
have one departing at that time for the same route.

    python manage.py seed_demo
    python manage.py seed_demo --reset-passwords
"""

import gzip
import json
import os
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime

from trips.models import DriverProfile, Trip

FIXTURE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "demo_data.json.gz"

# Overridable so a real deployment can seed with non-public credentials.
DEFAULT_PASSWORDS = {
    DriverProfile.Role.ADMIN: "RoadbookAdmin!2026",
    DriverProfile.Role.DRIVER: "RoadbookDriver!2026",
}


class Command(BaseCommand):
    help = "Create the demo admin/driver accounts and their saved trips."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Also reset passwords on accounts that already exist.",
        )
        parser.add_argument(
            "--skip-trips",
            action="store_true",
            help="Seed accounts only, leaving trip history untouched.",
        )

    def handle(self, *args, **options):
        if not FIXTURE.exists():
            self.stderr.write(self.style.ERROR(f"Fixture missing: {FIXTURE}"))
            return

        with gzip.open(FIXTURE, "rt", encoding="utf-8") as fh:
            data = json.load(fh)

        passwords = {
            DriverProfile.Role.ADMIN: os.environ.get(
                "SEED_ADMIN_PASSWORD", DEFAULT_PASSWORDS[DriverProfile.Role.ADMIN]
            ),
            DriverProfile.Role.DRIVER: os.environ.get(
                "SEED_DRIVER_PASSWORD", DEFAULT_PASSWORDS[DriverProfile.Role.DRIVER]
            ),
        }

        with transaction.atomic():
            users = self._seed_accounts(data["accounts"], passwords, options["reset_passwords"])
            trips_added = 0 if options["skip_trips"] else self._seed_trips(data["trips"], users)

        self.stdout.write(
            self.style.SUCCESS(f"Seed complete: {len(users)} accounts, {trips_added} trips added.")
        )

    def _seed_accounts(self, accounts, passwords, reset_passwords):
        users = {}
        for entry in accounts:
            user, created = User.objects.get_or_create(
                username=entry["username"],
                defaults={
                    "email": entry["email"],
                    "first_name": entry["first_name"],
                    "last_name": entry["last_name"],
                },
            )
            user.email = entry["email"]
            user.first_name = entry["first_name"]
            user.last_name = entry["last_name"]
            user.is_staff = entry["is_staff"]
            user.is_superuser = entry["is_superuser"]
            user.is_active = True
            if created or reset_passwords:
                user.set_password(passwords[entry["role"]])
            user.save()

            DriverProfile.objects.update_or_create(
                user=user,
                defaults={
                    "role": entry["role"],
                    "status": entry["status"],
                    "truck_number": entry["truck_number"],
                    "carrier_name": entry["carrier_name"],
                },
            )
            users[entry["username"]] = user
            action = "created" if created else "updated"
            self.stdout.write(f"  {action}: {entry['username']} ({entry['role']}/{entry['status']})")
        return users

    def _seed_trips(self, trips, users):
        added = 0
        for entry in trips:
            driver = users.get(entry["driver"])
            if driver is None:
                continue
            start_time = parse_datetime(entry["start_time"])
            already_seeded = Trip.objects.filter(
                driver=driver,
                start_time=start_time,
                pickup_location=entry["pickup_location"],
                dropoff_location=entry["dropoff_location"],
            ).exists()
            if already_seeded:
                continue
            Trip.objects.create(
                driver=driver,
                current_location=entry["current_location"],
                pickup_location=entry["pickup_location"],
                dropoff_location=entry["dropoff_location"],
                current_cycle_used_hours=entry["current_cycle_used_hours"],
                start_time=start_time,
                driver_name=entry["driver_name"],
                carrier_name=entry["carrier_name"],
                truck_number=entry["truck_number"],
                total_miles=entry["total_miles"],
                total_days=entry["total_days"],
                driving_hours=entry["driving_hours"],
                on_duty_hours=entry["on_duty_hours"],
                plan=entry["plan"],
            )
            added += 1
        return added
