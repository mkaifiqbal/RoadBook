from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("locations/", views.location_search, name="location-search"),
    path("auth/signup/", views.signup, name="signup"),
    path("auth/login/", views.login, name="login"),
    path("auth/profile/", views.profile, name="profile"),
    path("admin/drivers/", views.admin_drivers, name="admin-drivers"),
    path("admin/drivers/<int:pk>/status/", views.admin_driver_status, name="admin-driver-status"),
    path("plan-trip/", views.plan_trip, name="plan-trip"),
    path("trips/", views.TripListView.as_view(), name="trip-list"),
    path("trips/<int:pk>/", views.TripDetailView.as_view(), name="trip-detail"),
]
