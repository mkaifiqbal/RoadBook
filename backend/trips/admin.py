from django.contrib import admin

from .models import DriverProfile, Trip


@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "status", "truck_number", "carrier_name", "requested_at")
    list_filter = ("role", "status")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "driver",
        "pickup_location",
        "dropoff_location",
        "total_miles",
        "total_days",
        "current_cycle_used_hours",
        "created_at",
    )
    search_fields = ("current_location", "pickup_location", "dropoff_location", "driver_name")
    readonly_fields = ("created_at", "plan")
