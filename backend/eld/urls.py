from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health_check(request):
    return JsonResponse({"status": "ok"})


def api_index(request):
    """Root landing response.

    The backend serves no HTML, so a bare GET / used to raise a 404. Returning
    a small index keeps uptime checks and anyone poking at the service URL from
    landing on an error page.
    """
    return JsonResponse(
        {
            "service": "Roadbook API",
            "status": "ok",
            "app": "https://road-book-rouge.vercel.app",
            "endpoints": {
                "health": "/health/",
                "admin": "/admin/",
                "login": "/api/auth/login/",
                "signup": "/api/auth/signup/",
                "profile": "/api/auth/profile/",
                "locations": "/api/locations/?q=",
                "plan_trip": "/api/plan-trip/",
                "trips": "/api/trips/",
            },
        }
    )


urlpatterns = [
    path("", api_index, name="api-index"),
    path("health/", health_check, name="health-check"),
    path("admin/", admin.site.urls),
    path("api/", include("trips.urls")),
]
