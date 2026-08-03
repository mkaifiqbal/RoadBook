from django.conf import settings
from django.contrib.auth.models import User
from django.db import models


class DriverProfile(models.Model):
    class Role(models.TextChoices):
        DRIVER = "driver", "Driver"
        ADMIN = "admin", "Admin"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="driver_profile")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.DRIVER)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    truck_number = models.CharField(max_length=60, blank=True)
    carrier_name = models.CharField(max_length=120, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_driver_profiles"
    )

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self) -> str:
        return f"{self.user.get_full_name() or self.user.username} ({self.status})"


class Trip(models.Model):
    """A planned trip, persisted so it can be re-opened without re-routing."""

    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="trips"
    )

    current_location = models.CharField(max_length=255)
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    current_cycle_used_hours = models.FloatField(
        help_text="On-duty hours already used in the driver's 70hr/8-day cycle."
    )
    start_time = models.DateTimeField()

    driver_name = models.CharField(max_length=120, blank=True)
    carrier_name = models.CharField(max_length=120, blank=True)
    truck_number = models.CharField(max_length=60, blank=True)

    total_miles = models.FloatField(default=0)
    total_days = models.PositiveIntegerField(default=0)
    driving_hours = models.FloatField(default=0)
    on_duty_hours = models.FloatField(
        default=0,
        help_text="Total driving plus on-duty-not-driving hours for this trip.",
    )

    # Full planner response, so a saved trip renders identically on reload.
    plan = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.pickup_location} -> {self.dropoff_location} ({self.total_miles:.0f} mi)"
