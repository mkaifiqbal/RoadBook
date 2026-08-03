from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import DriverProfile, Trip

User = get_user_model()


def normalize_for_comparison(value, reference):
    """Put datetimes on the same side of Django's timezone setting."""
    if value and timezone.is_naive(value) != timezone.is_naive(reference):
        if timezone.is_naive(reference):
            return timezone.make_naive(value, timezone.get_current_timezone())
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def trip_end_time(trip):
    """Return the best available end timestamp for a persisted trip plan."""
    end_value = (trip.plan or {}).get("summary", {}).get("end_time")
    end_time = parse_datetime(end_value) if end_value else None
    if end_time is None:
        end_time = trip.start_time
    if end_time and timezone.is_naive(end_time):
        end_time = timezone.make_aware(end_time, timezone.get_current_timezone())
    return end_time


def trip_status(trip):
    now = timezone.now()
    start_time = normalize_for_comparison(trip.start_time, now)
    end_time = normalize_for_comparison(trip_end_time(trip), now)
    if end_time and end_time <= now:
        return "completed"
    if start_time and start_time <= now:
        return "in_progress"
    return "upcoming"


def trip_can_delete(trip):
    """Allow cancellation only while departure is at least 24 hours away."""
    now = timezone.now()
    start_time = normalize_for_comparison(trip.start_time, now)
    return bool(start_time and start_time >= now + timezone.timedelta(hours=24))


class UserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    role = serializers.CharField(source="driver_profile.role", read_only=True)
    status = serializers.CharField(source="driver_profile.status", read_only=True)
    truck_number = serializers.CharField(source="driver_profile.truck_number", read_only=True)
    carrier_name = serializers.CharField(source="driver_profile.carrier_name", read_only=True)
    requested_at = serializers.DateTimeField(source="driver_profile.requested_at", read_only=True)
    trip_count = serializers.SerializerMethodField()
    scheduled_driving_hours = serializers.SerializerMethodField()
    completed_driving_hours = serializers.SerializerMethodField()
    total_driving_hours = serializers.SerializerMethodField()
    total_on_duty_hours = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "name", "username", "email", "role", "status", "truck_number",
            "carrier_name", "requested_at", "trip_count", "scheduled_driving_hours",
            "completed_driving_hours", "total_driving_hours", "total_on_duty_hours",
        )

    def get_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_trip_count(self, obj):
        annotated = getattr(obj, "trip_count", None)
        return annotated if annotated is not None else obj.trips.count()

    def _hour_totals(self, obj):
        """Split planned driving into elapsed and upcoming work.

        A saved trip is a schedule, not proof that the work has already happened.
        Until explicit trip-status tracking is introduced, a trip becomes completed
        once the HOS plan's end time has passed. Legacy plans without an end time use
        the trip start time as a conservative fallback.
        """
        cached = getattr(obj, "_roadbook_hour_totals", None)
        if cached is not None:
            return cached

        now = timezone.now()
        completed_driving = scheduled_driving = total_driving = total_on_duty = 0.0
        trips = obj.trips.all()
        for trip in trips:
            driving = max(float(trip.driving_hours or 0), 0.0)
            # Protect reporting from legacy rows whose duty total was left at zero.
            on_duty = max(float(trip.on_duty_hours or 0), driving)
            end_time = trip_end_time(trip)
            end_time = normalize_for_comparison(end_time, now)

            if end_time and end_time <= now:
                completed_driving += driving
            else:
                scheduled_driving += driving
            total_driving += driving
            total_on_duty += on_duty

        totals = {
            "scheduled": round(scheduled_driving, 2),
            "completed": round(completed_driving, 2),
            "driving": round(total_driving, 2),
            "on_duty": round(max(total_on_duty, total_driving), 2),
        }
        obj._roadbook_hour_totals = totals
        return totals

    def get_scheduled_driving_hours(self, obj):
        return self._hour_totals(obj)["scheduled"]

    def get_completed_driving_hours(self, obj):
        return self._hour_totals(obj)["completed"]

    def get_total_driving_hours(self, obj):
        return self._hour_totals(obj)["driving"]

    def get_total_on_duty_hours(self, obj):
        return self._hour_totals(obj)["on_duty"]


class DriverCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    truck_number = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    carrier_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(username__iexact=value).exists() or User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        active = self.context.get("active", False)
        name_parts = validated_data["name"].strip().split(maxsplit=1)
        user = User.objects.create_user(
            username=validated_data["email"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=name_parts[0],
            last_name=name_parts[1] if len(name_parts) > 1 else "",
            is_active=True,
        )
        DriverProfile.objects.create(
            user=user,
            status=DriverProfile.Status.ACTIVE if active else DriverProfile.Status.PENDING,
            truck_number=validated_data.get("truck_number", ""),
            carrier_name=validated_data.get("carrier_name", ""),
        )
        return user


class ProfileUpdateSerializer(serializers.Serializer):
    truck_number = serializers.CharField(max_length=60, required=False, allow_blank=True)
    carrier_name = serializers.CharField(max_length=120, required=False, allow_blank=True)


class TripRequestSerializer(serializers.Serializer):
    """The four required inputs, plus optional log-header metadata."""

    current_location = serializers.CharField(max_length=255)
    pickup_location = serializers.CharField(max_length=255)
    dropoff_location = serializers.CharField(max_length=255)
    current_cycle_used = serializers.FloatField(min_value=0, max_value=70)

    start_time = serializers.DateTimeField(required=False, allow_null=True)
    driver_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    carrier_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    truck_number = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    save = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        if attrs["pickup_location"].strip().lower() == attrs["dropoff_location"].strip().lower():
            raise serializers.ValidationError(
                {"dropoff_location": "Drop-off must differ from pickup."}
            )
        return attrs


class TripListSerializer(serializers.ModelSerializer):
    driver = UserSerializer(read_only=True)
    status = serializers.SerializerMethodField()
    end_time = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    delete_restriction = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = (
            "id",
            "driver",
            "current_location",
            "pickup_location",
            "dropoff_location",
            "current_cycle_used_hours",
            "start_time",
            "total_miles",
            "total_days",
            "driving_hours",
            "on_duty_hours",
            "created_at",
            "status",
            "end_time",
            "can_delete",
            "delete_restriction",
        )

    def get_status(self, obj):
        return trip_status(obj)

    def get_end_time(self, obj):
        end_time = trip_end_time(obj)
        return end_time.isoformat() if end_time else None

    def get_can_delete(self, obj):
        return trip_can_delete(obj)

    def get_delete_restriction(self, obj):
        if trip_can_delete(obj):
            return None
        if trip_status(obj) != "upcoming":
            return "Completed or started trips cannot be deleted."
        return "Trips can only be deleted at least 24 hours before departure."


class TripDetailSerializer(TripListSerializer):
    class Meta:
        model = Trip
        fields = TripListSerializer.Meta.fields + ("driver_name", "carrier_name", "truck_number", "plan")
