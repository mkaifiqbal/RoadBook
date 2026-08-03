from rest_framework.permissions import BasePermission

from .models import DriverProfile


def profile_for(user):
    if not user or not user.is_authenticated:
        return None
    profile, _ = DriverProfile.objects.get_or_create(
        user=user,
        defaults={
            "role": DriverProfile.Role.ADMIN if user.is_staff else DriverProfile.Role.DRIVER,
            "status": DriverProfile.Status.ACTIVE if user.is_staff else DriverProfile.Status.PENDING,
        },
    )
    return profile


def is_admin(user):
    profile = profile_for(user)
    return bool(user and user.is_authenticated and (user.is_staff or (profile and profile.role == "admin")))


class IsActiveAccount(BasePermission):
    message = "Account is not active."

    def has_permission(self, request, view):
        profile = profile_for(request.user)
        return bool(profile and (is_admin(request.user) or profile.status == DriverProfile.Status.ACTIVE))


class IsRoadbookAdmin(BasePermission):
    message = "Administrator access is required."

    def has_permission(self, request, view):
        return is_admin(request.user)