# Author: xhico
# Date: May 27, 2026
"""Root URL configuration for the FinancialAudit project."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    """
    Return a simple liveness response for container health checks.

    Args:
        request (HttpRequest): Incoming request

    Returns:
        JsonResponse: {"status": "ok"} with HTTP 200
    """

    # Report the service as alive
    return JsonResponse({"status": "ok"})


urlpatterns = [
    # Auth flow uses our own template so unauthenticated users land on a
    # page that matches the dashboard look, not the Django admin login
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    # Django 5 requires POST for logout; the sidebar's sign-out button is a
    # tiny CSRF-protected form that posts here
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("api/", include("finance.urls")),
    path("", include("finance.page_urls")),
]
