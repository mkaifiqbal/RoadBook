from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import ListAPIView, RetrieveDestroyAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from . import services
from .hos_engine import HOSViolation
from .models import DriverProfile, Trip
from .permissions import IsActiveAccount, IsRoadbookAdmin, is_admin, profile_for
from .routing import RoutingError, search_places
from .serializers import (
    DriverCreateSerializer, ProfileUpdateSerializer, TripDetailSerializer,
    TripListSerializer, TripRequestSerializer, UserSerializer, normalize_for_comparison,
    trip_can_delete, trip_end_time,
)


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def location_search(request):
    query = request.query_params.get("q", "").strip()
    if len(query) < 3:
        return Response({"results": []})
    try:
        places = search_places(query)
    except RoutingError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"results": [place.to_dict() for place in places]})


@api_view(["POST"])
@permission_classes([IsActiveAccount])
def plan_trip(request):
    """POST /api/plan-trip/ -- the single endpoint the assessment calls for."""
    serializer = TripRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    profile = profile_for(request.user)
    driver_name = data.get("driver_name") or request.user.get_full_name() or request.user.username
    carrier_name = data.get("carrier_name") or profile.carrier_name
    # The trip truck is intentionally editable; the profile truck is only its default.
    truck_number = data.get("truck_number") or profile.truck_number
    requested_start = data.get("start_time") or services.default_start_time()
    comparison_reference = timezone.now()
    normalized_start = normalize_for_comparison(requested_start, comparison_reference)
    existing_trips = list(Trip.objects.filter(driver=request.user).order_by("start_time"))

    # Restore HOS history only from the latest trip that actually finishes
    # before this requested departure. A later scheduled trip must not prevent
    # a driver from using a free gap earlier in the calendar.
    previous_trip = None
    previous_end = None
    for existing in existing_trips:
        existing_end = normalize_for_comparison(trip_end_time(existing), comparison_reference)
        if existing_end and existing_end <= normalized_start and (
            previous_end is None or existing_end > previous_end
        ):
            previous_trip = existing
            previous_end = existing_end
    cycle_state = None
    if previous_trip:
        cycle_state = previous_trip.plan.get("summary", {}).get("cycle_state")

    try:
        plan = services.build_plan(
            current_location=data["current_location"],
            pickup_location=data["pickup_location"],
            dropoff_location=data["dropoff_location"],
            current_cycle_used=data["current_cycle_used"],
            start_time=requested_start,
            driver_name=driver_name,
            carrier_name=carrier_name,
            truck_number=truck_number,
            cycle_state=cycle_state,
        )
    except RoutingError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except (HOSViolation, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    planned_start = normalize_for_comparison(
        parse_datetime(plan["summary"]["start_time"]), comparison_reference
    )
    planned_end = normalize_for_comparison(
        parse_datetime(plan["summary"]["end_time"]), comparison_reference
    )
    for existing in existing_trips:
        existing_start = normalize_for_comparison(existing.start_time, comparison_reference)
        existing_end = normalize_for_comparison(trip_end_time(existing), comparison_reference)
        if planned_start < existing_end and planned_end > existing_start:
            return Response(
                {
                    "detail": (
                        "This trip overlaps an existing trip scheduled from "
                        f"{existing_start.isoformat()} to {existing_end.isoformat()}. "
                        "Choose a departure time that keeps both trips separate."
                    )
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

    if data.get("save", True):
        trip = Trip.objects.create(
            driver=request.user,
            current_location=data["current_location"],
            pickup_location=data["pickup_location"],
            dropoff_location=data["dropoff_location"],
            current_cycle_used_hours=data["current_cycle_used"],
            start_time=plan["summary"]["start_time"],
            driver_name=driver_name,
            carrier_name=carrier_name,
            truck_number=truck_number,
            total_miles=plan["summary"]["total_miles"],
            total_days=plan["summary"]["days"],
            driving_hours=plan["summary"]["driving_hours"],
            on_duty_hours=(
                plan["summary"]["driving_hours"]
                + plan["summary"]["on_duty_not_driving_hours"]
            ),
            plan=plan,
        )
        plan["trip_id"] = trip.id

    return Response(plan, status=status.HTTP_200_OK)


class TripListView(ListAPIView):
    serializer_class = TripListSerializer
    permission_classes = [IsActiveAccount]

    def get_queryset(self):
        queryset = Trip.objects.select_related("driver", "driver__driver_profile").order_by("-start_time", "-id")
        driver_id = self.request.query_params.get("driver")
        if is_admin(self.request.user):
            return queryset.filter(driver_id=driver_id) if driver_id else queryset
        return queryset.filter(driver=self.request.user)


class TripDetailView(RetrieveDestroyAPIView):
    serializer_class = TripDetailSerializer
    permission_classes = [IsActiveAccount]

    def get_queryset(self):
        queryset = Trip.objects.select_related("driver", "driver__driver_profile")
        return queryset if is_admin(self.request.user) else queryset.filter(driver=self.request.user)

    def perform_destroy(self, instance):
        if not trip_can_delete(instance):
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"detail": "Trips can only be deleted at least 24 hours before departure."})
        instance.delete()


def _token_payload(user):
    profile = profile_for(user)
    refresh = RefreshToken.for_user(user)
    refresh["role"] = profile.role
    refresh["status"] = profile.status
    refresh.access_token["role"] = profile.role
    refresh.access_token["status"] = profile.status
    return {"access": str(refresh.access_token), "refresh": str(refresh), "user": UserSerializer(user).data}


@api_view(["POST"])
@permission_classes([AllowAny])
def signup(request):
    serializer = DriverCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response(
        {"detail": "Your account is pending admin approval.", "user": UserSerializer(user).data},
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    identifier = str(request.data.get("email") or request.data.get("username") or "").strip().lower()
    password = request.data.get("password", "")
    existing = User.objects.filter(username__iexact=identifier).first()
    user = authenticate(request, username=existing.username if existing else identifier, password=password)
    if not user:
        return Response({"detail": "Invalid email or password."}, status=status.HTTP_401_UNAUTHORIZED)

    profile = profile_for(user)
    blocked = {
        DriverProfile.Status.PENDING: "Account pending approval.",
        DriverProfile.Status.REJECTED: "Account was not approved.",
        DriverProfile.Status.SUSPENDED: "Account is suspended. Contact an administrator.",
    }
    if not is_admin(user) and profile.status in blocked:
        return Response({"detail": blocked[profile.status], "status": profile.status}, status=status.HTTP_403_FORBIDDEN)
    return Response(_token_payload(user))


@api_view(["GET", "PATCH"])
@permission_classes([IsActiveAccount])
def profile(request):
    driver_profile = profile_for(request.user)
    if request.method == "PATCH":
        serializer = ProfileUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(driver_profile, field, value)
        driver_profile.save(update_fields=list(serializer.validated_data))
    return Response(UserSerializer(request.user).data)


@api_view(["GET", "POST"])
@permission_classes([IsRoadbookAdmin])
def admin_drivers(request):
    if request.method == "POST":
        serializer = DriverCreateSerializer(data=request.data, context={"active": True})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    queryset = User.objects.filter(driver_profile__role=DriverProfile.Role.DRIVER).select_related(
        "driver_profile"
    ).prefetch_related("trips").annotate(trip_count=Count("trips"))
    requested_status = request.query_params.get("status")
    if requested_status:
        queryset = queryset.filter(driver_profile__status=requested_status)
    return Response(UserSerializer(queryset, many=True).data)


@api_view(["PATCH"])
@permission_classes([IsRoadbookAdmin])
def admin_driver_status(request, pk):
    target = User.objects.filter(pk=pk, driver_profile__role=DriverProfile.Role.DRIVER).select_related("driver_profile").first()
    if not target:
        return Response({"detail": "Driver not found."}, status=status.HTTP_404_NOT_FOUND)
    new_status = request.data.get("status")
    allowed = set(DriverProfile.Status.values)
    if new_status not in allowed:
        return Response({"status": ["Choose a valid status."]}, status=status.HTTP_400_BAD_REQUEST)
    target.driver_profile.status = new_status
    target.driver_profile.reviewed_at = timezone.now()
    target.driver_profile.reviewed_by = request.user
    target.driver_profile.save(update_fields=["status", "reviewed_at", "reviewed_by"])
    return Response(UserSerializer(target).data)
